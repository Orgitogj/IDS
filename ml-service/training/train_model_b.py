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
import xgboost as xgb
from sklearn.ensemble import RandomForestClassifier
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

from training.build_adaptation_dataset import adaptation_manifest

PHASE17C = _ML_SERVICE_ROOT / "reports" / "domain_adaptation" / "phase17c"
PROTOCOL_PATH = PHASE17C / "protocol.json"
ADAPT_CAPTURES = _ML_SERVICE_ROOT / "reports" / "domain_adaptation" / "data" / "captures"
LIVE_CAPTURES = _ML_SERVICE_ROOT / "reports" / "live_evaluation" / "captures"
ARTIFACTS = _ML_SERVICE_ROOT / "models" / "model_b"

SCENARIO_OF = {
    "adapt-v1-benign-002": "benign",
    "adapt-v1-benign-003": "benign",
    "adapt-v1-benign-004": "benign",
    "adapt-v1-portscan-002": "portscan",
    "adapt-v1-portscan-003": "portscan",
    "adapt-v1-portscan-004": "portscan",
    "adapt-v1-ssh-002": "ssh",
    "adapt-v1-ssh-003": "ssh",
    "adapt-v1-ssh-004": "ssh",
    "lab-v1-benign-001": "benign",
    "lab-v1-portscan-001": "portscan",
    "lab-v1-ssh-bruteforce-001": "ssh",
}

LABEL_VALUE = {"BENIGN": 0, "ATTACK": 1}
Z95 = 1.959963984540054


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def capture_path(run_id):
    adapt = ADAPT_CAPTURES / f"{run_id}.csv"
    return adapt if adapt.exists() else LIVE_CAPTURES / f"{run_id}.csv"


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


def load_run(run_id, features):
    scenario = SCENARIO_OF[run_id]
    mani = adaptation_manifest(scenario, run_id)
    path = capture_path(run_id)
    rows, labels = [], []
    total = 0
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            total += 1
            expected = mani.expected_for_flow(row)
            if expected not in LABEL_VALUE:
                continue
            rows.append([row[c] for c in features])
            labels.append(LABEL_VALUE[expected])
    frame = pd.DataFrame(rows, columns=features)
    return frame, np.asarray(labels, dtype=int), total, scenario, path


def to_numeric(frame, features):
    out = frame[features].apply(pd.to_numeric, errors="coerce")
    out = out.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return out.to_numpy(dtype=np.float64)


def build_partition(run_ids, features):
    blocks, labels, meta = [], [], []
    for run_id in run_ids:
        frame, y, total, scenario, path = load_run(run_id, features)
        blocks.append(frame)
        labels.append(y)
        meta.append({
            "run_id": run_id,
            "scenario": scenario,
            "capture_csv": str(path.relative_to(_ML_SERVICE_ROOT)).replace("\\", "/"),
            "capture_sha256": sha256_file(path),
            "total_flows": total,
            "evaluable_flows": int(len(y)),
            "attack_flows": int((y == 1).sum()),
            "benign_flows": int((y == 0).sum()),
            "unlabelled_flows": int(total - len(y)),
        })
    frame = pd.concat(blocks, ignore_index=True)
    X = to_numeric(frame, features)
    y = np.concatenate(labels)
    scenarios = np.concatenate([
        np.full(m["evaluable_flows"], m["scenario"], dtype=object) for m in meta
    ])
    return X, y, scenarios, meta


def class_weights(y):
    n_total = len(y)
    n_classes = 2
    counts = {0: int((y == 0).sum()), 1: int((y == 1).sum())}
    return {c: n_total / (n_classes * counts[c]) for c in (0, 1)}, counts


def evaluate(name, model, X_val, y_val, scenarios, threshold):
    proba = model.predict_proba(X_val)[:, 1]
    pred = (proba >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_val, pred, labels=[0, 1]).ravel()
    single_class = len(np.unique(y_val)) < 2
    reason = "validation partition contains a single ground-truth class"

    per_scenario = {}
    for scenario in ("benign", "portscan", "ssh"):
        mask = scenarios == scenario
        if not mask.any():
            continue
        ys, ps = y_val[mask], pred[mask]
        if scenario == "benign":
            per_scenario[scenario] = {
                "quantity": "benign_false_positive_rate",
                "wilson_95": wilson(int((ps == 1).sum()), int(mask.sum())),
            }
        else:
            attack = ys == 1
            per_scenario[scenario] = {
                "quantity": "attack_detection_rate",
                "wilson_95": wilson(int((ps[attack] == 1).sum()), int(attack.sum())),
            }

    benign_mask = y_val == 0
    attack_mask = y_val == 1
    return {
        "model_id": name,
        "threshold": threshold,
        "confusion_matrix": {
            "true_benign_pred_benign": int(tn),
            "true_benign_pred_attack": int(fp),
            "true_attack_pred_benign": int(fn),
            "true_attack_pred_attack": int(tp),
        },
        "macro_f1": float(f1_score(y_val, pred, average="macro", zero_division=0)),
        "balanced_accuracy": float(balanced_accuracy_score(y_val, pred)),
        "attack_recall_detection_rate": float(
            recall_score(y_val, pred, pos_label=1, zero_division=0)),
        "attack_precision": float(
            precision_score(y_val, pred, pos_label=1, zero_division=0)),
        "benign_false_positive_rate": float(fp / benign_mask.sum())
        if benign_mask.any() else None,
        "roc_auc": None if single_class else float(roc_auc_score(y_val, proba)),
        "roc_auc_unavailable_reason": reason if single_class else None,
        "pr_auc": None if single_class else float(average_precision_score(y_val, proba)),
        "pr_auc_unavailable_reason": reason if single_class else None,
        "overall_wilson_95": {
            "benign_false_positive_rate": wilson(int(fp), int(benign_mask.sum())),
            "attack_detection_rate": wilson(int(tp), int(attack_mask.sum())),
        },
        "per_scenario": per_scenario,
    }


def main():
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    features = protocol["feature_contract"]["feature_list"]
    threshold = protocol["threshold"]["primary"]
    seed = protocol["reproducibility"]["seed"]
    train_runs = protocol["split"]["train_runs"]
    val_runs = protocol["split"]["validation_runs"]

    assert threshold == 0.50, threshold
    assert len(features) == 76, len(features)
    assert len(train_runs) == 9 and len(val_runs) == 3
    assert not set(train_runs) & set(val_runs)
    assert protocol["split"]["final_test_runs"] == []

    X_tr, y_tr, sc_tr, meta_tr = build_partition(train_runs, features)
    X_va, y_va, sc_va, meta_va = build_partition(val_runs, features)

    weights, counts = class_weights(y_tr)
    sample_weight = np.asarray([weights[int(v)] for v in y_tr], dtype=np.float64)

    xgb_params = protocol["models"]["primary"]["params"]
    rf_params = protocol["models"]["robustness"]["params"]

    primary = xgb.XGBClassifier(**xgb_params)
    primary.fit(X_tr, y_tr, sample_weight=sample_weight)

    robustness = RandomForestClassifier(**rf_params)
    robustness.fit(X_tr, y_tr)

    ablation = xgb.XGBClassifier(**protocol["models"]["ablation"]["params"])
    ablation.fit(X_tr, y_tr)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    paths = {
        "model-b-xgb-weighted-v1": ARTIFACTS / "model_b_xgb_weighted_v1.joblib",
        "model-b-rf-weighted-v1": ARTIFACTS / "model_b_rf_weighted_v1.joblib",
        "model-b-xgb-unweighted-v1": ARTIFACTS / "model_b_xgb_unweighted_v1.joblib",
    }
    joblib.dump(primary, paths["model-b-xgb-weighted-v1"])
    joblib.dump(robustness, paths["model-b-rf-weighted-v1"])
    joblib.dump(ablation, paths["model-b-xgb-unweighted-v1"])

    results = {
        "model-b-xgb-weighted-v1": evaluate(
            "model-b-xgb-weighted-v1", primary, X_va, y_va, sc_va, threshold),
        "model-b-rf-weighted-v1": evaluate(
            "model-b-rf-weighted-v1", robustness, X_va, y_va, sc_va, threshold),
        "model-b-xgb-unweighted-v1": evaluate(
            "model-b-xgb-unweighted-v1", ablation, X_va, y_va, sc_va, threshold),
    }

    train_constant = [
        features[i] for i in range(len(features)) if len(np.unique(X_tr[:, i])) <= 1
    ]

    metadata = {
        "schema_version": 1,
        "protocol_version": protocol["protocol_version"],
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
        "phase17b_frozen_head": protocol["phase17b_frozen_head"],
        "generated_at": utc_now(),
        "primary_model_id": protocol["selection_and_freeze_rule"]["pre_declared_primary"],
        "primary_selected_post_hoc": False,
        "threshold": threshold,
        "seed": seed,
        "feature_schema_id": protocol["feature_contract"]["schema_id"],
        "n_features": len(features),
        "feature_list": features,
        "train_constant_features": train_constant,
        "train_runs": train_runs,
        "validation_runs": val_runs,
        "final_test_runs": [],
        "train_partition": meta_tr,
        "validation_partition": meta_va,
        "train_class_counts": {"BENIGN": counts[0], "ATTACK": counts[1]},
        "train_class_weights": {"BENIGN": weights[0], "ATTACK": weights[1]},
        "class_weight_partition": "TRAIN_ONLY",
        "benign_undersampling": False,
        "smote": False,
        "validation_class_counts": {
            "BENIGN": int((y_va == 0).sum()), "ATTACK": int((y_va == 1).sum()),
        },
        "models": {
            "model-b-xgb-weighted-v1": {
                "role": "PRIMARY", "params": xgb_params,
                "artifact": str(paths["model-b-xgb-weighted-v1"].relative_to(
                    _ML_SERVICE_ROOT)).replace("\\", "/"),
                "artifact_sha256": sha256_file(paths["model-b-xgb-weighted-v1"]),
            },
            "model-b-rf-weighted-v1": {
                "role": "ROBUSTNESS", "params": rf_params,
                "artifact": str(paths["model-b-rf-weighted-v1"].relative_to(
                    _ML_SERVICE_ROOT)).replace("\\", "/"),
                "artifact_sha256": sha256_file(paths["model-b-rf-weighted-v1"]),
            },
            "model-b-xgb-unweighted-v1": {
                "role": "ABLATION",
                "params": protocol["models"]["ablation"]["params"],
                "artifact": str(paths["model-b-xgb-unweighted-v1"].relative_to(
                    _ML_SERVICE_ROOT)).replace("\\", "/"),
                "artifact_sha256": sha256_file(paths["model-b-xgb-unweighted-v1"]),
            },
        },
        "environment": protocol["reproducibility"]["environment"],
    }

    validation = {
        "schema_version": 1,
        "protocol_version": protocol["protocol_version"],
        "generated_at": utc_now(),
        "threshold": threshold,
        "threshold_tuned_on_validation": False,
        "validation_runs": val_runs,
        "validation_is_development_only": True,
        "validation_note": (
            "Historical adaptation runs used as a development validation partition. "
            "They are NOT unseen final evaluation data."),
        "validation_class_counts": {
            "BENIGN": int((y_va == 0).sum()), "ATTACK": int((y_va == 1).sum()),
        },
        "results": results,
        "frozen_model_a_historical": protocol["model_comparison"][
            "frozen_model_a_historical_values"],
        "comparison_caveat": protocol["model_comparison"]["forbidden"],
        "ssh_support_note": protocol["metrics"]["small_support_disclosure"]["rule"],
    }

    (PHASE17C / "model_b_metadata.json").write_text(
        json.dumps(metadata, indent=1) + "\n", encoding="utf-8")
    (PHASE17C / "validation_results.json").write_text(
        json.dumps(validation, indent=1) + "\n", encoding="utf-8")

    print(f"train evaluable={len(y_tr)} BENIGN={counts[0]} ATTACK={counts[1]}")
    print(f"weights BENIGN={weights[0]:.6f} ATTACK={weights[1]:.6f}")
    print(f"validation evaluable={len(y_va)} "
          f"BENIGN={int((y_va == 0).sum())} ATTACK={int((y_va == 1).sum())}")
    print(f"train constant features: {len(train_constant)}")
    for key, res in results.items():
        print(f"\n{key}")
        print(f"  macro_f1={res['macro_f1']:.4f} "
              f"bal_acc={res['balanced_accuracy']:.4f} "
              f"det={res['attack_recall_detection_rate']:.4f} "
              f"prec={res['attack_precision']:.4f} "
              f"fpr={res['benign_false_positive_rate']:.6f}")
        print(f"  roc_auc={res['roc_auc']} pr_auc={res['pr_auc']}")
        for scenario, payload in res["per_scenario"].items():
            w = payload["wilson_95"]
            print(f"  {scenario:9s} {payload['quantity']:28s} "
                  f"{w['successes']}/{w['n']} = {w['point']:.6f} "
                  f"[{w['low']:.6f}, {w['high']:.6f}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
