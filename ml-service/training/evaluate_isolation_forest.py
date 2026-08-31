import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import train_test_split

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

DEFAULT_DATASET = "datasets/cicids2017_cleaned.parquet"
DEFAULT_REFERENCE = "reports/training_feature_reference.json"
DEFAULT_OUT = "reports/isolation_forest_evaluation.json"

BENIGN = "BENIGN"
TARGET_BENIGN_FLAG_RATES = [0.001, 0.005, 0.01, 0.02, 0.05]
LEAKED_CONTAMINATION = 0.1968099777925513
MIN_SUPPORT_FOR_CLAIM = 100


def _clean_label(label):
    return str(label).replace("\x96", "-").strip()


def load_reference(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def load_split(dataset_path, feature_columns, test_size, seed):
    frame = pd.read_parquet(dataset_path, columns=feature_columns + ["Label"])
    labels = frame["Label"].map(_clean_label).to_numpy()
    features = frame[feature_columns].to_numpy(dtype="float32")
    del frame

    train_idx, test_idx = train_test_split(
        np.arange(len(labels)), test_size=test_size, random_state=seed, stratify=labels
    )
    return features, labels, train_idx, test_idx


def fit_and_calibrate(features, labels, train_idx, calibration_frac, seed):
    benign_train = train_idx[labels[train_idx] == BENIGN]
    fit_idx, calibration_idx = train_test_split(
        benign_train, test_size=calibration_frac, random_state=seed
    )

    model = IsolationForest(
        n_estimators=100,
        contamination="auto",
        random_state=seed,
        n_jobs=-1,
    )
    model.fit(features[fit_idx])

    calibration_scores = model.score_samples(features[calibration_idx])
    return model, calibration_scores, len(fit_idx), len(calibration_idx)


def thresholds_from_calibration(calibration_scores):
    return {
        rate: float(np.quantile(calibration_scores, rate))
        for rate in TARGET_BENIGN_FLAG_RATES
    }


def per_family_detection(labels_test, scores_test, threshold):
    flagged = scores_test < threshold
    families = {}
    for family in sorted(set(labels_test)):
        mask = labels_test == family
        support = int(mask.sum())
        families[family] = {
            "support": support,
            "flagged": int(flagged[mask].sum()),
            "flag_rate": float(flagged[mask].mean()) if support else 0.0,
        }
    return families


def evaluate_feature_set(name, features, labels, train_idx, test_idx,
                         calibration_frac, seed):
    print(f"\n=== {name} ({features.shape[1]} features) ===")
    model, calibration_scores, n_fit, n_cal = fit_and_calibrate(
        features, labels, train_idx, calibration_frac, seed)
    print(f"  fit on {n_fit:,} BENIGN rows, calibrated on {n_cal:,} held-out BENIGN rows")

    labels_test = labels[test_idx]
    scores_test = model.score_samples(features[test_idx])
    is_attack = (labels_test != BENIGN).astype(int)

    anomaly = -scores_test
    roc_auc = float(roc_auc_score(is_attack, anomaly))
    pr_auc = float(average_precision_score(is_attack, anomaly))
    print(f"  ROC AUC {roc_auc:.4f} | PR AUC {pr_auc:.4f} | "
          f"test attack rate {is_attack.mean():.4f}")

    thresholds = thresholds_from_calibration(calibration_scores)
    operating_points = {}

    for rate, threshold in thresholds.items():
        flagged = scores_test < threshold
        true_positive = int((flagged & (is_attack == 1)).sum())
        false_positive = int((flagged & (is_attack == 0)).sum())
        attacks = int(is_attack.sum())
        benign = int((is_attack == 0).sum())

        precision = true_positive / (true_positive + false_positive) if flagged.any() else 0.0
        recall = true_positive / attacks if attacks else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

        operating_points[f"{rate:.3f}"] = {
            "target_benign_flag_rate": rate,
            "threshold": threshold,
            "observed_benign_flag_rate": float(false_positive / benign) if benign else 0.0,
            "attack_recall": recall,
            "precision": precision,
            "f1": f1,
            "per_family": per_family_detection(labels_test, scores_test, threshold),
        }
        print(f"  target FPR {rate:6.3f} -> observed {false_positive / benign:6.4f} | "
              f"attack recall {recall:6.4f} | precision {precision:6.4f}")

    leaked = evaluate_leaked_baseline(features, labels, train_idx, test_idx, seed)

    return {
        "feature_set": name,
        "n_features": int(features.shape[1]),
        "fit_rows": n_fit,
        "calibration_rows": n_cal,
        "test_rows": int(len(test_idx)),
        "test_attack_rate": float(is_attack.mean()),
        "roc_auc": roc_auc,
        "pr_auc": pr_auc,
        "operating_points": operating_points,
        "leaked_baseline": leaked,
    }


def evaluate_leaked_baseline(features, labels, train_idx, test_idx, seed):
    benign_train = train_idx[labels[train_idx] == BENIGN]
    model = IsolationForest(
        n_estimators=100,
        contamination=LEAKED_CONTAMINATION,
        random_state=seed,
        n_jobs=-1,
    )
    model.fit(features[benign_train])

    labels_test = labels[test_idx]
    is_attack = (labels_test != BENIGN).astype(int)
    predicted = (model.predict(features[test_idx]) == -1).astype(int)

    true_positive = int((predicted & is_attack).sum())
    false_positive = int((predicted & (1 - is_attack)).sum())
    precision = true_positive / predicted.sum() if predicted.sum() else 0.0
    recall = true_positive / is_attack.sum() if is_attack.sum() else 0.0

    print(f"  [leaked contamination={LEAKED_CONTAMINATION:.4f}] "
          f"recall {recall:.4f} | precision {precision:.4f} | "
          f"benign flagged {false_positive / (1 - is_attack).sum():.4f}")

    return {
        "contamination": LEAKED_CONTAMINATION,
        "note": "contamination was taken from the test-set attack rate; reported only "
                "to quantify what the leak was worth",
        "attack_recall": recall,
        "precision": precision,
        "benign_flag_rate": float(false_positive / (1 - is_attack).sum()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Vlereson Isolation Forest pa rrjedhje nga test-set dhe zgjedh nje prag.")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--calibration-frac", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.is_absolute():
        dataset_path = _ML_SERVICE_ROOT / dataset_path
    if not dataset_path.exists():
        print(f"Dataset-i s'u gjet: {dataset_path}", file=sys.stderr)
        return 1

    reference_path = Path(args.reference)
    if not reference_path.is_absolute():
        reference_path = _ML_SERVICE_ROOT / reference_path
    reference = load_reference(reference_path)

    all_features = reference["feature_sets"]["cicids2017-78-v1"]
    top50 = reference["feature_sets"]["cicids2017-top50-v1"]

    print(f"Duke lexuar {dataset_path.name} ...")
    features, labels, train_idx, test_idx = load_split(
        dataset_path, all_features, args.test_size, args.seed)
    print(f"  {len(labels):,} rreshta | train {len(train_idx):,} | test {len(test_idx):,}")

    results = [
        evaluate_feature_set("cicids2017-78-v1", features, labels, train_idx, test_idx,
                             args.calibration_frac, args.seed)
    ]

    top50_positions = [all_features.index(name) for name in top50]
    results.append(
        evaluate_feature_set("cicids2017-top50-v1", features[:, top50_positions], labels,
                             train_idx, test_idx, args.calibration_frac, args.seed)
    )

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "dataset": dataset_path.name,
        "seed": args.seed,
        "test_size": args.test_size,
        "calibration_frac": args.calibration_frac,
        "min_support_for_claim": MIN_SUPPORT_FOR_CLAIM,
        "protocol": "IsolationForest is fitted on BENIGN training rows only and the decision "
                    "threshold is chosen from a held-out BENIGN calibration split. No attack "
                    "row and no test row influences the model or the threshold.",
        "results": results,
    }

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = _ML_SERVICE_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1)

    print(f"\nU ruajt: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
