import numpy as np

from training.evaluate import random_split, temporal_split, temporal_split_per_class

STRATEGY_RANDOM = "random"
STRATEGY_TEMPORAL_GLOBAL = "temporal_global"
STRATEGY_TEMPORAL_PER_CLASS = "temporal_per_class"


class SplitError(RuntimeError):
    pass


def split_indices(dataset, strategy, test_size, seed):
    if strategy == STRATEGY_RANDOM:
        train_idx, test_idx = random_split(dataset.labels, test_size, seed)
        return np.sort(train_idx), np.sort(test_idx)

    if dataset.stamps is None:
        raise SplitError(
            f"Strategjia '{strategy}' kerkon timestamp-e; ngarko dataset-in me "
            "needs_timestamps=True.")

    if strategy == STRATEGY_TEMPORAL_GLOBAL:
        train_idx, test_idx = temporal_split(dataset.stamps, test_size)
        return np.sort(train_idx), np.sort(test_idx)

    if strategy == STRATEGY_TEMPORAL_PER_CLASS:
        train_idx, test_idx = temporal_split_per_class(
            dataset.stamps, dataset.labels, test_size)
        return np.sort(train_idx), np.sort(test_idx)

    raise SplitError(f"Strategji e panjohur split-i: {strategy}")


def describe(dataset, train_idx, test_idx, strategy, test_size):
    labels = dataset.labels
    classes = sorted(set(labels))

    description = {
        "strategy": strategy,
        "test_size": float(test_size),
        "train_rows": int(len(train_idx)),
        "test_rows": int(len(test_idx)),
        "train_class_support": {name: int((labels[train_idx] == name).sum())
                                for name in classes},
        "test_class_support": {name: int((labels[test_idx] == name).sum())
                               for name in classes},
        "classes_absent_from_train": [name for name in classes
                                      if not (labels[train_idx] == name).any()],
        "classes_absent_from_test": [name for name in classes
                                     if not (labels[test_idx] == name).any()],
    }

    if dataset.stamps is not None:
        description["train_first_timestamp"] = str(dataset.stamps[train_idx].min())
        description["train_last_timestamp"] = str(dataset.stamps[train_idx].max())
        description["test_first_timestamp"] = str(dataset.stamps[test_idx].min())
        description["test_last_timestamp"] = str(dataset.stamps[test_idx].max())

    return description


def assert_disjoint(train_idx, test_idx):
    overlap = np.intersect1d(train_idx, test_idx)
    if overlap.size:
        raise SplitError(
            f"{overlap.size} rreshta ndodhen njekohesisht ne train dhe ne test.")
    return True
