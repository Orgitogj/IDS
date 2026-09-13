import csv
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
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
from training.build_final_eval_dataset import DATA, FINAL_RUNS, OUT, RUNS, SCENARIO_OF

PHASE17C = _ML_SERVICE_ROOT / "reports" / "domain_adaptation" / "phase17c"
MODEL_B_ARTIFACT = _ML_SERVICE_ROOT / "models" / "model_b" / "model_b_xgb_weighted_v1.joblib"
MODEL_B_SHA = "c2bb8f0043eb2eb4c9a8d4639e41e86939675a2a0f1d40bf65c3e8ce181cb237"
MODEL_A_SHA = "2b7625fc32e5f9e066c3a7b356b8a606c9a1f26e5f2a8d1cc4b6fce4ff2fddfa"
THRESHOLD = 0.50
Z95 = 1.959963984540054
CHUNK = 40000


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


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


def _capture_path(run_id):
    return (_ML_SERVICE_ROOT / "reports" / "domain_adaptation" / "phase17d" /
            "captures" / f"{run_id}.csv")


def _model_b_matrix(raw_columns, features_b):
    frame = pd.DataFrame({c: raw_columns[c] for c in features_b})
    frame = frame.apply(pd.to_numeric, errors="coerce")
    frame = frame.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return frame[features_b].to_numpy(dtype=np.float64)


def score():
    require_sealed()
    verify_frozen_models()

    model_a, label_encoder, feature_columns_a, identity = lab_runner.load_frozen_model(
        _ML_SERVICE_ROOT / "models")
    validator = lab_runner.build_validator(feature_columns_a)

    c17c = json.loads((PHASE17C / "protocol.json").read_text(encoding="utf-8"))
    features_b = c17c["feature_contract"]["feature_list"]
    model_b = joblib.load(MODEL_B_ARTIFACT)

    OUT.mkdir(parents=True, exist_ok=True)
    pred_path = OUT / "paired_predictions.csv"
    fields = ["run_id", "scenario", "ground_truth", "model_a_predicted_class",
              "model_a_binary", "model_b_binary", "model_b_attack_probability",
              "model_a_correct", "model_b_correct"]

    g_gt, g_ab, g_bb, g_bp = [], [], [], []
    g_scn = []
    per_run = {}

    with open(pred_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()

        for run_id in FINAL_RUNS:
            scenario = SCENARIO_OF[run_id]
            mani = adaptation_manifest(scenario, run_id)
            per_run[run_id] = {"scenario": scenario, "n": 0, "a_pos": 0, "b_pos": 0}

            vecs_a, raw_b, gts = [], {c: [] for c in features_b}, []

            def flush():
                if not gts:
                    return
                da = pd.DataFrame(vecs_a, columns=feature_columns_a)
                idx = model_a.predict(da)
                a_labels = [str(x) for x in label_encoder.inverse_transform(idx)]
                a_bin = [0 if lab == "BENIGN" else 1 for lab in a_labels]
                xb = _model_b_matrix(raw_b, features_b)
                proba = model_b.predict_proba(xb)[:, 1]
                b_bin = (proba >= THRESHOLD).astype(int)
                for k in range(len(gts)):
                    gt = gts[k]
                    ab, bb = a_bin[k], int(b_bin[k])
                    writer.writerow({
                        "run_id": run_id, "scenario": scenario,
                        "ground_truth": "ATTACK" if gt == 1 else "BENIGN",
                        "model_a_predicted_class": a_labels[k],
                        "model_a_binary": "ATTACK" if ab else "BENIGN",
                        "model_b_binary": "ATTACK" if bb else "BENIGN",
                        "model_b_attack_probability": float(proba[k]),
                        "model_a_correct": int(ab == gt),
                        "model_b_correct": int(bb == gt),
                    })
                    per_run[run_id]["n"] += 1
                    per_run[run_id]["a_pos"] += ab
                    per_run[run_id]["b_pos"] += bb
                    g_gt.append(gt)
                    g_ab.append(ab)
                    g_bb.append(bb)
                    g_bp.append(float(proba[k]))
                    g_scn.append(scenario)
                vecs_a.clear()
                for c in features_b:
                    raw_b[c].clear()
                gts.clear()

            with open(_capture_path(run_id), newline="", encoding="utf-8") as cap:
                for row in csv.DictReader(cap):
                    expected = mani.expected_for_flow(row)
                    if expected not in protocol.EXPECTED_BINARY_LABELS:
                        continue
                    mapped = lab_runner.map_row(row)
                    validation = validator.validate(mapped)
                    status = lab_runner.schema_guard.status_from_validation(
                        validation, None)
                    if status["validation_status"] != protocol.STATUS_VALID:
                        continue
                    vecs_a.append(validation.vector)
                    for c in features_b:
                        raw_b[c].append(row.get(c))
                    gts.append(1 if expected == "ATTACK" else 0)
                    if len(gts) >= CHUNK:
                        flush()
            flush()

    gt = np.asarray(g_gt, dtype=np.int8)
    ab = np.asarray(g_ab, dtype=np.int8)
    bb = np.asarray(g_bb, dtype=np.int8)
    bp = np.asarray(g_bp, dtype=np.float64)
    scn = np.asarray(g_scn, dtype=object)

    scenario_results = _scenario_results(gt, ab, bb, scn)
    per_run_rows = _per_run_rows(per_run)
    pooled = _pooled_secondary(gt, ab, bb, bp)
    paired = _paired_comparison(gt, ab, bb, scn)

    (OUT / "scenario_results.json").write_text(
        json.dumps(scenario_results, indent=1) + "\n", encoding="utf-8")
    (OUT / "paired_comparison.json").write_text(
        json.dumps({"paired": paired, "pooled_secondary": pooled}, indent=1) + "\n",
        encoding="utf-8")
    _write_per_run_csv(per_run_rows)

    summary = {
        "generated_at": utc_now(),
        "threshold": THRESHOLD,
        "model_a_sha256": MODEL_A_SHA,
        "model_b_sha256": MODEL_B_SHA,
        "n_evaluable": int(gt.shape[0]),
        "paired_predictions_sha256": sha256_file(pred_path),
        "scenario_results": scenario_results,
        "paired": paired,
        "pooled_secondary": pooled,
    }
    (OUT / "evaluation_summary.json").write_text(
        json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    return summary


def _scenario_results(gt, ab, bb, scn):
    out = {}
    for scenario in ("benign", "portscan", "ssh"):
        mask = scn == scenario
        n = int(mask.sum())
        entry = {"n_evaluable": n}
        for model, pred in (("model_a", ab), ("model_b", bb)):
            pm = pred[mask]
            if scenario == "benign":
                fp = int((pm == 1).sum())
                entry[model] = {"quantity": "benign_false_positive_rate",
                                "false_positives": fp, "n": n,
                                "wilson_95": wilson(fp, n)}
            else:
                det = int((pm == 1).sum())
                entry[model] = {"quantity": "attack_detection_rate",
                                "detected": det, "n": n,
                                "wilson_95": wilson(det, n)}
        out[scenario] = entry
    return out


def _per_run_rows(per_run):
    rows = []
    for run_id, d in per_run.items():
        n = d["n"]
        for model, pos in (("model_a", d["a_pos"]), ("model_b", d["b_pos"])):
            if d["scenario"] == "benign":
                w = wilson(pos, n)
                rows.append([run_id, d["scenario"], model,
                             "benign_false_positive_rate", pos, n,
                             w["point"], w["low"], w["high"]])
            else:
                w = wilson(pos, n)
                rows.append([run_id, d["scenario"], model,
                             "attack_detection_rate", pos, n,
                             w["point"], w["low"], w["high"]])
    return rows


def _write_per_run_csv(rows):
    with open(OUT / "per_run_results.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["run_id", "scenario", "model", "quantity", "count", "n",
                    "rate", "wilson_low", "wilson_high"])
        w.writerows(rows)


def _pooled_secondary(gt, ab, bb, bp):
    out = {"note": "SECONDARY; PortScan dominates flow count",
           "n_evaluable": int(gt.shape[0])}
    for model, pred in (("model_a", ab), ("model_b", bb)):
        tn, fp, fn, tp = confusion_matrix(gt, pred, labels=[0, 1]).ravel()
        entry = {
            "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn),
                                 "tp": int(tp)},
            "macro_f1": float(f1_score(gt, pred, average="macro", zero_division=0)),
            "balanced_accuracy": float(balanced_accuracy_score(gt, pred)),
            "attack_recall": float(recall_score(gt, pred, pos_label=1,
                                                zero_division=0)),
            "attack_precision": float(precision_score(gt, pred, pos_label=1,
                                                      zero_division=0)),
            "benign_fpr": float(fp / (tn + fp)) if (tn + fp) else None,
        }
        if model == "model_b":
            single = len(np.unique(gt)) < 2
            entry["roc_auc"] = None if single else float(roc_auc_score(gt, bp))
            entry["pr_auc"] = None if single else float(average_precision_score(gt, bp))
            if single:
                entry["auc_unavailable_reason"] = "single ground-truth class in pool"
        out[model] = entry
    return out


def _paired_comparison(gt, ab, bb, scn):
    atk = gt == 1
    ben = gt == 0
    a_atk, b_atk = ab == 1, bb == 1
    attack_counts = {
        "both_detect": int((atk & a_atk & b_atk).sum()),
        "model_a_only": int((atk & a_atk & ~b_atk).sum()),
        "model_b_only": int((atk & ~a_atk & b_atk).sum()),
        "neither": int((atk & ~a_atk & ~b_atk).sum()),
        "n": int(atk.sum()),
    }
    benign_counts = {
        "both_correct": int((ben & ~a_atk & ~b_atk).sum()),
        "model_a_fp_only": int((ben & a_atk & ~b_atk).sum()),
        "model_b_fp_only": int((ben & ~a_atk & b_atk).sum()),
        "both_fp": int((ben & a_atk & b_atk).sum()),
        "n": int(ben.sum()),
    }
    return {
        "attack_scenarios": attack_counts,
        "benign": benign_counts,
        "mcnemar_exact_attack_detection": _mcnemar(attack_counts["model_a_only"],
                                                   attack_counts["model_b_only"]),
        "mcnemar_exact_benign_fp": _mcnemar(benign_counts["model_a_fp_only"],
                                            benign_counts["model_b_fp_only"]),
        "mcnemar_note": ("secondary paired diagnostic on discordant pairs; does not "
                         "override descriptive results"),
    }


def _mcnemar(b, c):
    n = b + c
    if n == 0:
        return {"b": b, "c": c, "n_discordant": 0, "p_value": None,
                "note": "no discordant pairs"}
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) * (0.5 ** n)
    return {"b": int(b), "c": int(c), "n_discordant": int(n),
            "p_value": float(min(1.0, 2.0 * tail)),
            "test": "two-sided exact binomial (McNemar)"}


def main():
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
