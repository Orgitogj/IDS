import csv
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

from app.live import lab_runner, protocol
from training.build_adaptation_dataset import adaptation_manifest
from training.build_final_eval_dataset import (
    DATA,
    FINAL_RUNS,
    OUT,
    RUNS,
    SCENARIO_OF,
    sha256_file,
)

PHASE17C = _ML_SERVICE_ROOT / "reports" / "domain_adaptation" / "phase17c"
MODEL_B_ARTIFACT = _ML_SERVICE_ROOT / "models" / "model_b" / "model_b_xgb_weighted_v1.joblib"
MODEL_B_SHA = "c2bb8f0043eb2eb4c9a8d4639e41e86939675a2a0f1d40bf65c3e8ce181cb237"
MODEL_A_SHA = "2b7625fc32e5f9e066c3a7b356b8a606c9a1f26e5f2a8d1cc4b6fce4ff2fddfa"
THRESHOLD = 0.50
Z95 = 1.959963984540054


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def wilson(successes, n, z=Z95):
    if n == 0:
        return {"point": None, "low": None, "high": None, "n": 0, "successes": 0}
    p = successes / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return {
        "point": p,
        "low": min(p, max(0.0, centre - half)),
        "high": max(p, min(1.0, centre + half)),
        "n": int(n),
        "successes": int(successes),
    }


def require_sealed():
    seal_path = DATA / "final_test_seal.json"
    if not seal_path.exists():
        raise SystemExit("final-test dataset is not sealed; run seal first")
    seal = json.load(open(seal_path, encoding="utf-8"))
    if not seal.get("sealed"):
        raise SystemExit("final-test seal present but not sealed")
    manifest_bytes = (DATA / "final_test_manifest.json").read_bytes()
    import hashlib
    if hashlib.sha256(manifest_bytes).hexdigest() != seal["manifest_sha256"]:
        raise SystemExit("final-test manifest hash does not match seal")
    return seal


def verify_frozen_models():
    got_a = sha256_file(_ML_SERVICE_ROOT / "models" / "xgb_baseline_cicids2017_v2.joblib")
    got_b = sha256_file(MODEL_B_ARTIFACT)
    if got_a != MODEL_A_SHA:
        raise SystemExit(f"Model A hash changed: {got_a}")
    if got_b != MODEL_B_SHA:
        raise SystemExit(f"Model B hash changed: {got_b}")
    return got_a, got_b


def load_ground_truth(run_id):
    scenario = SCENARIO_OF[run_id]
    mani = adaptation_manifest(scenario, run_id)
    capture = None
    prov = json.load(open(RUNS / run_id / "provenance.json", encoding="utf-8"))
    csv_rel = prov["flow_csv_path"]
    candidate = _ML_SERVICE_ROOT / csv_rel
    capture = candidate if candidate.exists() else Path(csv_rel)
    labels = []
    rows = []
    with open(capture, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            expected = mani.expected_for_flow(row)
            rows.append(row)
            labels.append(expected)
    return scenario, rows, labels


def score():
    require_sealed()
    verify_frozen_models()

    model_a, label_encoder, feature_columns_a, identity = lab_runner.load_frozen_model(
        _ML_SERVICE_ROOT / "models")
    validator = lab_runner.build_validator(feature_columns_a)

    c17c = json.loads((PHASE17C / "protocol.json").read_text(encoding="utf-8"))
    features_b = c17c["feature_contract"]["feature_list"]
    id_cols = c17c["feature_contract"]["excluded_identity_columns"]
    model_b = joblib.load(MODEL_B_ARTIFACT)

    OUT.mkdir(parents=True, exist_ok=True)
    pred_path = OUT / "paired_predictions.csv"
    fields = [
        "run_id", "scenario", "ground_truth", "model_a_predicted_class",
        "model_a_binary", "model_b_binary", "model_b_attack_probability",
        "model_a_correct", "model_b_correct",
    ]

    per_flow = []
    with open(pred_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for run_id in FINAL_RUNS:
            scenario, rows, labels = load_ground_truth(run_id)
            for row, gt in zip(rows, labels):
                if gt not in protocol.EXPECTED_BINARY_LABELS:
                    continue
                mapped = lab_runner.map_row(row)
                validation = validator.validate(mapped)
                status = lab_runner.schema_guard.status_from_validation(validation, None)
                if status["validation_status"] != protocol.STATUS_VALID:
                    continue

                record, _ = lab_runner.process_row(
                    row, adaptation_manifest(scenario, run_id), model_a,
                    label_encoder, feature_columns_a, validator, identity)
                a_class = str(record.get("predicted_label"))
                a_binary = "ATTACK" if a_class != "BENIGN" else "BENIGN"

                vec = np.asarray(
                    [[float(_to_num(row.get(c))) for c in features_b]],
                    dtype=np.float64)
                vec = np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)
                proba = float(model_b.predict_proba(vec)[0, 1])
                b_binary = "ATTACK" if proba >= THRESHOLD else "BENIGN"

                entry = {
                    "run_id": run_id,
                    "scenario": scenario,
                    "ground_truth": gt,
                    "model_a_predicted_class": a_class,
                    "model_a_binary": a_binary,
                    "model_b_binary": b_binary,
                    "model_b_attack_probability": proba,
                    "model_a_correct": int(a_binary == gt),
                    "model_b_correct": int(b_binary == gt),
                }
                writer.writerow(entry)
                per_flow.append(entry)

    scenario_results = _scenario_results(per_flow)
    per_run = _per_run_results(per_flow)
    pooled = _pooled_secondary(per_flow)
    paired = _paired_comparison(per_flow)

    (OUT / "scenario_results.json").write_text(
        json.dumps(scenario_results, indent=1) + "\n", encoding="utf-8")
    (OUT / "paired_comparison.json").write_text(
        json.dumps({"paired": paired, "pooled_secondary": pooled}, indent=1) + "\n",
        encoding="utf-8")
    _write_per_run_csv(per_run)

    summary = {
        "generated_at": utc_now(),
        "threshold": THRESHOLD,
        "model_a_sha256": MODEL_A_SHA,
        "model_b_sha256": MODEL_B_SHA,
        "n_evaluable": len(per_flow),
        "paired_predictions_sha256": sha256_file(pred_path),
        "scenario_results": scenario_results,
        "paired": paired,
        "pooled_secondary": pooled,
    }
    (OUT / "evaluation_summary.json").write_text(
        json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    return summary


def _to_num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _scenario_results(per_flow):
    out = {}
    for scenario in ("benign", "portscan", "ssh"):
        flows = [f for f in per_flow if f["scenario"] == scenario]
        entry = {"n_evaluable": len(flows)}
        for model, key in (("model_a", "model_a_binary"), ("model_b", "model_b_binary")):
            if scenario == "benign":
                fp = sum(1 for f in flows if f[key] == "ATTACK")
                entry[model] = {
                    "quantity": "benign_false_positive_rate",
                    "false_positives": fp, "n": len(flows),
                    "wilson_95": wilson(fp, len(flows)),
                }
            else:
                detected = sum(1 for f in flows if f[key] == "ATTACK")
                entry[model] = {
                    "quantity": "attack_detection_rate",
                    "detected": detected, "n": len(flows),
                    "wilson_95": wilson(detected, len(flows)),
                }
        out[scenario] = entry
    return out


def _per_run_results(per_flow):
    rows = []
    for run_id in FINAL_RUNS:
        flows = [f for f in per_flow if f["run_id"] == run_id]
        scenario = SCENARIO_OF[run_id]
        n = len(flows)
        for model, key in (("model_a", "model_a_binary"), ("model_b", "model_b_binary")):
            if scenario == "benign":
                count = sum(1 for f in flows if f[key] == "ATTACK")
                w = wilson(count, n)
                rows.append([run_id, scenario, model, "benign_false_positive_rate",
                             count, n, w["point"], w["low"], w["high"]])
            else:
                count = sum(1 for f in flows if f[key] == "ATTACK")
                w = wilson(count, n)
                rows.append([run_id, scenario, model, "attack_detection_rate",
                             count, n, w["point"], w["low"], w["high"]])
    return rows


def _write_per_run_csv(rows):
    with open(OUT / "per_run_results.csv", "w", newline="", encoding="utf-8") as handle:
        w = csv.writer(handle)
        w.writerow(["run_id", "scenario", "model", "quantity", "count", "n",
                    "rate", "wilson_low", "wilson_high"])
        w.writerows(rows)


def _pooled_secondary(per_flow):
    y = np.array([1 if f["ground_truth"] == "ATTACK" else 0 for f in per_flow])
    out = {"note": "SECONDARY; PortScan dominates flow count", "n_evaluable": len(y)}
    for model, key in (("model_a", "model_a_binary"), ("model_b", "model_b_binary")):
        pred = np.array([1 if f[key] == "ATTACK" else 0 for f in per_flow])
        tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
        entry = {
            "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn),
                                 "tp": int(tp)},
            "macro_f1": float(f1_score(y, pred, average="macro", zero_division=0)),
            "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
            "attack_recall": float(recall_score(y, pred, pos_label=1, zero_division=0)),
            "attack_precision": float(
                precision_score(y, pred, pos_label=1, zero_division=0)),
            "benign_fpr": float(fp / (tn + fp)) if (tn + fp) else None,
        }
        if model == "model_b":
            proba = np.array([f["model_b_attack_probability"] for f in per_flow])
            single = len(np.unique(y)) < 2
            entry["roc_auc"] = None if single else float(roc_auc_score(y, proba))
            entry["pr_auc"] = None if single else float(
                average_precision_score(y, proba))
            if single:
                entry["auc_unavailable_reason"] = "single ground-truth class in pool"
        out[model] = entry
    return out


def _paired_comparison(per_flow):
    attack = [f for f in per_flow if f["ground_truth"] == "ATTACK"]
    benign = [f for f in per_flow if f["ground_truth"] == "BENIGN"]

    def a_det(f):
        return f["model_a_binary"] == "ATTACK"

    def b_det(f):
        return f["model_b_binary"] == "ATTACK"

    attack_counts = {
        "both_detect": sum(1 for f in attack if a_det(f) and b_det(f)),
        "model_a_only": sum(1 for f in attack if a_det(f) and not b_det(f)),
        "model_b_only": sum(1 for f in attack if b_det(f) and not a_det(f)),
        "neither": sum(1 for f in attack if not a_det(f) and not b_det(f)),
        "n": len(attack),
    }
    benign_counts = {
        "both_correct": sum(1 for f in benign if not a_det(f) and not b_det(f)),
        "model_a_fp_only": sum(1 for f in benign if a_det(f) and not b_det(f)),
        "model_b_fp_only": sum(1 for f in benign if b_det(f) and not a_det(f)),
        "both_fp": sum(1 for f in benign if a_det(f) and b_det(f)),
        "n": len(benign),
    }
    mcnemar_attack = _mcnemar(attack_counts["model_a_only"],
                              attack_counts["model_b_only"])
    mcnemar_benign = _mcnemar(benign_counts["model_a_fp_only"],
                              benign_counts["model_b_fp_only"])
    return {
        "attack_scenarios": attack_counts,
        "benign": benign_counts,
        "mcnemar_exact_attack_detection": mcnemar_attack,
        "mcnemar_exact_benign_fp": mcnemar_benign,
        "mcnemar_note": ("secondary paired diagnostic on discordant pairs; does not "
                         "override descriptive results"),
    }


def _mcnemar(b, c):
    n = b + c
    if n == 0:
        return {"b": b, "c": c, "n_discordant": 0, "p_value": None,
                "note": "no discordant pairs"}
    k = min(b, c)
    p = 0.0
    for i in range(0, k + 1):
        p += math.comb(n, i) * (0.5 ** n)
    p_value = min(1.0, 2.0 * p)
    return {"b": b, "c": c, "n_discordant": n, "p_value": p_value,
            "test": "two-sided exact binomial (McNemar)"}


def main() -> int:
    summary = score()
    s = summary["scenario_results"]
    print(f"evaluable={summary['n_evaluable']} threshold={summary['threshold']}")
    for scenario in ("benign", "portscan", "ssh"):
        e = s[scenario]
        for model in ("model_a", "model_b"):
            m = e[model]
            w = m["wilson_95"]
            val = m.get("detected", m.get("false_positives"))
            print(f"  {scenario:9s} {model} {m['quantity']:28s} {val}/{m['n']} "
                  f"= {w['point']} [{w['low']}, {w['high']}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
