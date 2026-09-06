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

from training.build_feature_reference import sha256_of
from training.evaluate import parse_cicids_timestamps
from training.pipeline.data import clean_labels

DEFAULT_DATASET = "datasets/cicids2017_cleaned.parquet"
DEFAULT_REFERENCE = "reports/training_feature_reference.json"
DEFAULT_OUT = "reports/temporal_evaluation/temporal_audit.json"

DEFAULT_TEST_SIZE = 0.2
DUPLICATE_SAMPLE_COLUMNS = 78

CHRONOLOGY_SOURCE = (
    "The 'Timestamp' column of the cleaned parquet, repaired from CICIDS2017's 12-hour "
    "clock by training.evaluate.parse_cicids_timestamps. Hours 1-5 become 13-17; hours "
    "8-12 are left alone; the parser raises if 6 or 7 ever appears, which they do not. "
    "'source_file' is retained as an independent corroboration of the day, and is never "
    "used to order rows.")


def resolve(value):
    path = Path(value)
    return path if path.is_absolute() else _ML_SERVICE_ROOT / path


def describe_sources(stamps, labels, sources):
    entries = {}
    for name in sorted(set(sources)):
        mask = sources == name
        window = stamps[mask]
        day_labels = labels[mask]
        counts = {}
        for label in sorted(set(day_labels)):
            counts[label] = int((day_labels == label).sum())

        ordered = np.diff(window) >= np.timedelta64(0, "ns")
        entries[name] = {
            "rows": int(mask.sum()),
            "first_timestamp": str(window.min()),
            "last_timestamp": str(window.max()),
            "non_decreasing_in_file_order": (
                float(ordered.mean()) if len(window) > 1 else None),
            "class_counts": counts,
            "classes": sorted(counts),
        }
    return entries


def class_windows(stamps, labels):
    windows = {}
    for label in sorted(set(labels)):
        mask = labels == label
        window = stamps[mask]
        windows[label] = {
            "rows": int(mask.sum()),
            "first_occurrence": str(window.min()),
            "last_occurrence": str(window.max()),
        }
    return windows


def global_cutoff(stamps, test_size):
    order = np.argsort(stamps, kind="stable")
    cut = int(round(len(order) * (1.0 - test_size)))
    boundary = stamps[order][cut - 1] if cut else None

    if boundary is not None:
        while cut < len(order) and stamps[order][cut] == boundary:
            cut += 1

    train_idx = np.sort(order[:cut])
    test_idx = np.sort(order[cut:])
    return train_idx, test_idx, boundary


def partition_report(stamps, labels, train_idx, test_idx):
    train_labels = labels[train_idx]
    test_labels = labels[test_idx]

    train_classes = sorted(set(train_labels))
    test_classes = sorted(set(test_labels))
    both = sorted(set(train_classes) & set(test_classes))
    only_train = sorted(set(train_classes) - set(test_classes))
    only_test = sorted(set(test_classes) - set(train_classes))

    unseen_rows = int(sum((test_labels == label).sum() for label in only_test))

    return {
        "train_rows": int(len(train_idx)),
        "test_rows": int(len(test_idx)),
        "test_fraction": float(len(test_idx) / (len(train_idx) + len(test_idx))),
        "train_first_timestamp": str(stamps[train_idx].min()),
        "train_last_timestamp": str(stamps[train_idx].max()),
        "test_first_timestamp": str(stamps[test_idx].min()),
        "test_last_timestamp": str(stamps[test_idx].max()),
        "chronology_respected": bool(stamps[train_idx].max() <= stamps[test_idx].min()),
        "train_classes": train_classes,
        "test_classes": test_classes,
        "classes_in_both": both,
        "classes_only_in_train": only_train,
        "classes_only_in_test": only_test,
        "n_train_classes": len(train_classes),
        "n_test_classes": len(test_classes),
        "n_unseen_test_classes": len(only_test),
        "unseen_test_rows": unseen_rows,
        "unseen_test_fraction": (
            float(unseen_rows / len(test_idx)) if len(test_idx) else 0.0),
        "train_class_support": {label: int((train_labels == label).sum())
                                for label in sorted(set(labels))},
        "test_class_support": {label: int((test_labels == label).sum())
                               for label in sorted(set(labels))},
    }


def duplicate_analysis(dataset_path, feature_columns, labels, train_idx, test_idx):
    frame = pd.read_parquet(dataset_path, columns=feature_columns)
    digest = pd.util.hash_pandas_object(frame, index=False).to_numpy()
    del frame

    membership = np.zeros(len(digest), dtype=np.int8)
    membership[train_idx] = 1
    membership[test_idx] = 2

    order = np.argsort(digest, kind="stable")
    sorted_digest = digest[order]
    sorted_membership = membership[order]

    group_start = np.flatnonzero(
        np.concatenate(([True], sorted_digest[1:] != sorted_digest[:-1])))
    group_end = np.concatenate((group_start[1:], [len(sorted_digest)]))

    straddling = 0
    straddling_rows = 0
    duplicate_groups = 0
    for start, end in zip(group_start, group_end):
        if end - start < 2:
            continue
        duplicate_groups += 1
        block = sorted_membership[start:end]
        if (block == 1).any() and (block == 2).any():
            straddling += 1
            straddling_rows += int(end - start)

    unique_rows = int(len(group_start))
    return {
        "method": ("64-bit pandas row hash over the feature columns only (labels and "
                   "metadata excluded). Collisions are possible in principle and would "
                   "over-report, so this is an upper bound on duplication."),
        "total_rows": int(len(digest)),
        "unique_feature_rows": unique_rows,
        "duplicate_rate": float(1.0 - unique_rows / len(digest)),
        "duplicate_groups": duplicate_groups,
        "groups_straddling_the_cutoff": straddling,
        "rows_in_straddling_groups": straddling_rows,
        "straddling_fraction_of_dataset": float(straddling_rows / len(digest)),
        "interpretation": (
            "A duplicate group that straddles the cutoff means an identical feature "
            "vector appears both before and after the boundary. Under a chronological "
            "split this is not preprocessing leakage - the rows are genuinely distinct "
            "flows that happen to be identical - but it does mean the test set is not "
            "fully novel with respect to training, and the figure belongs in the "
            "limitations."),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Auditon kronologjine e CICIDS2017 perpara ndarjes kohore.")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--test-size", type=float, default=DEFAULT_TEST_SIZE)
    parser.add_argument("--skip-duplicates", action="store_true")
    args = parser.parse_args()

    dataset_path = resolve(args.dataset)
    with open(resolve(args.reference), encoding="utf-8") as handle:
        reference = json.load(handle)
    feature_columns = list(reference["feature_sets"]["cicids2017-78-v1"])

    print(f"Duke lexuar {dataset_path.name} ...")
    meta = pd.read_parquet(dataset_path, columns=["Label", "Timestamp", "source_file"])
    labels = clean_labels(meta["Label"].to_numpy())
    stamps = parse_cicids_timestamps(meta["Timestamp"])
    sources = meta["source_file"].to_numpy()
    del meta

    print(f"  {len(labels):,} rreshta | {stamps.min()} .. {stamps.max()}")

    sources_report = describe_sources(stamps, labels, sources)
    windows = class_windows(stamps, labels)
    train_idx, test_idx, boundary = global_cutoff(stamps, args.test_size)
    partition = partition_report(stamps, labels, train_idx, test_idx)

    print(f"\nPrerja globale kronologjike ({args.test_size:.0%} test):")
    print(f"  boundary            : {boundary}")
    print(f"  train / test        : {partition['train_rows']:,} / {partition['test_rows']:,}"
          f"  ({partition['test_fraction']:.1%} test)")
    print(f"  kronologjia ruhet   : {partition['chronology_respected']}")
    print(f"  klasa ne train/test : {partition['n_train_classes']} / "
          f"{partition['n_test_classes']}")
    print(f"  klasa vetem ne test : {partition['n_unseen_test_classes']} "
          f"{partition['classes_only_in_test']}")
    print(f"  rreshta te paparë   : {partition['unseen_test_rows']:,} "
          f"({partition['unseen_test_fraction']:.1%} e test-it)")

    duplicates = None
    if not args.skip_duplicates:
        print("\nDuke analizuar dublikatat mbi kufirin ...")
        duplicates = duplicate_analysis(dataset_path, feature_columns, labels,
                                        train_idx, test_idx)
        print(f"  rreshta unike       : {duplicates['unique_feature_rows']:,} "
              f"({duplicates['duplicate_rate']:.2%} dublikate)")
        print(f"  grupe qe kalojne kufirin: {duplicates['groups_straddling_the_cutoff']:,}"
              f"  ({duplicates['straddling_fraction_of_dataset']:.2%} e rreshtave)")

    payload = {
        "schema_version": 1,
        "experiment_type": "temporal",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "dataset": {
            "name": dataset_path.name,
            "sha256": sha256_of(dataset_path),
            "rows": int(len(labels)),
        },
        "chronology_source": CHRONOLOGY_SOURCE,
        "timestamp_is_a_feature": "Timestamp" in feature_columns,
        "identifier_columns_excluded_from_features": [
            name for name in ("Flow ID", "Source IP", "Source Port", "Destination IP",
                              "Timestamp", "Label", "source_file")
            if name not in feature_columns],
        "dataset_first_timestamp": str(stamps.min()),
        "dataset_last_timestamp": str(stamps.max()),
        "sources": sources_report,
        "class_windows": windows,
        "proposed_cutoff": {
            "strategy": "global_chronological",
            "test_size": float(args.test_size),
            "boundary_timestamp": str(boundary),
            "rule": ("Sort every row by repaired timestamp, take the last test_size as "
                     "test, then extend the cut forward so that no single timestamp "
                     "value is split across the boundary."),
        },
        "partition": partition,
        "duplicates": duplicates,
    }

    out_path = resolve(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1)

    print(f"\nU ruajt: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
