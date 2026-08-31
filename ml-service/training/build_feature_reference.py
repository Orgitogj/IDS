import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_DATASET = "datasets/cicids2017_cleaned.parquet"
DEFAULT_MODELS_DIR = "models"
DEFAULT_OUT = "reports/training_feature_reference.json"

BASE_FEATURE_VERSION = "cicids2017-78-v1"

FEATURE_SET_ARTIFACTS = {
    "cicids2017-78-v1": "xgb_smote_cicids2017_v1.joblib",
    "cicids2017-top50-v1": "xgb_smote_top50features_v1.joblib",
    "cicids2017-top30-v1": "xgb_smote_top30features_v1.joblib",
    "cicids2017-top20-v1": "xgb_smote_top20features_v1.joblib",
    "cicids2017-top10-v1": "xgb_smote_top10features_v1.joblib",
}

QUANTILE_GRID = [round(q / 100.0, 2) for q in range(0, 101)]

READ_CHUNK = 1024 * 1024 * 8


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(READ_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _finite(value):
    number = float(value)
    if np.isnan(number) or np.isinf(number):
        return None
    return number


def summarise_feature(series: pd.Series) -> dict:
    values = series.to_numpy(dtype="float64", copy=False)
    finite = values[np.isfinite(values)]

    quantiles = np.quantile(finite, QUANTILE_GRID) if finite.size else np.zeros(len(QUANTILE_GRID))
    unique_count = int(series.nunique(dropna=True))

    summary = {
        "count": int(finite.size),
        "nan_count": int(np.isnan(values).sum()),
        "inf_count": int(np.isinf(values).sum()),
        "nunique": unique_count,
        "constant": unique_count <= 1,
        "mean": _finite(finite.mean()) if finite.size else None,
        "std": _finite(finite.std(ddof=1)) if finite.size > 1 else 0.0,
        "min": _finite(finite.min()) if finite.size else None,
        "max": _finite(finite.max()) if finite.size else None,
        "p01": _finite(quantiles[1]),
        "p25": _finite(quantiles[25]),
        "p50": _finite(quantiles[50]),
        "p75": _finite(quantiles[75]),
        "p99": _finite(quantiles[99]),
        "zero_fraction": float((values == 0).mean()) if values.size else 0.0,
        "negative_fraction": float((values < 0).mean()) if values.size else 0.0,
        "quantiles": [_finite(q) for q in quantiles],
    }

    if summary["constant"]:
        summary["constant_value"] = summary["min"]
    else:
        summary["constant_value"] = None

    return summary


def collect_feature_sets(models_dir: Path, base_columns: list) -> dict:
    feature_sets = {BASE_FEATURE_VERSION: list(base_columns)}

    for version, filename in FEATURE_SET_ARTIFACTS.items():
        if version == BASE_FEATURE_VERSION:
            continue
        artifact = models_dir / filename
        if not artifact.exists():
            print(f"  [skip] {version}: mungon {artifact.name}", file=sys.stderr)
            continue
        model = joblib.load(artifact)
        names = getattr(model, "feature_names_in_", None)
        if names is None:
            print(f"  [skip] {version}: modeli s'ka feature_names_in_", file=sys.stderr)
            continue
        feature_sets[version] = [str(name) for name in names]

    return feature_sets


def build(dataset_path: Path, models_dir: Path, feature_columns: list) -> dict:
    print(f"Duke lexuar {dataset_path.name} ...")
    frame = pd.read_parquet(dataset_path, columns=feature_columns + ["Label"])
    print(f"  {len(frame):,} rreshta, {len(feature_columns)} features")

    label_counts = frame["Label"].value_counts()
    features = {}
    constant_zero = []
    near_zero = []

    for column in feature_columns:
        summary = summarise_feature(frame[column])
        features[column] = summary
        if summary["constant"] and summary["constant_value"] == 0.0:
            constant_zero.append(column)
        elif summary["zero_fraction"] >= 0.99:
            near_zero.append(column)

    print(f"  {len(constant_zero)} features konstante-zero, {len(near_zero)} features >=99% zero")

    feature_sets = collect_feature_sets(models_dir, feature_columns)

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "base_feature_version": BASE_FEATURE_VERSION,
        "dataset": {
            "name": dataset_path.name,
            "path": str(dataset_path.relative_to(_ML_SERVICE_ROOT)),
            "rows": int(len(frame)),
            "sha256": sha256_of(dataset_path),
        },
        "label_distribution": {
            repr(label)[1:-1]: int(count) for label, count in label_counts.items()
        },
        "n_features": len(feature_columns),
        "quantile_grid": QUANTILE_GRID,
        "feature_sets": feature_sets,
        "constant_zero_features": constant_zero,
        "near_zero_features": near_zero,
        "features": features,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ndertjon referencen statistikore te features nga dataset-i i trajnimit.")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--models-dir", default=DEFAULT_MODELS_DIR)
    parser.add_argument("--feature-columns", default=None)
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.is_absolute():
        dataset_path = _ML_SERVICE_ROOT / dataset_path
    if not dataset_path.exists():
        print(f"Dataset-i s'u gjet: {dataset_path}", file=sys.stderr)
        return 1

    models_dir = Path(args.models_dir)
    if not models_dir.is_absolute():
        models_dir = _ML_SERVICE_ROOT / models_dir

    columns_path = Path(args.feature_columns) if args.feature_columns else models_dir / "feature_columns.json"
    with open(columns_path) as handle:
        feature_columns = json.load(handle)

    reference = build(dataset_path, models_dir, feature_columns)

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = _ML_SERVICE_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(reference, handle, indent=1)

    size_kb = out_path.stat().st_size / 1024
    print(f"\nU ruajt: {out_path} ({size_kb:.0f} KB)")
    print(f"Feature sets: {', '.join(reference['feature_sets'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
