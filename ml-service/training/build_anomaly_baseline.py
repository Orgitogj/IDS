import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

DEFAULT_DATASET = "datasets/cicids2017_cleaned.parquet"
DEFAULT_MODELS_DIR = "models"
DEFAULT_CALIBRATION = "isolation_forest_benign_v2_calibration.json"
DEFAULT_OUT = "reports/anomaly_feature_baseline.json"

BENIGN = "BENIGN"
CALIBRATION_FRAC = 0.2


def _clean_label(label):
    return str(label).replace("\x96", "-").strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Nxjerr vlerat tipike BENIGN te rreshtave mbi te cilet u fitua "
                    "detektori i anomalive, per atribuimin e features.")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--models-dir", default=DEFAULT_MODELS_DIR)
    parser.add_argument("--calibration", default=DEFAULT_CALIBRATION)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    def _resolve(value):
        path = Path(value)
        return path if path.is_absolute() else _ML_SERVICE_ROOT / path

    dataset_path = _resolve(args.dataset)
    if not dataset_path.exists():
        print(f"Dataset-i s'u gjet: {dataset_path}", file=sys.stderr)
        return 1

    calibration_path = _resolve(args.models_dir) / args.calibration
    if not calibration_path.exists():
        print(f"Kalibrimi s'u gjet: {calibration_path}", file=sys.stderr)
        return 1

    with open(calibration_path, encoding="utf-8") as handle:
        calibration = json.load(handle)

    feature_columns = calibration["feature_columns"]
    if calibration["seed"] != args.seed:
        print(f"KUJDES: seed i kalibrimit {calibration['seed']} != {args.seed}; "
              "rreshtat e fit-it nuk do te perputhen.", file=sys.stderr)

    print(f"Duke lexuar {dataset_path.name} ({len(feature_columns)} features) ...")
    frame = pd.read_parquet(dataset_path, columns=feature_columns + ["Label"])
    labels = frame["Label"].map(_clean_label).to_numpy()
    features = frame[feature_columns].to_numpy(dtype="float64")
    del frame

    train_idx, _ = train_test_split(
        np.arange(len(labels)), test_size=args.test_size,
        random_state=args.seed, stratify=labels
    )
    benign_train = train_idx[labels[train_idx] == BENIGN]
    fit_idx, _ = train_test_split(
        benign_train, test_size=CALIBRATION_FRAC, random_state=args.seed
    )

    if len(fit_idx) != calibration["fit_rows"]:
        print(f"KUJDES: {len(fit_idx):,} rreshta fit kunder {calibration['fit_rows']:,} "
              "te regjistruar ne kalibrim.", file=sys.stderr)

    fitted = features[fit_idx]
    print(f"  {len(fit_idx):,} rreshta BENIGN (te njejtet mbi te cilet u fitua detektori)")

    medians = np.median(fitted, axis=0)
    p25 = np.quantile(fitted, 0.25, axis=0)
    p75 = np.quantile(fitted, 0.75, axis=0)
    p99 = np.quantile(fitted, 0.99, axis=0)

    baseline = {
        name: {
            "median": float(medians[position]),
            "p25": float(p25[position]),
            "p75": float(p75[position]),
            "p99": float(p99[position]),
        }
        for position, name in enumerate(feature_columns)
    }

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "artifact_file": calibration["artifact_file"],
        "feature_version": calibration["feature_version"],
        "feature_columns": feature_columns,
        "dataset": dataset_path.name,
        "dataset_sha256": calibration.get("dataset_sha256"),
        "seed": args.seed,
        "fit_rows": int(len(fit_idx)),
        "derived_from": "the exact BENIGN rows the isolation forest was fitted on, "
                        "reconstructed with the same seed and split parameters recorded in "
                        "the calibration file",
        "purpose": "substitution baseline for anomaly feature attribution: replacing one "
                   "feature with its median here and re-scoring measures how much that "
                   "feature alone is driving the anomaly verdict",
        "baseline": baseline,
    }

    out_path = _resolve(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1)

    print(f"\nU ruajt: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
