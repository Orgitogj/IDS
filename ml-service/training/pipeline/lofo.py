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
