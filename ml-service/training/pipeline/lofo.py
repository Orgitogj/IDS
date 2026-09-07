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
