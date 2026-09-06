import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

from training.pipeline import splitting
from training.pipeline.data import LoadedDataset, clean_labels

DEFAULT_DATASET = "datasets/cicids2017_cleaned.parquet"
DEFAULT_REFERENCE = "reports/training_feature_reference.json"
DEFAULT_MODELS_DIR = "models"
DEFAULT_OUT = "reports/input_path_benchmark.json"

DEFAULT_ARTIFACTS = [
    "xgb_smote_cicids2017_v2.joblib",
    "xgb_smote_cicids2017_v1.joblib",
    "rf_smote_cicids2017_v1.joblib",
]

SAMPLES = 200
WARMUP = 20

NOTE = ("Controlled decomposition of the one-row inference cost. Each stage is timed "
        "separately over the same sampled rows so that the DataFrame overhead can be "
        "attributed rather than assumed. No production code is optimised here.")


def resolve(value):
    path = Path(value)
    return path if path.is_absolute() else _ML_SERVICE_ROOT / path


def _stats(durations):
    return {
        "mean_ms": float(np.mean(durations)),
        "median_ms": float(np.median(durations)),
        "p95_ms": float(np.percentile(durations, 95)),
    }


def time_frame_construction(values, columns, picks):
    for index in picks[:WARMUP]:
        pd.DataFrame([values[index].tolist()], columns=columns)

    durations = []
    for index in picks:
        vector = values[index].tolist()
        started = time.perf_counter()
        pd.DataFrame([vector], columns=columns)
        durations.append((time.perf_counter() - started) * 1000.0)
    return _stats(durations)


def time_predict_on_frame(model, values, columns, picks):
    frames = [pd.DataFrame([values[index].tolist()], columns=columns) for index in picks]

    for frame in frames[:WARMUP]:
        model.predict(frame)

    durations = []
    for frame in frames:
        started = time.perf_counter()
        model.predict(frame)
        durations.append((time.perf_counter() - started) * 1000.0)
    return _stats(durations)


def time_predict_on_ndarray(model, values, picks):
    rows = [values[index:index + 1] for index in picks]

    for row in rows[:WARMUP]:
        model.predict(row)

    durations = []
    for row in rows:
        started = time.perf_counter()
        model.predict(row)
        durations.append((time.perf_counter() - started) * 1000.0)
    return _stats(durations)


def time_dmatrix_path(model, values, columns, picks):
    booster = getattr(model, "get_booster", None)
    if booster is None:
        return None

    try:
        import xgboost as xgb
    except ImportError:
        return None

    booster = booster()
    frames = [pd.DataFrame([values[index].tolist()], columns=columns) for index in picks]

    construction = []
    for frame in frames[:WARMUP]:
        xgb.DMatrix(frame)
    for frame in frames:
        started = time.perf_counter()
        xgb.DMatrix(frame)
        construction.append((time.perf_counter() - started) * 1000.0)

    matrices = [xgb.DMatrix(frame) for frame in frames]
    predict = []
    for matrix in matrices[:WARMUP]:
        booster.predict(matrix)
    for matrix in matrices:
        started = time.perf_counter()
        booster.predict(matrix)
        predict.append((time.perf_counter() - started) * 1000.0)

    return {
        "dmatrix_construction_from_frame": _stats(construction),
        "booster_predict_on_dmatrix": _stats(predict),
    }


def benchmark(model, name, values, columns, picks):
    frame_build = time_frame_construction(values, columns, picks)
    predict_frame = time_predict_on_frame(model, values, columns, picks)
    predict_array = time_predict_on_ndarray(model, values, picks)
    dmatrix = time_dmatrix_path(model, values, columns, picks)

    overhead = predict_frame["mean_ms"] - predict_array["mean_ms"]
    attributed = frame_build["mean_ms"]

    result = {
        "artifact": name,
        "model_class": type(model).__name__,
        "n_features": int(getattr(model, "n_features_in_", len(columns))),
        "samples": int(len(picks)),
        "warmup": WARMUP,
        "dataframe_construction_only": frame_build,
        "predict_on_dataframe": predict_frame,
        "predict_on_ndarray": predict_array,
        "xgboost_internal": dmatrix,
        "attribution": {
            "frame_vs_array_overhead_ms": float(overhead),
            "explained_by_dataframe_construction_ms": float(attributed),
            "explained_fraction": float(attributed / overhead) if overhead else None,
            "residual_inside_predict_ms": float(overhead - attributed),
            "ratio_frame_over_array": (
                float(predict_frame["mean_ms"] / predict_array["mean_ms"])
                if predict_array["mean_ms"] else None),
        },
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Zberthen koston e inference per nje rresht: ndertim DataFrame, "
                    "predict mbi DataFrame, predict mbi ndarray.")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--models-dir", default=DEFAULT_MODELS_DIR)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--artifacts", nargs="+", default=DEFAULT_ARTIFACTS)
    parser.add_argument("--rows", type=int, default=20000)
    args = parser.parse_args()

    models_dir = resolve(args.models_dir)
    with open(resolve(args.reference), encoding="utf-8") as handle:
        reference = json.load(handle)
    base = list(reference["feature_sets"]["cicids2017-78-v1"])

    dataset_path = resolve(args.dataset)
    labels = clean_labels(
        pd.read_parquet(dataset_path, columns=["Label"])["Label"].to_numpy())
    frame = pd.read_parquet(dataset_path, columns=base)
    features = frame[base].to_numpy(dtype="float32")
    del frame

    _, test_idx = splitting.split_indices(
        LoadedDataset(features, labels, base), "random", 0.2, 42)
    subset = test_idx[:args.rows]

    rng = np.random.default_rng(42)
    picks = rng.choice(len(subset), size=min(SAMPLES, len(subset)), replace=False)

    results = []
    for artifact in args.artifacts:
        path = models_dir / artifact
        if not path.exists():
            print(f"  [skip] {artifact} mungon", file=sys.stderr)
            continue

        model = joblib.load(path)
        columns = [str(name) for name in getattr(model, "feature_names_in_", base)]
        positions = [base.index(name) for name in columns]
        values = features[np.ix_(subset, positions)]

        print(f"\n=== {artifact} ({type(model).__name__}, {len(columns)} features) ===")
        result = benchmark(model, artifact, values, columns, picks)
        results.append(result)

        print(f"  DataFrame construction only : {result['dataframe_construction_only']['mean_ms']:.4f} ms")
        print(f"  predict(DataFrame)          : {result['predict_on_dataframe']['mean_ms']:.4f} ms")
        print(f"  predict(ndarray)            : {result['predict_on_ndarray']['mean_ms']:.4f} ms")
        attribution = result["attribution"]
        print(f"  overhead frame vs array     : {attribution['frame_vs_array_overhead_ms']:.4f} ms "
              f"({attribution['ratio_frame_over_array']:.1f}x)")
        print(f"    explained by construction : {attribution['explained_by_dataframe_construction_ms']:.4f} ms "
              f"({(attribution['explained_fraction'] or 0) * 100:.1f}%)")
        print(f"    residual inside predict   : {attribution['residual_inside_predict_ms']:.4f} ms")
        if result["xgboost_internal"]:
            internal = result["xgboost_internal"]
            print(f"  DMatrix(frame) construction : {internal['dmatrix_construction_from_frame']['mean_ms']:.4f} ms")
            print(f"  booster.predict(DMatrix)    : {internal['booster_predict_on_dmatrix']['mean_ms']:.4f} ms")

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "note": NOTE,
        "samples": SAMPLES,
        "warmup": WARMUP,
        "rows_pool": int(len(subset)),
        "results": results,
    }

    out_path = resolve(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1)

    print(f"\nU ruajt: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
