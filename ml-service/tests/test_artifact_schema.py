import json

import joblib
import numpy as np
import pytest

from app.ml import inference
from app.ml.model_registry import ModelIdentity
from training.pipeline import artifacts, data, runner

BENIGN = "BENIGN"


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
    return rng.normal(0, 0.5, size=(len(labels), n_features)).astype("float32") + base[:, None]


@pytest.fixture
def synthetic():
    counts = {BENIGN: 4000, "DoS Hulk": 800, "PortScan": 600, "Bot": 40, "Heartbleed": 12}
    labels = make_labels(counts)
    return make_features(labels), labels


def base_config(tmp_path, columns, **overrides):
    from training.pipeline import config as config_module

    payload = {
        "name": "schema-run",
        "seed": 42,
        "features": {"columns": list(columns)},
        "split": {"strategy": "random", "test_size": 0.2},
        "balancing": {"benign_cap": 1000, "rare_class_min": 200},
        "model": {"type": "xgboost", "params": {"n_estimators": 5}},
        "output": {
            "models_dir": str(tmp_path / "models"),
            "reports_dir": str(tmp_path / "reports"),
            "artifact_name": "schema_artifact",
        },
    }
    payload.update(overrides)
    return config_module.from_dict(payload)


def stub_dataset(monkeypatch, features, labels, columns):
    monkeypatch.setattr(runner.data, "load_feature_columns", lambda config: list(columns))
    monkeypatch.setattr(
        runner.data, "load_dataset",
        lambda *a, **k: data.LoadedDataset(
            features, labels, list(columns),
            metadata={"name": "synthetic", "subsampled": False}))


class TestTrainedArtifactCarriesItsSchema:

    @pytest.mark.parametrize("model_type,params", [
        ("xgboost", {"n_estimators": 5}),
        ("random_forest", {"n_estimators": 5}),
        ("mlp", {"max_iter": 5, "hidden_layer_sizes": [8]}),
    ])
    def test_every_model_type_exposes_feature_names_in(self, tmp_path, monkeypatch,
                                                       synthetic, model_type, params):
        features, labels = synthetic
        columns = [f"f{i}" for i in range(6)]
        stub_dataset(monkeypatch, features, labels, columns)

        config = base_config(tmp_path, columns,
                             model={"type": model_type, "params": params})
        result = runner.run(config, verbose=False)

        model = joblib.load(result.paths["model"])
        assert artifacts.model_feature_names(model) == columns

    def test_the_order_matches_the_configured_feature_set(self, tmp_path, monkeypatch,
                                                          synthetic):
        features, labels = synthetic
        columns = ["f5", "f0", "f3", "f1", "f4", "f2"]
        renamed = [f"f{i}" for i in range(6)]
        positions = [renamed.index(name) for name in columns]
        stub_dataset(monkeypatch, features[:, positions], labels, columns)

        result = runner.run(base_config(tmp_path, columns), verbose=False)
        model = joblib.load(result.paths["model"])

        assert artifacts.model_feature_names(model) == columns

    def test_model_sidecar_and_bundle_all_agree(self, tmp_path, monkeypatch, synthetic):
        features, labels = synthetic
        columns = [f"f{i}" for i in range(6)]
        stub_dataset(monkeypatch, features, labels, columns)

        result = runner.run(base_config(tmp_path, columns), verbose=False)

        model = joblib.load(result.paths["model"])
        sidecar = json.loads(result.paths["feature_columns"].read_text(encoding="utf-8"))

        assert artifacts.model_feature_names(model) == columns
        assert sidecar == columns
        assert result.bundle["feature_columns"] == columns
        assert result.bundle["n_features"] == len(columns)

    def test_a_narrower_feature_set_is_honoured_end_to_end(self, tmp_path, monkeypatch,
                                                           synthetic):
        features, labels = synthetic
        columns = ["f0", "f2", "f4"]
        stub_dataset(monkeypatch, features[:, [0, 2, 4]], labels, columns)

        result = runner.run(base_config(tmp_path, columns), verbose=False)
        model = joblib.load(result.paths["model"])

        assert model.n_features_in_ == 3
        assert artifacts.model_feature_names(model) == columns


class TestSchemaGuards:

    class Named:
        def __init__(self, names):
            self.feature_names_in_ = np.array(names, dtype=object)
            self.n_features_in_ = len(names)

    class Bare:
        n_features_in_ = 3

    def test_a_model_without_feature_names_is_rejected(self):
        with pytest.raises(artifacts.SchemaMismatch, match="feature_names_in_"):
            artifacts.verify_model_schema(self.Bare(), ["a", "b", "c"])

    def test_a_matching_model_passes(self):
        assert artifacts.verify_model_schema(self.Named(["a", "b"]), ["a", "b"]) == \
            ["a", "b"]

    def test_an_order_mismatch_is_rejected(self):
        with pytest.raises(artifacts.SchemaMismatch, match="pozicione"):
            artifacts.verify_model_schema(self.Named(["b", "a"]), ["a", "b"])

    def test_a_count_mismatch_is_rejected(self):
        with pytest.raises(artifacts.SchemaMismatch, match="features"):
            artifacts.verify_model_schema(self.Named(["a"]), ["a", "b"])

    def test_a_sidecar_mismatch_is_rejected(self, tmp_path):
        sidecar = tmp_path / "x_feature_columns.json"
        sidecar.write_text(json.dumps(["a", "z"]), encoding="utf-8")
        paths = {"feature_columns": sidecar}

        with pytest.raises(artifacts.SchemaMismatch, match="feature_columns"):
            artifacts.verify_saved_schema(
                paths, {"feature_columns": ["a", "b"], "n_features": 2}, ["a", "b"])

    def test_a_bundle_mismatch_is_rejected(self, tmp_path):
        sidecar = tmp_path / "x_feature_columns.json"
        sidecar.write_text(json.dumps(["a", "b"]), encoding="utf-8")
        paths = {"feature_columns": sidecar}

        with pytest.raises(artifacts.SchemaMismatch, match="bundle"):
            artifacts.verify_saved_schema(
                paths, {"feature_columns": ["a", "z"], "n_features": 2}, ["a", "b"])

    def test_a_consistent_set_passes(self, tmp_path):
        sidecar = tmp_path / "x_feature_columns.json"
        sidecar.write_text(json.dumps(["a", "b"]), encoding="utf-8")

        assert artifacts.verify_saved_schema(
            {"feature_columns": sidecar},
            {"feature_columns": ["a", "b"], "n_features": 2}, ["a", "b"])

    def test_a_broken_model_never_reaches_disk(self, tmp_path, monkeypatch, synthetic):
        features, labels = synthetic
        columns = [f"f{i}" for i in range(6)]
        stub_dataset(monkeypatch, features, labels, columns)

        original_build = runner.models.build_model

        def strip_names(model_type, params, seed):
            model = original_build(model_type, params, seed)
            original_fit = model.fit

            def fit(X, y, *args, **kwargs):
                return original_fit(np.asarray(X), y, *args, **kwargs)

            model.fit = fit
            return model

        monkeypatch.setattr(runner.models, "build_model", strip_names)

        with pytest.raises(artifacts.SchemaMismatch, match="feature_names_in_"):
            runner.run(base_config(tmp_path, columns), verbose=False)

        assert not (tmp_path / "models" / "schema_artifact.joblib").exists()


class TestNoSilentFallback:

    def _write(self, models_dir, name, columns):
        (models_dir / name).write_text(json.dumps(columns), encoding="utf-8")

    class Model:
        def __init__(self, n):
            self.n_features_in_ = n

    def test_a_narrow_model_never_gets_the_generic_78_list(self, tmp_path):
        models_dir = tmp_path
        self._write(models_dir, "feature_columns.json", [f"f{i}" for i in range(78)])

        with pytest.raises(RuntimeError, match="Refuzoj fallback-un e heshtur"):
            inference._feature_columns_for(self.Model(50), models_dir,
                                           "xgb_smote_top50features_v2.joblib")

    def test_the_sidecar_is_preferred_when_present(self, tmp_path):
        models_dir = tmp_path
        self._write(models_dir, "feature_columns.json", [f"f{i}" for i in range(78)])
        self._write(models_dir, "top50_feature_columns.json",
                    [f"s{i}" for i in range(50)])

        columns = inference._feature_columns_for(self.Model(50), models_dir,
                                                 "top50.joblib")

        assert columns == [f"s{i}" for i in range(50)]

    def test_a_sidecar_that_disagrees_with_the_model_is_rejected(self, tmp_path):
        models_dir = tmp_path
        self._write(models_dir, "feature_columns.json", [f"f{i}" for i in range(78)])
        self._write(models_dir, "top50_feature_columns.json",
                    [f"s{i}" for i in range(30)])

        with pytest.raises(RuntimeError, match="30 features ndersa modeli pret 50"):
            inference._feature_columns_for(self.Model(50), models_dir, "top50.joblib")

    def test_the_full_78_model_still_works_from_the_generic_file(self, tmp_path):
        models_dir = tmp_path
        columns = [f"f{i}" for i in range(78)]
        self._write(models_dir, "feature_columns.json", columns)

        assert inference._feature_columns_for(self.Model(78), models_dir,
                                              "xgb_78.joblib") == columns

    def test_a_model_carrying_its_own_names_wins_over_every_file(self, tmp_path):
        models_dir = tmp_path
        self._write(models_dir, "feature_columns.json", [f"f{i}" for i in range(78)])

        class Named:
            feature_names_in_ = np.array(["a", "b"], dtype=object)
            n_features_in_ = 2

        assert inference._feature_columns_for(Named(), models_dir, "m.joblib") == ["a", "b"]


class TestHistoricalV1Compatibility:

    @pytest.mark.artifacts
    def test_v1_artifacts_still_expose_their_own_schema(self):
        from tests.conftest import MODELS_DIR

        for name in ("xgb_smote_cicids2017_v1.joblib",
                     "xgb_smote_top50features_v1.joblib",
                     "rf_baseline_cicids2017_v1.joblib"):
            path = MODELS_DIR / name
            if not path.exists():
                pytest.skip(f"{name} mungon")
            names = artifacts.model_feature_names(joblib.load(path))
            assert names is not None, name
            assert len(names) == joblib.load(path).n_features_in_

    @pytest.mark.artifacts
    def test_a_v1_identity_loads_without_a_sidecar(self):
        from tests.conftest import MODELS_DIR

        path = MODELS_DIR / "xgb_smote_top50features_v1.joblib"
        if not path.exists():
            pytest.skip("artefakti mungon")

        model = joblib.load(path)
        columns = inference._feature_columns_for(model, MODELS_DIR, path.name)

        assert len(columns) == 50


class TestLatencyExcludesFrameConstruction:

    def test_the_matrix_is_built_before_the_timed_region(self, tmp_path, monkeypatch,
                                                         synthetic):
        features, labels = synthetic
        columns = [f"f{i}" for i in range(6)]
        stub_dataset(monkeypatch, features, labels, columns)

        seen = {}
        original = runner.evaluation.measure_batch_latency

        def spy(model, X_test, **kwargs):
            seen["type"] = type(X_test).__name__
            seen["prebuilt_columns"] = list(getattr(X_test, "columns", []))
            return original(model, X_test, **kwargs)

        monkeypatch.setattr(runner.evaluation, "measure_batch_latency", spy)
        runner.run(base_config(tmp_path, columns), save=False, verbose=False)

        assert seen["type"] == "DataFrame"
        assert seen["prebuilt_columns"] == columns

    def test_the_model_only_metric_converts_before_timing(self):
        calls = []

        class Recorder:
            def predict(self, X):
                calls.append(type(X).__name__)
                return np.zeros(len(X), dtype=int)

        import pandas as pd

        frame = pd.DataFrame(np.zeros((2000, 3), dtype="float32"),
                             columns=["a", "b", "c"])
        _, timing = runner.evaluation.measure_batch_latency(Recorder(), frame)

        assert set(calls) == {"ndarray"}
        assert timing["repetitions"] == 3
        assert timing["metric"] == runner.evaluation.METRIC_MODEL_INFERENCE
