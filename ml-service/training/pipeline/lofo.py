import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

from training.evaluate import confusion_matrix_frame, per_class_metrics
from training.pipeline import families

PROTOCOL_VERSION = "lofo-v1"
BENIGN = families.BENIGN

BENIGN_FPR_DEFINITION = (
    "fraction of true BENIGN rows predicted as some attack class - identical to the "
    "definition used by random-v2 (overall_metrics.binary_benign_vs_attack) and by the "
    "corrected temporal evaluation. It is NOT the per-class BENIGN fpr and NOT "
    "attack_rows_predicted_as_benign_rate.")


class LofoError(RuntimeError):
    pass


def remove_family_from_train(labels, train_idx, member_labels):
    labels = np.asarray(labels, dtype=object)
    train_idx = np.asarray(train_idx)

    mask = ~np.isin(labels[train_idx], list(member_labels))
    kept = train_idx[mask]
    removed = int(len(train_idx) - len(kept))

    remaining = np.isin(labels[kept], list(member_labels)).sum()
    if remaining:
        raise LofoError(
            f"{remaining} rreshta te familjes se hequr mbeten ne train pas filtrimit.")

    return kept, removed


def assert_absent_after_balancing(balanced_labels, member_labels):
    present = int(np.isin(np.asarray(balanced_labels, dtype=object),
                          list(member_labels)).sum())
    if present:
        raise LofoError(
            f"{present} rreshta te familjes se hequr u shfaqen pas balancimit. SMOTE ose "
            "undersampling po prek familjen e mbajtur jashte.")
    return True


def detection_report(y_true_held, y_pred_held):
    y_pred_held = np.asarray(y_pred_held, dtype=object)
    support = int(len(y_pred_held))

    if not support:
        return {"held_out_support": 0, "note": "no held-out rows in the canonical test set"}

    predicted_benign = int((y_pred_held == BENIGN).sum())
    predicted_attack = support - predicted_benign

    return {
        "held_out_support": support,
        "predicted_attack_count": predicted_attack,
        "predicted_benign_count": predicted_benign,
        "attack_detection_rate": float(predicted_attack / support),
        "attack_miss_rate": float(predicted_benign / support),
        "definition": ("attack_detection_rate is the fraction of held-out-family rows "
                       "predicted as ANY non-BENIGN class. It says the traffic was "
                       "flagged as malicious; it says nothing about whether the label "
                       "was correct. Attribution is reported separately."),
    }


def attribution_report(y_pred_held):
    y_pred_held = np.asarray(y_pred_held, dtype=object)
    attack_predictions = y_pred_held[y_pred_held != BENIGN]

    if not len(attack_predictions):
        return {
            "attack_predictions": 0,
            "predicted_label_distribution": {},
            "predicted_family_distribution": {},
            "dominant_predicted_label": None,
            "dominant_predicted_family": None,
            "note": "no held-out row was predicted as an attack",
        }

    labels, counts = np.unique(attack_predictions, return_counts=True)
    label_distribution = {str(name): int(count) for name, count in zip(labels, counts)}

    family_distribution = {}
    for name, count in label_distribution.items():
        family = families.family_of(name) or "unmapped"
        family_distribution[family] = family_distribution.get(family, 0) + count

    dominant_label = max(label_distribution.items(), key=lambda item: item[1])
    dominant_family = max(family_distribution.items(), key=lambda item: item[1])

    return {
        "attack_predictions": int(len(attack_predictions)),
        "predicted_label_distribution": dict(sorted(
            label_distribution.items(), key=lambda item: -item[1])),
        "predicted_family_distribution": dict(sorted(
            family_distribution.items(), key=lambda item: -item[1])),
        "dominant_predicted_label": dominant_label[0],
        "dominant_predicted_label_share": float(dominant_label[1] / len(attack_predictions)),
        "dominant_predicted_family": dominant_family[0],
        "dominant_predicted_family_share": float(
            dominant_family[1] / len(attack_predictions)),
        "note": ("These are the labels the model assigned to held-out traffic it flagged "
                 "as malicious. A dominant label here is a misattribution, not a correct "
                 "detection of that class."),
    }


def binary_diagnostic(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=object)
    y_pred = np.asarray(y_pred, dtype=object)

    true_attack = y_true != BENIGN
    pred_attack = y_pred != BENIGN

    true_positive = int((true_attack & pred_attack).sum())
    false_positive = int((~true_attack & pred_attack).sum())
    false_negative = int((true_attack & ~pred_attack).sum())
    true_negative = int((~true_attack & ~pred_attack).sum())

    benign_rows = true_negative + false_positive
    attack_rows = true_positive + false_negative

    precision = true_positive / (true_positive + false_positive) \
        if (true_positive + false_positive) else None
    recall = true_positive / attack_rows if attack_rows else None
    f1 = (2 * precision * recall / (precision + recall)) \
        if precision and recall else 0.0

    return {
        "binary_accuracy": float((true_positive + true_negative) / len(y_true)),
        "attack_precision": float(precision) if precision is not None else None,
        "attack_recall": float(recall) if recall is not None else None,
        "attack_f1": float(f1),
        "benign_false_positive_rate": (
            float(false_positive / benign_rows) if benign_rows else None),
        "attack_false_negative_rate": (
            float(false_negative / attack_rows) if attack_rows else None),
        "attack_rows_predicted_as_benign_rate": (
            float(false_negative / attack_rows) if attack_rows else None),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "true_negative": true_negative,
        "benign_rows": benign_rows,
        "attack_rows": attack_rows,
        "benign_fpr_definition": BENIGN_FPR_DEFINITION,
    }


def known_class_metrics(y_true, y_pred, known_labels):
    y_true = np.asarray(y_true, dtype=object)
    y_pred = np.asarray(y_pred, dtype=object)
    known = sorted(str(name) for name in known_labels)

    mask = np.isin(y_true, known)
    if not mask.any():
        return {"classes": known, "n_classes": len(known), "rows": 0}

    subset_true = y_true[mask]
    subset_pred = y_pred[mask]

    return {
        "classes": known,
        "n_classes": len(known),
        "rows": int(mask.sum()),
        "macro_f1": float(f1_score(y_true, y_pred, labels=known, average="macro",
                                   zero_division=0)),
        "macro_precision": float(precision_score(y_true, y_pred, labels=known,
                                                 average="macro", zero_division=0)),
        "macro_recall": float(recall_score(y_true, y_pred, labels=known,
                                           average="macro", zero_division=0)),
        "accuracy_over_known_rows": float(accuracy_score(subset_true, subset_pred)),
        "note": ("Computed over test rows whose true label was still represented in "
                 "training after the family was removed. BENIGN is included."),
    }


def matched_baseline_from_confusion(csv_path, known_labels):
    frame = pd.read_csv(csv_path, index_col=0)
    frame.index = [str(name) for name in frame.index]
    frame.columns = [str(name) for name in frame.columns]

    known = [name for name in sorted(str(n) for n in known_labels) if name in frame.index]
    if not known:
        return None

    per_class = per_class_metrics(frame)

    scores = [per_class[name]["f1"] for name in known]
    precisions = [per_class[name]["precision"] or 0.0 for name in known]
    recalls = [per_class[name]["recall"] or 0.0 for name in known]

    true_positive = sum(per_class[name]["true_positive"] for name in known)
    support = sum(per_class[name]["support"] for name in known)

    values = frame.to_numpy(dtype="int64")
    labels = list(frame.index)
    benign_position = labels.index(BENIGN) if BENIGN in labels else None
    benign_fpr = None
    if benign_position is not None:
        benign_row = values[benign_position]
        benign_total = int(benign_row.sum())
        benign_flagged = benign_total - int(benign_row[benign_position])
        benign_fpr = float(benign_flagged / benign_total) if benign_total else None

    return {
        "source": str(csv_path.name),
        "classes": known,
        "n_classes": len(known),
        "macro_f1": float(np.mean(scores)) if scores else None,
        "macro_precision": float(np.mean(precisions)) if precisions else None,
        "macro_recall": float(np.mean(recalls)) if recalls else None,
        "accuracy_over_known_rows": float(true_positive / support) if support else None,
        "benign_false_positive_rate_full_test": benign_fpr,
        "note": ("Recomputed from the frozen random-v2 confusion matrix over exactly the "
                 "class subset that survived family removal, so the comparison is "
                 "like-for-like. The random-v2 report itself is not modified."),
    }


def fold_report(family, member_labels, y_true, y_pred, known_labels, held_mask):
    held_true = np.asarray(y_true, dtype=object)[held_mask]
    held_pred = np.asarray(y_pred, dtype=object)[held_mask]

    classes = sorted(set(np.asarray(y_true, dtype=object)) |
                     set(np.asarray(y_pred, dtype=object)))
    matrix = confusion_matrix_frame(y_true, y_pred, classes)

    return {
        "protocol_version": PROTOCOL_VERSION,
        "experiment_type": "lofo",
        "taxonomy_version": families.TAXONOMY_VERSION,
        "held_out_family": family,
        "member_labels": list(member_labels),
        "primary_metric": "attack_detection_rate",
        "detection": detection_report(held_true, held_pred),
        "attribution": attribution_report(held_pred),
        "binary": binary_diagnostic(y_true, y_pred),
        "known_class": known_class_metrics(y_true, y_pred, known_labels),
        "per_class": per_class_metrics(matrix),
        "confusion_matrix": matrix,
    }
