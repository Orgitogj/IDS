import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

from app.ml.drift import ks_against_reference

DEFAULT_DATASET = "datasets/cicids2017_cleaned.parquet"
DEFAULT_REFERENCE = "reports/training_feature_reference.json"
DEFAULT_OUT = "reports/drift_thresholds.json"

WINDOW_SIZES = [200, 500, 1000, 2000]
BOOTSTRAP_DRAWS = 200
FEATURE_QUANTILES = [0.95, 0.99]
FRACTION_QUANTILES = [0.95, 0.99]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Nxjerr pragjet e drift-it nga vete dataset-i i trajnimit (bootstrap).")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--draws", type=int, default=BOOTSTRAP_DRAWS)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.is_absolute():
        dataset_path = _ML_SERVICE_ROOT / dataset_path
    reference_path = Path(args.reference)
    if not reference_path.is_absolute():
        reference_path = _ML_SERVICE_ROOT / reference_path

    with open(reference_path, encoding="utf-8") as handle:
        reference = json.load(handle)

    feature_columns = reference["feature_sets"][reference["base_feature_version"]]
    percentiles = np.asarray(reference["quantile_grid"], dtype="float64")

    print(f"Duke lexuar {dataset_path.name} ...")
    frame = pd.read_parquet(dataset_path, columns=feature_columns)
    values = frame.to_numpy(dtype="float64")
    del frame
    print(f"  {values.shape[0]:,} rreshta, {values.shape[1]} features")

    reference_quantiles = {
        name: np.asarray(reference["features"][name]["quantiles"], dtype="float64")
        for name in feature_columns
    }

    rng = np.random.default_rng(args.seed)
    windows = {}

    for window in WINDOW_SIZES:
        print(f"\nDritarja {window} rreshta, {args.draws} terheqje ...")
        per_feature = {name: [] for name in feature_columns}
        exceeded_fractions_95 = []

        for _ in range(args.draws):
            rows = rng.choice(values.shape[0], size=window, replace=False)
            sample = values[rows]
            for position, name in enumerate(feature_columns):
                per_feature[name].append(
                    ks_against_reference(sample[:, position], reference_quantiles[name],
                                         percentiles))

        feature_thresholds = {}
        for name in feature_columns:
            draws = np.asarray(per_feature[name])
            feature_thresholds[name] = {
                f"p{int(q * 100)}": float(np.quantile(draws, q)) for q in FEATURE_QUANTILES
            }

        for draw_index in range(args.draws):
            exceeded = sum(
                1 for name in feature_columns
                if per_feature[name][draw_index] > feature_thresholds[name]["p95"]
            )
            exceeded_fractions_95.append(exceeded / len(feature_columns))

        fractions = np.asarray(exceeded_fractions_95)
        fraction_thresholds = {
            f"p{int(q * 100)}": float(np.quantile(fractions, q)) for q in FRACTION_QUANTILES
        }

        analytic = 1.358 / np.sqrt(window)
        median_p95 = float(np.median([feature_thresholds[n]["p95"] for n in feature_columns]))

        windows[str(window)] = {
            "window_size": window,
            "feature_ks_thresholds": feature_thresholds,
            "drifted_fraction_thresholds": fraction_thresholds,
            "median_feature_p95": median_p95,
            "asymptotic_p95_reference": float(analytic),
            "mean_drifted_fraction": float(fractions.mean()),
        }

        print(f"  KS p95 mesatar per feature: {median_p95:.4f} "
              f"(vlera asimptotike 1.358/sqrt(n) = {analytic:.4f})")
        print(f"  Pjesa e features qe e kalojne p95-in e vet: "
              f"mesatarja {fractions.mean() * 100:.1f}%, "
              f"p95 {fraction_thresholds['p95'] * 100:.1f}%, "
              f"p99 {fraction_thresholds['p99'] * 100:.1f}%")

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "dataset": dataset_path.name,
        "dataset_sha256": reference["dataset"]["sha256"],
        "base_feature_version": reference["base_feature_version"],
        "seed": args.seed,
        "bootstrap_draws": args.draws,
        "window_sizes": WINDOW_SIZES,
        "protocol": "For each window size, random samples are drawn from the training data "
                    "itself and scored against the training reference. The resulting KS "
                    "distribution is the null: what 'no drift' looks like at that sample "
                    "size. A feature counts as drifted when its KS exceeds its own p95 "
                    "under that null, and the fraction of drifted features is compared "
                    "against the null distribution of that same fraction.",
        "windows": windows,
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
