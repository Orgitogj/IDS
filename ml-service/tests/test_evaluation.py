import numpy as np
import pandas as pd
import pytest

from training.evaluate import (
    MIN_SUPPORT_FOR_CLAIM,
    confusion_matrix_frame,
    macro_f1_from_per_class,
    overall_metrics,
    parse_cicids_timestamps,
    per_class_metrics,
    random_split,
    save_confusion_matrix_csv,
    save_confusion_matrix_png,
    temporal_split,
    temporal_split_per_class,
    weighted_f1_from_per_class,
)

NOTEBOOK_RANDOM_ACCURACY = 0.9988
NOTEBOOK_RANDOM_MACRO_F1 = 0.8785
NOTEBOOK_RANDOM_MACRO_PRECISION = 0.8671
NOTEBOOK_RANDOM_MACRO_RECALL = 0.8978

RANDOM_SPLIT_TEST_SUPPORT = {
    "BENIGN": 454265,
    "Bot": 391,
    "DDoS": 25605,
    "DoS GoldenEye": 2059,
    "DoS Hulk": 46025,
    "DoS Slowhttptest": 1100,
    "DoS slowloris": 1159,
    "FTP-Patator": 1587,
    "Heartbleed": 2,
    "Infiltration": 7,
    "PortScan": 31761,
    "SSH-Patator": 1180,
    "Web Attack - Brute Force": 301,
    "Web Attack - Sql Injection": 4,
    "Web Attack - XSS": 130,
}

INSUFFICIENT_SUPPORT_CLASSES = ["Heartbleed", "Infiltration", "Web Attack - Sql Injection"]


def test_the_afternoon_hours_are_shifted_and_the_morning_hours_are_not():
    stamps = parse_cicids_timestamps([
        "3/7/2017 8:55:58",
        "3/7/2017 11:00:00",
        "3/7/2017 12:30:00",
        "3/7/2017 1:00:00",
        "3/7/2017 5:02:00",
    ])
    hours = pd.DatetimeIndex(stamps).hour.tolist()
    assert hours == [8, 11, 12, 13, 17]


def test_timestamps_without_seconds_parse_to_the_same_minute():
    with_seconds = parse_cicids_timestamps(["7/7/2017 3:30:00"])
    without_seconds = parse_cicids_timestamps(["7/7/2017 3:30"])
    assert with_seconds[0] == without_seconds[0]


def test_the_day_month_order_is_day_first():
    stamps = parse_cicids_timestamps(["7/7/2017 9:00", "03/07/2017 9:00"])
    assert pd.DatetimeIndex(stamps).day.tolist() == [7, 3]
    assert pd.DatetimeIndex(stamps).month.tolist() == [7, 7]


def test_an_ambiguous_hour_is_rejected_rather_than_guessed():
    with pytest.raises(ValueError, match="AM/PM"):
        parse_cicids_timestamps(["3/7/2017 6:00", "3/7/2017 9:00"])

    with pytest.raises(ValueError, match="AM/PM"):
        parse_cicids_timestamps(["3/7/2017 7:30"])


def test_an_hour_outside_a_twelve_hour_clock_is_rejected():
    with pytest.raises(ValueError, match="12-oreshe"):
        parse_cicids_timestamps(["3/7/2017 22:00"])


def test_the_temporal_split_puts_every_test_row_after_every_train_row():
    stamps = parse_cicids_timestamps([f"3/7/2017 9:{minute:02d}" for minute in range(50)])
    train_idx, test_idx = temporal_split(stamps, 0.2)

    assert len(train_idx) + len(test_idx) == 50
    assert stamps[train_idx].max() < stamps[test_idx].min()


def test_the_temporal_split_never_puts_the_same_timestamp_on_both_sides():
    stamps = parse_cicids_timestamps(["3/7/2017 9:00"] * 30 + ["3/7/2017 9:01"] * 10)
    train_idx, test_idx = temporal_split(stamps, 0.5)

    assert set(stamps[train_idx]).isdisjoint(set(stamps[test_idx]))
    assert len(train_idx) == 30


def test_the_temporal_split_is_not_the_random_split():
    stamps = parse_cicids_timestamps([f"3/7/2017 9:{minute:02d}" for minute in range(60)])
    labels = np.array(["BENIGN"] * 30 + ["DoS Hulk"] * 30)

    _, temporal_test = temporal_split(stamps, 0.2)
    _, random_test = random_split(labels, 0.2, 42)

    assert set(temporal_test) != set(random_test)


def test_the_per_class_temporal_split_keeps_the_latest_rows_of_every_class():
    stamps = parse_cicids_timestamps(
        [f"3/7/2017 9:{minute:02d}" for minute in range(10)]
        + [f"3/7/2017 10:{minute:02d}" for minute in range(10)]
    )
    labels = np.array(["BENIGN"] * 10 + ["PortScan"] * 10)

    train_idx, test_idx = temporal_split_per_class(stamps, labels, 0.2)

    assert sorted(test_idx.tolist()) == [8, 9, 18, 19]
    assert len(train_idx) == 16


def test_the_per_class_temporal_split_honours_requested_support():
    stamps = parse_cicids_timestamps([f"3/7/2017 9:{minute:02d}" for minute in range(20)])
    labels = np.array(["BENIGN"] * 12 + ["Bot"] * 8)

    _, test_idx = temporal_split_per_class(stamps, labels, 0.2, {"BENIGN": 5, "Bot": 3})

    assert (labels[test_idx] == "BENIGN").sum() == 5
    assert (labels[test_idx] == "Bot").sum() == 3


def test_the_per_class_temporal_split_matches_the_random_split_support():
    stamps = parse_cicids_timestamps([f"3/7/2017 9:{minute:02d}" for minute in range(60)])
    labels = np.array(["BENIGN"] * 40 + ["DDoS"] * 15 + ["Bot"] * 5)

    _, random_test = random_split(labels, 0.2, 42)
    counts = {name: int((labels[random_test] == name).sum()) for name in set(labels)}
    _, temporal_test = temporal_split_per_class(stamps, labels, 0.2, counts)

    for name in set(labels):
        assert (labels[temporal_test] == name).sum() == counts[name]


def test_the_random_split_is_reproducible_for_a_fixed_seed():
    labels = np.array(["BENIGN"] * 80 + ["PortScan"] * 20)
    first = random_split(labels, 0.2, 42)
    second = random_split(labels, 0.2, 42)

    assert np.array_equal(first[0], second[0])
    assert np.array_equal(first[1], second[1])


def test_the_confusion_matrix_counts_every_row_once():
    y_true = np.array(["BENIGN", "BENIGN", "PortScan", "PortScan", "DDoS"])
    y_pred = np.array(["BENIGN", "PortScan", "PortScan", "BENIGN", "DDoS"])

    matrix = confusion_matrix_frame(y_true, y_pred)

    assert matrix.to_numpy().sum() == 5
    assert list(matrix.index) == ["BENIGN", "DDoS", "PortScan"]
    assert matrix.loc["BENIGN", "PortScan"] == 1
    assert matrix.loc["PortScan", "BENIGN"] == 1
    assert matrix.loc["DDoS", "DDoS"] == 1


def test_the_confusion_matrix_rejects_a_label_outside_the_class_list():
    with pytest.raises(ValueError):
        confusion_matrix_frame(np.array(["BENIGN"]), np.array(["Bot"]), ["BENIGN"])


def test_per_class_metrics_match_a_hand_computed_example():
    matrix = pd.DataFrame(
        [[90, 10], [20, 80]],
        index=["BENIGN", "PortScan"],
        columns=["BENIGN", "PortScan"],
    )
    rows = per_class_metrics(matrix)

    assert rows["PortScan"]["support"] == 100
    assert rows["PortScan"]["true_positive"] == 80
    assert rows["PortScan"]["false_negative"] == 20
    assert rows["PortScan"]["false_positive"] == 10
    assert rows["PortScan"]["true_negative"] == 90
    assert rows["PortScan"]["precision"] == pytest.approx(80 / 90)
    assert rows["PortScan"]["recall"] == pytest.approx(0.80)
    assert rows["PortScan"]["fpr"] == pytest.approx(10 / 100)
    assert rows["PortScan"]["fnr"] == pytest.approx(0.20)


def test_every_per_class_row_carries_its_own_support():
    y_true = np.array(["BENIGN"] * 200 + ["Heartbleed"] * 2)
    y_pred = np.array(["BENIGN"] * 200 + ["Heartbleed"] * 2)
    rows = per_class_metrics(confusion_matrix_frame(y_true, y_pred))

    assert set(rows["BENIGN"]) >= {"support", "precision", "recall", "f1", "fpr", "fnr"}
    assert rows["BENIGN"]["support"] == 200
    assert rows["Heartbleed"]["support"] == 2


def test_a_class_below_the_support_floor_is_flagged_rather_than_scored_silently():
    y_true = np.array(["BENIGN"] * 500 + ["Heartbleed"] * 2)
    y_pred = np.array(["BENIGN"] * 500 + ["Heartbleed"] * 2)
    rows = per_class_metrics(confusion_matrix_frame(y_true, y_pred))

    assert MIN_SUPPORT_FOR_CLAIM == 100
    assert rows["BENIGN"]["sufficient_support"] is True
    assert rows["Heartbleed"]["sufficient_support"] is False
    assert rows["Heartbleed"]["f1"] == 1.0


def test_a_class_the_model_never_predicts_scores_zero_rather_than_crashing():
    y_true = np.array(["BENIGN"] * 10 + ["PortScan"] * 5)
    y_pred = np.array(["BENIGN"] * 15)
    rows = per_class_metrics(confusion_matrix_frame(y_true, y_pred))

    assert rows["PortScan"]["precision"] is None
    assert rows["PortScan"]["recall"] == 0.0
    assert rows["PortScan"]["f1"] == 0.0
    assert rows["PortScan"]["fnr"] == 1.0


def test_the_macro_and_weighted_f1_agree_with_the_confusion_matrix():
    rng = np.random.default_rng(7)
    classes = ["BENIGN", "DoS Hulk", "PortScan", "Bot"]
    y_true = rng.choice(classes, 4000, p=[0.8, 0.1, 0.08, 0.02])
    y_pred = np.where(rng.random(4000) < 0.85, y_true, rng.choice(classes, 4000))

    matrix = confusion_matrix_frame(y_true, y_pred)
    rows = per_class_metrics(matrix)
    overall = overall_metrics(y_true, y_pred, matrix)

    assert overall["macro_f1"] == pytest.approx(macro_f1_from_per_class(rows))
    assert overall["weighted_f1"] == pytest.approx(weighted_f1_from_per_class(rows))
    assert overall["accuracy"] == pytest.approx(overall["accuracy_sklearn"])


def test_the_binary_view_counts_attacks_called_benign_as_missed():
    y_true = np.array(["BENIGN"] * 100 + ["PortScan"] * 10)
    y_pred = np.array(["BENIGN"] * 95 + ["PortScan"] * 5 + ["BENIGN"] * 4 + ["PortScan"] * 6)

    overall = overall_metrics(y_true, y_pred, confusion_matrix_frame(y_true, y_pred))
    binary = overall["binary_benign_vs_attack"]

    assert binary["benign_rows"] == 100
    assert binary["attack_rows"] == 10
    assert binary["attack_recall"] == pytest.approx(0.6)
    assert binary["benign_false_positive_rate"] == pytest.approx(0.05)


def test_the_confusion_matrix_is_written_as_csv_and_png(tmp_path):
    y_true = np.array(["BENIGN"] * 20 + ["PortScan"] * 5)
    y_pred = np.array(["BENIGN"] * 19 + ["PortScan"] * 6)
    matrix = confusion_matrix_frame(y_true, y_pred)

    csv_path = save_confusion_matrix_csv(matrix, tmp_path / "cm.csv")
    png_path = save_confusion_matrix_png(matrix, tmp_path / "cm.png", "test")

    assert csv_path.exists() and png_path.exists()
    assert png_path.stat().st_size > 0

    restored = pd.read_csv(csv_path, index_col=0)
    assert restored.to_numpy().tolist() == matrix.to_numpy().tolist()
    assert list(restored.columns) == list(matrix.columns)


@pytest.mark.report
def test_the_random_split_still_holds_the_support_the_audit_recorded(evaluation_report):
    support = evaluation_report["splits"]["random"]["test_class_support"]
    assert support == RANDOM_SPLIT_TEST_SUPPORT
    assert evaluation_report["splits"]["random"]["test_rows"] == 565_576


@pytest.mark.report
def test_the_registered_artifact_still_reproduces_the_notebook_numbers(evaluation_report):
    runs = {run["run"]: run for run in evaluation_report["runs"]}
    if "registered_artifact_random" not in runs:
        pytest.skip("artefakti i regjistruar s'u vleresua ne kete raport")

    overall = runs["registered_artifact_random"]["overall"]
    assert round(overall["accuracy"], 4) == NOTEBOOK_RANDOM_ACCURACY
    assert round(overall["macro_f1"], 4) == NOTEBOOK_RANDOM_MACRO_F1
    assert round(overall["macro_precision"], 4) == NOTEBOOK_RANDOM_MACRO_PRECISION
    assert round(overall["macro_recall"], 4) == NOTEBOOK_RANDOM_MACRO_RECALL


@pytest.mark.report
def test_the_random_split_per_class_support_is_unchanged_in_every_run(evaluation_report):
    for run in evaluation_report["runs"]:
        if run["split"] != "random":
            continue
        for label, expected in RANDOM_SPLIT_TEST_SUPPORT.items():
            assert run["per_class"][label]["support"] == expected, run["run"]


@pytest.mark.report
def test_the_three_minority_classes_are_reported_as_insufficient_support(evaluation_report):
    for run in evaluation_report["runs"]:
        if run["split"] != "random":
            continue
        for label in INSUFFICIENT_SUPPORT_CLASSES:
            assert run["per_class"][label]["sufficient_support"] is False, run["run"]
            assert label in run["insufficient_support_classes"], run["run"]


@pytest.mark.report
def test_the_temporal_splits_are_reported_alongside_the_random_split(evaluation_report):
    splits = evaluation_report["splits"]
    assert set(splits) == {"random", "temporal_global", "temporal_per_class"}

    runs = {run["run"] for run in evaluation_report["runs"]}
    assert {"controlled_random", "controlled_temporal_global",
            "controlled_temporal_per_class"} <= runs


@pytest.mark.report
def test_the_temporal_per_class_split_holds_the_random_split_support(evaluation_report):
    assert (evaluation_report["splits"]["temporal_per_class"]["test_class_support"]
            == RANDOM_SPLIT_TEST_SUPPORT)


@pytest.mark.report
def test_the_global_temporal_split_leaves_the_last_day_untouched_by_training(evaluation_report):
    split = evaluation_report["splits"]["temporal_global"]
    assert split["train_last_timestamp"] < split["test_first_timestamp"]
