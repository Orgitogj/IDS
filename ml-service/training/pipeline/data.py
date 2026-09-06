import json

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from training.build_feature_reference import sha256_of
from training.evaluate import _clean_label, parse_cicids_timestamps


class DatasetError(RuntimeError):
    pass


class LoadedDataset:
    def __init__(self, features, labels, feature_columns, stamps=None, metadata=None):
        self.features = features
        self.labels = labels
        self.feature_columns = list(feature_columns)
        self.stamps = stamps
        self.metadata = metadata or {}

    def __len__(self):
        return len(self.labels)

    @property
    def class_counts(self):
        names, counts = np.unique(self.labels, return_counts=True)
        return {str(name): int(count) for name, count in zip(names, counts)}


def clean_labels(values):
    return np.array([_clean_label(value) for value in values], dtype=object)


def load_feature_columns(config):
    explicit = config.features.get("columns")
    if explicit:
        return [str(name) for name in explicit]

    reference_path = config.reference_path
    if not reference_path.exists():
        raise DatasetError(
            f"Referenca e features s'u gjet: {reference_path}. "
            "Xhiro 'python -m training.build_feature_reference' ose cakto features.columns.")

    with open(reference_path, encoding="utf-8") as handle:
        reference = json.load(handle)

    feature_set = config.features["feature_set"]
    feature_sets = reference.get("feature_sets", {})
    if feature_set not in feature_sets:
        raise DatasetError(
            f"Feature set '{feature_set}' s'ekziston ne {reference_path.name}. "
            f"Te disponueshme: {', '.join(sorted(feature_sets))}.")

    return [str(name) for name in feature_sets[feature_set]]


DEFAULT_MIN_CLASS_ROWS = 10


def stratified_subset(labels, sample_rows, seed, min_class_rows=DEFAULT_MIN_CLASS_ROWS):
    total = len(labels)
    if sample_rows is None or sample_rows >= total:
        return np.arange(total), {"applied": False}

    rng = np.random.default_rng(seed)
    ratio = sample_rows / total

    kept = []
    floored = []
    for name in sorted(set(labels)):
        positions = np.flatnonzero(labels == name)
        proportional = int(round(len(positions) * ratio))
        wanted = min(len(positions), max(min_class_rows, proportional))
        if wanted > proportional:
            floored.append(name)
        picks = rng.choice(positions, size=wanted, replace=False)
        kept.append(picks)

    indices = np.sort(np.concatenate(kept))

    return indices, {
        "applied": True,
        "requested_rows": int(sample_rows),
        "selected_rows": int(len(indices)),
        "min_class_rows": int(min_class_rows),
        "classes_raised_to_the_floor": floored,
        "note": "Stratified subsample with a per-class floor so that rare classes survive "
                "the split and SMOTE. Class proportions are NOT those of the full dataset, "
                "so metrics from a subsampled run are a smoke test only.",
    }


def load_dataset(config, feature_columns, sample_rows=None, needs_timestamps=False,
                 min_class_rows=DEFAULT_MIN_CLASS_ROWS):
    dataset_path = config.dataset_path
    if not dataset_path.exists():
        raise DatasetError(
            f"Dataset-i s'u gjet: {dataset_path}. "
            "Vendos cicids2017_cleaned.parquet ne datasets/ ose ndrysho dataset.path.")

    label_column = config.dataset["label_column"]
    timestamp_column = config.dataset["timestamp_column"]

    meta_columns = [label_column]
    if needs_timestamps:
        meta_columns.append(timestamp_column)

    meta = pd.read_parquet(dataset_path, columns=meta_columns)
    labels = clean_labels(meta[label_column].to_numpy())
    total_rows = len(labels)

    keep, subsample_report = stratified_subset(
        labels, sample_rows, config.seed, min_class_rows)
    subsampled = len(keep) < total_rows

    stamps = None
    if needs_timestamps:
        stamps = parse_cicids_timestamps(meta[timestamp_column])[keep]

    labels = labels[keep]
    del meta

    frame = pd.read_parquet(dataset_path, columns=feature_columns)
    missing = [name for name in feature_columns if name not in frame.columns]
    if missing:
        raise DatasetError(
            f"{len(missing)} features mungojne ne dataset: {', '.join(missing[:5])}")

    features = frame[feature_columns].to_numpy(dtype="float32")[keep]
    del frame

    metadata = {
        "name": dataset_path.name,
        "sha256": sha256_of(dataset_path),
        "rows_in_file": int(total_rows),
        "rows_used": int(len(keep)),
        "subsampled": bool(subsampled),
        "sample_rows_requested": int(sample_rows) if sample_rows is not None else None,
        "subsample": subsample_report,
        "label_column": label_column,
        "n_features": len(feature_columns),
    }

    return LoadedDataset(features, labels, feature_columns, stamps=stamps, metadata=metadata)
