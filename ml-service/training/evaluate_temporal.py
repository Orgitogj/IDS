import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

from training.build_feature_reference import sha256_of
from training.evaluate import _clean_label
from training.pipeline import evaluation, splitting, temporal
from training.pipeline.data import LoadedDataset, clean_labels

DEFAULT_DATASET = "datasets/cicids2017_cleaned.parquet"
DEFAULT_REFERENCE = "reports/training_feature_reference.json"
DEFAULT_MODELS_DIR = "models"
DEFAULT_REPORTS_DIR = "reports/temporal_evaluation"
DEFAULT_RANDOM_INDEX = "reports/artifact_evaluation/index.json"

TEMPORAL_SUFFIX = "_temporal_v1"

RANDOM_COUNTERPART = {
    "xgb_smote_temporal_v1": "xgb_smote_cicids2017_v2.joblib",
    "xgb_baseline_temporal_v1": "xgb_baseline_cicids2017_v2.joblib",
    "rf_smote_temporal_v1": "rf_smote_cicids2017_v2.joblib",
    "rf_baseline_temporal_v1": "rf_baseline_cicids2017_v2.joblib",
    "mlp_smote_temporal_v1": "mlp_smote_cicids2017_v2.joblib",
    "xgb_smote_top50_temporal_v1": "xgb_smote_top50features_v2.joblib",
}


def resolve(value):
    path = Path(value)
    return path if path.is_absolute() else _ML_SERVICE_ROOT / path


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def git_commit():
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=_ML_SERVICE_ROOT,
                                capture_output=True, text=True)
        return result.stdout.strip() or None
    except OSError:
        return None


def library_versions():
    import sklearn
    import xgboost

    return {
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit-learn": sklearn.__version__,
        "xgboost": xgboost.__version__,
    }


def discover_temporal_bundles(models_dir):
    found = []
    for path in sorted(Path(models_dir).glob(f"*{TEMPORAL_SUFFIX}_bundle.json")):
        with open(path, encoding="utf-8") as handle:
            found.append(json.load(handle))
    return found


def random_reference(index_path):
    if not index_path.exists():
        return {}
    with open(index_path, encoding="utf-8") as handle:
        index = json.load(handle)

    reference = {}
    for record in index["artifacts"]:
        if not record.get("evaluated"):
            continue
        report = index_path.parent / record["report_dir"] / "metrics.json"
        if not report.exists():
            continue
        with open(report, encoding="utf-8") as handle:
            reference[record["artifact"]] = json.load(handle)
    return reference


def evaluate_one(bundle, models_dir, dataset, train_idx, test_idx, reports_dir):
    artifact = bundle["artifact_file"]
    stem = Path(artifact).stem
    model = joblib.load(models_dir / artifact)
    encoder = joblib.load(models_dir / bundle["label_encoder_file"])

    columns = list(bundle["feature_columns"])
    positions = [dataset.feature_columns.index(name) for name in columns]
    X_test = dataset.features[np.ix_(test_idx, positions)]

    scaler_file = bundle.get("scaler_file")
    if scaler_file:
        scaler = joblib.load(models_dir / scaler_file)
        X_test = scaler.transform(pd.DataFrame(X_test, columns=columns))

    frame = pd.DataFrame(np.asarray(X_test), columns=columns)
    encoded, batch_timing = evaluation.measure_batch_latency(model, frame)
    classes = [_clean_label(name) for name in encoder.classes_]
    y_pred = np.array([classes[int(index)] for index in encoded], dtype=object)
    y_test = dataset.labels[test_idx]

    train_classes = sorted(set(dataset.labels[train_idx]))

    run_reports = reports_dir / stem
    run_reports.mkdir(parents=True, exist_ok=True)
    metrics = temporal.evaluate_temporal(y_test, y_pred, train_classes,
                                         run_reports, bundle["name"])

    timings = evaluation.build_timings(
        bundle["timings"].get("train_seconds"), batch_timing,
        evaluation.measure_single_flow_latency(model, frame, seed=bundle["seed"]),
        evaluation.measure_production_path_latency(model, frame, columns,
                                                   seed=bundle["seed"]))

    report = {
        "schema_version": 1,
        "experiment_type": "temporal",
        "protocol_version": temporal.PROTOCOL_VERSION,
        "distinct_from": ("random-split v2 (reports/artifact_evaluation). Different "
                          "split protocol, different training rows, different artifacts. "
                          "The two are not interchangeable."),
        "generated_at": utc_now(),
        "evaluated_at": utc_now(),
        "trained_at": bundle.get("trained_at"),
        "name": bundle["name"],
        "version": bundle.get("version"),
        "algorithm": bundle.get("algorithm"),
        "artifact_file": artifact,
        "artifact_sha256": sha256_of(models_dir / artifact),
        "label_encoder_file": bundle["label_encoder_file"],
        "scaler_file": scaler_file,
        "scaler_provenance": ("fitted on the balanced temporal TRAINING partition only"
                              if scaler_file else None),
        "feature_version": bundle.get("feature_version"),
        "feature_columns": columns,
        "n_features": len(columns),
        "seed": bundle.get("seed"),
        "balancing": bundle.get("balancing"),
        "model_params": bundle.get("model_params"),
        "dataset": bundle.get("dataset"),
        "split": bundle.get("split"),
        "train_classes": train_classes,
        "n_train_classes": len(train_classes),
        "timings": timings,
        "metrics": metrics,
        "config_source": bundle.get("config_source"),
        "git_commit": git_commit(),
        "library_versions": library_versions(),
    }

    report_path = run_reports / "metrics.json"
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)

    return stem, report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Vlereson modelet kohore mbi particionin kohor te testit.")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--models-dir", default=DEFAULT_MODELS_DIR)
    parser.add_argument("--reports-dir", default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--random-index", default=DEFAULT_RANDOM_INDEX)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    models_dir = resolve(args.models_dir)
    reports_dir = resolve(args.reports_dir)
    dataset_path = resolve(args.dataset)

    bundles = discover_temporal_bundles(models_dir)
    if not bundles:
        print("Asnje bundle temporal s'u gjet; trajno fillimisht modelet kohore.",
              file=sys.stderr)
        return 1

    with open(resolve(args.reference), encoding="utf-8") as handle:
        reference = json.load(handle)
    base = list(reference["feature_sets"]["cicids2017-78-v1"])

    print(f"Duke lexuar {dataset_path.name} ...")
    meta = pd.read_parquet(dataset_path, columns=["Label", "Timestamp"])
    labels = clean_labels(meta["Label"].to_numpy())
    from training.evaluate import parse_cicids_timestamps
    stamps = parse_cicids_timestamps(meta["Timestamp"])
    del meta

    frame = pd.read_parquet(dataset_path, columns=base)
    features = frame[base].to_numpy(dtype="float32")
    del frame

    dataset = LoadedDataset(features, labels, base, stamps=stamps)
    train_idx, test_idx = splitting.split_indices(
        dataset, "temporal_global", args.test_size, args.seed)
    splitting.assert_disjoint(train_idx, test_idx)

    print(f"  train {len(train_idx):,} | test {len(test_idx):,} | "
          f"kufiri {stamps[train_idx].max()}")

    results = {}
    for bundle in bundles:
        print(f"\n--- {bundle['name']} ---")
        stem, report = evaluate_one(bundle, models_dir, dataset, train_idx, test_idx,
                                    reports_dir)
        results[stem] = report
        metrics = report["metrics"]
        strict = temporal.strict_macro_f1(metrics)
        seen = temporal.seen_macro_f1(metrics)
        print(f"  strict macro F1 ({metrics['metrics_by_class_set'][temporal.CLASS_SET_TEST]['n_classes']} test classes) : {strict:.6f}")
        print(f"  seen-class macro F1 ({metrics['metrics_by_class_set'][temporal.CLASS_SET_SEEN]['n_classes']} classes)   : {seen:.6f}")
        print(f"  unseen classes {metrics['unseen']['unseen_test_classes']} = "
              f"{metrics['unseen']['unseen_fraction_of_test']:.1%} of test")

    random_ref = random_reference(resolve(args.random_index))
    index = {
        "schema_version": 1,
        "experiment_type": "temporal",
        "protocol_version": temporal.PROTOCOL_VERSION,
        "generated_at": utc_now(),
        "git_commit": git_commit(),
        "library_versions": library_versions(),
        "dataset": {"name": dataset_path.name, "sha256": sha256_of(dataset_path),
                    "rows": int(len(labels))},
        "split": {
            "strategy": "temporal_global",
            "test_size": float(args.test_size),
            "boundary_timestamp": str(stamps[train_idx].max()),
            "train_rows": int(len(train_idx)),
            "test_rows": int(len(test_idx)),
            "train_first_timestamp": str(stamps[train_idx].min()),
            "train_last_timestamp": str(stamps[train_idx].max()),
            "test_first_timestamp": str(stamps[test_idx].min()),
            "test_last_timestamp": str(stamps[test_idx].max()),
        },
        "random_baseline_index": str(Path(args.random_index).as_posix()),
        "models": {stem: {
            "name": report["name"],
            "artifact": report["artifact_file"],
            "artifact_sha256": report["artifact_sha256"],
            "random_counterpart": RANDOM_COUNTERPART.get(stem),
            "strict_macro_f1": temporal.strict_macro_f1(report["metrics"]),
            "seen_macro_f1": temporal.seen_macro_f1(report["metrics"]),
            "unseen_fraction_of_test": report["metrics"]["unseen"][
                "unseen_fraction_of_test"],
        } for stem, report in results.items()},
    }

    reports_dir.mkdir(parents=True, exist_ok=True)
    index_path = reports_dir / "index.json"
    with open(index_path, "w", encoding="utf-8") as handle:
        json.dump(index, handle, indent=1)

    print(f"\nU vleresuan {len(results)} modele kohore.")
    print(f"U ruajt: {index_path}")
    print(f"Modelet random-v2 nuk u prekur ({len(random_ref)} raporte referencë të lexuara).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
