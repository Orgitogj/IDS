import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

DEFAULT_DATASET = "datasets/cicids2017_cleaned.parquet"
DEFAULT_REFERENCE = "reports/training_feature_reference.json"
DEFAULT_MODELS_DIR = "models"
DEFAULT_REPORTS_DIR = "reports"
DEFAULT_OUT = "reports/evaluation_random_vs_temporal.json"

REGISTERED_ARTIFACT = "xgb_smote_cicids2017_v1.joblib"
LABEL_ENCODER = "label_encoder_cicids2017.joblib"

BENIGN = "BENIGN"
BENIGN_CAP = 200_000
MIN_SUPPORT_FOR_CLAIM = 100

SPLIT_RANDOM = "random"
SPLIT_TEMPORAL_GLOBAL = "temporal_global"
SPLIT_TEMPORAL_PER_CLASS = "temporal_per_class"

AMBIGUOUS_HOURS = {6, 7}
AFTERNOON_MAX_HOUR = 5


def _clean_label(label):
    return str(label).replace("\x96", "-").strip()


def _report_path(path):
    try:
        return path.relative_to(_ML_SERVICE_ROOT).as_posix()
    except ValueError:
        return str(path)


def parse_cicids_timestamps(values):
    text = pd.Series(list(values), dtype="object").astype(str).str.strip()
    parts = text.str.split(" ", n=1, expand=True)
    if parts.shape[1] < 2:
        raise ValueError("Timestamp-i s'ka pjese ore; pritej 'd/m/YYYY H:MM[:SS]'.")

    date_parts = parts[0].str.split("/", expand=True)
    if date_parts.shape[1] != 3:
        raise ValueError("Data s'ka tre pjese; pritej 'd/m/YYYY'.")

    clock_parts = parts[1].str.split(":", expand=True)
    hour = clock_parts[0].astype("int64")
    minute = clock_parts[1].astype("int64")
    if clock_parts.shape[1] > 2:
        second = clock_parts[2].fillna("0").astype("int64")
    else:
        second = pd.Series(0, index=text.index, dtype="int64")

    observed_hours = set(int(value) for value in pd.unique(hour))
    if not observed_hours.issubset(set(range(1, 13))):
        raise ValueError(
            f"Ore jashte intervalit 1-12: {sorted(observed_hours - set(range(1, 13)))}. "
            "Ora nuk eshte 12-oreshe dhe riparimi AM/PM s'aplikohet.")

    ambiguous = observed_hours & AMBIGUOUS_HOURS
    if ambiguous:
        raise ValueError(
            f"Ore {sorted(ambiguous)} te pranishme: AM/PM s'percaktohet dot qarte "
            "sepse kapja shtrihet 08:00-17:00.")

    hour24 = hour.where(hour > AFTERNOON_MAX_HOUR, hour + 12)

    return pd.to_datetime({
        "year": date_parts[2].astype("int64"),
        "month": date_parts[1].astype("int64"),
        "day": date_parts[0].astype("int64"),
        "hour": hour24,
        "minute": minute,
        "second": second,
    }).to_numpy()


def random_split(labels, test_size, seed):
    return train_test_split(
        np.arange(len(labels)), test_size=test_size, random_state=seed, stratify=labels
    )


def temporal_split(stamps, test_size):
    order = np.argsort(stamps, kind="stable")
    cut = int(round(len(order) * (1.0 - test_size)))
    boundary = stamps[order][cut - 1] if cut else None

    if boundary is not None:
        while cut < len(order) and stamps[order][cut] == boundary:
            cut += 1

    return order[:cut], order[cut:]


def temporal_split_per_class(stamps, labels, test_size, test_counts=None):
    train_parts = []
    test_parts = []

    for name in sorted(set(labels)):
        positions = np.flatnonzero(labels == name)
        order = positions[np.argsort(stamps[positions], kind="stable")]
        if test_counts is None:
            wanted = int(round(len(order) * test_size))
        else:
            wanted = int(test_counts.get(name, 0))
        cut = len(order) - min(wanted, len(order))
        train_parts.append(order[:cut])
        test_parts.append(order[cut:])

    return np.concatenate(train_parts), np.concatenate(test_parts)


def balanced_training_indices(labels, train_idx, seed):
    rng = np.random.default_rng(seed)

    benign = train_idx[labels[train_idx] == BENIGN]
    attacks = train_idx[labels[train_idx] != BENIGN]

    if len(benign) > BENIGN_CAP:
        benign = rng.choice(benign, size=BENIGN_CAP, replace=False)

    selected = np.concatenate([benign, attacks])
    rng.shuffle(selected)
    return selected


def confusion_matrix_frame(y_true, y_pred, classes=None):
    if classes is None:
        classes = sorted(set(y_true) | set(y_pred))

    size = len(classes)
    true_codes = pd.Categorical(y_true, categories=classes).codes
    pred_codes = pd.Categorical(y_pred, categories=classes).codes

    if (true_codes < 0).any() or (pred_codes < 0).any():
        raise ValueError("Etiketa jashte listes se klasave te dhena.")

    counts = np.bincount(true_codes.astype("int64") * size + pred_codes.astype("int64"),
                         minlength=size * size)
    return pd.DataFrame(counts.reshape(size, size), index=list(classes), columns=list(classes))


def per_class_metrics(matrix):
    values = matrix.to_numpy(dtype="int64")
    total = int(values.sum())

    true_positive = np.diag(values).astype("int64")
    support = values.sum(axis=1)
    predicted = values.sum(axis=0)
    false_negative = support - true_positive
    false_positive = predicted - true_positive
    true_negative = total - true_positive - false_negative - false_positive

    def _ratio(numerator, denominator):
        return [float(n) / float(d) if d else None
                for n, d in zip(numerator, denominator)]

    precision = _ratio(true_positive, predicted)
    recall = _ratio(true_positive, support)
    fpr = _ratio(false_positive, false_positive + true_negative)
    fnr = _ratio(false_negative, support)

    rows = {}
    for position, name in enumerate(matrix.index):
        p = precision[position]
        r = recall[position]
        f1 = (2 * p * r / (p + r)) if p and r else 0.0
        rows[name] = {
            "support": int(support[position]),
            "sufficient_support": bool(support[position] >= MIN_SUPPORT_FOR_CLAIM),
            "predicted_count": int(predicted[position]),
            "true_positive": int(true_positive[position]),
            "false_positive": int(false_positive[position]),
            "false_negative": int(false_negative[position]),
            "true_negative": int(true_negative[position]),
            "precision": p,
            "recall": r,
            "f1": f1,
            "fpr": fpr[position],
            "fnr": fnr[position],
        }
    return rows


def overall_metrics(y_true, y_pred, matrix):
    values = matrix.to_numpy(dtype="int64")
    total = int(values.sum())
    correct = int(np.diag(values).sum())

    benign_position = list(matrix.index).index(BENIGN) if BENIGN in matrix.index else None
    binary = None
    if benign_position is not None:
        attack_rows = np.delete(values, benign_position, axis=0)
        benign_row = values[benign_position]
        attacks_total = int(attack_rows.sum())
        benign_total = int(benign_row.sum())
        attack_detected = int(attack_rows.sum()) - int(attack_rows[:, benign_position].sum())
        benign_flagged = benign_total - int(benign_row[benign_position])
        binary = {
            "attack_rows": attacks_total,
            "benign_rows": benign_total,
            "attack_recall": float(attack_detected / attacks_total) if attacks_total else None,
            "benign_false_positive_rate": (
                float(benign_flagged / benign_total) if benign_total else None),
        }

    return {
        "rows": total,
        "accuracy": float(correct / total) if total else None,
        "accuracy_sklearn": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
        "macro_precision": float(
            precision_score(y_true, y_pred, average="macro", zero_division=0)),
        "macro_recall": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
        "binary_benign_vs_attack": binary,
    }


def macro_f1_from_per_class(per_class):
    scores = [row["f1"] for row in per_class.values()]
    return float(np.mean(scores)) if scores else 0.0


def weighted_f1_from_per_class(per_class):
    total = sum(row["support"] for row in per_class.values())
    if not total:
        return 0.0
    return float(sum(row["f1"] * row["support"] for row in per_class.values()) / total)


def save_confusion_matrix_csv(matrix, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    matrix.to_csv(path, index_label="true\\predicted", encoding="utf-8")
    return path


def save_confusion_matrix_png(matrix, path, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm

    values = matrix.to_numpy(dtype="float64")
    labels = list(matrix.index)

    figure, axes = plt.subplots(figsize=(1.05 * len(labels) + 4, 0.85 * len(labels) + 3))
    shown = np.where(values > 0, values, np.nan)
    image = axes.imshow(shown, cmap="Blues", norm=LogNorm(vmin=1, vmax=max(values.max(), 1)))

    axes.set_xticks(range(len(labels)))
    axes.set_yticks(range(len(labels)))
    axes.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    axes.set_yticklabels(labels, fontsize=8)
    axes.set_xlabel("predicted")
    axes.set_ylabel("true")
    axes.set_title(title, fontsize=10)

    threshold = np.nanmax(values) ** 0.5 if np.nanmax(values) else 0
    for row in range(len(labels)):
        for column in range(len(labels)):
            count = int(values[row, column])
            if not count:
                continue
            axes.text(column, row, f"{count:,}", ha="center", va="center", fontsize=6,
                      color="white" if count > threshold else "black")

    figure.colorbar(image, ax=axes, fraction=0.035, pad=0.02, label="flows (log)")
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=150)
    plt.close(figure)
    return path


def train_controlled_model(features, labels, train_idx, seed):
    training_idx = balanced_training_indices(labels, train_idx, seed)
    classes = sorted(set(labels[training_idx]))
    class_to_index = {name: position for position, name in enumerate(classes)}
    y_train = np.array([class_to_index[name] for name in labels[training_idx]])

    model = xgb.XGBClassifier(n_estimators=100, random_state=seed, n_jobs=-1,
                              tree_method="hist", eval_metric="mlogloss")
    model.fit(features[training_idx], y_train)

    return model, classes, training_idx


def score_run(name, split_name, y_true, y_pred, reports_dir, notes=None, extra=None):
    classes = sorted(set(y_true) | set(y_pred))
    matrix = confusion_matrix_frame(y_true, y_pred, classes)
    per_class = per_class_metrics(matrix)
    overall = overall_metrics(y_true, y_pred, matrix)

    csv_path = save_confusion_matrix_csv(
        matrix, reports_dir / f"confusion_matrix_{name}.csv")
    png_path = save_confusion_matrix_png(
        matrix, reports_dir / f"confusion_matrix_{name}.png",
        f"Confusion matrix - {name} ({overall['rows']:,} test flows)")

    insufficient = [label for label, row in per_class.items()
                    if not row["sufficient_support"] and row["support"] > 0]
    absent = [label for label, row in per_class.items() if row["support"] == 0]

    payload = {
        "run": name,
        "split": split_name,
        "notes": notes,
        "overall": overall,
        "macro_f1_from_confusion_matrix": macro_f1_from_per_class(per_class),
        "weighted_f1_from_confusion_matrix": weighted_f1_from_per_class(per_class),
        "min_support_for_claim": MIN_SUPPORT_FOR_CLAIM,
        "insufficient_support_classes": insufficient,
        "absent_from_test_classes": absent,
        "per_class": per_class,
        "confusion_matrix_csv": _report_path(csv_path),
        "confusion_matrix_png": _report_path(png_path),
    }
    if extra:
        payload.update(extra)

    print(f"\n=== {name} ===")
    print(f"  test rows {overall['rows']:,} | accuracy {overall['accuracy']:.4f} | "
          f"macro F1 {overall['macro_f1']:.4f} | weighted F1 {overall['weighted_f1']:.4f}")
    if overall["binary_benign_vs_attack"]:
        binary = overall["binary_benign_vs_attack"]
        print(f"  attack recall {binary['attack_recall']:.4f} | "
              f"benign FPR {binary['benign_false_positive_rate']:.4f}")
    print(f"  {'class':<28}{'support':>9}{'prec':>8}{'recall':>8}{'F1':>8}{'FPR':>10}{'FNR':>8}")
    for label, row in per_class.items():
        if row["support"] == 0:
            flag = "  <- absent from this test set"
        elif not row["sufficient_support"]:
            flag = "  <- insufficient support"
        else:
            flag = ""
        print(f"  {label:<28}{row['support']:>9,}"
              f"{(row['precision'] if row['precision'] is not None else float('nan')):>8.3f}"
              f"{(row['recall'] if row['recall'] is not None else float('nan')):>8.3f}"
              f"{row['f1']:>8.3f}"
              f"{(row['fpr'] if row['fpr'] is not None else float('nan')):>10.5f}"
              f"{(row['fnr'] if row['fnr'] is not None else float('nan')):>8.3f}{flag}")

    return payload


def describe_split(name, stamps, labels, train_idx, test_idx):
    return {
        "name": name,
        "train_rows": int(len(train_idx)),
        "test_rows": int(len(test_idx)),
        "train_first_timestamp": str(stamps[train_idx].min()),
        "train_last_timestamp": str(stamps[train_idx].max()),
        "test_first_timestamp": str(stamps[test_idx].min()),
        "test_last_timestamp": str(stamps[test_idx].max()),
        "train_class_support": {label: int((labels[train_idx] == label).sum())
                                for label in sorted(set(labels))},
        "test_class_support": {label: int((labels[test_idx] == label).sum())
                               for label in sorted(set(labels))},
    }


def timestamp_audit(stamps, source_files):
    audit = {}
    for source in sorted(set(source_files)):
        mask = source_files == source
        window = stamps[mask]
        ordered = np.diff(window) >= np.timedelta64(0, "ns")
        audit[source] = {
            "rows": int(mask.sum()),
            "first": str(window.min()),
            "last": str(window.max()),
            "non_decreasing_in_file_order": float(ordered.mean()) if len(window) > 1 else None,
        }
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Vlereson XGBoost me split random dhe me split kohor, krahas njeri-tjetrit.")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--models-dir", default=DEFAULT_MODELS_DIR)
    parser.add_argument("--reports-dir", default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--feature-set", default="cicids2017-78-v1")
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--skip-registered", action="store_true")
    args = parser.parse_args()

    def _resolve(value):
        path = Path(value)
        return path if path.is_absolute() else _ML_SERVICE_ROOT / path

    dataset_path = _resolve(args.dataset)
    if not dataset_path.exists():
        print(f"Dataset-i s'u gjet: {dataset_path}", file=sys.stderr)
        return 1

    models_dir = _resolve(args.models_dir)
    reports_dir = _resolve(args.reports_dir)

    with open(_resolve(args.reference), encoding="utf-8") as handle:
        reference = json.load(handle)
    feature_columns = reference["feature_sets"][args.feature_set]

    print(f"Duke lexuar {dataset_path.name} ({args.feature_set}, "
          f"{len(feature_columns)} features) ...")
    meta = pd.read_parquet(dataset_path, columns=["Label", "Timestamp", "source_file"])
    labels = meta["Label"].map(_clean_label).to_numpy()
    stamps = parse_cicids_timestamps(meta["Timestamp"])
    source_files = meta["source_file"].to_numpy()
    del meta

    frame = pd.read_parquet(dataset_path, columns=feature_columns)
    features = frame[feature_columns].to_numpy(dtype="float32")
    del frame

    print(f"  {len(labels):,} rreshta | {stamps.min()} .. {stamps.max()}")

    audit = timestamp_audit(stamps, source_files)
    for source, entry in audit.items():
        print(f"  {source[:46]:<46} {entry['first']} .. {entry['last']}")

    random_train, random_test = random_split(labels, args.test_size, args.seed)
    global_train, global_test = temporal_split(stamps, args.test_size)

    random_test_counts = {label: int((labels[random_test] == label).sum())
                          for label in sorted(set(labels))}
    per_class_train, per_class_test = temporal_split_per_class(
        stamps, labels, args.test_size, random_test_counts)

    splits = {
        SPLIT_RANDOM: describe_split(SPLIT_RANDOM, stamps, labels, random_train, random_test),
        SPLIT_TEMPORAL_GLOBAL: describe_split(
            SPLIT_TEMPORAL_GLOBAL, stamps, labels, global_train, global_test),
        SPLIT_TEMPORAL_PER_CLASS: describe_split(
            SPLIT_TEMPORAL_PER_CLASS, stamps, labels, per_class_train, per_class_test),
    }

    runs = []

    if not args.skip_registered:
        artifact_path = models_dir / REGISTERED_ARTIFACT
        encoder_path = models_dir / LABEL_ENCODER
        if artifact_path.exists() and encoder_path.exists():
            print(f"\nDuke vleresuar artefaktin e regjistruar {REGISTERED_ARTIFACT} "
                  "mbi split-in random ...")
            registered = joblib.load(artifact_path)
            encoder = joblib.load(encoder_path)
            encoder_classes = [_clean_label(name) for name in encoder.classes_]

            expected = list(getattr(registered, "feature_names_in_", feature_columns))
            if [str(name) for name in expected] != list(feature_columns):
                print("  KUJDES: rendi i features te artefaktit ndryshon nga feature-set-i; "
                      "vleresimi i artefaktit u anashkalua.", file=sys.stderr)
            else:
                predicted = registered.predict(features[random_test])
                predicted_names = np.array([encoder_classes[index] for index in predicted])
                runs.append(score_run(
                    "registered_artifact_random", SPLIT_RANDOM,
                    labels[random_test], predicted_names, reports_dir,
                    notes="The production artifact xgb_smote_cicids2017_v1, evaluated on the "
                          "same random split it was trained against. This reproduces the "
                          "headline number the project currently reports. It is deliberately "
                          "NOT evaluated on either temporal split: its training rows include "
                          "rows that the temporal splits place in test.",
                    extra={"artifact": REGISTERED_ARTIFACT,
                           "balancing": "undersample_benign_200k_oversample_rare_2k (metadata; "
                                        "not reproducible until P2-1)"}))
        else:
            print(f"\nArtefakti {REGISTERED_ARTIFACT} ose {LABEL_ENCODER} mungon; "
                  "vleresimi i tij u anashkalua.")

    controlled = {
        SPLIT_RANDOM: (random_train, random_test),
        SPLIT_TEMPORAL_GLOBAL: (global_train, global_test),
        SPLIT_TEMPORAL_PER_CLASS: (per_class_train, per_class_test),
    }

    for split_name, (train_idx, test_idx) in controlled.items():
        print(f"\nDuke trajnuar modelin e kontrolluar mbi split-in '{split_name}' "
              f"({len(train_idx):,} rreshta para balancimit) ...")
        model, classes, training_idx = train_controlled_model(
            features, labels, train_idx, args.seed)
        print(f"  trajnuar mbi {len(training_idx):,} rreshta, {len(classes)} klasa")

        predicted = model.predict(features[test_idx])
        predicted_names = np.array([classes[index] for index in predicted])

        runs.append(score_run(
            f"controlled_{split_name}", split_name,
            labels[test_idx], predicted_names, reports_dir,
            notes="Controlled comparison XGBoost: BENIGN capped at 200,000 training rows, "
                  "no SMOTE, identical hyperparameters on every split. Only the split "
                  "differs between these runs, so the difference between them is the "
                  "split effect and nothing else.",
            extra={"training_rows": int(len(training_idx)),
                   "classes_seen_in_training": len(classes),
                   "classes_absent_from_training": sorted(set(labels) - set(classes))}))

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "dataset": dataset_path.name,
        "feature_set": args.feature_set,
        "seed": args.seed,
        "test_size": args.test_size,
        "benign_cap_in_training": BENIGN_CAP,
        "min_support_for_claim": MIN_SUPPORT_FOR_CLAIM,
        "timestamp_repair": "CICIDS2017 stores a 12-hour clock with no AM/PM marker. Hours "
                            "1-5 are the afternoon and become 13-17; hours 8-12 are left as "
                            "they are. Hours 6 and 7 never occur, so the repair is "
                            "unambiguous, and it is rejected at parse time if they do.",
        "protocol": "The same controlled XGBoost recipe is trained and evaluated on three "
                    "splits of the same dataset. 'random' is the split the project already "
                    "uses (test_size=0.2, random_state=42, stratified). 'temporal_global' "
                    "sorts every row by timestamp and takes the last 20% as test. "
                    "'temporal_per_class' takes the last 20% of each class by timestamp, so "
                    "per-class support matches the random split exactly and the only "
                    "difference is which rows land on each side.",
        "timestamp_audit": audit,
        "splits": splits,
        "runs": runs,
    }

    out_path = _resolve(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1)

    print(f"\nU ruajt: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
