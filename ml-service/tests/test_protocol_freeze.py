import json

import numpy as np
import pytest

from app.ml import feature_validation as fv
from training import build_feature_ranking as ranking
from training.evaluate import (
    MIN_SUPPORT_FOR_CLAIM,
    classes_at_min_support,
    macro_f1_at_min_support,
    macro_f1_from_per_class,
)
from training.pipeline import evaluation


def per_class(entries):
    return {name: {"support": support, "f1": f1}
            for name, support, f1 in entries}


class TestMacroF1Reporting:

    def test_the_full_macro_f1_is_the_mean_over_every_class(self):
        rows = per_class([("BENIGN", 400000, 1.0), ("DDoS", 25000, 0.9),
                          ("Heartbleed", 2, 0.0)])
        assert macro_f1_from_per_class(rows) == pytest.approx((1.0 + 0.9 + 0.0) / 3)

    def test_the_sensitivity_metric_drops_classes_below_the_threshold(self):
        rows = per_class([("BENIGN", 400000, 1.0), ("DDoS", 25000, 0.9),
                          ("Heartbleed", 2, 0.0), ("Infiltration", 7, 0.5)])
        assert macro_f1_at_min_support(rows) == pytest.approx((1.0 + 0.9) / 2)

    def test_a_class_exactly_on_the_threshold_is_kept(self):
        rows = per_class([("A", MIN_SUPPORT_FOR_CLAIM, 0.4), ("B", 1000, 0.8)])
        assert macro_f1_at_min_support(rows) == pytest.approx(0.6)

    def test_the_threshold_is_configurable(self):
        rows = per_class([("A", 50, 0.2), ("B", 1000, 0.8)])
        assert macro_f1_at_min_support(rows, min_support=10) == pytest.approx(0.5)

    def test_no_qualifying_class_yields_none_not_zero(self):
        rows = per_class([("Heartbleed", 2, 1.0)])
        assert macro_f1_at_min_support(rows) is None

    def test_the_qualifying_classes_are_listed(self):
        rows = per_class([("BENIGN", 400000, 1.0), ("Heartbleed", 2, 0.0),
                          ("DDoS", 25000, 0.9)])
        assert classes_at_min_support(rows) == ["BENIGN", "DDoS"]

    def test_the_two_metrics_differ_on_the_real_shape_of_this_dataset(self):
        rows = per_class([("BENIGN", 454265, 0.9995), ("DDoS", 25605, 0.9998),
                          ("Infiltration", 7, 0.7143),
                          ("Web Attack - Sql Injection", 4, 0.4444),
                          ("Heartbleed", 2, 1.0)])
        full = macro_f1_from_per_class(rows)
        restricted = macro_f1_at_min_support(rows)

        assert restricted > full
        assert abs(restricted - full) > 0.05

    def test_both_metrics_reach_the_evaluation_report(self, tmp_path):
        y_true = np.array(["BENIGN"] * 200 + ["DDoS"] * 150 + ["Heartbleed"] * 2,
                          dtype=object)
        y_pred = y_true.copy()
        y_pred[0] = "DDoS"

        metrics = evaluation.evaluate_predictions(y_true, y_pred, tmp_path, "demo")

        assert metrics["primary_metric"] == "macro_f1"
        assert metrics["sensitivity_metric"] == "macro_f1_min_support"
        assert metrics["macro_f1_min_support"] is not None
        assert metrics["classes_in_macro_f1_min_support"] == ["BENIGN", "DDoS"]
        assert metrics["overall"]["macro_f1_min_support"] == \
            metrics["macro_f1_min_support"]
        assert metrics["overall"]["macro_f1"] != metrics["macro_f1_min_support"]


class StubModel:

    def __init__(self, n_classes=3):
        self.calls = []
        self.n_classes = n_classes

    def predict(self, X):
        self.calls.append(len(X))
        return np.zeros(len(X), dtype=int)


class TestLatencyProtocol:

    def test_the_batch_protocol_is_frozen_at_the_agreed_values(self):
        assert evaluation.BATCH_WARMUP_ROWS == 1000
        assert evaluation.BATCH_REPETITIONS == 3
        assert evaluation.SINGLE_FLOW_WARMUP == 20
        assert evaluation.SINGLE_FLOW_SAMPLES == 200

    def test_batch_measurement_warms_up_then_repeats_three_times(self):
        model = StubModel()
        X = np.zeros((5000, 4), dtype="float32")

        predictions, timing = evaluation.measure_batch_latency(model, X)

        assert len(model.calls) == 1 + evaluation.BATCH_REPETITIONS
        assert model.calls[0] == evaluation.BATCH_WARMUP_ROWS
        assert model.calls[1:] == [5000, 5000, 5000]
        assert len(predictions) == 5000
        assert timing["repetitions"] == 3
        assert timing["warmup_rows"] == 1000
        assert timing["batch_size"] == 5000

    def test_the_reported_batch_figure_is_the_median(self):
        model = StubModel()
        X = np.zeros((2000, 4), dtype="float32")

        _, timing = evaluation.measure_batch_latency(model, X)

        assert timing["median_seconds"] == pytest.approx(
            float(np.median(timing["seconds_per_repetition"])))
        assert timing["min_seconds"] <= timing["median_seconds"] <= timing["max_seconds"]
        assert timing["ms_per_flow"] == pytest.approx(
            timing["median_seconds"] / 2000 * 1000)

    def test_a_warmup_larger_than_the_set_is_clamped(self):
        model = StubModel()
        X = np.zeros((100, 4), dtype="float32")

        _, timing = evaluation.measure_batch_latency(model, X)

        assert model.calls[0] == 100
        assert timing["warmup_rows"] == 100

    def test_an_empty_test_set_does_not_crash(self):
        model = StubModel()
        predictions, timing = evaluation.measure_batch_latency(
            model, np.zeros((0, 4), dtype="float32"))

        assert len(predictions) == 0
        assert timing["ms_per_flow"] is None
        assert model.calls == []

    def test_single_flow_warms_up_and_samples_the_agreed_count(self):
        model = StubModel()
        X = np.zeros((1000, 4), dtype="float32")

        result = evaluation.measure_single_flow_latency(model, X)

        assert result["samples"] == evaluation.SINGLE_FLOW_SAMPLES
        assert result["warmup"] == evaluation.SINGLE_FLOW_WARMUP
        assert len(model.calls) == evaluation.SINGLE_FLOW_WARMUP + \
            evaluation.SINGLE_FLOW_SAMPLES
        assert all(count == 1 for count in model.calls)

    def test_single_flow_reports_mean_median_and_p95(self):
        result = evaluation.measure_single_flow_latency(
            StubModel(), np.zeros((300, 4), dtype="float32"))

        for key in ("mean_ms", "median_ms", "p95_ms"):
            assert isinstance(result[key], float)
        assert result["p95_ms"] >= result["median_ms"]

    def test_single_flow_sampling_is_deterministic_for_a_seed(self):
        X = np.arange(400 * 3, dtype="float32").reshape(400, 3)

        first = StubModel()
        second = StubModel()
        evaluation.measure_single_flow_latency(first, X, seed=42)
        evaluation.measure_single_flow_latency(second, X, seed=42)

        assert first.calls == second.calls

    def test_the_two_methodologies_declare_themselves_incomparable(self):
        assert "NOT comparable" in evaluation.SINGLE_FLOW_METHODOLOGY
        assert "warm-up" in evaluation.BATCH_METHODOLOGY

    def test_the_timed_region_excludes_everything_but_inference(self):
        for text in (evaluation.BATCH_METHODOLOGY, evaluation.SINGLE_FLOW_METHODOLOGY):
            for excluded in ("SHAP", "HTTP", "database", "frontend",
                             "DataFrame construction"):
                assert excluded in text

    def test_build_timings_keeps_the_key_the_registry_reads(self):
        model = StubModel()
        X = np.zeros((500, 4), dtype="float32")
        _, batch = evaluation.measure_batch_latency(model, X)
        single = evaluation.measure_single_flow_latency(StubModel(), X)

        timings = evaluation.build_timings(12.5, batch, single)

        assert timings["train_seconds"] == 12.5
        assert timings["avg_latency_ms_batch"] == batch["ms_per_flow"]
        assert timings["latency_methodology"]
        assert timings["batch_latency"]["repetitions"] == 3
        assert timings["single_flow_latency"]["samples"] == 200


class TestFeatureVersionPairing:

    @pytest.fixture
    def reference(self):
        return {
            "base_feature_version": "cicids2017-78-v1",
            "feature_sets": {
                "cicids2017-78-v1": ["a", "b", "c", "d"],
                "cicids2017-top2-v1": ["a", "b"],
                "cicids2017-top2-v2": ["c", "d"],
            },
        }

    def test_a_matching_declaration_passes(self, reference):
        assert fv.verify_feature_version(["a", "b"], "cicids2017-top2-v1", reference) is None

    def test_a_different_member_set_is_a_mismatch(self, reference):
        report = fv.verify_feature_version(["c", "d"], "cicids2017-top2-v1", reference)

        assert report["reason"] == "member_mismatch"
        assert report["resolved_feature_version"] == "cicids2017-top2-v2"
        assert "cift i versionuar" in report["message"]

    def test_the_same_members_in_a_different_order_is_a_mismatch(self, reference):
        report = fv.verify_feature_version(["b", "a"], "cicids2017-top2-v1", reference)

        assert report["reason"] == "order_mismatch"
        assert "renditje tjeter" in report["message"]

    def test_an_unregistered_declaration_cannot_be_verified(self, reference):
        assert fv.verify_feature_version(["a"], "something-else", reference) is None

    def test_no_declaration_and_no_reference_are_both_skipped(self, reference):
        assert fv.verify_feature_version(["a"], None, reference) is None
        assert fv.verify_feature_version(["a"], "cicids2017-top2-v1", None) is None

    def test_the_mismatch_report_names_what_differs(self, reference):
        report = fv.verify_feature_version(["a", "z"], "cicids2017-top2-v1", reference)

        assert report["missing_from_artifact"] == ["b"]
        assert report["unexpected_in_artifact"] == ["z"]
        assert report["declared_n_features"] == 2
        assert report["actual_n_features"] == 2

    def test_inference_refuses_to_load_a_mismatched_pair(self, monkeypatch, tmp_path):
        from app.ml import inference
        from app.ml.model_registry import ModelIdentity

        class FakeModel:
            feature_names_in_ = np.array(["c", "d"], dtype=object)

        monkeypatch.setattr(inference, "_reference", {
            "feature_sets": {"cicids2017-top2-v1": ["a", "b"]}})
        monkeypatch.setattr(inference, "_models_dir", lambda: tmp_path)
        monkeypatch.setattr(inference.joblib, "load", lambda path: FakeModel())
        (tmp_path / "model.joblib").write_bytes(b"x")

        identity = ModelIdentity(artifact_file="model.joblib",
                                 feature_version="cicids2017-top2-v1")

        with pytest.raises(fv.FeatureVersionMismatch, match="NUK perputhet"):
            inference._load(identity)


class TestFeatureRanking:

    class Model:
        def __init__(self, names, importances):
            self.feature_names_in_ = np.array(names, dtype=object)
            self.feature_importances_ = np.array(importances, dtype="float32")

    @pytest.fixture
    def reference(self):
        return {
            "base_feature_version": "cicids2017-78-v1",
            "feature_sets": {
                "cicids2017-78-v1": ["a", "b", "c", "d"],
                "cicids2017-top2-v1": ["a", "b"],
            },
        }

    def test_features_are_ranked_by_descending_gain(self):
        model = self.Model(["a", "b", "c"], [0.1, 0.7, 0.2])
        result = ranking.rank_features(model)

        assert [entry["feature"] for entry in result] == ["b", "c", "a"]
        assert result[0]["rank"] == 1
        assert result[0]["importance"] == pytest.approx(0.7)

    def test_ties_are_broken_by_dataset_column_order(self):
        model = self.Model(["a", "b", "c"], [0.0, 0.0, 0.5])
        result = ranking.rank_features(model)

        assert [entry["feature"] for entry in result] == ["c", "a", "b"]

    def test_a_model_without_feature_names_is_refused(self):
        class Bare:
            feature_importances_ = np.array([0.5])

        with pytest.raises(ranking.RankingError, match="feature_names_in_"):
            ranking.rank_features(Bare())

    def test_a_model_without_importances_is_refused(self):
        class Bare:
            feature_names_in_ = np.array(["a"], dtype=object)
            feature_importances_ = None

        with pytest.raises(ranking.RankingError, match="feature_importances_"):
            ranking.rank_features(Bare())

    def test_top_n_sets_are_prefixes_of_the_ranking(self, reference):
        model = self.Model(["a", "b", "c", "d"], [0.1, 0.4, 0.3, 0.2])
        payload = ranking.build(model, __import__("pathlib").Path(__file__), reference,
                                [2, 3], "v2", 42, "demo-v2")

        ordered = [entry["feature"] for entry in payload["ranking"]]
        assert payload["feature_sets"]["cicids2017-top2-v2"] == ordered[:2]
        assert payload["feature_sets"]["cicids2017-top3-v2"] == ordered[:3]

    def test_the_full_set_keeps_dataset_column_order(self, reference):
        model = self.Model(["a", "b", "c", "d"], [0.1, 0.4, 0.3, 0.2])
        payload = ranking.build(model, __import__("pathlib").Path(__file__), reference,
                                [2], "v2", 42, "demo-v2")

        assert payload["feature_sets"]["cicids2017-4-v2"] == ["a", "b", "c", "d"]

    def test_zero_gain_features_are_counted_and_warned_about(self, reference):
        model = self.Model(["a", "b", "c", "d"], [0.6, 0.4, 0.0, 0.0])
        payload = ranking.build(model, __import__("pathlib").Path(__file__), reference,
                                [2], "v2", 42, "demo-v2")

        assert payload["non_zero_importance_count"] == 2
        assert payload["zero_importance_features"] == ["c", "d"]
        assert "arbitrary" in payload["zero_importance_warning"]

    def test_provenance_is_recorded(self, reference):
        model = self.Model(["a", "b", "c", "d"], [0.6, 0.4, 0.0, 0.0])
        payload = ranking.build(model, __import__("pathlib").Path(__file__), reference,
                                [2], "v2", 42, "demo-v2")

        assert payload["source_model"] == "demo-v2"
        assert payload["seed"] == 42
        assert len(payload["source_artifact_sha256"]) == 64
        assert "TRAINING rows only" in payload["ranking_method"]
        assert "gain" in payload["ranking_method"]

    def test_overlap_with_the_previous_version_is_reported(self, reference):
        model = self.Model(["a", "b", "c", "d"], [0.6, 0.0, 0.4, 0.0])
        payload = ranking.build(model, __import__("pathlib").Path(__file__), reference,
                                [2], "v2", 42, "demo-v2")

        overlap = payload["overlap_with_previous"]["cicids2017-top2-v2"]
        assert overlap["compared_with"] == "cicids2017-top2-v1"
        assert overlap["available"] is True
        assert overlap["shared"] == 1
        assert overlap["only_in_new"] == ["c"]
        assert overlap["only_in_previous"] == ["b"]
        assert overlap["identical_members"] is False

    def test_a_missing_previous_version_is_reported_not_fatal(self, reference):
        model = self.Model(["a", "b", "c", "d"], [0.6, 0.3, 0.1, 0.0])
        payload = ranking.build(model, __import__("pathlib").Path(__file__), reference,
                                [3], "v2", 42, "demo-v2")

        assert payload["overlap_with_previous"]["cicids2017-top3-v2"]["available"] is False

    def test_merging_into_the_reference_adds_without_dropping(self, reference):
        updated, added, replaced = ranking.merge_into_reference(
            reference, {"cicids2017-top2-v2": ["c", "d"]})

        assert "cicids2017-top2-v1" in updated["feature_sets"]
        assert updated["feature_sets"]["cicids2017-top2-v2"] == ["c", "d"]
        assert added == ["cicids2017-top2-v2"]
        assert replaced == []

    def test_merging_reports_a_replacement(self, reference):
        _, added, replaced = ranking.merge_into_reference(
            reference, {"cicids2017-top2-v1": ["x", "y"]})

        assert replaced == ["cicids2017-top2-v1"]
        assert added == []

    def test_the_generated_sets_round_trip_through_verification(self, reference):
        model = self.Model(["a", "b", "c", "d"], [0.1, 0.0, 0.6, 0.3])
        payload = ranking.build(model, __import__("pathlib").Path(__file__), reference,
                                [2], "v2", 42, "demo-v2")
        updated, _, _ = ranking.merge_into_reference(reference, payload["feature_sets"])

        columns = payload["feature_sets"]["cicids2017-top2-v2"]
        assert columns == ["c", "d"]
        assert fv.verify_feature_version(columns, "cicids2017-top2-v2", updated) is None

        crossed = fv.verify_feature_version(columns, "cicids2017-top2-v1", updated)
        assert crossed is not None
        assert crossed["resolved_feature_version"] == "cicids2017-top2-v2"


class TestLatencyMetricSeparation:

    class Recorder:
        def __init__(self):
            self.seen = []

        def predict(self, X):
            self.seen.append(type(X).__name__)
            return np.zeros(len(X), dtype=int)

    def frame(self, rows=500, cols=("a", "b", "c")):
        import pandas as pd
        return pd.DataFrame(np.zeros((rows, len(cols)), dtype="float32"),
                            columns=list(cols))

    def test_the_two_metrics_have_names_that_cannot_be_confused(self):
        assert evaluation.METRIC_MODEL_INFERENCE == "model_inference_latency"
        assert evaluation.METRIC_PRODUCTION_PATH == "production_path_inference_latency"
        assert evaluation.METRIC_MODEL_INFERENCE != evaluation.METRIC_PRODUCTION_PATH
        assert "NOT production latency" in evaluation.LATENCY_SCOPE

    def test_model_only_batch_times_an_ndarray(self):
        recorder = self.Recorder()
        _, timing = evaluation.measure_batch_latency(recorder, self.frame())

        assert set(recorder.seen) == {"ndarray"}
        assert timing["metric"] == evaluation.METRIC_MODEL_INFERENCE

    def test_model_only_single_flow_times_an_ndarray(self):
        recorder = self.Recorder()
        result = evaluation.measure_single_flow_latency(recorder, self.frame())

        assert set(recorder.seen) == {"ndarray"}
        assert result["metric"] == evaluation.METRIC_MODEL_INFERENCE

    def test_the_production_path_times_a_dataframe(self):
        recorder = self.Recorder()
        result = evaluation.measure_production_path_latency(
            recorder, self.frame(), ["a", "b", "c"])

        assert set(recorder.seen) == {"DataFrame"}
        assert result["metric"] == evaluation.METRIC_PRODUCTION_PATH
        assert "DataFrame construction IS inside" in result["methodology"]

    def test_the_production_path_uses_the_declared_feature_columns(self):
        seen = {}

        class Checker:
            def predict(self, X):
                seen["columns"] = list(X.columns)
                return np.zeros(len(X), dtype=int)

        evaluation.measure_production_path_latency(
            Checker(), self.frame(), ["a", "b", "c"], samples=5, warmup=1)

        assert seen["columns"] == ["a", "b", "c"]

    def test_both_metrics_report_mean_median_p95(self):
        recorder = self.Recorder()
        model_only = evaluation.measure_single_flow_latency(recorder, self.frame())
        production = evaluation.measure_production_path_latency(
            self.Recorder(), self.frame(), ["a", "b", "c"])

        for result in (model_only, production):
            for key in ("mean_ms", "median_ms", "p95_ms", "samples", "warmup"):
                assert key in result

    def test_the_same_sampling_policy_applies_to_both(self):
        recorder = self.Recorder()
        model_only = evaluation.measure_single_flow_latency(recorder, self.frame())
        production = evaluation.measure_production_path_latency(
            self.Recorder(), self.frame(), ["a", "b", "c"])

        assert model_only["samples"] == production["samples"]
        assert model_only["warmup"] == production["warmup"]

    def test_build_timings_namespaces_both_metrics(self):
        recorder = self.Recorder()
        frame = self.frame()
        _, batch = evaluation.measure_batch_latency(recorder, frame)
        single = evaluation.measure_single_flow_latency(self.Recorder(), frame)
        production = evaluation.measure_production_path_latency(
            self.Recorder(), frame, ["a", "b", "c"])

        timings = evaluation.build_timings(10.0, batch, single, production)

        assert timings["model_inference_latency"]["batch"]["metric"] == \
            evaluation.METRIC_MODEL_INFERENCE
        assert timings["model_inference_latency"]["single_flow"]["metric"] == \
            evaluation.METRIC_MODEL_INFERENCE
        assert timings["production_path_inference_latency"]["metric"] == \
            evaluation.METRIC_PRODUCTION_PATH
        assert timings["avg_latency_ms_batch"] == batch["ms_per_flow"]

    def test_a_run_without_the_production_path_still_builds(self):
        recorder = self.Recorder()
        _, batch = evaluation.measure_batch_latency(recorder, self.frame())
        timings = evaluation.build_timings(1.0, batch, None)

        assert timings["production_path_inference_latency"] is None
        assert timings["model_inference_latency"]["batch"] is batch

    def test_v1_and_v2_models_go_through_the_same_conversion(self):
        recorder_v1 = self.Recorder()
        recorder_v2 = self.Recorder()

        evaluation.measure_single_flow_latency(recorder_v1, self.frame())
        evaluation.measure_single_flow_latency(recorder_v2, np.zeros((500, 3),
                                                                    dtype="float32"))

        assert set(recorder_v1.seen) == set(recorder_v2.seen) == {"ndarray"}


class TestArtifactDiscovery:

    def _bundle(self, tmp_path, name, artifact, **overrides):
        payload = {
            "artifact_file": artifact,
            "name": name,
            "algorithm": "xgboost",
            "feature_version": "cicids2017-78-v2",
            "label_encoder_file": f"{artifact[:-7]}_label_encoder.joblib",
            "scaler_file": None,
            "feature_columns": ["a", "b"],
            "artifact_sha256": "f" * 64,
            "balancing": {"strategy": "undersample_benign_200k_oversample_rare_2k"},
        }
        payload.update(overrides)
        (tmp_path / f"{artifact[:-7]}_bundle.json").write_text(
            json.dumps(payload), encoding="utf-8")
        (tmp_path / artifact).write_bytes(b"x")
        return payload

    def test_a_v2_bundle_is_discovered(self, tmp_path):
        from training import evaluate_artifacts as ea

        self._bundle(tmp_path, "xgb-smote-cicids2017-v2",
                     "xgb_smote_cicids2017_v2.joblib")
        found = ea.discover_artifacts(tmp_path)

        assert len(found) == 1
        spec = found[0]
        assert spec["registry_name"] == "xgb-smote-cicids2017-v2"
        assert spec["version_tag"] == ea.VERSION_V2
        assert spec["algorithm"] == "XGBoost"
        assert spec["labels"] == ea.LABELS_AS_ENCODED

    def test_the_v2_spec_points_at_its_own_label_encoder(self, tmp_path):
        from training import evaluate_artifacts as ea

        self._bundle(tmp_path, "mlp-smote-cicids2017-v2", "mlp_smote_cicids2017_v2.joblib",
                     algorithm="mlp", scaler_file="mlp_smote_cicids2017_v2_scaler.joblib")
        spec = ea.discover_artifacts(tmp_path)[0]

        assert spec["label_encoder_file"] == "mlp_smote_cicids2017_v2_label_encoder.joblib"
        assert spec["scaler_file"] == "mlp_smote_cicids2017_v2_scaler.joblib"
        assert spec["needs_scaler"] is True
        assert spec["algorithm"] == "NeuralNetwork"

    def test_a_v2_without_a_scaler_declares_none(self, tmp_path):
        from training import evaluate_artifacts as ea

        self._bundle(tmp_path, "xgb-v2", "xgb_v2.joblib")
        spec = ea.discover_artifacts(tmp_path)[0]

        assert spec["scaler_file"] is None
        assert spec["needs_scaler"] is False

    def test_legacy_v1_specs_are_included_when_the_file_exists(self, tmp_path):
        from training import evaluate_artifacts as ea

        (tmp_path / "xgb_smote_cicids2017_v1.joblib").write_bytes(b"x")
        found = ea.discover_artifacts(tmp_path)

        assert [spec["registry_name"] for spec in found] == ["xgb-smote-cicids2017-v1"]
        assert found[0]["version_tag"] == ea.VERSION_V1
        assert found[0]["label_encoder_file"] == ea.LABEL_ENCODER

    def test_a_legacy_spec_without_its_file_is_skipped(self, tmp_path):
        from training import evaluate_artifacts as ea

        assert ea.discover_artifacts(tmp_path) == []

    def test_v1_and_v2_are_not_mixed(self, tmp_path):
        from training import evaluate_artifacts as ea

        self._bundle(tmp_path, "xgb-smote-cicids2017-v2",
                     "xgb_smote_cicids2017_v2.joblib")
        (tmp_path / "xgb_smote_cicids2017_v1.joblib").write_bytes(b"x")

        found = ea.discover_artifacts(tmp_path)
        by_tag = {spec["version_tag"]: spec for spec in found}

        assert set(by_tag) == {ea.VERSION_V1, ea.VERSION_V2}
        assert by_tag[ea.VERSION_V1]["artifact"] == "xgb_smote_cicids2017_v1.joblib"
        assert by_tag[ea.VERSION_V2]["artifact"] == "xgb_smote_cicids2017_v2.joblib"
        assert by_tag[ea.VERSION_V1]["label_encoder_file"] != \
            by_tag[ea.VERSION_V2]["label_encoder_file"]

    def test_a_bundle_wins_over_a_legacy_entry_for_the_same_file(self, tmp_path):
        from training import evaluate_artifacts as ea

        self._bundle(tmp_path, "renamed-v2", "xgb_smote_cicids2017_v1.joblib")
        found = ea.discover_artifacts(tmp_path)

        assert len(found) == 1
        assert found[0]["registry_name"] == "renamed-v2"

    def test_ordering_is_deterministic(self, tmp_path):
        from training import evaluate_artifacts as ea

        self._bundle(tmp_path, "b-model-v2", "b_model_v2.joblib")
        self._bundle(tmp_path, "a-model-v2", "a_model_v2.joblib")
        (tmp_path / "rf_smote_cicids2017_v1.joblib").write_bytes(b"x")

        first = [spec["registry_name"] for spec in ea.discover_artifacts(tmp_path)]
        second = [spec["registry_name"] for spec in ea.discover_artifacts(tmp_path)]

        assert first == second
        assert first == ["rf-smote-cicids2017-v1", "a-model-v2", "b-model-v2"]

    def test_a_corrupt_bundle_is_skipped_not_fatal(self, tmp_path):
        from training import evaluate_artifacts as ea

        (tmp_path / "broken_bundle.json").write_text("{not json", encoding="utf-8")
        (tmp_path / "rf_smote_cicids2017_v1.joblib").write_bytes(b"x")

        found = ea.discover_artifacts(tmp_path)
        assert [spec["registry_name"] for spec in found] == ["rf-smote-cicids2017-v1"]

    def test_the_isolation_forests_stay_anomaly_kind(self, tmp_path):
        from training import evaluate_artifacts as ea

        for name in ("isolation_forest_cicids2017_v1.joblib",
                     "isolation_forest_benign_v2.joblib"):
            (tmp_path / name).write_bytes(b"x")

        found = ea.discover_artifacts(tmp_path)
        assert all(spec["kind"] == ea.KIND_ANOMALY for spec in found)
        assert all(spec["excluded_reason"] for spec in found)

    def test_discovery_finds_the_real_v2_anchor(self):
        from pathlib import Path

        from training import evaluate_artifacts as ea
        from tests.conftest import MODELS_DIR

        if not (MODELS_DIR / "xgb_smote_cicids2017_v2.joblib").exists():
            pytest.skip("anchor v2 mungon")

        found = ea.discover_artifacts(MODELS_DIR)
        names = {spec["artifact"] for spec in found}

        assert "xgb_smote_cicids2017_v2.joblib" in names
        assert "xgb_smote_cicids2017_v1.joblib" in names
        anchor = next(s for s in found if s["artifact"] == "xgb_smote_cicids2017_v2.joblib")
        assert anchor["version_tag"] == ea.VERSION_V2
        assert Path(anchor["label_encoder_file"]).name.startswith("xgb_smote_cicids2017_v2")


class TestRegistryCollisions:

    def _spec(self, artifact, registry_name, version_tag="v2"):
        return {"artifact": artifact, "registry_name": registry_name,
                "version_tag": version_tag}

    def test_distinct_identities_pass(self):
        from training import evaluate_artifacts as ea

        assert ea.assert_no_collisions([
            self._spec("a_v1.joblib", "model-v1", "v1"),
            self._spec("a_v2.joblib", "model-v2", "v2"),
        ])

    def test_two_artifacts_sharing_a_registry_name_fail_explicitly(self):
        from training import evaluate_artifacts as ea

        with pytest.raises(ea.RegistryCollision, match="Emra regjistri te dyfishuar"):
            ea.assert_no_collisions([
                self._spec("rf_baseline_cicids2017_v1.joblib",
                           "rf-baseline-cicids2017-v2", "v1"),
                self._spec("rf_baseline_cicids2017_v2.joblib",
                           "rf-baseline-cicids2017-v2", "v2"),
            ])

    def test_the_collision_message_names_both_artifacts(self):
        from training import evaluate_artifacts as ea

        with pytest.raises(ea.RegistryCollision) as error:
            ea.assert_no_collisions([
                self._spec("a.joblib", "same-name", "v1"),
                self._spec("b.joblib", "same-name", "v2"),
            ])

        assert "a.joblib" in str(error.value)
        assert "b.joblib" in str(error.value)
        assert "UNIQUE" in str(error.value)

    def test_report_directories_are_keyed_by_artifact_not_registry_name(self):
        from training import evaluate_artifacts as ea

        first = self._spec("rf_baseline_cicids2017_v1.joblib", "shared-name", "v1")
        second = self._spec("rf_baseline_cicids2017_v2.joblib", "other-name", "v2")

        assert ea.report_dir_for(first) == "rf_baseline_cicids2017_v1"
        assert ea.report_dir_for(second) == "rf_baseline_cicids2017_v2"
        assert ea.report_dir_for(first) != ea.report_dir_for(second)

    def test_the_real_models_directory_has_no_collisions(self):
        from training import evaluate_artifacts as ea
        from tests.conftest import MODELS_DIR

        specs = ea.discover_artifacts(MODELS_DIR)
        if not specs:
            pytest.skip("models/ bosh")

        names = [spec["registry_name"] for spec in specs]
        dirs = [ea.report_dir_for(spec) for spec in specs]

        assert len(names) == len(set(names))
        assert len(dirs) == len(set(dirs))

    def test_the_historical_rf_baseline_keeps_its_notebook_identity(self):
        from training import evaluate_artifacts as ea
        from tests.conftest import MODELS_DIR

        if not (MODELS_DIR / "rf_baseline_cicids2017_v1.joblib").exists():
            pytest.skip("artefakti historik mungon")

        specs = {spec["artifact"]: spec for spec in ea.discover_artifacts(MODELS_DIR)}
        legacy = specs["rf_baseline_cicids2017_v1.joblib"]

        assert legacy["registry_name"] == "rf-baseline-cicids2017-v2"
        assert legacy["version_tag"] == "v1"
        assert legacy["label_encoder_file"] == ea.LABEL_ENCODER

    def test_the_retrained_rf_baseline_took_the_new_identity(self):
        from training import evaluate_artifacts as ea
        from tests.conftest import MODELS_DIR

        if not (MODELS_DIR / "rf_baseline_cicids2017_v2.joblib").exists():
            pytest.skip("artefakti i ri mungon")

        specs = {spec["artifact"]: spec for spec in ea.discover_artifacts(MODELS_DIR)}
        retrained = specs["rf_baseline_cicids2017_v2.joblib"]

        assert retrained["registry_name"] == "rf-baseline-cicids2017-v2-final"
        assert retrained["version_tag"] == "v2"

    def test_legacy_spec_metadata_is_never_mutated_by_discovery(self):
        from copy import deepcopy

        from training import evaluate_artifacts as ea
        from tests.conftest import MODELS_DIR

        before = deepcopy(ea.LEGACY_V1_SPECS)
        ea.discover_artifacts(MODELS_DIR)

        assert ea.LEGACY_V1_SPECS == before

    def test_every_shipped_config_name_is_unique(self):
        from pathlib import Path

        from training.pipeline import config as config_module

        config_dir = Path(__file__).resolve().parent.parent / "training" / "configs"
        names = [config_module.load(path).name
                 for path in sorted(config_dir.glob("*.yaml"))]

        assert len(names) == len(set(names))
        assert "rf-baseline-cicids2017-v2-final" in names
        assert "rf-baseline-cicids2017-v2" not in names
