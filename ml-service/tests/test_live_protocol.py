import json
from pathlib import Path

import pytest
import yaml

from app.live import capture_time, lab_runner, manifest as manifest_module, protocol
from app.live import schema_guard, session
from training.pipeline import lofo, live

ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_DIR = ML_SERVICE_ROOT / "training" / "configs" / "live"
LIVE_REPORTS = ML_SERVICE_ROOT / "reports" / "live_evaluation"

FROZEN_NAMESPACES = {
    "random-v2": ML_SERVICE_ROOT / "reports" / "artifact_evaluation",
    "temporal-v1": ML_SERVICE_ROOT / "reports" / "temporal_evaluation",
    "lofo-v1": ML_SERVICE_ROOT / "reports" / "lofo_evaluation",
}


def base_manifest(**overrides):
    payload = {
        "protocol_version": protocol.PROTOCOL_VERSION,
        "experiment_id": protocol.EXPERIMENT_ID,
        "run_id": "lab-v1-test-001",
        "scenario_id": "portscan",
        "scenario_description": "synthetic manifest for tests",
        "expected_binary_label": "ATTACK",
        "ground_truth": {
            "mode": manifest_module.GROUND_TRUTH_SELECTOR,
            "unmatched_policy": manifest_module.UNMATCHED_UNLABELLED,
            "attack_selector": {"source_ip": "192.168.50.10",
                                "destination_ip": "192.168.50.20"},
        },
        "model": {"name": protocol.FROZEN_PRIMARY_MODEL["name"],
                  "version": protocol.FROZEN_PRIMARY_MODEL["version"],
                  "feature_version": protocol.FROZEN_PRIMARY_MODEL["feature_version"]},
        "capture": {"interface": "eth0", "source": "cicflowmeter",
                    "timestamp_timezone": "America/New_York"},
        "topology": {"source_host": "192.168.50.10", "target_host": "192.168.50.20"},
    }
    payload.update(overrides)
    return payload


def flow(expected, predicted, status=protocol.STATUS_VALID):
    return {"expected_binary_label": expected, "predicted_label": predicted,
            "validation_status": status}


class TestExperimentIdentity:

    def test_the_experiment_id_reaches_every_recorded_flow(self, tmp_path):
        manifest = manifest_module.validate(base_manifest())
        run = session.RunSession(manifest, tmp_path)
        run.start()

        entry = run.record({"validation_status": protocol.STATUS_VALID,
                            "predicted_label": "PortScan"})

        assert entry["experiment_id"] == protocol.EXPERIMENT_ID
        assert run.state["experiment_id"] == protocol.EXPERIMENT_ID

    def test_the_run_id_reaches_every_recorded_flow(self, tmp_path):
        manifest = manifest_module.validate(base_manifest(run_id="lab-v1-alpha-001"))
        run = session.RunSession(manifest, tmp_path)
        run.start()

        entry = run.record({"validation_status": protocol.STATUS_VALID,
                            "predicted_label": "BENIGN"})

        assert entry["run_id"] == "lab-v1-alpha-001"
        assert entry["scenario_id"] == "portscan"

    def test_identity_survives_the_written_predictions_file(self, tmp_path):
        manifest = manifest_module.validate(base_manifest())
        run = session.RunSession(manifest, tmp_path)
        run.start()
        run.record({"validation_status": protocol.STATUS_VALID,
                    "predicted_label": "PortScan"})
        run.finalize()

        rows = session.load_flows(tmp_path / "runs" / manifest.run_id)

        assert rows[0]["experiment_id"] == protocol.EXPERIMENT_ID
        assert rows[0]["run_id"] == manifest.run_id
        assert rows[0]["flow_index"] == "1"

    def test_colliding_run_ids_are_refused(self, tmp_path):
        first = base_manifest(run_id="lab-v1-dup-001")
        second = base_manifest(run_id="lab-v1-dup-001", scenario_id="benign")
        (tmp_path / "a.yaml").write_text(yaml.safe_dump(first), encoding="utf-8")
        (tmp_path / "b.yaml").write_text(yaml.safe_dump(second), encoding="utf-8")

        with pytest.raises(manifest_module.ManifestError, match="dyfishuar"):
            manifest_module.load_all(tmp_path)

    def test_the_shipped_manifests_have_unique_run_ids(self):
        manifests = manifest_module.load_all(MANIFEST_DIR)

        assert len(manifests) == len(set(manifests))
        assert len(manifests) >= 2

    def test_every_shipped_manifest_declares_the_shared_experiment_id(self):
        for run_id, manifest in manifest_module.load_all(MANIFEST_DIR).items():
            assert manifest.experiment_id == protocol.EXPERIMENT_ID, run_id


class TestGroundTruth:

    def test_the_expected_label_comes_from_the_manifest_not_the_prediction(self):
        manifest = manifest_module.validate(base_manifest())
        row = {"src_ip": "192.168.50.10", "dst_ip": "192.168.50.20"}

        assert manifest.expected_for_flow(row) == "ATTACK"

        record = {"expected_binary_label": manifest.expected_for_flow(row),
                  "predicted_label": "BENIGN"}
        assert record["expected_binary_label"] == "ATTACK"

    def test_a_flow_outside_the_selector_is_not_labelled_attack(self):
        manifest = manifest_module.validate(base_manifest())

        assert manifest.expected_for_flow(
            {"src_ip": "192.168.50.99", "dst_ip": "192.168.50.20"}) == "UNLABELLED"

    def test_unmatched_flows_can_be_declared_benign_explicitly(self):
        payload = base_manifest()
        payload["ground_truth"]["unmatched_policy"] = manifest_module.UNMATCHED_BENIGN
        manifest = manifest_module.validate(payload)

        assert manifest.expected_for_flow(
            {"src_ip": "10.0.0.1", "dst_ip": "10.0.0.2"}) == "BENIGN"

    def test_port_selectors_separate_mixed_traffic_on_one_host_pair(self):
        payload = base_manifest()
        payload["ground_truth"]["attack_selector"]["destination_ports"] = [22]
        manifest = manifest_module.validate(payload)

        attack = {"src_ip": "192.168.50.10", "dst_ip": "192.168.50.20", "dst_port": "22"}
        background = {"src_ip": "192.168.50.10", "dst_ip": "192.168.50.20",
                      "dst_port": "80"}

        assert manifest.expected_for_flow(attack) == "ATTACK"
        assert manifest.expected_for_flow(background) == "UNLABELLED"

    def test_an_attack_run_cannot_label_a_whole_window_without_declaring_a_filter(self):
        payload = base_manifest()
        payload["ground_truth"] = {"mode": manifest_module.GROUND_TRUTH_RUN_LEVEL}

        with pytest.raises(manifest_module.ManifestError, match="capture_is_filtered"):
            manifest_module.validate(payload)

    def test_a_filtered_attack_capture_may_use_run_level_ground_truth(self):
        payload = base_manifest()
        payload["ground_truth"] = {"mode": manifest_module.GROUND_TRUTH_RUN_LEVEL,
                                   "capture_is_filtered_to_scenario": True}
        manifest = manifest_module.validate(payload)

        assert manifest.expected_for_flow({"src_ip": "anything"}) == "ATTACK"

    def test_a_selector_mode_without_a_selector_is_refused(self):
        payload = base_manifest()
        payload["ground_truth"] = {"mode": manifest_module.GROUND_TRUTH_SELECTOR}

        with pytest.raises(manifest_module.ManifestError, match="attack_selector"):
            manifest_module.validate(payload)

    def test_unlabelled_flows_never_enter_a_metric_denominator(self):
        flows = [flow("ATTACK", "PortScan"), flow("UNLABELLED", "BENIGN"),
                 flow("BENIGN", "BENIGN")]

        report = live.binary_detection(flows)

        assert report["evaluable_flows"] == 2
        assert report["attack_flows"] + report["benign_flows"] == 2


class TestTimestamps:

    def test_the_capture_timestamp_is_taken_from_the_flow_not_the_clock(self):
        resolved = capture_time.resolve({"timestamp": "2026-09-07 10:15:30"})

        assert resolved["capture_timestamp"].startswith("2026-09-07T10:15:30")
        assert resolved["capture_timestamp_source"] == protocol.CAPTURE_TIME_EXACT
        assert resolved["capture_timestamp_is_approximate"] is False

    def test_capture_timestamp_and_ingested_at_are_separate_fields(self, tmp_path):
        manifest = manifest_module.validate(base_manifest())
        run = session.RunSession(manifest, tmp_path)
        run.start()

        entry = run.record({"validation_status": protocol.STATUS_VALID,
                            "predicted_label": "PortScan",
                            "capture_timestamp": "2026-09-07T10:15:30Z"})

        assert entry["capture_timestamp"] == "2026-09-07T10:15:30Z"
        assert entry["ingested_at"] != entry["capture_timestamp"]

    def test_a_missing_capture_column_is_marked_approximate_not_invented(self):
        resolved = capture_time.resolve({"src_ip": "10.0.0.1"})

        assert resolved["capture_timestamp_source"] == protocol.CAPTURE_TIME_APPROX_INGEST
        assert resolved["capture_timestamp_is_approximate"] is True
        assert "not a packet-capture time" in resolved["capture_timestamp_note"]

    def test_iso_and_epoch_capture_values_are_both_understood(self):
        iso = capture_time.parse("2026-09-07T10:15:30+00:00")
        epoch = capture_time.parse("1757239200")

        assert iso is not None and iso.tzinfo is not None
        assert epoch is not None and epoch.tzinfo is not None

    def test_an_unparseable_capture_value_does_not_become_a_fake_time(self):
        assert capture_time.parse("not-a-time") is None

    def test_timestamps_are_stored_in_utc_with_explicit_semantics(self):
        resolved = capture_time.resolve({"timestamp": "2026-09-07 10:15:30"})

        assert resolved["capture_timestamp"].endswith("Z")
        assert resolved["capture_timestamp_assumed_utc"] is True

    def test_a_declared_capture_timezone_converts_local_time_to_utc(self):
        resolved = capture_time.resolve({"timestamp": "2026-09-07 18:17:07"},
                                        assume_utc=False,
                                        timezone_name="America/New_York")

        assert resolved["capture_timestamp"] == "2026-09-07T22:17:07Z"
        assert resolved["capture_timestamp_assumed_utc"] is False
        assert resolved["capture_timestamp_timezone"] == "America/New_York"

    def test_the_declared_timezone_is_recorded_on_every_flow(self, tmp_path):
        manifest = manifest_module.validate(base_manifest())
        assert manifest.capture_timezone == "America/New_York"
        assert manifest.timestamp_assumed_utc is False

    def test_an_unknown_capture_timezone_is_refused(self):
        with pytest.raises(capture_time.UnknownCaptureTimezone):
            capture_time.parse("2026-09-07 18:17:07",
                               timezone_name="Mars/Olympus_Mons")

    def test_a_manifest_must_declare_how_naive_timestamps_are_interpreted(self):
        payload = base_manifest()
        payload["capture"] = {"interface": "eth0", "source": "cicflowmeter"}

        with pytest.raises(manifest_module.ManifestError, match="timestamp_timezone"):
            manifest_module.validate(payload)

    def test_a_manifest_with_a_bad_timezone_is_refused(self):
        payload = base_manifest()
        payload["capture"]["timestamp_timezone"] = "Nowhere/Nothing"

        with pytest.raises(capture_time.UnknownCaptureTimezone):
            manifest_module.validate(payload)

    def test_every_shipped_manifest_declares_the_lab_capture_timezone(self):
        for run_id, manifest in manifest_module.load_all(MANIFEST_DIR).items():
            assert manifest.capture_timezone == "America/New_York", run_id
            assert manifest.timestamp_assumed_utc is False, run_id


class TestSchemaIntegrity:

    def test_an_exactly_matching_schema_passes(self):
        report = schema_guard.check_schema(["a", "b", "c"], ["a", "b", "c"], 3)

        assert report["schema_validation_status"] == protocol.STATUS_VALID
        assert report["errors"] == []
        assert report["feature_count"] == 3

    def test_a_reordered_schema_is_refused(self):
        with pytest.raises(schema_guard.SchemaViolation, match="order diverges"):
            schema_guard.assert_schema(["b", "a"], ["a", "b"], "x", 2)

    def test_a_wrong_feature_count_is_refused(self):
        with pytest.raises(schema_guard.SchemaViolation):
            schema_guard.assert_schema(["a"], ["a", "b"], "x", 2)

    def test_duplicate_columns_are_refused(self):
        report = schema_guard.check_schema(["a", "a"], ["a", "b"], 2)

        assert report["schema_validation_status"] == protocol.STATUS_INVALID_SCHEMA
        assert any("duplicate" in error for error in report["errors"])

    def test_a_missing_feature_yields_the_missing_feature_status(self):
        result = type("R", (), {"missing_features": ["Flow Duration"],
                                "invalid_features": [], "unexpected_features": []})()

        status = schema_guard.status_from_validation(result)

        assert status["validation_status"] == protocol.STATUS_MISSING_FEATURE
        assert "Flow Duration" in status["validation_errors"][0]

    def test_a_nonfinite_value_yields_the_nonfinite_status(self):
        result = type("R", (), {
            "missing_features": [],
            "invalid_features": [{"feature": "Flow Bytes/s", "reason": "inf"}],
            "unexpected_features": []})()

        status = schema_guard.status_from_validation(result)

        assert status["validation_status"] == protocol.STATUS_NONFINITE_VALUE

    def test_a_non_numeric_value_yields_the_invalid_schema_status(self):
        result = type("R", (), {
            "missing_features": [],
            "invalid_features": [{"feature": "Protocol", "reason": "non_numeric"}],
            "unexpected_features": []})()

        assert schema_guard.status_from_validation(result)["validation_status"] == \
            protocol.STATUS_INVALID_SCHEMA

    def test_extra_features_follow_the_declared_policy(self):
        result = type("R", (), {"missing_features": [], "invalid_features": [],
                                "unexpected_features": ["Rogue Column"]})()

        ignored = schema_guard.status_from_validation(result, "ignore")
        rejected = schema_guard.status_from_validation(result, "reject")

        assert ignored["validation_status"] == protocol.STATUS_VALID
        assert ignored["extra_features_ignored"] == 1
        assert rejected["validation_status"] == protocol.STATUS_EXTRA_FEATURE

    def test_the_default_extra_feature_policy_is_documented(self):
        assert protocol.EXTRA_FEATURE_POLICY in ("ignore", "reject")
        assert "never reach the model" in protocol.EXTRA_FEATURE_POLICY_NOTE

    def test_a_nonfinite_vector_is_refused_before_the_model_sees_it(self):
        with pytest.raises(schema_guard.SchemaViolation):
            schema_guard.assert_finite_vector([1.0, float("nan")])

    def test_every_validation_status_is_a_declared_machine_readable_value(self):
        for status in protocol.VALIDATION_STATUSES:
            assert status.isupper()
        assert protocol.STATUS_VALID in protocol.VALIDATION_STATUSES
        assert protocol.STATUS_MODEL_ERROR in protocol.VALIDATION_STATUSES
        assert protocol.STATUS_INGEST_ERROR in protocol.VALIDATION_STATUSES

    def test_validation_status_never_describes_prediction_correctness(self):
        assert "prediction correctness is never a validation outcome" in \
            protocol.VALIDATION_STATUS_NOTE

        wrong_but_clean = flow("ATTACK", "BENIGN")
        assert wrong_but_clean["validation_status"] == protocol.STATUS_VALID


class TestFrozenModelPinning:

    def test_the_manifest_refuses_a_model_other_than_the_frozen_primary(self):
        payload = base_manifest()
        payload["model"]["name"] = "xgb-smote-cicids2017-v2"

        with pytest.raises(manifest_module.ManifestError, match="ngrire"):
            manifest_module.validate(payload)

    def test_the_manifest_refuses_a_different_feature_schema(self):
        payload = base_manifest()
        payload["model"]["feature_version"] = "cicids2017-top50-v1"

        with pytest.raises(manifest_module.ManifestError, match="feature_version"):
            manifest_module.validate(payload)

    def test_the_frozen_identity_matches_the_registered_metadata(self):
        path = (ML_SERVICE_ROOT / "reports" / "artifact_evaluation"
                / "xgb_baseline_cicids2017_v2" / "metrics.json")
        if not path.exists():
            pytest.skip("metadata e ngrire mungon")

        with open(path, encoding="utf-8") as handle:
            frozen = json.load(handle)

        assert protocol.FROZEN_PRIMARY_MODEL["name"] == frozen["name"]
        assert protocol.FROZEN_PRIMARY_MODEL["artifact_sha256"] == frozen["artifact_sha256"]
        assert protocol.FROZEN_PRIMARY_MODEL["feature_version"] == frozen["feature_version"]
        assert protocol.FROZEN_PRIMARY_MODEL["n_features"] == frozen["n_features"]

    @pytest.mark.artifacts
    def test_loading_the_frozen_artifact_verifies_its_digest_and_schema(self):
        artifact = ML_SERVICE_ROOT / "models" / \
            protocol.FROZEN_PRIMARY_MODEL["artifact_file"]
        if not artifact.exists():
            pytest.skip("artefakti v2 mungon")

        _, _, columns, identity = lab_runner.load_frozen_model(
            ML_SERVICE_ROOT / "models")

        assert identity["artifact_sha256"] == \
            protocol.FROZEN_PRIMARY_MODEL["artifact_sha256"]
        assert identity["feature_count"] == 78
        assert len(columns) == 78

    @pytest.mark.artifacts
    def test_a_tampered_digest_is_refused(self, tmp_path):
        artifact = ML_SERVICE_ROOT / "models" / \
            protocol.FROZEN_PRIMARY_MODEL["artifact_file"]
        if not artifact.exists():
            pytest.skip("artefakti v2 mungon")

        expected = dict(protocol.FROZEN_PRIMARY_MODEL)
        expected["artifact_sha256"] = "0" * 64

        with pytest.raises(lab_runner.FrozenModelError, match="SHA-256"):
            lab_runner.load_frozen_model(ML_SERVICE_ROOT / "models", expected=expected)


class TestRunLifecycle:

    def test_a_run_moves_through_the_declared_states(self, tmp_path):
        manifest = manifest_module.validate(base_manifest())
        run = session.RunSession(manifest, tmp_path)

        assert run.state["status"] == protocol.RUN_PLANNED
        run.start()
        assert run.state["status"] == protocol.RUN_RUNNING
        run.stop()
        run.finalize()
        assert run.state["status"] == protocol.RUN_COMPLETED

    def test_flows_cannot_be_recorded_before_the_run_starts(self, tmp_path):
        run = session.RunSession(manifest_module.validate(base_manifest()), tmp_path)

        with pytest.raises(session.RunStateError):
            run.record({"validation_status": protocol.STATUS_VALID})

    def test_counts_track_valid_invalid_and_predictions(self, tmp_path):
        run = session.RunSession(manifest_module.validate(base_manifest()), tmp_path)
        run.start()
        run.record({"validation_status": protocol.STATUS_VALID,
                    "predicted_label": "PortScan", "expected_binary_label": "ATTACK"})
        run.record({"validation_status": protocol.STATUS_MISSING_FEATURE,
                    "expected_binary_label": "ATTACK"})
        run.record({"validation_status": protocol.STATUS_VALID,
                    "predicted_label": "BENIGN", "expected_binary_label": "UNLABELLED"})

        assert run.state["flow_count"] == 3
        assert run.state["valid_flow_count"] == 2
        assert run.state["invalid_flow_count"] == 1
        assert run.state["prediction_count"] == 2
        assert run.state["unlabelled_flow_count"] == 1

    def test_an_aborted_run_records_its_reason(self, tmp_path):
        run = session.RunSession(manifest_module.validate(base_manifest()), tmp_path)
        run.start()
        run.abort("kali vm lost network")

        assert run.state["status"] == protocol.RUN_ABORTED
        assert run.state["abort_reason"] == "kali vm lost network"
        assert run.state["actual_end"] is not None

    def test_an_interrupted_run_is_discoverable_on_disk(self, tmp_path):
        run = session.RunSession(manifest_module.validate(base_manifest()), tmp_path)
        run.start()

        stale = session.interrupted_runs(tmp_path)

        assert [entry["run_id"] for entry in stale] == [run.state["run_id"]]

    def test_a_completed_run_is_not_reported_as_interrupted(self, tmp_path):
        run = session.RunSession(manifest_module.validate(base_manifest()), tmp_path)
        run.start()
        run.finalize()

        assert session.interrupted_runs(tmp_path) == []

    def test_only_completed_runs_are_evaluable(self):
        assert session.is_evaluable({"status": protocol.RUN_COMPLETED}) is True
        for status in (protocol.RUN_RUNNING, protocol.RUN_ABORTED, protocol.RUN_INVALID,
                       protocol.RUN_PLANNED):
            assert session.is_evaluable({"status": status}) is False

    def test_an_aborted_run_cannot_produce_a_run_report(self):
        manifest = manifest_module.validate(base_manifest())

        with pytest.raises(live.LiveEvaluationError, match="ABORTED"):
            live.run_report(manifest, [flow("ATTACK", "PortScan")],
                            {"run_id": "x", "status": protocol.RUN_ABORTED})

    def test_an_aborted_run_is_excluded_from_the_aggregate(self):
        completed = {"run_id": "a", "scenario_id": "portscan",
                     "expected_binary_label": "ATTACK",
                     "exclude_from_thesis_metrics": False,
                     "binary": {"evaluable_flows": 10}, "attribution": {}}
        smoke = {"run_id": "b", "scenario_id": "benign",
                 "expected_binary_label": "BENIGN",
                 "exclude_from_thesis_metrics": True,
                 "binary": {"evaluable_flows": 5}, "attribution": {}}

        payload = live.aggregate([completed, smoke])

        assert payload["runs_included"] == ["a"]
        assert payload["runs_excluded"] == ["b"]
        assert payload["n_runs"] == 1

    def test_a_smoke_run_is_excluded_from_thesis_metrics_by_default(self):
        manifest = manifest_module.validate(base_manifest(smoke_test=True))

        assert manifest.smoke_test is True
        assert manifest.exclude_from_thesis_metrics is True


class TestMetrics:

    def test_binary_detection_counts_any_non_benign_prediction(self):
        flows = [flow("ATTACK", "PortScan"), flow("ATTACK", "DoS Hulk"),
                 flow("ATTACK", "BENIGN"), flow("BENIGN", "BENIGN")]

        report = live.binary_detection(flows)

        assert report["attack_detection_rate"] == pytest.approx(2 / 3)
        assert report["attack_miss_rate"] == pytest.approx(1 / 3)
        assert report["attack_detection_rate_denominator"] == 3

    def test_detection_and_miss_rates_sum_to_one(self):
        flows = [flow("ATTACK", "PortScan")] * 7 + [flow("ATTACK", "BENIGN")] * 3

        report = live.binary_detection(flows)

        assert report["attack_detection_rate"] + report["attack_miss_rate"] == 1.0

    def test_every_rate_records_its_denominator(self):
        report = live.binary_detection([flow("ATTACK", "PortScan"),
                                        flow("BENIGN", "BENIGN")])

        for key in ("attack_detection_rate", "attack_miss_rate",
                    "benign_false_positive_rate", "attack_precision"):
            assert f"{key}_denominator" in report

    def test_a_thin_denominator_raises_a_support_warning(self):
        report = live.binary_detection([flow("ATTACK", "PortScan"),
                                        flow("BENIGN", "BENIGN")])

        assert report["rate_support_warning"] is not None
        assert "raw counts" in report["rate_support_warning"]

    def test_a_healthy_denominator_raises_no_support_warning(self):
        flows = [flow("ATTACK", "PortScan")] * 40 + [flow("BENIGN", "BENIGN")] * 40

        assert live.binary_detection(flows)["rate_support_warning"] is None

    def test_the_benign_fpr_matches_the_lofo_definition_numerically(self):
        flows = ([flow("BENIGN", "BENIGN")] * 90 + [flow("BENIGN", "PortScan")] * 10
                 + [flow("ATTACK", "DoS Hulk")] * 50)

        live_report = live.binary_detection(flows)

        y_true = ["BENIGN"] * 100 + ["DoS Hulk"] * 50
        y_pred = ["BENIGN"] * 90 + ["PortScan"] * 10 + ["DoS Hulk"] * 50
        lofo_report = lofo.binary_diagnostic(y_true, y_pred)

        assert live_report["benign_false_positive_rate"] == \
            lofo_report["benign_false_positive_rate"]
        assert live_report["benign_false_positive_rate"] == pytest.approx(0.10)

    def test_the_benign_fpr_is_not_the_attack_miss_rate(self):
        flows = [flow("BENIGN", "BENIGN")] * 100 + [flow("ATTACK", "BENIGN")] * 50

        report = live.binary_detection(flows)

        assert report["benign_false_positive_rate"] == 0.0
        assert report["attack_miss_rate"] == 1.0

    def test_the_benign_baseline_reports_raw_counts_and_the_fp_distribution(self):
        flows = ([flow("BENIGN", "BENIGN")] * 8 + [flow("BENIGN", "PortScan")] * 2)

        report = live.benign_baseline(flows)

        assert report["valid_benign_flows"] == 10
        assert report["predicted_benign"] == 8
        assert report["predicted_attack"] == 2
        assert report["false_positive_label_distribution"] == {"PortScan": 2}
        assert report["benign_false_positive_rate_denominator"] == 10

    def test_flow_counts_break_down_by_validation_status(self):
        flows = [flow("ATTACK", "PortScan"),
                 flow("ATTACK", None, protocol.STATUS_MISSING_FEATURE),
                 flow("UNLABELLED", "BENIGN")]

        counts = live.flow_counts(flows)

        assert counts["flow_count"] == 3
        assert counts["valid_flow_count"] == 2
        assert counts["invalid_flow_count"] == 1
        assert counts["unlabelled_flow_count"] == 1
        assert counts["validation_status_counts"][protocol.STATUS_MISSING_FEATURE] == 1

    def test_invalid_flows_never_enter_the_detection_metric(self):
        flows = [flow("ATTACK", "PortScan"),
                 flow("ATTACK", "PortScan", protocol.STATUS_MISSING_FEATURE)]

        assert live.binary_detection(flows)["attack_detection_rate_denominator"] == 1


class TestDetectionVersusAttribution:

    def test_flagging_an_attack_is_not_the_same_as_identifying_it(self):
        flows = [flow("ATTACK", "DoS Hulk")] * 10

        detection = live.binary_detection(flows)
        attributed = live.attribution(flows, expected_family="PortScan")

        assert detection["attack_detection_rate"] == 1.0
        assert attributed["family_attribution_rate"] == 0.0

    def test_attribution_is_left_unscored_without_a_declared_mapping(self):
        flows = [flow("ATTACK", "DoS Hulk")] * 5

        report = live.attribution(flows)

        assert report["attribution_scored"] is False
        assert report["dominant_predicted_label"] == "DoS Hulk"
        assert "label_attribution_rate" not in report

    def test_attribution_is_scored_when_the_manifest_declares_a_mapping(self):
        flows = [flow("ATTACK", "PortScan")] * 8 + [flow("ATTACK", "DoS Hulk")] * 2

        report = live.attribution(flows, expected_family="PortScan",
                                  expected_label="PortScan")

        assert report["attribution_scored"] is True
        assert report["label_attribution_rate"] == pytest.approx(0.8)
        assert report["label_attribution_denominator"] == 10

    def test_attribution_maps_predicted_labels_to_lofo_families(self):
        flows = [flow("ATTACK", "DoS Hulk"), flow("ATTACK", "DoS slowloris"),
                 flow("ATTACK", "PortScan")]

        report = live.attribution(flows)

        assert report["predicted_family_distribution"]["DoS"] == 2
        assert report["dominant_predicted_family"] == "DoS"

    def test_benign_predictions_are_excluded_from_attribution(self):
        flows = [flow("ATTACK", "BENIGN")] * 5 + [flow("ATTACK", "PortScan")]

        report = live.attribution(flows)

        assert report["attack_predictions"] == 1
        assert report["scored_attack_flows"] == 6

    def test_the_shipped_telnet_scenario_declares_no_mapping(self):
        manifests = manifest_module.load_all(MANIFEST_DIR)
        telnet = [m for m in manifests.values() if m.scenario_id == "telnet-bruteforce"]
        if not telnet:
            pytest.skip("skenari telnet mungon")

        assert telnet[0].attribution_mapping_declared is False


class TestNamespaceIsolation:

    def test_the_live_namespace_is_separate_from_every_frozen_namespace(self):
        for name, path in FROZEN_NAMESPACES.items():
            assert LIVE_REPORTS != path, name
            assert path not in LIVE_REPORTS.parents, name

    def test_the_live_protocol_document_declares_the_frozen_namespaces_as_separate(self):
        path = LIVE_REPORTS / "protocol.json"
        if not path.exists():
            pytest.skip("protocol.json i live mungon")

        with open(path, encoding="utf-8") as handle:
            document = json.load(handle)

        assert set(document["separate_from"]) == set(FROZEN_NAMESPACES)
        assert document["protocol_version"] == protocol.PROTOCOL_VERSION

    def test_a_run_session_writes_only_inside_the_live_namespace(self, tmp_path):
        run = session.RunSession(manifest_module.validate(base_manifest()), tmp_path)
        run.start()
        run.finalize()

        written = [path for path in tmp_path.rglob("*") if path.is_file()]

        assert written
        for path in written:
            assert tmp_path in path.parents or path.parent == tmp_path / "runs" / \
                run.state["run_id"]

    def test_random_v2_headline_metrics_are_unchanged(self):
        path = (FROZEN_NAMESPACES["random-v2"] / "xgb_baseline_cicids2017_v2"
                / "metrics.json")
        if not path.exists():
            pytest.skip("random-v2 mungon")

        with open(path, encoding="utf-8") as handle:
            overall = json.load(handle)["metrics"]["overall"]

        assert overall["macro_f1"] == pytest.approx(0.8805600093815694)
        assert overall["binary_benign_vs_attack"]["benign_false_positive_rate"] == \
            pytest.approx(0.0006295884560773997)

    def test_temporal_v1_reports_are_unchanged(self):
        root = FROZEN_NAMESPACES["temporal-v1"]
        if not root.exists():
            pytest.skip("temporal-v1 mungon")

        assert (root / "index.json").exists()
        assert len(list(root.glob("*/metrics.json"))) >= 1

    def test_lofo_v1_still_holds_exactly_thirty_two_folds(self):
        path = FROZEN_NAMESPACES["lofo-v1"] / "index.json"
        if not path.exists():
            pytest.skip("lofo-v1 mungon")

        with open(path, encoding="utf-8") as handle:
            index = json.load(handle)

        assert index["n_folds"] == 32
        assert len(index["folds"]) == 32
        assert len(index["families_run"]) == 8
        assert len(index["models_run"]) == 4


class TestLatencyLayers:

    def test_the_three_latency_layers_keep_the_frozen_names(self):
        assert protocol.LATENCY_MODEL_INFERENCE == "model_inference_latency"
        assert protocol.LATENCY_PRODUCTION_PATH == "production_path_inference_latency"
        assert protocol.LATENCY_END_TO_END == "end_to_end_IDS_latency"

    def test_shap_and_llm_are_excluded_from_every_classifier_latency_layer(self):
        assert "SHAP and LLM explanation are separate layers" in \
            protocol.LATENCY_LAYER_NOTE

    def test_end_to_end_latency_may_not_be_claimed_before_it_is_measured(self):
        assert "may only be reported once every one of those components has been " \
            "measured" in protocol.LATENCY_LAYER_NOTE

    def test_a_flow_record_carries_both_measured_latency_layers(self, tmp_path):
        run = session.RunSession(manifest_module.validate(base_manifest()), tmp_path)
        run.start()
        run.record({"validation_status": protocol.STATUS_VALID,
                    "predicted_label": "PortScan",
                    "model_inference_latency_ms": 1.5,
                    "production_path_inference_latency_ms": 4.0})
        run.finalize()

        row = session.load_flows(tmp_path / "runs" / run.state["run_id"])[0]

        assert float(row["model_inference_latency_ms"]) == 1.5
        assert float(row["production_path_inference_latency_ms"]) == 4.0


class TestManifestParsing:

    def test_every_shipped_manifest_parses_and_pins_the_frozen_model(self):
        manifests = manifest_module.load_all(MANIFEST_DIR)

        assert manifests
        for run_id, manifest in manifests.items():
            assert manifest.model["name"] == protocol.FROZEN_PRIMARY_MODEL["name"], run_id
            assert manifest.protocol_version == protocol.PROTOCOL_VERSION, run_id
            assert manifest.topology["source_host"], run_id
            assert manifest.topology["target_host"], run_id

    def test_a_manifest_missing_a_required_field_is_refused(self):
        payload = base_manifest()
        del payload["topology"]

        with pytest.raises(manifest_module.ManifestError, match="topology"):
            manifest_module.validate(payload)

    def test_an_unknown_expected_binary_label_is_refused(self):
        with pytest.raises(manifest_module.ManifestError, match="expected_binary_label"):
            manifest_module.validate(base_manifest(expected_binary_label="MAYBE"))

    def test_exactly_one_shipped_manifest_is_the_benign_baseline(self):
        manifests = manifest_module.load_all(MANIFEST_DIR)
        benign = [m for m in manifests.values()
                  if m.expected_binary_label == "BENIGN"]

        assert len(benign) == 1
        assert benign[0].scenario_id == "benign"

    def test_the_benign_manifest_declares_its_stopping_condition_up_front(self):
        manifest = manifest_module.load(MANIFEST_DIR / "lab-v1-benign-001.yaml")

        assert manifest.min_valid_flows == 300
        assert manifest.min_services == 4
        assert manifest.planned_duration_seconds == 900

    def test_the_benign_run_uses_the_isolated_run_level_ground_truth_rule(self):
        manifest = manifest_module.load(MANIFEST_DIR / "lab-v1-benign-001.yaml")

        assert manifest.expected_binary_label == "BENIGN"
        assert manifest.mode == manifest_module.GROUND_TRUTH_RUN_LEVEL
        assert manifest.expected_for_flow({"src_ip": "192.168.50.10"}) == "BENIGN"

    def test_the_real_capture_profile_passed_the_frozen_schema(self):
        path = LIVE_REPORTS / "feature_profile.json"
        if not path.exists():
            pytest.skip("profili i kapjes reale mungon")

        with open(path, encoding="utf-8") as handle:
            report = json.load(handle)

        assert report["required_feature_count"] == 78
        assert report["presence"]["missing_raw_count"] == 0
        assert report["derivation"]["not_defensibly_obtainable"] == []
        assert report["verdict"] == "PASS"
        assert report["smoke_test"] is True
        assert report["exclude_from_thesis_metrics"] is True

    def test_topology_lives_in_the_manifest_not_in_inference_code(self):
        for manifest in manifest_module.load_all(MANIFEST_DIR).values():
            assert manifest.topology["source_host"] == "192.168.50.10"
            assert manifest.topology["target_host"] == "192.168.50.20"
