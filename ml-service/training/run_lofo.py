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
