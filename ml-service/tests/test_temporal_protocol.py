import json
from pathlib import Path

import numpy as np
import pytest

from training.pipeline import config as config_module
from training.pipeline import data, runner, splitting, temporal

BENIGN = "BENIGN"


def make_stamps(count, start="2017-07-03T09:00:00"):
    return np.array([np.datetime64(start) + np.timedelta64(i, "m")
                     for i in range(count)])


def make_labels(sequence):
    labels = []
    for name, count in sequence:
        labels.extend([name] * count)
    return np.array(labels, dtype=object)


def make_features(labels, seed=0, n_features=5):
    rng = np.random.default_rng(seed)
    names = sorted(set(labels))
    offsets = {name: position * 10.0 for position, name in enumerate(names)}
    base = np.array([offsets[name] for name in labels], dtype="float32")
    return rng.normal(0, 0.4, size=(len(labels), n_features)).astype("float32") \
        + base[:, None]


@pytest.fixture
def chronological():
    labels = make_labels([(BENIGN, 400), ("DoS Hulk", 100), (BENIGN, 300),
                          ("Bot", 60), ("PortScan", 140)])
    stamps = make_stamps(len(labels))
    features = make_features(labels)
    columns = [f"f{i}" for i in range(5)]
    return data.LoadedDataset(features, labels, columns, stamps=stamps,
                             metadata={"name": "synthetic", "subsampled": False})


class TestTemporalSplit:

    def test_the_split_is_deterministic(self, chronological):
        first = splitting.split_indices(chronological, "temporal_global", 0.2, 42)
        second = splitting.split_indices(chronological, "temporal_global", 0.2, 42)

        np.testing.assert_array_equal(first[0], second[0])
        np.testing.assert_array_equal(first[1], second[1])

    def test_the_split_ignores_the_seed(self, chronological):
        first = splitting.split_indices(chronological, "temporal_global", 0.2, 42)
        second = splitting.split_indices(chronological, "temporal_global", 0.2, 999)

        np.testing.assert_array_equal(first[0], second[0])
        np.testing.assert_array_equal(first[1], second[1])

    def test_chronology_is_never_violated(self, chronological):
        train_idx, test_idx = splitting.split_indices(
            chronological, "temporal_global", 0.2, 42)

        assert chronological.stamps[train_idx].max() <= chronological.stamps[test_idx].min()

    def test_the_partitions_are_disjoint_and_complete(self, chronological):
        train_idx, test_idx = splitting.split_indices(
            chronological, "temporal_global", 0.2, 42)

        assert splitting.assert_disjoint(train_idx, test_idx)
        assert len(train_idx) + len(test_idx) == len(chronological.labels)

    def test_the_test_partition_is_the_later_traffic(self, chronological):
        train_idx, test_idx = splitting.split_indices(
            chronological, "temporal_global", 0.2, 42)

        assert test_idx.min() > train_idx.max()

    def test_a_temporal_strategy_without_timestamps_is_refused(self):
        labels = make_labels([(BENIGN, 50)])
        dataset = data.LoadedDataset(make_features(labels), labels, ["f0"], stamps=None)

        with pytest.raises(splitting.SplitError, match="timestamp"):
            splitting.split_indices(dataset, "temporal_global", 0.2, 42)

    def test_the_split_description_records_both_periods(self, chronological):
        train_idx, test_idx = splitting.split_indices(
            chronological, "temporal_global", 0.2, 42)
        described = splitting.describe(chronological, train_idx, test_idx,
                                       "temporal_global", 0.2)

        assert described["strategy"] == "temporal_global"
        assert described["train_last_timestamp"] <= described["test_first_timestamp"]
        assert described["classes_absent_from_train"]


class TestUnseenClassAccounting:

    def test_unseen_classes_are_identified(self):
        y_true = np.array([BENIGN] * 10 + ["PortScan"] * 5, dtype=object)
        report = temporal.unseen_report(y_true, [BENIGN, "DoS Hulk"])

        assert report["unseen_test_classes"] == ["PortScan"]
        assert report["unseen_test_rows"] == 5
        assert report["unseen_fraction_of_test"] == pytest.approx(5 / 15)

    def test_nothing_is_unseen_when_training_covered_everything(self):
        y_true = np.array([BENIGN] * 10, dtype=object)
        report = temporal.unseen_report(y_true, [BENIGN, "Bot"])

        assert report["unseen_test_classes"] == []
        assert report["unseen_fraction_of_test"] == 0.0

    def test_the_unseen_note_refuses_the_zero_day_framing(self):
        report = temporal.unseen_report(np.array([BENIGN], dtype=object), [BENIGN])
        assert "NOT zero-day detection" in report["note"]

    def test_class_sets_are_partitioned_correctly(self):
        y_true = np.array([BENIGN] * 5 + ["PortScan"] * 3, dtype=object)
        sets = temporal.class_sets([BENIGN, "DoS Hulk"], y_true)

        assert sets[temporal.CLASS_SET_TEST] == [BENIGN, "PortScan"]
        assert sets[temporal.CLASS_SET_SEEN] == [BENIGN]
        assert sets[temporal.CLASS_SET_UNION] == [BENIGN, "DoS Hulk", "PortScan"]
        assert sets["classes_only_in_test"] == ["PortScan"]
        assert sets["classes_only_in_train"] == ["DoS Hulk"]


class TestTemporalMetrics:

    @pytest.fixture
    def scored(self, tmp_path):
        y_true = np.array([BENIGN] * 8 + ["Bot"] * 4 + ["PortScan"] * 4, dtype=object)
        y_pred = np.array([BENIGN] * 8 + ["Bot"] * 3 + [BENIGN] * 1 + [BENIGN] * 4,
                          dtype=object)
        return temporal.evaluate_temporal(
            y_true, y_pred, [BENIGN, "Bot", "DoS Hulk"], tmp_path, "demo")

    def test_the_strict_metric_keeps_unseen_classes(self, scored):
        strict = scored["metrics_by_class_set"][temporal.CLASS_SET_TEST]

        assert strict["classes"] == [BENIGN, "Bot", "PortScan"]
        assert strict["n_classes"] == 3
        assert "not dropped" in strict["note"]

    def test_the_seen_diagnostic_covers_only_shared_classes(self, scored):
        seen = scored["metrics_by_class_set"][temporal.CLASS_SET_SEEN]

        assert seen["classes"] == [BENIGN, "Bot"]
        assert seen["macro_f1"] > scored["metrics_by_class_set"][
            temporal.CLASS_SET_TEST]["macro_f1"]

    def test_an_unseen_class_scores_zero_recall(self, scored):
        assert scored["per_class"]["PortScan"]["recall"] == 0.0
        assert scored["unseen"]["unseen_test_classes"] == ["PortScan"]

    def test_the_union_set_is_reported_but_flagged_as_unrankable(self, scored):
        union = scored["metrics_by_class_set"][temporal.CLASS_SET_UNION]

        assert "DoS Hulk" in union["classes"]
        assert "should not be used to rank" in union["note"]

    def test_every_class_set_declares_what_it_covers(self, scored):
        for key, entry in scored["metrics_by_class_set"].items():
            assert entry["class_set"] == key
            assert entry["note"]
            assert entry["n_classes"] == len(entry["classes"])

    def test_the_primary_metric_is_the_strict_one(self, scored):
        assert scored["primary_metric"] == temporal.CLASS_SET_TEST
        assert scored["diagnostic_metric"] == temporal.CLASS_SET_SEEN
        assert temporal.strict_macro_f1(scored) == scored["metrics_by_class_set"][
            temporal.CLASS_SET_TEST]["macro_f1"]

    def test_benign_false_positive_rate_is_reported(self, scored):
        assert scored["benign_false_positive_rate"] is not None

    def test_confusion_matrix_files_are_written(self, scored, tmp_path):
        assert (tmp_path / "confusion_matrix.csv").exists()
        assert (tmp_path / "confusion_matrix.png").exists()

    def test_the_protocol_version_is_recorded(self, scored):
        assert scored["protocol_version"] == "temporal-v1"
        assert scored["experiment_type"] == "temporal"


class TestTemporalLeakageControls:

    def base_config(self, tmp_path, columns, **overrides):
        payload = {
            "name": "temporal-test-run",
            "seed": 42,
            "features": {"columns": list(columns)},
            "split": {"strategy": "temporal_global", "test_size": 0.2},
            "balancing": {"benign_cap": 300, "rare_class_min": 60},
            "model": {"type": "xgboost", "params": {"n_estimators": 5}},
            "output": {
                "models_dir": str(tmp_path / "models"),
                "reports_dir": str(tmp_path / "reports"),
                "artifact_name": "temporal_test_artifact",
            },
        }
        payload.update(overrides)
        return config_module.from_dict(payload)

    def stub(self, monkeypatch, dataset):
        monkeypatch.setattr(runner.data, "load_feature_columns",
                            lambda config: list(dataset.feature_columns))
        monkeypatch.setattr(runner.data, "load_dataset", lambda *a, **k: dataset)

    def test_balancing_only_ever_sees_the_temporal_training_partition(
            self, tmp_path, monkeypatch, chronological):
        self.stub(monkeypatch, chronological)
        seen = {}

        original = runner.balancing.balance_training_set

        def spy(features, labels, train_idx, settings, seed):
            seen["max_train_stamp"] = chronological.stamps[train_idx].max()
            seen["rows"] = len(train_idx)
            return original(features, labels, train_idx, settings, seed)

        monkeypatch.setattr(runner.balancing, "balance_training_set", spy)
        runner.run(self.base_config(tmp_path, chronological.feature_columns),
                   save=False, verbose=False)

        train_idx, test_idx = splitting.split_indices(
            chronological, "temporal_global", 0.2, 42)
        assert seen["rows"] == len(train_idx)
        assert seen["max_train_stamp"] <= chronological.stamps[test_idx].min()

    def test_the_scaler_never_sees_temporal_test_rows(self, tmp_path, monkeypatch,
                                                      chronological):
        self.stub(monkeypatch, chronological)
        seen = {}

        real_builder = runner.models.build_scaler

        def spying(model_type):
            scaler = real_builder(model_type)
            if scaler is None:
                return None
            original_fit = scaler.fit_transform

            def fit_transform(X, *args, **kwargs):
                seen["rows"] = len(X)
                return original_fit(X, *args, **kwargs)

            scaler.fit_transform = fit_transform
            return scaler

        monkeypatch.setattr(runner.models, "build_scaler", spying)

        config = self.base_config(
            tmp_path, chronological.feature_columns,
            model={"type": "mlp", "params": {"max_iter": 5, "hidden_layer_sizes": [8]}})
        result = runner.run(config, save=False, verbose=False)

        assert seen["rows"] == result.balancing["rows_after"]
        assert seen["rows"] < len(chronological.labels)

    def test_no_synthetic_row_reaches_the_temporal_test_partition(
            self, tmp_path, monkeypatch, chronological):
        self.stub(monkeypatch, chronological)
        snapshot = chronological.features.copy()

        result = runner.run(self.base_config(tmp_path, chronological.feature_columns),
                            save=False, verbose=False)

        np.testing.assert_array_equal(chronological.features, snapshot)
        assert result.bundle["split"]["test_rows"] == 200
        assert result.bundle["split"]["train_rows"] == 800
        assert result.balancing["rows_after"] != result.bundle["split"]["train_rows"]

    def test_the_temporal_test_support_is_untouched_by_balancing(
            self, tmp_path, monkeypatch, chronological):
        self.stub(monkeypatch, chronological)
        result = runner.run(self.base_config(tmp_path, chronological.feature_columns),
                            save=False, verbose=False)

        train_idx, test_idx = splitting.split_indices(
            chronological, "temporal_global", 0.2, 42)
        expected = {name: int((chronological.labels[test_idx] == name).sum())
                    for name in sorted(set(chronological.labels))}

        assert result.bundle["split"]["test_class_support"] == expected

    def test_the_run_records_the_temporal_strategy(self, tmp_path, monkeypatch,
                                                   chronological):
        self.stub(monkeypatch, chronological)
        result = runner.run(self.base_config(tmp_path, chronological.feature_columns),
                            save=False, verbose=False)

        assert result.bundle["split"]["strategy"] == "temporal_global"
        assert result.bundle["split"]["train_last_timestamp"] <= \
            result.bundle["split"]["test_first_timestamp"]


class TestNamespaceIsolation:

    def test_temporal_configs_write_outside_the_random_v2_namespace(self):
        config_dir = Path(__file__).resolve().parent.parent / "training" / "configs"
        temporal_dir = config_dir / "temporal"
        assert temporal_dir.exists()

        for path in sorted(temporal_dir.glob("*.yaml")):
            config = config_module.load(path)
            reports = config.output["reports_dir"].replace("\\", "/")
            assert "temporal" in reports
            assert reports != "reports/training"
            assert config.artifact_name.endswith("_temporal_v1")
            assert config.split["strategy"] == "temporal_global"

    def test_temporal_artifact_names_never_collide_with_random_v2(self):
        config_dir = Path(__file__).resolve().parent.parent / "training" / "configs"

        random_names = {config_module.load(path).name
                        for path in sorted(config_dir.glob("*.yaml"))}
        temporal_names = {config_module.load(path).name
                          for path in sorted((config_dir / "temporal").glob("*.yaml"))}

        assert random_names.isdisjoint(temporal_names)

        random_artifacts = {config_module.load(path).artifact_name
                            for path in sorted(config_dir.glob("*.yaml"))}
        temporal_artifacts = {config_module.load(path).artifact_name
                              for path in sorted((config_dir / "temporal").glob("*.yaml"))}

        assert random_artifacts.isdisjoint(temporal_artifacts)

    def test_every_temporal_config_name_is_unique(self):
        config_dir = Path(__file__).resolve().parent.parent / "training" / "configs"
        names = [config_module.load(path).name
                 for path in sorted((config_dir / "temporal").glob("*.yaml"))]

        assert len(names) == len(set(names))
        assert len(names) == 6


@pytest.mark.dataset
class TestAgainstTheRealChronology:

    def test_the_audit_report_matches_the_dataset(self):
        report_path = (Path(__file__).resolve().parent.parent / "reports"
                       / "temporal_evaluation" / "temporal_audit.json")
        if not report_path.exists():
            pytest.skip("temporal_audit.json mungon; xhiro training.temporal_audit")

        with open(report_path, encoding="utf-8") as handle:
            audit = json.load(handle)

        assert audit["timestamp_is_a_feature"] is False
        assert audit["partition"]["chronology_respected"] is True
        assert audit["dataset"]["rows"] == 2_827_876
        assert set(audit["partition"]["classes_only_in_test"]) == {"DDoS", "PortScan"}
        assert audit["partition"]["unseen_test_fraction"] > 0.5

    def test_the_canonical_random_reports_are_untouched(self):
        reports = Path(__file__).resolve().parent.parent / "reports"
        canonical = reports / "artifact_evaluation" / "index.json"
        if not canonical.exists():
            pytest.skip("index.json i random-v2 mungon")

        with open(canonical, encoding="utf-8") as handle:
            index = json.load(handle)

        names = [record["registry_name"] for record in index["artifacts"]]
        assert not any("temporal" in name for name in names)
