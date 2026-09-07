import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

from training.build_feature_reference import sha256_of
from training.evaluate import save_confusion_matrix_csv, save_confusion_matrix_png
from training.pipeline import balancing, evaluation, families, lofo, models, splitting
from training.pipeline.data import LoadedDataset, clean_labels

DEFAULT_DATASET = "datasets/cicids2017_cleaned.parquet"
DEFAULT_REFERENCE = "reports/training_feature_reference.json"
DEFAULT_REPORTS_DIR = "reports/lofo_evaluation"
DEFAULT_MODELS_DIR = "models/lofo"
RANDOM_REPORTS = "reports/artifact_evaluation"

CANONICAL_SPLIT = {"strategy": "random", "test_size": 0.2, "seed": 42}
FEATURE_SET = "cicids2017-78-v1"
SEED = 42

BALANCING = {"enabled": True, "benign_label": "BENIGN", "benign_cap": 200000,
             "rare_class_min": 2000, "oversampler": "smote", "smote_k_neighbors": 5}

MODEL_SPECS = {
    "xgb_baseline": {"type": "xgboost", "balanced": False,
                     "params": {"n_estimators": 100, "tree_method": "hist",
                                "eval_metric": "mlogloss", "n_jobs": -1},
                     "random_counterpart": "xgb_baseline_cicids2017_v2"},
    "xgb_balanced": {"type": "xgboost", "balanced": True,
                     "params": {"n_estimators": 100, "tree_method": "hist",
                                "eval_metric": "mlogloss", "n_jobs": -1},
                     "random_counterpart": "xgb_smote_cicids2017_v2"},
    "rf_baseline": {"type": "random_forest", "balanced": False,
                    "params": {"n_estimators": 100, "n_jobs": -1, "class_weight": None},
                    "random_counterpart": "rf_baseline_cicids2017_v2"},
    "rf_balanced": {"type": "random_forest", "balanced": True,
                    "params": {"n_estimators": 100, "n_jobs": -1, "class_weight": None},
                    "random_counterpart": "rf_smote_cicids2017_v2"},
}

PRIMARY_MODELS = ["xgb_baseline", "xgb_balanced", "rf_baseline"]


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

    return {"python": sys.version.split()[0], "numpy": np.__version__,
            "pandas": pd.__version__, "scikit-learn": sklearn.__version__,
            "xgboost": xgboost.__version__}


def collect_folds_from_disk(reports_dir):
    folds = {}
    for path in sorted(Path(reports_dir).glob("lofo_*/metrics.json")):
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        folds[payload["name"]] = {
            "held_out_family": payload["held_out_family"],
            "model_key": payload["model_key"],
            "held_out_family_test_support": payload["held_out_family_test_support"],
            "attack_detection_rate": payload["metrics"]["detection"].get(
                "attack_detection_rate"),
            "known_macro_f1": payload["metrics"]["known_class"].get("macro_f1"),
        }
    return folds


def summarise_folds(folds):
    return {
        "families_run": sorted({entry["held_out_family"] for entry in folds.values()}),
        "models_run": sorted({entry["model_key"] for entry in folds.values()}),
        "n_folds": len(folds),
    }


def write_index(index_path, folds, dataset_path, dataset_rows):
    summary = summarise_folds(folds)
    index = {
        "schema_version": 1,
        "experiment_type": "lofo",
        "protocol_version": lofo.PROTOCOL_VERSION,
        "taxonomy_version": families.TAXONOMY_VERSION,
        "generated_at": utc_now(),
        "git_commit": git_commit(),
        "library_versions": library_versions(),
        "canonical_split": CANONICAL_SPLIT,
        "dataset": {"name": dataset_path.name, "sha256": sha256_of(dataset_path),
                    "rows": int(dataset_rows)},
        "families_run": summary["families_run"],
        "models_run": summary["models_run"],
        "n_folds": summary["n_folds"],
        "index_source": ("derived from every lofo_*/metrics.json present on disk, so the "
                         "summary fields always describe the complete accumulated "
                         "experiment rather than the most recent invocation"),
        "folds": folds,
    }
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as handle:
        json.dump(index, handle, indent=1)
    return index


def run_fold(family, model_key, dataset, train_idx, test_idx, reports_dir, models_dir,
             save_model=True):
    spec = MODEL_SPECS[model_key]
    members = families.member_labels(family)
    labels = dataset.labels
    columns = dataset.feature_columns

    kept_idx, removed = lofo.remove_family_from_train(labels, train_idx, members)

    if spec["balanced"]:
        X_train, y_train, balance_report = balancing.balance_training_set(
            dataset.features, labels, kept_idx, BALANCING, SEED)
    else:
        X_train, y_train = dataset.features[kept_idx], labels[kept_idx]
        balance_report = {"enabled": False, "rows_before": int(len(kept_idx)),
                          "rows_after": int(len(kept_idx))}

    lofo.assert_absent_after_balancing(y_train, members)

    X_train = pd.DataFrame(X_train, columns=columns)
    X_test = pd.DataFrame(dataset.features[test_idx], columns=columns)

    scaler = models.build_scaler(spec["type"])
    if scaler is not None:
        X_train = pd.DataFrame(scaler.fit_transform(X_train), columns=columns)
        X_test = pd.DataFrame(scaler.transform(X_test), columns=columns)

    encoder = LabelEncoder()
    y_encoded = encoder.fit_transform(y_train)
    known_labels = [str(name) for name in encoder.classes_]

    params = models.resolve_params(spec["type"], spec["params"])
    model = models.build_model(spec["type"], params, SEED)

    started = time.perf_counter()
    model.fit(X_train, y_encoded)
    train_seconds = time.perf_counter() - started

    encoded, batch_timing = evaluation.measure_batch_latency(model, X_test)
    y_pred = np.array([known_labels[int(index)] for index in encoded], dtype=object)
    y_true = labels[test_idx]

    held_mask = np.isin(y_true, members)
    report = lofo.fold_report(family, members, y_true, y_pred, known_labels, held_mask)
    matrix = report.pop("confusion_matrix")

    stem = f"lofo_{model_key}_{family.replace(' ', '_').lower()}"
    run_reports = reports_dir / stem
    run_reports.mkdir(parents=True, exist_ok=True)
    save_confusion_matrix_csv(matrix, run_reports / "confusion_matrix.csv")
    save_confusion_matrix_png(matrix, run_reports / "confusion_matrix.png",
                              f"LOFO {family} held out - {model_key}")

    matched_csv = resolve(RANDOM_REPORTS) / spec["random_counterpart"] / \
        "confusion_matrix.csv"
    matched = lofo.matched_baseline_from_confusion(matched_csv, known_labels) \
        if matched_csv.exists() else None

    artifact_sha = None
    artifact_file = None
    if save_model:
        models_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = models_dir / f"{stem}.joblib"
        joblib.dump(model, artifact_path)
        joblib.dump(encoder, models_dir / f"{stem}_label_encoder.joblib")
        if scaler is not None:
            joblib.dump(scaler, models_dir / f"{stem}_scaler.joblib")
        artifact_sha = sha256_of(artifact_path)
        artifact_file = artifact_path.name
        with open(models_dir / f"{stem}_feature_columns.json", "w",
                  encoding="utf-8") as handle:
            json.dump(list(columns), handle, indent=1)

    payload = {
        "schema_version": 1,
        "experiment_type": "lofo",
        "protocol_version": lofo.PROTOCOL_VERSION,
        "taxonomy_version": families.TAXONOMY_VERSION,
        "distinct_from": ("random-v2 (reports/artifact_evaluation) and temporal-v1 "
                          "(reports/temporal_evaluation). Different training partition; "
                          "the canonical test set is reused unchanged."),
        "generated_at": utc_now(),
        "name": stem,
        "model_key": model_key,
        "algorithm": spec["type"],
        "balanced": spec["balanced"],
        "held_out_family": family,
        "member_labels": members,
        "canonical_split": CANONICAL_SPLIT,
        "canonical_base_commit": git_commit(),
        "rows_removed_from_train": removed,
        "train_rows_after_removal": int(len(kept_idx)),
        "balancing_rows_before": balance_report.get("rows_before"),
        "balancing_rows_after": balance_report.get("rows_after"),
        "balancing": balance_report,
        "test_rows": int(len(test_idx)),
        "held_out_family_test_support": int(held_mask.sum()),
        "support_tier": families.support_tier(int(held_mask.sum())),
        "training_labels": known_labels,
        "n_training_labels": len(known_labels),
        "seed": SEED,
        "feature_version": FEATURE_SET,
        "feature_columns": list(columns),
        "n_features": len(columns),
        "model_params": models.serialisable_params(params, SEED),
        "preprocessing_provenance": (
            "family removed from TRAIN only; balancing applied after removal on the "
            "remaining training rows; scaler (when used) fitted on those rows only; "
            "canonical test partition untouched"),
        "scaler_fitted_on": "training rows after family removal" if scaler else None,
        "artifact_file": artifact_file,
        "artifact_sha256": artifact_sha,
        "train_seconds": float(train_seconds),
        "timings": evaluation.build_timings(train_seconds, batch_timing, None),
        "metrics": report,
        "matched_random_v2_baseline": matched,
        "git_commit": git_commit(),
        "library_versions": library_versions(),
    }

    with open(run_reports / "metrics.json", "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1)

    return stem, payload
