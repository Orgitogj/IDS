import copy
import json

import pytest

from app.services import spring_client
from training.pipeline import historical, registration
from training.pipeline.reporting import (
    ARTIFACT_ABSENT,
    ARTIFACT_MISMATCH,
    ARTIFACT_OK,
    KIND_ARTIFACT_EVALUATION,
    REPORT_SCHEMA_VERSION,
    EvaluationReport,
    EvaluationReportError,
    sha256_of_payload,
)

MODEL_ID = "11111111-2222-3333-4444-555555555555"


def valid_payload(**overrides):
    payload = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_kind": KIND_ARTIFACT_EVALUATION,
        "generated_at": "2026-09-06T10:00:00Z",
        "evaluated_at": "2026-09-06T10:00:00Z",
        "name": "demo-model-v1",
        "version": "1.0",
        "algorithm": "XGBoost",
        "artifact_file": "demo.joblib",
        "artifact_sha256": "a" * 64,
        "feature_version": "cicids2017-78-v1",
        "n_features": 78,
        "model_params": {"n_estimators": 100},
        "dataset": {"name": "cicids2017_cleaned.parquet", "sha256": "b" * 64,
                    "subsampled": False},
        "split": {"strategy": "random", "test_size": 0.2},
        "seed": 42,
        "balancing": {"strategy": "undersample_benign_200k_oversample_rare_2k",
                      "rows_after": 653897},
        "timings": {
            "avg_latency_ms_batch": 0.0059,
            "latency_methodology": "batch predict over the test set / row count",
            "single_flow_latency": {"samples": 200, "mean_ms": 0.6, "median_ms": 0.5,
                                    "p95_ms": 0.9},
        },
        "metrics": {
            "overall": {
                "rows": 100,
                "accuracy": 0.9,
                "accuracy_sklearn": 0.9,
                "macro_precision": 0.8,
                "macro_recall": 0.7,
                "macro_f1": 0.75,
                "weighted_f1": 0.88,
            },
            "macro_f1_from_confusion_matrix": 0.75,
            "per_class": {
                "BENIGN": {"support": 60, "precision": 0.95, "recall": 0.97, "f1": 0.96},
                "DDoS": {"support": 40, "precision": 0.65, "recall": 0.43, "f1": 0.54},
            },
        },
    }
    payload.update(overrides)
    return payload


def write_report(tmp_path, payload, name="metrics.json"):
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture
def report(tmp_path):
    return EvaluationReport.from_path(write_report(tmp_path, valid_payload()))


class TestReportValidation:

    def test_a_well_formed_report_validates(self, report):
        assert report.name == "demo-model-v1"
        assert report.sample_size == 100
        assert report.feature_version == "cicids2017-78-v1"
        assert report.batch_latency_ms == 0.0059

    def test_a_missing_file_is_reported(self, tmp_path):
        with pytest.raises(EvaluationReportError, match="s'u gjet"):
            EvaluationReport.from_path(tmp_path / "nope.json")

    def test_malformed_json_is_rejected(self, tmp_path):
        path = tmp_path / "metrics.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(EvaluationReportError, match="JSON i pavlefshem"):
            EvaluationReport.from_path(path)

    def test_a_json_array_is_rejected(self, tmp_path):
        path = tmp_path / "metrics.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(EvaluationReportError, match="objekt JSON"):
            EvaluationReport.from_path(path)

    @pytest.mark.parametrize("field", ["name", "artifact_file", "metrics", "dataset",
                                       "split", "timings"])
    def test_missing_required_fields_are_rejected(self, tmp_path, field):
        payload = valid_payload()
        payload.pop(field)
        with pytest.raises(EvaluationReportError, match="mungojne"):
            EvaluationReport.from_path(write_report(tmp_path, payload))

    def test_an_unknown_schema_version_is_rejected(self, tmp_path):
        with pytest.raises(EvaluationReportError, match="schema_version"):
            EvaluationReport.from_path(
                write_report(tmp_path, valid_payload(schema_version=99)))

    def test_an_unknown_report_kind_is_rejected(self, tmp_path):
        with pytest.raises(EvaluationReportError, match="report_kind"):
            EvaluationReport.from_path(
                write_report(tmp_path, valid_payload(report_kind="guesswork")))

    def test_a_report_without_an_artifact_hash_is_rejected(self, tmp_path):
        payload = valid_payload()
        payload["artifact_sha256"] = ""
        with pytest.raises(EvaluationReportError, match="artifact_sha256"):
            EvaluationReport.from_path(write_report(tmp_path, payload))

    def test_missing_overall_metrics_are_rejected(self, tmp_path):
        payload = valid_payload()
        del payload["metrics"]["overall"]["macro_f1"]
        with pytest.raises(EvaluationReportError, match="macro_f1"):
            EvaluationReport.from_path(write_report(tmp_path, payload))

    @pytest.mark.parametrize("value", [1.5, -0.2])
    def test_metrics_outside_zero_to_one_are_rejected(self, tmp_path, value):
        payload = valid_payload()
        payload["metrics"]["overall"]["accuracy"] = value
        with pytest.raises(EvaluationReportError, match="jashte intervalit"):
            EvaluationReport.from_path(write_report(tmp_path, payload))

    def test_a_non_numeric_metric_is_rejected(self, tmp_path):
        payload = valid_payload()
        payload["metrics"]["overall"]["accuracy"] = "0.99"
        with pytest.raises(EvaluationReportError, match="s'eshte numer"):
            EvaluationReport.from_path(write_report(tmp_path, payload))

    def test_support_that_disagrees_with_row_count_is_rejected(self, tmp_path):
        payload = valid_payload()
        payload["metrics"]["per_class"]["BENIGN"]["support"] = 59
        with pytest.raises(EvaluationReportError, match="support"):
            EvaluationReport.from_path(write_report(tmp_path, payload))

    def test_a_tampered_macro_f1_is_caught_by_the_confusion_matrix(self, tmp_path):
        payload = valid_payload()
        payload["metrics"]["overall"]["macro_f1"] = 0.99
        with pytest.raises(EvaluationReportError, match="matrica e konfuzionit"):
            EvaluationReport.from_path(write_report(tmp_path, payload))

    def test_a_tampered_accuracy_is_caught_by_the_sklearn_cross_check(self, tmp_path):
        payload = valid_payload()
        payload["metrics"]["overall"]["accuracy"] = 0.95
        with pytest.raises(EvaluationReportError, match="accuracy_sklearn"):
            EvaluationReport.from_path(write_report(tmp_path, payload))

    def test_empty_per_class_metrics_are_rejected(self, tmp_path):
        payload = valid_payload()
        payload["metrics"]["per_class"] = {}
        with pytest.raises(EvaluationReportError, match="per_class"):
            EvaluationReport.from_path(write_report(tmp_path, payload))

    def test_latency_without_a_documented_methodology_is_rejected(self, tmp_path):
        payload = valid_payload()
        del payload["timings"]["latency_methodology"]
        with pytest.raises(EvaluationReportError, match="latency_methodology"):
            EvaluationReport.from_path(write_report(tmp_path, payload))


class TestProvenance:

    def test_every_requested_field_is_carried(self, report):
        provenance = report.provenance()

        for key in ("experiment_name", "model_artifact", "model_artifact_sha256",
                    "model_version", "dataset", "feature_set", "split_strategy", "seed",
                    "balancing_strategy", "hyperparameters", "evaluated_at",
                    "metrics_report", "metrics_report_sha256", "latency_methodology"):
            assert key in provenance

        assert provenance["experiment_name"] == "demo-model-v1"
        assert provenance["seed"] == 42
        assert provenance["balancing_strategy"] == \
            "undersample_benign_200k_oversample_rare_2k"

    def test_the_report_hash_is_stable_and_content_dependent(self, tmp_path):
        first = EvaluationReport.from_path(write_report(tmp_path, valid_payload()))
        assert first.report_sha256() == first.report_sha256()

        changed = valid_payload()
        changed["metrics"]["overall"]["macro_precision"] = 0.81
        second = EvaluationReport.from_path(
            write_report(tmp_path, changed, name="other.json"))

        assert first.report_sha256() != second.report_sha256()

    def test_payload_hashing_ignores_key_order(self):
        assert sha256_of_payload({"a": 1, "b": 2}) == sha256_of_payload({"b": 2, "a": 1})


class TestArtifactHashChecks:

    def _artifact(self, tmp_path, content=b"model-bytes"):
        models_dir = tmp_path / "models"
        models_dir.mkdir(exist_ok=True)
        (models_dir / "demo.joblib").write_bytes(content)
        return models_dir

    def test_a_matching_hash_passes(self, tmp_path):
        models_dir = self._artifact(tmp_path)
        from training.build_feature_reference import sha256_of

        digest = sha256_of(models_dir / "demo.joblib")
        report = EvaluationReport.from_path(
            write_report(tmp_path, valid_payload(artifact_sha256=digest)))

        assert report.verify_artifact(models_dir) == (ARTIFACT_OK, digest)
        assert registration.check_artifact(report, models_dir)[0] == ARTIFACT_OK

    def test_a_mismatched_hash_is_refused(self, tmp_path):
        models_dir = self._artifact(tmp_path)
        report = EvaluationReport.from_path(write_report(tmp_path, valid_payload()))

        status, _ = report.verify_artifact(models_dir)
        assert status == ARTIFACT_MISMATCH

        with pytest.raises(registration.ArtifactHashMismatch, match="SHA256"):
            registration.check_artifact(report, models_dir)

    def test_a_mismatch_can_be_overridden_explicitly(self, tmp_path):
        models_dir = self._artifact(tmp_path)
        report = EvaluationReport.from_path(write_report(tmp_path, valid_payload()))

        status, _ = registration.check_artifact(report, models_dir, allow_mismatch=True)
        assert status == ARTIFACT_MISMATCH

    def test_an_absent_artifact_is_refused(self, tmp_path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        report = EvaluationReport.from_path(write_report(tmp_path, valid_payload()))

        assert report.verify_artifact(models_dir)[0] == ARTIFACT_ABSENT
        with pytest.raises(registration.ArtifactHashMismatch, match="s'gjendet"):
            registration.check_artifact(report, models_dir)


class TestPayloadConstruction:

    def test_the_payload_comes_from_the_report(self, report):
        payload = registration.experiment_payload(report, MODEL_ID)

        assert payload["accuracy"] == 0.9
        assert payload["precisionScore"] == 0.8
        assert payload["recall"] == 0.7
        assert payload["f1Score"] == 0.75
        assert payload["sampleSize"] == 100
        assert payload["avgLatencyMs"] == 0.0059
        assert payload["mlModelId"] == MODEL_ID
        assert payload["notes"].startswith("provenance=")

    def test_a_raw_dict_is_refused(self, tmp_path):
        with pytest.raises(registration.RegistrationError, match="EvaluationReport"):
            registration.experiment_payload(valid_payload(), MODEL_ID)

    def test_loose_metric_kwargs_are_refused(self):
        with pytest.raises(registration.RegistrationError):
            registration.experiment_payload({"accuracy": 0.99}, MODEL_ID)

    def test_the_payload_keys_match_the_backend_contract(self, report):
        payload = registration.experiment_payload(report, MODEL_ID)
        assert set(payload) <= set(spring_client.EXPERIMENT_PAYLOAD_KEYS)

    def test_notes_stay_within_the_column_budget(self, report):
        payload = registration.experiment_payload(report, MODEL_ID)
        assert len(payload["notes"]) <= registration.MAX_NOTES_CHARS

    def test_oversized_provenance_drops_hyperparameters_rather_than_truncating(self,
                                                                              tmp_path):
        payload = valid_payload()
        payload["model_params"] = {f"param_{i}": "x" * 200 for i in range(80)}
        report = EvaluationReport.from_path(write_report(tmp_path, payload))

        notes = registration.build_notes(report)
        decoded = json.loads(notes[len(registration.NOTES_PREFIX):])

        assert len(notes) <= registration.MAX_NOTES_CHARS
        assert "hyperparameters" not in decoded
        assert decoded["experiment_name"] == "demo-model-v1"
        assert decoded["model_artifact_sha256"]


class TestManualMetricsAreRefused:

    def test_the_old_loose_kwargs_function_now_raises(self):
        with pytest.raises(NotImplementedError, match="EvaluationReport"):
            spring_client.record_experiment_result(
                ml_model_id=MODEL_ID, tested_on_dataset="CICIDS2017",
                accuracy=0.99, precision=0.9, recall=0.9, f1=0.9)

    def test_a_payload_without_provenance_is_refused(self):
        with pytest.raises(ValueError, match="Metrikat"):
            spring_client.create_experiment_result({
                "mlModelId": MODEL_ID, "testedOnDataset": "CICIDS2017",
                "accuracy": 0.99, "precisionScore": 0.9, "recall": 0.9,
                "f1Score": 0.9, "notes": "typed by hand",
            })

    def test_unknown_payload_fields_are_refused(self, report):
        payload = registration.experiment_payload(report, MODEL_ID)
        payload["somethingElse"] = 1
        with pytest.raises(ValueError, match="Fusha te panjohura"):
            spring_client.create_experiment_result(payload)

    def test_a_non_dict_payload_is_refused(self):
        with pytest.raises(TypeError):
            spring_client.create_experiment_result("accuracy=0.99")


class TestDryRun:

    def test_dry_run_never_calls_the_client(self, tmp_path, report, monkeypatch):
        from training.build_feature_reference import sha256_of

        models_dir = tmp_path / "models"
        models_dir.mkdir(exist_ok=True)
        (models_dir / "demo.joblib").write_bytes(b"model-bytes")
        digest = sha256_of(models_dir / "demo.joblib")
        report = EvaluationReport.from_path(
            write_report(tmp_path, valid_payload(artifact_sha256=digest)))

        calls = []

        class Recorder:
            def create_experiment_result(self, payload):
                calls.append(payload)
                return {"id": "written"}

        outcome = registration.register(report, MODEL_ID, Recorder(), models_dir,
                                        dry_run=True)

        assert calls == []
        assert outcome["written"] is False
        assert outcome["response"] is None
        assert outcome["payload"]["accuracy"] == 0.9

    def test_dry_run_makes_no_http_request_at_all(self, tmp_path, monkeypatch):
        from training.build_feature_reference import sha256_of

        models_dir = tmp_path / "models"
        models_dir.mkdir(exist_ok=True)
        (models_dir / "demo.joblib").write_bytes(b"model-bytes")
        digest = sha256_of(models_dir / "demo.joblib")
        report = EvaluationReport.from_path(
            write_report(tmp_path, valid_payload(artifact_sha256=digest)))

        def explode(*args, **kwargs):
            raise AssertionError("dry-run must not touch the network")

        monkeypatch.setattr(spring_client.requests, "request", explode)
        monkeypatch.setattr(spring_client, "_request", explode)

        outcome = registration.register(report, MODEL_ID, spring_client, models_dir,
                                        dry_run=True)
        assert outcome["written"] is False

    def test_commit_calls_the_client_once(self, tmp_path):
        from training.build_feature_reference import sha256_of

        models_dir = tmp_path / "models"
        models_dir.mkdir(exist_ok=True)
        (models_dir / "demo.joblib").write_bytes(b"model-bytes")
        digest = sha256_of(models_dir / "demo.joblib")
        report = EvaluationReport.from_path(
            write_report(tmp_path, valid_payload(artifact_sha256=digest)))

        calls = []

        class Recorder:
            def create_experiment_result(self, payload):
                calls.append(payload)
                return {"id": "new-row"}

        outcome = registration.register(report, MODEL_ID, Recorder(), models_dir,
                                        dry_run=False)

        assert len(calls) == 1
        assert outcome["written"] is True
        assert outcome["response"]["id"] == "new-row"


class TestModelResolution:

    def test_a_model_is_found_by_registry_name(self, report):
        models = [{"id": "abc", "name": "demo-model-v1", "artifactPath": "models/x.joblib"}]
        model_id, entry = registration.resolve_model_id(models, report)

        assert model_id == "abc"
        assert entry["name"] == "demo-model-v1"

    def test_a_model_is_found_by_artifact_filename(self, report):
        models = [{"id": "def", "name": "other-name",
                   "artifactPath": "models/demo.joblib"}]
        model_id, _ = registration.resolve_model_id(models, report)

        assert model_id == "def"

    def test_an_unknown_model_resolves_to_nothing(self, report):
        model_id, entry = registration.resolve_model_id([], report)

        assert model_id is None
        assert entry is None


class TestHistoricalRecord:

    def test_the_hardcoded_rf_baseline_fields_are_named(self):
        assert historical.hardcoded_fields("rf-baseline-cicids2017-v2") == [
            "accuracy", "avgLatencyMs", "f1Score"]

    def test_the_computed_rf_baseline_fields_are_not_flagged(self):
        hardcoded = historical.hardcoded_fields("rf-baseline-cicids2017-v2")
        assert "precisionScore" not in hardcoded
        assert "recall" not in hardcoded

    def test_the_stored_values_are_the_ones_from_the_notebook(self):
        assert historical.stored_value("rf-baseline-cicids2017-v2", "accuracy") == 0.9986
        assert historical.stored_value("rf-baseline-cicids2017-v2", "f1Score") == 0.8724
        assert historical.stored_value("rf-baseline-cicids2017-v2",
                                       "avgLatencyMs") == 0.0054

    def test_an_unknown_model_has_no_stored_record(self):
        assert historical.stored_for("does-not-exist") is None
        assert historical.hardcoded_fields("does-not-exist") == []


class TestIsolationForestSeparation:

    def test_anomaly_detectors_are_marked_and_excluded(self):
        from training.evaluate_artifacts import LEGACY_V1_SPECS as ARTIFACT_SPECS, KIND_ANOMALY

        anomaly = [spec for spec in ARTIFACT_SPECS if spec["kind"] == KIND_ANOMALY]
        assert {spec["artifact"] for spec in anomaly} == {
            "isolation_forest_cicids2017_v1.joblib",
            "isolation_forest_benign_v2.joblib"}

        for spec in anomaly:
            assert spec["excluded_reason"]
            assert spec["labels"] is None

    def test_every_multiclass_spec_declares_a_label_mode(self):
        from training.evaluate_artifacts import (LEGACY_V1_SPECS as ARTIFACT_SPECS,
                                                 KIND_MULTICLASS,
                                                 LABELS_AS_ENCODED, LABELS_AS_STRINGS)

        multiclass = [spec for spec in ARTIFACT_SPECS
                      if spec["kind"] == KIND_MULTICLASS]
        assert multiclass
        for spec in multiclass:
            assert spec["labels"] in (LABELS_AS_STRINGS, LABELS_AS_ENCODED)

    def test_only_the_mlp_declares_a_scaler(self):
        from training.evaluate_artifacts import LEGACY_V1_SPECS as ARTIFACT_SPECS

        needing = [spec["artifact"] for spec in ARTIFACT_SPECS if spec["needs_scaler"]]
        assert needing == ["mlp_smote_cicids2017_v1.joblib"]


@pytest.mark.artifacts
@pytest.mark.dataset
class TestRecomputationIsDeterministic:

    def test_the_rf_baseline_recomputation_repeats_exactly(self):
        import joblib
        import numpy as np
        import pandas as pd

        from tests.conftest import DATASET_PATH, MODELS_DIR
        from training.pipeline import splitting
        from training.pipeline.data import LoadedDataset, clean_labels
        from training.evaluate_artifacts import decode_predictions, LABELS_AS_STRINGS

        artifact = MODELS_DIR / "rf_baseline_cicids2017_v1.joblib"
        if not artifact.exists():
            pytest.skip("rf_baseline_cicids2017_v1.joblib mungon")

        model = joblib.load(artifact)
        columns = [str(name) for name in model.feature_names_in_]

        labels = clean_labels(
            pd.read_parquet(DATASET_PATH, columns=["Label"])["Label"].to_numpy())
        frame = pd.read_parquet(DATASET_PATH, columns=columns)
        features = frame[columns].to_numpy(dtype="float32")
        del frame

        dataset = LoadedDataset(features, labels, columns)
        _, test_idx = splitting.split_indices(dataset, "random", 0.2, 42)
        sample = test_idx[:5000]

        spec = {"labels": LABELS_AS_STRINGS}
        first = decode_predictions(model.predict(features[sample]), spec, None)
        second = decode_predictions(model.predict(features[sample]), spec, None)

        np.testing.assert_array_equal(first, second)
        assert len(test_idx) == 565_576
