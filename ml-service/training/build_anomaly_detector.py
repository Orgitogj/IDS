import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.model_selection import train_test_split

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

DEFAULT_DATASET = "datasets/cicids2017_cleaned.parquet"
DEFAULT_REFERENCE = "reports/training_feature_reference.json"
DEFAULT_MODELS_DIR = "models"

ARTIFACT_NAME = "isolation_forest_benign_v2.joblib"
CALIBRATION_NAME = "isolation_forest_benign_v2_calibration.json"

BENIGN = "BENIGN"
CALIBRATION_FRAC = 0.2
TARGET_FLAG_RATES = [0.001, 0.005, 0.01, 0.02, 0.05]
PERCENTILE_GRID = [round(q / 100.0, 2) for q in range(0, 101)]


def _clean_label(label):
    return str(label).replace("\x96", "-").strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ndertjon detektorin e anomalive pa rrjedhje nga test-set.")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--models-dir", default=DEFAULT_MODELS_DIR)
    parser.add_argument("--feature-set", default="cicids2017-78-v1")
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-estimators", type=int, default=100)
    parser.add_argument("--max-samples", default="auto")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.is_absolute():
        dataset_path = _ML_SERVICE_ROOT / dataset_path
    reference_path = Path(args.reference)
    if not reference_path.is_absolute():
        reference_path = _ML_SERVICE_ROOT / reference_path
    models_dir = Path(args.models_dir)
    if not models_dir.is_absolute():
        models_dir = _ML_SERVICE_ROOT / models_dir

    with open(reference_path, encoding="utf-8") as handle:
        reference = json.load(handle)
    feature_columns = reference["feature_sets"][args.feature_set]

    print(f"Duke lexuar {dataset_path.name} ({len(feature_columns)} features) ...")
    frame = pd.read_parquet(dataset_path, columns=feature_columns + ["Label"])
    labels = frame["Label"].map(_clean_label).to_numpy()
    features = frame[feature_columns].to_numpy(dtype="float32")
    del frame

    train_idx, _ = train_test_split(
        np.arange(len(labels)), test_size=args.test_size,
        random_state=args.seed, stratify=labels
    )
    benign_train = train_idx[labels[train_idx] == BENIGN]
    fit_idx, calibration_idx = train_test_split(
        benign_train, test_size=CALIBRATION_FRAC, random_state=args.seed
    )
    print(f"  fit {len(fit_idx):,} BENIGN | kalibrim {len(calibration_idx):,} BENIGN")

    max_samples = args.max_samples
    if max_samples != "auto":
        max_samples = min(int(max_samples), len(fit_idx))

    model = IsolationForest(
        n_estimators=args.n_estimators,
        max_samples=max_samples,
        contamination="auto",
        random_state=args.seed,
        n_jobs=-1,
    )
    model.fit(features[fit_idx])

    calibration_scores = model.score_samples(features[calibration_idx])
    thresholds = {f"{rate:.3f}": float(np.quantile(calibration_scores, rate))
                  for rate in TARGET_FLAG_RATES}
    quantiles = [float(value) for value in np.quantile(calibration_scores, PERCENTILE_GRID)]

    artifact_path = models_dir / ARTIFACT_NAME
    joblib.dump(model, artifact_path)

    calibration = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "artifact_file": ARTIFACT_NAME,
        "algorithm": "IsolationForest",
        "feature_version": args.feature_set,
        "feature_columns": feature_columns,
        "dataset": dataset_path.name,
        "dataset_sha256": reference["dataset"]["sha256"],
        "seed": args.seed,
        "n_estimators": args.n_estimators,
        "max_samples": int(model.max_samples_),
        "max_samples_setting": str(args.max_samples),
        "fit_rows": int(len(fit_idx)),
        "calibration_rows": int(len(calibration_idx)),
        "trained_on": "BENIGN training rows only",
        "threshold_selection": "quantiles of held-out BENIGN calibration scores; no attack "
                               "row and no test row influences the model or the thresholds",
        "thresholds": thresholds,
        "percentile_grid": PERCENTILE_GRID,
        "calibration_quantiles": quantiles,
    }

    calibration_path = models_dir / CALIBRATION_NAME
    with open(calibration_path, "w", encoding="utf-8") as handle:
        json.dump(calibration, handle, indent=1)

    print(f"\nU ruajt: {artifact_path.name} ({artifact_path.stat().st_size / 1024:.0f} KB)")
    print(f"U ruajt: {calibration_path.name}")
    print("Pragjet (shkalla e synuar e flamurimit te BENIGN -> pragu):")
    for rate, value in thresholds.items():
        print(f"  {rate} -> {value:.6f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
