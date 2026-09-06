import json

import numpy as np
import pytest

from training.pipeline import artifacts, balancing, config as config_module, data, models
from training.pipeline import runner, splitting

BENIGN = "BENIGN"

RECOVERED_BALANCED_ROWS = 653_897
RECOVERED_TRAIN_ROWS = 2_262_300


def make_labels(counts):
    labels = []
    for name, count in counts.items():
        labels.extend([name] * count)
    return np.array(labels, dtype=object)


def make_features(labels, seed=0, n_features=6):
    rng = np.random.default_rng(seed)
    names = sorted(set(labels))
    offsets = {name: position * 10.0 for position, name in enumerate(names)}
    base = np.array([offsets[name] for name in labels], dtype="float32")
    noise = rng.normal(0, 0.5, size=(len(labels), n_features)).astype("float32")
    return noise + base[:, None]


@pytest.fixture
def synthetic():
    counts = {BENIGN: 4000, "DoS Hulk": 800, "PortScan": 600, "Bot": 40, "Heartbleed": 12}
    labels = make_labels(counts)
    features = make_features(labels)
    return features, labels


@pytest.fixture
def synthetic_balancing():
    return {
        "enabled": True,
        "benign_label": BENIGN,
        "benign_cap": 1000,
        "rare_class_min": 200,
        "oversampler": "smote",
        "smote_k_neighbors": 5,
    }


def base_config(tmp_path, **overrides):
    payload = {
        "name": "test-run",
        "seed": 42,
        "features": {"columns": [f"f{i}" for i in range(6)]},
        "split": {"strategy": "random", "test_size": 0.2},
        "balancing": {"benign_cap": 1000, "rare_class_min": 200},
        "model": {"type": "xgboost", "params": {"n_estimators": 5}},
        "output": {
            "models_dir": str(tmp_path / "models"),
            "reports_dir": str(tmp_path / "reports"),
            "artifact_name": "test_artifact",
        },
    }
    payload.update(overrides)
    return config_module.from_dict(payload)


def stub_dataset(monkeypatch, features, labels, columns, metadata=None):
    monkeypatch.setattr(runner.data, "load_feature_columns", lambda config: columns)
    monkeypatch.setattr(
        runner.data, "load_dataset",
        lambda *a, **k: data.LoadedDataset(
            features, labels, columns,
            metadata=metadata or {"name": "synthetic", "subsampled": False}))


class TestBalancingPlan:

    def test_benign_is_capped_and_rare_classes_are_raised(self):
        counts = {BENIGN: 5000, "DoS Hulk": 900, "Bot": 40}
        plan = balancing.plan_targets(counts, BENIGN, benign_cap=1000, rare_class_min=200)

        assert plan[BENIGN]["target"] == 1000
        assert plan[BENIGN]["method"] == balancing.METHOD_UNDERSAMPLED
        assert plan["DoS Hulk"]["target"] == 900
        assert plan["DoS Hulk"]["method"] == balancing.METHOD_UNCHANGED
        assert plan["Bot"]["target"] == 200
        assert plan["Bot"]["method"] == balancing.METHOD_SMOTE

    def test_benign_below_the_cap_is_left_alone(self):
        plan = balancing.plan_targets({BENIGN: 500}, BENIGN, benign_cap=1000,
                                      rare_class_min=200)
        assert plan[BENIGN]["target"] == 500
        assert plan[BENIGN]["method"] == balancing.METHOD_UNCHANGED

    def test_benign_is_never_oversampled_by_the_rare_class_rule(self):
        plan = balancing.plan_targets({BENIGN: 50, "Bot": 40}, BENIGN, benign_cap=1000,
                                      rare_class_min=200)
        assert plan[BENIGN]["target"] == 50
        assert plan["Bot"]["target"] == 200

    def test_disabled_caps_produce_no_change(self):
        counts = {BENIGN: 5000, "Bot": 40}
        plan = balancing.plan_targets(counts, BENIGN, benign_cap=None, rare_class_min=None)
        assert balancing.planned_total(plan) == 5040

    def test_the_recovered_cicids2017_recipe_totals_653897(self):
        train_counts = {
            "BENIGN": 1_817_055, "DoS Hulk": 184_099, "PortScan": 127_043, "DDoS": 102_420,
            "DoS GoldenEye": 8_234, "FTP-Patator": 6_348, "SSH-Patator": 4_717,
            "DoS slowloris": 4_637, "DoS Slowhttptest": 4_399, "Bot": 1_565,
            "Web Attack - Brute Force": 1_206, "Web Attack - XSS": 522,
            "Infiltration": 29, "Web Attack - Sql Injection": 17, "Heartbleed": 9,
        }
        assert sum(train_counts.values()) == RECOVERED_TRAIN_ROWS

        plan = balancing.plan_targets(train_counts, BENIGN, benign_cap=200_000,
                                      rare_class_min=2_000)
        assert balancing.planned_total(plan) == RECOVERED_BALANCED_ROWS

    def test_k_neighbours_shrinks_for_tiny_classes(self):
        plan = balancing.plan_targets({BENIGN: 100, "Bot": 3}, BENIGN, None, 200)
        assert balancing.resolve_k_neighbors(plan, 5) == 2

    def test_k_neighbours_is_none_when_nothing_is_oversampled(self):
        plan = balancing.plan_targets({BENIGN: 100}, BENIGN, None, None)
        assert balancing.resolve_k_neighbors(plan, 5) is None


class TestBalancingExecution:

    def test_counts_match_the_plan_exactly(self, synthetic, synthetic_balancing):
        features, labels = synthetic
        train_idx = np.arange(len(labels))

        X, y, report = balancing.balance_training_set(
            features, labels, train_idx, synthetic_balancing, seed=42)

        assert len(X) == len(y) == report["rows_after"]
        assert report["rows_after"] == report["planned_total"]
        for name, entry in report["plan"].items():
            assert report["class_counts_after"][name] == entry["target"]

    def test_benign_is_undersampled_to_the_cap(self, synthetic, synthetic_balancing):
        features, labels = synthetic
        _, _, report = balancing.balance_training_set(
            features, labels, np.arange(len(labels)), synthetic_balancing, seed=42)

        assert report["class_counts_after"][BENIGN] == 1000
        assert report["plan"][BENIGN]["method"] == balancing.METHOD_UNDERSAMPLED

    def test_synthetic_rows_are_counted(self, synthetic, synthetic_balancing):
        features, labels = synthetic
        _, _, report = balancing.balance_training_set(
            features, labels, np.arange(len(labels)), synthetic_balancing, seed=42)

        expected = (200 - 40) + (200 - 12)
        assert report["synthetic_rows"] == expected

    def test_the_same_seed_reproduces_the_same_arrays(self, synthetic,
                                                      synthetic_balancing):
        features, labels = synthetic
        train_idx = np.arange(len(labels))

        first_X, first_y, _ = balancing.balance_training_set(
            features, labels, train_idx, synthetic_balancing, seed=42)
        second_X, second_y, _ = balancing.balance_training_set(
            features, labels, train_idx, synthetic_balancing, seed=42)

        np.testing.assert_array_equal(first_X, second_X)
        np.testing.assert_array_equal(first_y, second_y)

    def test_a_different_seed_changes_the_arrays(self, synthetic, synthetic_balancing):
        features, labels = synthetic
        train_idx = np.arange(len(labels))

        first_X, _, first_report = balancing.balance_training_set(
            features, labels, train_idx, synthetic_balancing, seed=42)
        second_X, _, second_report = balancing.balance_training_set(
            features, labels, train_idx, synthetic_balancing, seed=7)

        assert first_report["class_counts_after"] == second_report["class_counts_after"]
        assert not np.array_equal(first_X, second_X)

    def test_disabled_balancing_returns_the_training_rows_untouched(self, synthetic):
        features, labels = synthetic
        train_idx = np.arange(0, len(labels), 3)

        X, y, report = balancing.balance_training_set(
            features, labels, train_idx, {"enabled": False}, seed=42)

        np.testing.assert_array_equal(X, features[train_idx])
        np.testing.assert_array_equal(y, labels[train_idx])
        assert report["enabled"] is False

    def test_oversampler_none_undersamples_without_synthesising(self, synthetic,
                                                                synthetic_balancing):
        features, labels = synthetic
        settings = dict(synthetic_balancing, oversampler="none")

        _, _, report = balancing.balance_training_set(
            features, labels, np.arange(len(labels)), settings, seed=42)

        assert report["synthetic_rows"] == 0
        assert report["class_counts_after"]["Heartbleed"] == 12
        assert report["class_counts_after"][BENIGN] == 1000

    def test_a_single_row_class_is_replicated_instead_of_smoted(self):
        labels = make_labels({BENIGN: 300, "Bot": 1})
        features = make_features(labels)
        settings = {"enabled": True, "benign_label": BENIGN, "benign_cap": 100,
                    "rare_class_min": 20, "oversampler": "smote", "smote_k_neighbors": 5}

        _, _, report = balancing.balance_training_set(
            features, labels, np.arange(len(labels)), settings, seed=42)

        assert report["replicated_classes"] == ["Bot"]
        assert report["class_counts_after"]["Bot"] == 20


class TestLeakage:

    def test_balancing_only_ever_reads_training_rows(self, synthetic,
                                                     synthetic_balancing):
        features, labels = synthetic
        train_idx = np.arange(0, 3000)

        _, _, report = balancing.balance_training_set(
            features, labels, train_idx, synthetic_balancing, seed=42)

        assert report["rows_before"] == len(train_idx)
        assert set(report["class_counts_before"]) <= set(labels[train_idx])

    def test_the_split_is_disjoint(self, synthetic):
        features, labels = synthetic
        dataset = data.LoadedDataset(features, labels, [f"f{i}" for i in range(6)])

        train_idx, test_idx = splitting.split_indices(dataset, "random", 0.2, 42)

        assert splitting.assert_disjoint(train_idx, test_idx)
        assert len(train_idx) + len(test_idx) == len(labels)

    def test_the_test_set_keeps_its_natural_distribution(self, synthetic):
        features, labels = synthetic
        dataset = data.LoadedDataset(features, labels, [f"f{i}" for i in range(6)])
        _, test_idx = splitting.split_indices(dataset, "random", 0.2, 42)

        before = {name: int((labels == name).sum()) for name in sorted(set(labels))}
        after = {name: int((labels[test_idx] == name).sum()) for name in sorted(set(labels))}

        for name, count in before.items():
            assert after[name] == pytest.approx(count * 0.2, rel=0.15, abs=2)

    def test_a_pipeline_run_does_not_mutate_the_source_rows(self, tmp_path, monkeypatch,
                                                            synthetic):
        features, labels = synthetic
        columns = [f"f{i}" for i in range(6)]
        snapshot = features.copy()

        stub_dataset(monkeypatch, features, labels, columns)
        runner.run(base_config(tmp_path), save=False, verbose=False)

        np.testing.assert_array_equal(features, snapshot)

    def test_the_scaler_never_sees_the_test_rows(self, tmp_path, monkeypatch, synthetic):
        features, labels = synthetic
        columns = [f"f{i}" for i in range(6)]
        seen = {}

        stub_dataset(monkeypatch, features, labels, columns)

        real_scaler = models.build_scaler

        def spying_scaler(model_type):
            scaler = real_scaler(model_type)
            if scaler is None:
                return None
            original_fit = scaler.fit_transform

            def fit_transform(X, *args, **kwargs):
                seen["rows"] = len(X)
                return original_fit(X, *args, **kwargs)

            scaler.fit_transform = fit_transform
            return scaler

        monkeypatch.setattr(runner.models, "build_scaler", spying_scaler)

        config = base_config(tmp_path, model={
            "type": "mlp", "params": {"max_iter": 5, "hidden_layer_sizes": [8]}})
        result = runner.run(config, save=False, verbose=False)

        assert seen["rows"] == result.balancing["rows_after"]
        assert seen["rows"] < len(labels)


class TestFeatureOrder:

    def test_the_feature_set_is_read_from_the_reference_in_order(self, tmp_path):
        reference = {"feature_sets": {"demo-v1": ["b", "a", "c"]}}
        reference_path = tmp_path / "reference.json"
        reference_path.write_text(json.dumps(reference), encoding="utf-8")

        config = base_config(tmp_path, features={
            "reference": str(reference_path), "feature_set": "demo-v1", "columns": None})

        assert data.load_feature_columns(config) == ["b", "a", "c"]

    def test_an_unknown_feature_set_is_reported_clearly(self, tmp_path):
        reference_path = tmp_path / "reference.json"
        reference_path.write_text(json.dumps({"feature_sets": {"demo-v1": ["a"]}}),
                                  encoding="utf-8")
        config = base_config(tmp_path, features={
            "reference": str(reference_path), "feature_set": "missing-v9", "columns": None})

        with pytest.raises(data.DatasetError, match="missing-v9"):
            data.load_feature_columns(config)

    def test_explicit_columns_win_over_the_reference(self, tmp_path):
        config = base_config(tmp_path, features={
            "reference": "does/not/exist.json", "feature_set": "demo",
            "columns": ["x", "y"]})
        assert data.load_feature_columns(config) == ["x", "y"]

    def test_the_saved_feature_order_matches_the_configured_order(self, tmp_path,
                                                                  monkeypatch, synthetic):
        features, labels = synthetic
        columns = [f"f{i}" for i in range(6)]

        stub_dataset(monkeypatch, features, labels, columns)
        result = runner.run(base_config(tmp_path), verbose=False)

        assert result.bundle["feature_columns"] == columns
        saved = json.loads(result.paths["feature_columns"].read_text(encoding="utf-8"))
        assert saved == columns


class TestSubsampling:

    def test_no_subsample_returns_every_row(self, synthetic):
        _, labels = synthetic
        indices, report = data.stratified_subset(labels, None, seed=42)

        assert len(indices) == len(labels)
        assert report["applied"] is False

    def test_a_request_larger_than_the_dataset_returns_every_row(self, synthetic):
        _, labels = synthetic
        indices, report = data.stratified_subset(labels, 10 ** 9, seed=42)

        assert len(indices) == len(labels)
        assert report["applied"] is False

    def test_rare_classes_survive_the_floor(self, synthetic):
        _, labels = synthetic
        indices, report = data.stratified_subset(labels, 500, seed=42, min_class_rows=10)
        kept = labels[indices]

        for name in sorted(set(labels)):
            assert (kept == name).sum() >= min(10, int((labels == name).sum()))

        assert report["applied"] is True
        assert "Heartbleed" in report["classes_raised_to_the_floor"]

    def test_the_floor_never_invents_rows(self):
        labels = make_labels({BENIGN: 100, "Bot": 3})
        indices, _ = data.stratified_subset(labels, 20, seed=42, min_class_rows=10)
        kept = labels[indices]

        assert (kept == "Bot").sum() == 3

    def test_indices_are_sorted_and_unique(self, synthetic):
        _, labels = synthetic
        indices, _ = data.stratified_subset(labels, 500, seed=42)

        assert len(set(indices.tolist())) == len(indices)
        np.testing.assert_array_equal(indices, np.sort(indices))

    def test_the_subsample_is_deterministic_for_a_seed(self, synthetic):
        _, labels = synthetic
        first, _ = data.stratified_subset(labels, 500, seed=42)
        second, _ = data.stratified_subset(labels, 500, seed=42)
        third, _ = data.stratified_subset(labels, 500, seed=99)

        np.testing.assert_array_equal(first, second)
        assert not np.array_equal(first, third)

    def test_a_subsampled_run_is_flagged_in_the_report(self, synthetic):
        _, labels = synthetic
        _, report = data.stratified_subset(labels, 500, seed=42)

        assert "smoke test only" in report["note"]


class TestConfig:

    def test_defaults_are_applied(self):
        config = config_module.from_dict({"name": "x"})
        assert config.seed == 42
        assert config.balancing["benign_cap"] == 200000
        assert config.balancing["rare_class_min"] == 2000

    def test_the_artifact_name_falls_back_to_the_run_name(self):
        config = config_module.from_dict({"name": "xgb-smote-v2"})
        assert config.artifact_name == "xgb_smote_v2"

    def test_isolation_forest_is_redirected_to_its_own_script(self):
        with pytest.raises(config_module.ConfigError, match="build_anomaly_detector"):
            config_module.from_dict({"name": "x", "model": {"type": "isolation_forest"}})

    @pytest.mark.parametrize("payload,message", [
        ({"name": "x", "model": {"type": "svm"}}, "model.type"),
        ({"name": "x", "split": {"strategy": "kfold"}}, "split.strategy"),
        ({"name": "x", "split": {"test_size": 1.5}}, "test_size"),
        ({"name": "x", "balancing": {"oversampler": "adasyn"}}, "oversampler"),
        ({"name": "x", "balancing": {"benign_cap": -1}}, "benign_cap"),
        ({"name": "x", "seed": -3}, "seed"),
    ])
    def test_invalid_values_are_rejected(self, payload, message):
        with pytest.raises(config_module.ConfigError, match=message):
            config_module.from_dict(payload)

    def test_a_missing_name_is_rejected(self):
        with pytest.raises(config_module.ConfigError, match="name"):
            config_module.from_dict({})

    def test_only_the_mlp_asks_for_a_scaler(self):
        assert config_module.from_dict({"name": "a", "model": {"type": "mlp"}}).needs_scaler
        assert not config_module.from_dict({"name": "b"}).needs_scaler

    def test_every_shipped_config_loads(self):
        from pathlib import Path

        config_dir = Path(__file__).resolve().parent.parent / "training" / "configs"
        found = sorted(config_dir.glob("*.yaml"))
        assert found

        for path in found:
            config = config_module.load(path)
            assert config.name
            assert config.model_type in config_module.SUPERVISED_MODEL_TYPES
            assert config.artifact_name.endswith("_v2")


class TestArtifacts:

    def test_existing_artifacts_are_not_overwritten(self, tmp_path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "demo.joblib").write_text("x", encoding="utf-8")

        with pytest.raises(artifacts.ArtifactError, match="demo.joblib"):
            artifacts.guard_overwrite(models_dir, "demo", force=False)

        assert artifacts.guard_overwrite(models_dir, "demo", force=True)

    def test_the_bundle_records_everything_needed_to_reload(self, tmp_path, monkeypatch,
                                                            synthetic):
        features, labels = synthetic
        columns = [f"f{i}" for i in range(6)]

        stub_dataset(monkeypatch, features, labels, columns,
                     metadata={"name": "synthetic", "sha256": "abc", "subsampled": False})
        result = runner.run(base_config(tmp_path), verbose=False)
        bundle = result.bundle

        assert bundle["artifact_file"] == "test_artifact.joblib"
        assert bundle["label_encoder_file"] == "test_artifact_label_encoder.joblib"
        assert bundle["scaler_file"] is None
        assert bundle["n_features"] == 6
        assert bundle["seed"] == 42
        assert bundle["dataset"]["sha256"] == "abc"
        assert bundle["config"]["balancing"]["benign_cap"] == 1000
        assert sorted(bundle["label_classes"]) == sorted(set(labels))
        assert bundle["generated_at"].endswith("Z")

        for key in ("model", "label_encoder", "bundle", "feature_columns"):
            assert result.paths[key].exists()
        assert not result.paths["scaler"].exists()

    def test_the_mlp_run_saves_a_scaler(self, tmp_path, monkeypatch, synthetic):
        features, labels = synthetic
        columns = [f"f{i}" for i in range(6)]

        stub_dataset(monkeypatch, features, labels, columns)
        config = base_config(tmp_path, model={
            "type": "mlp", "params": {"max_iter": 5, "hidden_layer_sizes": [8]}})
        result = runner.run(config, verbose=False)

        assert result.paths["scaler"].exists()
        assert result.bundle["scaler_file"] == "test_artifact_scaler.joblib"

    def test_reports_are_written_for_every_run(self, tmp_path, monkeypatch, synthetic):
        features, labels = synthetic
        columns = [f"f{i}" for i in range(6)]

        stub_dataset(monkeypatch, features, labels, columns)
        result = runner.run(base_config(tmp_path), verbose=False)
        reports_dir = tmp_path / "reports" / "test-run"

        assert (reports_dir / "metrics.json").exists()
        assert (reports_dir / "config.resolved.yaml").exists()
        assert (reports_dir / "confusion_matrix.csv").exists()
        assert (reports_dir / "confusion_matrix.png").exists()
        assert result.report_paths["metrics"].exists()


class TestEndToEnd:

    @pytest.fixture
    def stubbed(self, monkeypatch, synthetic):
        features, labels = synthetic
        columns = [f"f{i}" for i in range(6)]
        stub_dataset(monkeypatch, features, labels, columns)
        return features, labels, columns

    def test_a_full_run_produces_every_required_metric(self, tmp_path, stubbed):
        result = runner.run(base_config(tmp_path), verbose=False)
        overall = result.metrics["overall"]

        for key in ("accuracy", "macro_f1", "macro_precision", "macro_recall",
                    "weighted_f1"):
            assert isinstance(overall[key], float)

        assert overall["rows"] > 0
        assert result.metrics["per_class"]
        for row in result.metrics["per_class"].values():
            assert {"precision", "recall", "f1", "support", "fpr", "fnr"} <= set(row)

        timings = result.bundle["timings"]
        assert timings["train_seconds"] > 0
        assert timings["avg_latency_ms_batch"] > 0
        assert timings["single_flow_latency"]["samples"] > 0

    def test_the_balancing_report_travels_with_the_run(self, tmp_path, stubbed):
        result = runner.run(base_config(tmp_path), verbose=False)
        report = result.balancing

        assert report["enabled"] is True
        assert report["strategy"] == "undersample_benign_1k_oversample_rare_200"
        assert report["rows_after"] == report["planned_total"]
        assert report["seed"] == 42

    def test_the_run_is_reproducible_with_the_same_seed(self, tmp_path, stubbed):
        first = runner.run(base_config(tmp_path, name="a"), save=False, verbose=False)
        second = runner.run(base_config(tmp_path, name="a"), save=False, verbose=False)

        assert first.metrics["overall"]["accuracy"] == second.metrics["overall"]["accuracy"]
        assert first.metrics["overall"]["macro_f1"] == second.metrics["overall"]["macro_f1"]
        assert first.balancing["class_counts_after"] == second.balancing["class_counts_after"]

    def test_a_different_seed_keeps_the_shape_but_changes_the_rows(self, tmp_path,
                                                                   stubbed):
        features, labels, columns = stubbed
        dataset = data.LoadedDataset(features, labels, columns)

        _, first_test = splitting.split_indices(dataset, "random", 0.2, 42)
        _, second_test = splitting.split_indices(dataset, "random", 0.2, 1234)

        assert len(first_test) == len(second_test)
        assert not np.array_equal(first_test, second_test)

        first = runner.run(base_config(tmp_path, name="a", seed=42), save=False,
                           verbose=False)
        second = runner.run(base_config(tmp_path, name="a", seed=1234), save=False,
                            verbose=False)

        assert first.bundle["split"]["train_rows"] == second.bundle["split"]["train_rows"]
        assert first.bundle["split"]["test_class_support"] == \
            second.bundle["split"]["test_class_support"]
        assert first.balancing["class_counts_after"] == second.balancing["class_counts_after"]

    def test_no_save_writes_no_artifacts(self, tmp_path, stubbed):
        runner.run(base_config(tmp_path), save=False, verbose=False)
        assert not (tmp_path / "models" / "test_artifact.joblib").exists()

    def test_the_trained_model_can_be_reloaded_and_used(self, tmp_path, stubbed):
        import joblib

        result = runner.run(base_config(tmp_path), verbose=False)
        model = joblib.load(result.paths["model"])
        encoder = joblib.load(result.paths["label_encoder"])

        row = np.zeros((1, 6), dtype="float32")
        predicted = encoder.inverse_transform(model.predict(row))

        assert predicted[0] in set(result.bundle["label_classes"])


class TestModelFactory:

    def test_the_seed_reaches_every_estimator(self):
        for model_type in ("xgboost", "random_forest", "mlp"):
            params = models.resolve_params(model_type, {})
            model = models.build_model(model_type, params, seed=7)
            assert model.get_params()["random_state"] == 7

    def test_config_params_override_the_defaults(self):
        params = models.resolve_params("xgboost", {"n_estimators": 250})
        assert params["n_estimators"] == 250
        assert params["tree_method"] == "hist"

    def test_only_the_mlp_gets_a_scaler(self):
        assert models.build_scaler("mlp") is not None
        assert models.build_scaler("xgboost") is None
        assert models.build_scaler("random_forest") is None

    def test_params_serialise_to_json(self):
        params = models.resolve_params("mlp", {})
        payload = models.serialisable_params(params, 42)
        assert payload["hidden_layer_sizes"] == [64, 32]
        assert payload["random_state"] == 42
        json.dumps(payload)


@pytest.mark.dataset
class TestAgainstTheRealDataset:

    NARROW_FEATURES = ["Flow Duration", "Total Fwd Packets", "Flow Bytes/s",
                       "Destination Port"]

    @pytest.fixture(scope="class")
    def real_labels(self):
        import pandas as pd
        from tests.conftest import DATASET_PATH

        return data.clean_labels(
            pd.read_parquet(DATASET_PATH, columns=["Label"])["Label"].to_numpy())

    def test_the_recovered_recipe_plans_653897_training_rows(self, real_labels):
        dataset = data.LoadedDataset(None, real_labels, [])

        train_idx, _ = splitting.split_indices(dataset, "random", 0.2, 42)
        assert len(train_idx) == RECOVERED_TRAIN_ROWS

        plan = balancing.plan_targets(
            balancing.class_counts(real_labels[train_idx]), BENIGN, 200_000, 2_000)

        assert balancing.planned_total(plan) == RECOVERED_BALANCED_ROWS
        assert plan[BENIGN]["target"] == 200_000
        assert plan["Heartbleed"]["target"] == 2_000

    def test_the_recipe_actually_executes_to_653897_rows(self, real_labels):
        import pandas as pd
        from tests.conftest import DATASET_PATH

        frame = pd.read_parquet(DATASET_PATH, columns=self.NARROW_FEATURES)
        features = frame[self.NARROW_FEATURES].to_numpy(dtype="float32")
        del frame

        dataset = data.LoadedDataset(features, real_labels, self.NARROW_FEATURES)
        train_idx, test_idx = splitting.split_indices(dataset, "random", 0.2, 42)
        test_snapshot = features[test_idx].copy()

        settings = {"enabled": True, "benign_label": BENIGN, "benign_cap": 200_000,
                    "rare_class_min": 2_000, "oversampler": "smote",
                    "smote_k_neighbors": 5}
        X, y, report = balancing.balance_training_set(
            features, real_labels, train_idx, settings, seed=42)

        assert report["rows_after"] == RECOVERED_BALANCED_ROWS
        assert len(X) == len(y) == RECOVERED_BALANCED_ROWS
        assert report["smote_k_neighbors"] == 5
        assert report["replicated_classes"] == []
        assert report["class_counts_after"][BENIGN] == 200_000
        assert report["class_counts_after"]["Heartbleed"] == 2_000

        np.testing.assert_array_equal(features[test_idx], test_snapshot)
        assert int((real_labels[test_idx] == BENIGN).sum()) == 454_265
        assert int((real_labels[test_idx] == "Heartbleed").sum()) == 2
        assert int((real_labels[test_idx] == "Infiltration").sum()) == 7
