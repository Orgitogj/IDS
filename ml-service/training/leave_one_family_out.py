import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.ensemble import IsolationForest
from sklearn.model_selection import train_test_split

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

DEFAULT_DATASET = "datasets/cicids2017_cleaned.parquet"
DEFAULT_REFERENCE = "reports/training_feature_reference.json"
DEFAULT_OUT = "reports/leave_one_family_out.json"

BENIGN = "BENIGN"
BENIGN_CAP = 200_000
MIN_TEST_SUPPORT = 100
CALIBRATION_FRAC = 0.2
OPERATING_RATES = [0.01, 0.02]


def _clean_label(label):
    return str(label).replace("\x96", "-").strip()


def load_everything(dataset_path, feature_columns, test_size, seed):
    frame = pd.read_parquet(dataset_path, columns=feature_columns + ["Label"])
    labels = frame["Label"].map(_clean_label).to_numpy()
    features = frame[feature_columns].to_numpy(dtype="float32")
    del frame

    train_idx, test_idx = train_test_split(
        np.arange(len(labels)), test_size=test_size, random_state=seed, stratify=labels
    )
    return features, labels, train_idx, test_idx


def build_anomaly_detector(features, labels, train_idx, seed):
    benign_train = train_idx[labels[train_idx] == BENIGN]
    fit_idx, calibration_idx = train_test_split(
        benign_train, test_size=CALIBRATION_FRAC, random_state=seed
    )

    model = IsolationForest(n_estimators=100, contamination="auto",
                            random_state=seed, n_jobs=-1)
    model.fit(features[fit_idx])

    calibration_scores = model.score_samples(features[calibration_idx])
    thresholds = {rate: float(np.quantile(calibration_scores, rate))
                  for rate in OPERATING_RATES}
    return model, thresholds


def balanced_training_indices(labels, train_idx, excluded_family, seed):
    rng = np.random.default_rng(seed)
    kept = train_idx[labels[train_idx] != excluded_family]

    benign = kept[labels[kept] == BENIGN]
    attacks = kept[labels[kept] != BENIGN]

    if len(benign) > BENIGN_CAP:
        benign = rng.choice(benign, size=BENIGN_CAP, replace=False)

    selected = np.concatenate([benign, attacks])
    rng.shuffle(selected)
    return selected


def evaluate_family(family, features, labels, train_idx, test_idx,
                    anomaly_model, thresholds, seed):
    family_test = test_idx[labels[test_idx] == family]
    support = len(family_test)

    training_indices = balanced_training_indices(labels, train_idx, family, seed)
    classes = sorted(set(labels[training_indices]))
    class_to_index = {name: position for position, name in enumerate(classes)}
    y_train = np.array([class_to_index[name] for name in labels[training_indices]])

    model = xgb.XGBClassifier(n_estimators=100, random_state=seed, n_jobs=-1,
                              tree_method="hist", eval_metric="mlogloss")
    model.fit(features[training_indices], y_train)

    predicted = model.predict(features[family_test])
    predicted_names = np.array([classes[index] for index in predicted])

    called_benign = predicted_names == BENIGN
    missed_rate = float(called_benign.mean()) if support else 0.0

    scores = anomaly_model.score_samples(features[family_test])

    operating = {}
    for rate, threshold in thresholds.items():
        flagged = scores < threshold
        recovered = int((flagged & called_benign).sum())
        missed_count = int(called_benign.sum())
        operating[f"{rate:.3f}"] = {
            "target_benign_flag_rate": rate,
            "anomaly_flag_rate_on_family": float(flagged.mean()) if support else 0.0,
            "supervised_missed": missed_count,
            "anomaly_recovered_from_missed": recovered,
            "recovery_rate_on_missed": float(recovered / missed_count) if missed_count else None,
            "combined_detection_rate": float(((~called_benign) | flagged).mean()) if support else 0.0,
        }

    print(f"  {family:<28} support={support:<7} "
          f"xgb_called_benign={missed_rate * 100:5.1f}%  "
          + "  ".join(
              f"IF@{rate:.0%}: recovered "
              f"{(operating[f'{rate:.3f}']['recovery_rate_on_missed'] or 0) * 100:5.1f}%"
              for rate in OPERATING_RATES))

    return {
        "family": family,
        "test_support": support,
        "sufficient_support": support >= MIN_TEST_SUPPORT,
        "training_rows": int(len(training_indices)),
        "classes_seen_in_training": len(classes),
        "supervised_called_benign_rate": missed_rate,
        "supervised_predicted_labels": {
            name: int((predicted_names == name).sum())
            for name in sorted(set(predicted_names))
        },
        "operating_points": operating,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sa ndihmon Isolation Forest per familje sulmesh qe XGBoost s'i ka pare kurre.")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--feature-set", default="cicids2017-78-v1")
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--families", nargs="*", default=None)
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.is_absolute():
        dataset_path = _ML_SERVICE_ROOT / dataset_path
    reference_path = Path(args.reference)
    if not reference_path.is_absolute():
        reference_path = _ML_SERVICE_ROOT / reference_path

    with open(reference_path, encoding="utf-8") as handle:
        reference = json.load(handle)
    feature_columns = reference["feature_sets"][args.feature_set]

    print(f"Duke lexuar {dataset_path.name} ({args.feature_set}) ...")
    features, labels, train_idx, test_idx = load_everything(
        dataset_path, feature_columns, args.test_size, args.seed)
    print(f"  train {len(train_idx):,} | test {len(test_idx):,}")

    print("Duke ndertuar detektorin e anomalive (vetem BENIGN, prag nga kalibrimi) ...")
    anomaly_model, thresholds = build_anomaly_detector(features, labels, train_idx, args.seed)
    print(f"  pragjet: " + ", ".join(f"{rate:.0%} -> {value:.4f}"
                                      for rate, value in thresholds.items()))

    test_labels = labels[test_idx]
    candidates = []
    for family in sorted(set(test_labels)):
        if family == BENIGN:
            continue
        if int((test_labels == family).sum()) >= MIN_TEST_SUPPORT:
            candidates.append(family)

    families = args.families or candidates
    print(f"\nFamiljet me mbeshtetje >= {MIN_TEST_SUPPORT} ne test: {len(families)}")
    print("Per secilen: XGBoost ritrajnohet PA ate familje, pastaj matet sa e kap IF.\n")

    results = []
    for family in families:
        results.append(evaluate_family(family, features, labels, train_idx, test_idx,
                                        anomaly_model, thresholds, args.seed))

    excluded = [f for f in sorted(set(test_labels)) if f != BENIGN and f not in families]

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "dataset": dataset_path.name,
        "feature_set": args.feature_set,
        "seed": args.seed,
        "benign_cap_in_training": BENIGN_CAP,
        "min_test_support": MIN_TEST_SUPPORT,
        "protocol": "For each family F: XGBoost is retrained on training data with every "
                    "row of F removed, so F is genuinely unseen. The Isolation Forest is "
                    "fitted on BENIGN training rows only, with its threshold taken from a "
                    "held-out BENIGN calibration split, and is identical across families. "
                    "Recovery is measured only on the rows the supervised model called BENIGN. "
                    "This XGBoost is a controlled comparison model trained without SMOTE; it "
                    "is not the production artifact.",
        "families_excluded_for_low_support": excluded,
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
