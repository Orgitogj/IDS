import numpy as np
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

from training.evaluate import (
    MIN_SUPPORT_FOR_CLAIM,
    confusion_matrix_frame,
    per_class_metrics,
    save_confusion_matrix_csv,
    save_confusion_matrix_png,
)

PROTOCOL_VERSION = "temporal-v1"

CLASS_SET_TEST = "classes_present_in_temporal_test"
CLASS_SET_SEEN = "classes_present_in_both_partitions"
CLASS_SET_UNION = "union_of_train_and_test_classes"
CLASS_SET_SUPPORTED = "test_classes_with_support_at_least_100"

CLASS_SET_NOTES = {
    CLASS_SET_TEST: ("Every class that occurs in the temporal test partition, including "
                     "classes never seen during temporal training. This is the STRICT "
                     "temporal result. Unseen classes are kept, not dropped."),
    CLASS_SET_SEEN: ("Only classes present in BOTH the temporal training and the temporal "
                     "test partition. This is the SEEN-CLASS DIAGNOSTIC: it isolates "
                     "degradation among classes the model actually had a chance to learn. "
                     "It is not a replacement for the strict result."),
    CLASS_SET_UNION: ("Union of temporal train and test classes. Classes with zero test "
                      "support score 0 by construction, so this figure is reported for "
                      "completeness only and should not be used to rank models."),
    CLASS_SET_SUPPORTED: ("Test classes with at least 100 test rows. Sensitivity analysis "
                          "only, mirroring the random-split convention."),
}


def _macro(y_true, y_pred, labels):
    if not labels:
        return {"macro_precision": None, "macro_recall": None, "macro_f1": None}
    return {
        "macro_precision": float(precision_score(y_true, y_pred, labels=labels,
                                                 average="macro", zero_division=0)),
        "macro_recall": float(recall_score(y_true, y_pred, labels=labels,
                                           average="macro", zero_division=0)),
        "macro_f1": float(f1_score(y_true, y_pred, labels=labels, average="macro",
                                   zero_division=0)),
    }


def _restricted_accuracy(y_true, y_pred, labels):
    if not labels:
        return None
    mask = np.isin(y_true, list(labels))
    if not mask.any():
        return None
    return float(accuracy_score(y_true[mask], y_pred[mask]))


def class_sets(train_classes, y_true):
    train_set = set(str(name) for name in train_classes)
    test_set = set(str(name) for name in np.unique(y_true))

    return {
        CLASS_SET_TEST: sorted(test_set),
        CLASS_SET_SEEN: sorted(test_set & train_set),
        CLASS_SET_UNION: sorted(test_set | train_set),
        "classes_only_in_test": sorted(test_set - train_set),
        "classes_only_in_train": sorted(train_set - test_set),
    }


def unseen_report(y_true, train_classes):
    train_set = set(str(name) for name in train_classes)
    unseen = sorted(set(str(name) for name in np.unique(y_true)) - train_set)

    rows = {name: int((y_true == name).sum()) for name in unseen}
    total = int(sum(rows.values()))

    return {
        "unseen_test_classes": unseen,
        "n_unseen_test_classes": len(unseen),
        "unseen_test_rows": total,
        "unseen_rows_per_class": rows,
        "unseen_fraction_of_test": float(total / len(y_true)) if len(y_true) else 0.0,
        "note": ("A class with zero temporal training rows cannot be predicted by the "
                 "classifier. Its recall is 0 by construction. This is an unseen-label "
                 "effect, not evidence about temporal drift among known classes, and it "
                 "is NOT zero-day detection."),
    }


def binary_benign_vs_attack(matrix, benign="BENIGN"):
    labels = list(matrix.index)
    if benign not in labels:
        return None

    values = matrix.to_numpy(dtype="int64")
    position = labels.index(benign)

    attack_rows = np.delete(values, position, axis=0)
    benign_row = values[position]
    attacks_total = int(attack_rows.sum())
    benign_total = int(benign_row.sum())
    attack_detected = attacks_total - int(attack_rows[:, position].sum())
    benign_flagged = benign_total - int(benign_row[position])

    return {
        "attack_rows": attacks_total,
        "benign_rows": benign_total,
        "attack_recall": float(attack_detected / attacks_total) if attacks_total else None,
        "benign_false_positive_rate": (
            float(benign_flagged / benign_total) if benign_total else None),
        "definition": ("benign_false_positive_rate is the fraction of true BENIGN rows "
                       "predicted as some attack class - the same definition the random "
                       "split uses, so the two are comparable. It is NOT the per-class "
                       "BENIGN fpr, which counts non-BENIGN rows predicted as BENIGN."),
    }


def evaluate_temporal(y_true, y_pred, train_classes, reports_dir, run_name,
                      min_support=MIN_SUPPORT_FOR_CLAIM):
    y_true = np.asarray(y_true, dtype=object)
    y_pred = np.asarray(y_pred, dtype=object)

    sets = class_sets(train_classes, y_true)
    matrix = confusion_matrix_frame(y_true, y_pred, sets[CLASS_SET_UNION])
    per_class = per_class_metrics(matrix)

    supported = sorted(name for name in sets[CLASS_SET_TEST]
                       if per_class[name]["support"] >= min_support)

    variants = {}
    for key, labels in ((CLASS_SET_TEST, sets[CLASS_SET_TEST]),
                        (CLASS_SET_SEEN, sets[CLASS_SET_SEEN]),
                        (CLASS_SET_UNION, sets[CLASS_SET_UNION]),
                        (CLASS_SET_SUPPORTED, supported)):
        entry = _macro(y_true, y_pred, labels)
        entry["class_set"] = key
        entry["classes"] = labels
        entry["n_classes"] = len(labels)
        entry["accuracy_over_these_classes"] = _restricted_accuracy(y_true, y_pred, labels)
        entry["note"] = CLASS_SET_NOTES[key]
        variants[key] = entry

    binary = binary_benign_vs_attack(matrix)
    benign_fpr = binary["benign_false_positive_rate"] if binary else None
    benign_row = per_class.get("BENIGN")
    attacks_predicted_as_benign_rate = benign_row["fpr"] if benign_row else None

    csv_path = save_confusion_matrix_csv(matrix, reports_dir / "confusion_matrix.csv")
    png_path = save_confusion_matrix_png(
        matrix, reports_dir / "confusion_matrix.png",
        f"Confusion matrix - {run_name} (temporal, {len(y_true):,} test flows)")

    return {
        "protocol_version": PROTOCOL_VERSION,
        "experiment_type": "temporal",
        "primary_metric": CLASS_SET_TEST,
        "diagnostic_metric": CLASS_SET_SEEN,
        "test_rows": int(len(y_true)),
        "overall_accuracy": float(accuracy_score(y_true, y_pred)),
        "benign_false_positive_rate": benign_fpr,
        "binary_benign_vs_attack": binary,
        "attack_rows_predicted_as_benign_rate": attacks_predicted_as_benign_rate,
        "class_sets": sets,
        "metrics_by_class_set": variants,
        "unseen": unseen_report(y_true, train_classes),
        "per_class": per_class,
        "min_support_for_claim": min_support,
        "insufficient_support_classes": sorted(
            name for name in sets[CLASS_SET_TEST]
            if 0 < per_class[name]["support"] < min_support),
        "confusion_matrix_csv": csv_path.name,
        "confusion_matrix_png": png_path.name,
    }


def strict_macro_f1(report):
    return report["metrics_by_class_set"][CLASS_SET_TEST]["macro_f1"]


def seen_macro_f1(report):
    return report["metrics_by_class_set"][CLASS_SET_SEEN]["macro_f1"]
