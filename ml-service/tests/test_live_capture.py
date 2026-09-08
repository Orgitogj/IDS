import json
from pathlib import Path

import pytest

from app.live import capture_source, protocol
from training import live_profile, run_lab_capture

ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent

HEADER = "src_ip,dst_ip,src_port,dst_port,protocol,timestamp,flow_duration"
ROW_A = "192.168.50.10,192.168.50.20,40001,80,6,2026-09-08 10:00:00,1234"
ROW_B = "192.168.50.10,192.168.50.20,40002,22,6,2026-09-08 10:00:01,5678"


def write(path, *lines, newline=True):
    text = "\n".join(lines) + ("\n" if newline else "")
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(text)


class TestCsvFlowSource:

    def test_a_missing_file_yields_nothing_rather_than_failing(self, tmp_path):
        source = capture_source.CsvFlowSource(tmp_path / "absent.csv")

        assert source.exists() is False
        assert source.read_new() == []

    def test_the_header_is_consumed_and_not_returned_as_a_flow(self, tmp_path):
        path = tmp_path / "flows.csv"
        write(path, HEADER, ROW_A)
        source = capture_source.CsvFlowSource(path)

        rows = source.read_new()

        assert source.header[0] == "src_ip"
        assert len(rows) == 1
        assert rows[0]["dst_port"] == "80"

    def test_only_new_rows_are_returned_on_a_second_read(self, tmp_path):
        path = tmp_path / "flows.csv"
        write(path, HEADER, ROW_A)
        source = capture_source.CsvFlowSource(path)
        source.read_new()

        write(path, ROW_B)
        rows = source.read_new()

        assert len(rows) == 1
        assert rows[0]["src_port"] == "40002"

    def test_a_partially_written_line_is_held_until_it_is_complete(self, tmp_path):
        path = tmp_path / "flows.csv"
        write(path, HEADER)
        source = capture_source.CsvFlowSource(path)
        source.read_new()

        write(path, "192.168.50.10,192.168.50.20,40003,21", newline=False)
        assert source.read_new() == []

        write(path, ",6,2026-09-08 10:00:02,999")
        rows = source.read_new()

        assert len(rows) == 1
        assert rows[0]["dst_port"] == "21"

    def test_a_row_with_the_wrong_column_count_is_counted_not_silently_reshaped(
            self, tmp_path):
        path = tmp_path / "flows.csv"
        write(path, HEADER, "192.168.50.10,192.168.50.20", ROW_A)
        source = capture_source.CsvFlowSource(path)

        rows = source.read_new()

        assert len(rows) == 1
        assert source.malformed_lines == 1

    def test_read_all_drains_the_file(self, tmp_path):
        path = tmp_path / "flows.csv"
        write(path, HEADER, ROW_A, ROW_B)

        rows = capture_source.CsvFlowSource(path).read_all()

        assert len(rows) == 2

    def test_the_column_report_surfaces_duplicates_and_counts(self, tmp_path):
        path = tmp_path / "flows.csv"
        write(path, HEADER + ",flow_duration", ROW_A + ",1234")

        report = capture_source.column_report(path)

        assert report["row_count"] == 1
        assert report["duplicate_columns"] == ["flow_duration"]

    def test_a_capture_without_a_header_is_refused(self, tmp_path):
        path = tmp_path / "empty.csv"
        path.write_text("", encoding="utf-8")

        with pytest.raises(capture_source.CaptureError):
            capture_source.column_report(path)

    def test_follow_stops_on_the_stopping_predicate(self, tmp_path):
        path = tmp_path / "flows.csv"
        write(path, HEADER, ROW_A, ROW_B)
        source = capture_source.CsvFlowSource(path)

        seen = list(source.follow(poll_interval=0, max_rows=2))

        assert len(seen) == 2


class TestStoppingAndLatency:

    def test_the_stopping_condition_counts_only_valid_flows(self):
        stopping = run_lab_capture.StoppingCondition(min_valid_flows=2)

        stopping.note({"validation_status": protocol.STATUS_VALID})
        stopping.note({"validation_status": protocol.STATUS_MISSING_FEATURE})
        assert stopping.reached() is False

        stopping.note({"validation_status": protocol.STATUS_VALID})
        assert stopping.reached() is True

    def test_no_minimum_means_the_run_never_self_terminates(self):
        stopping = run_lab_capture.StoppingCondition()
        stopping.note({"validation_status": protocol.STATUS_VALID})

        assert stopping.reached() is False

    def test_the_validity_floor_is_not_used_as_the_stop_trigger(self):
        import inspect
        signature = inspect.signature(run_lab_capture.run)

        assert "min_valid_flows" in signature.parameters
        assert "stop_after_valid_flows" in signature.parameters
        assert signature.parameters["stop_after_valid_flows"].default is None

        source = inspect.getsource(run_lab_capture.run)
        assert "StoppingCondition(stop_after_valid_flows)" in source

    def test_the_latency_summary_separates_the_two_measured_layers(self):
        records = [{"model_inference_latency_ms": 1.0,
                    "production_path_inference_latency_ms": 3.0},
                   {"model_inference_latency_ms": 2.0,
                    "production_path_inference_latency_ms": 5.0}]

        summary = run_lab_capture.latency_summary(records)

        assert summary[protocol.LATENCY_MODEL_INFERENCE]["median_ms"] == 1.5
        assert summary[protocol.LATENCY_PRODUCTION_PATH]["median_ms"] == 4.0

    def test_end_to_end_latency_is_never_populated_by_the_harness(self):
        summary = run_lab_capture.latency_summary(
            [{"model_inference_latency_ms": 1.0,
              "production_path_inference_latency_ms": 2.0}])

        assert summary[protocol.LATENCY_END_TO_END] is None

    def test_latency_is_absent_rather_than_zero_when_nothing_was_measured(self):
        summary = run_lab_capture.latency_summary([{"validation_status": "X"}])

        assert summary[protocol.LATENCY_MODEL_INFERENCE] is None


@pytest.mark.artifacts
class TestRealCaptureProfile:

    def _capture(self, tmp_path, feature_columns, drop=(), extra_columns=(),
                 values=None, with_timestamp=True):
        from app.replay.feature_mapping import CICFLOWMETER_TO_CICIDS2017

        inverted = {}
        for cicflow, cicids in CICFLOWMETER_TO_CICIDS2017.items():
            inverted.setdefault(cicids, cicflow)

        columns = []
        for name in feature_columns:
            if name in drop:
                continue
            mapped = inverted.get(name)
            if mapped:
                columns.append(mapped)

        meta = [name for name in ("src_ip", "dst_ip", "src_port", "protocol")
                if name not in columns]
        if with_timestamp:
            meta.append("timestamp")
        header = meta + columns + list(extra_columns)

        row = [{"src_ip": "192.168.50.10", "dst_ip": "192.168.50.20",
                "src_port": "40001", "protocol": "6",
                "timestamp": "2026-09-08 10:00:00"}[name] for name in meta]
        by_capture_name = {inverted[k]: v for k, v in (values or {}).items()
                           if k in inverted}
        row += [str(by_capture_name.get(name, "1")) for name in columns]
        row += ["0"] * len(extra_columns)

        path = tmp_path / "capture.csv"
        path.write_text(",".join(header) + "\n" + ",".join(row) + "\n",
                        encoding="utf-8")
        return path

    def _numeric_target(self, columns):
        from app.replay.feature_mapping import CICFLOWMETER_TO_CICIDS2017
        reverse = {}
        for cicflow, cicids in CICFLOWMETER_TO_CICIDS2017.items():
            reverse.setdefault(cicids, cicflow)
        return next(name for name in columns
                    if reverse.get(name) not in ("src_ip", "dst_ip", "src_port",
                                                 "dst_port", "protocol", "timestamp")
                    and name not in live_profile.DERIVATIONS
                    and name not in live_profile.CONST_ZERO_IN_TRAINING)

    def _columns(self):
        from app.live import lab_runner
        models = ML_SERVICE_ROOT / "models"
        if not (models / protocol.FROZEN_PRIMARY_MODEL["artifact_file"]).exists():
            pytest.skip("artefakti v2 mungon")
        _, _, columns, _ = lab_runner.load_frozen_model(models)
        return columns

    def test_a_complete_capture_profiles_as_pass(self, tmp_path):
        columns = self._columns()
        path = self._capture(tmp_path, columns)

        report = live_profile.profile(path, ML_SERVICE_ROOT / "models")

        assert report["required_feature_count"] == 78
        assert report["presence"]["missing_raw_count"] == 0
        assert report["verdict"] == live_profile.VERDICT_PASS
        assert report["timestamp"]["capture_column_present"] is True
        assert report["timestamp"]["rows_with_exact_capture_time"] == 1

    def test_the_profile_is_always_marked_as_setup_not_thesis_data(self, tmp_path):
        report = live_profile.profile(self._capture(tmp_path, self._columns()),
                                      ML_SERVICE_ROOT / "models")

        assert report["smoke_test"] is True
        assert report["exclude_from_thesis_metrics"] is True

    def test_extra_capture_columns_are_reported_not_silently_dropped(self, tmp_path):
        columns = self._columns()
        path = self._capture(tmp_path, columns, extra_columns=("rogue_column",))

        report = live_profile.profile(path, ML_SERVICE_ROOT / "models")

        assert "rogue_column" in report["extra"]["unmapped_capture_columns"]
        assert report["extra"]["policy"] == protocol.EXTRA_FEATURE_POLICY

    def test_a_missing_feature_is_reported_as_missing_and_never_patched(self, tmp_path):
        columns = self._columns()
        from app.replay.feature_mapping import (CICFLOWMETER_TO_CICIDS2017,
                                                META_COLUMNS)
        reverse = {}
        for cicflow, cicids in CICFLOWMETER_TO_CICIDS2017.items():
            reverse.setdefault(cicids, cicflow)
        target = next(name for name in columns
                      if name not in live_profile.DERIVATIONS
                      and name not in live_profile.CONST_ZERO_IN_TRAINING
                      and reverse.get(name) not in META_COLUMNS
                      and reverse.get(name) not in ("src_ip", "dst_ip", "src_port",
                                                    "dst_port", "protocol"))
        path = self._capture(tmp_path, columns, drop=(target,))

        report = live_profile.profile(path, ML_SERVICE_ROOT / "models")

        assert target in report["presence"]["missing_raw"]
        assert target in report["derivation"]["not_defensibly_obtainable"]
        assert report["verdict"] == live_profile.VERDICT_BLOCKED
        assert "never patches a value" in report["derivation"]["policy"]

    def test_a_nonfinite_value_is_counted_in_the_profile(self, tmp_path):
        columns = self._columns()
        target = self._numeric_target(columns)
        path = self._capture(tmp_path, columns, values={target: "inf"})

        report = live_profile.profile(path, ML_SERVICE_ROOT / "models")

        assert report["values"].get("inf", {}).get(target) == 1

    def test_a_non_numeric_value_is_counted_in_the_profile(self, tmp_path):
        columns = self._columns()
        target = self._numeric_target(columns)
        path = self._capture(tmp_path, columns, values={target: "abc"})

        report = live_profile.profile(path, ML_SERVICE_ROOT / "models")

        assert report["values"].get("non_numeric", {}).get(target) == 1

    def test_a_capture_without_a_timestamp_column_is_flagged(self, tmp_path):
        path = self._capture(tmp_path, self._columns(), with_timestamp=False)

        report = live_profile.profile(path, ML_SERVICE_ROOT / "models")

        assert report["timestamp"]["capture_column_present"] is False
        assert report["timestamp"]["rows_falling_back_to_approximation"] == 1

    def test_the_profile_records_the_frozen_ordering(self, tmp_path):
        columns = self._columns()
        report = live_profile.profile(self._capture(tmp_path, columns),
                                      ML_SERVICE_ROOT / "models")

        assert report["ordering"]["frozen_schema_order"] == columns

    def test_the_selector_fields_needed_for_ground_truth_are_checked(self, tmp_path):
        report = live_profile.profile(self._capture(tmp_path, self._columns()),
                                      ML_SERVICE_ROOT / "models")

        assert report["ground_truth_selector_fields"]["src_ip"] is True
        assert report["ground_truth_selector_fields"]["dst_ip"] is True
        assert report["ground_truth_selector_fields"]["dst_port"] is True


class TestLlmTestHygiene:

    def test_the_default_addopts_deselect_the_llm_marker(self):
        ini = (ML_SERVICE_ROOT / "pytest.ini").read_text(encoding="utf-8")

        assert 'addopts' in ini
        addopts = next(line for line in ini.splitlines()
                       if line.strip().startswith("addopts"))
        assert '-m "not llm"' in addopts

    def test_the_provider_gate_requires_an_explicit_environment_opt_in(self,
                                                                      monkeypatch):
        from tests import conftest

        monkeypatch.delenv(conftest.LLM_INTEGRATION_ENV, raising=False)
        assert conftest._llm_opted_in() is False
        assert conftest._llm_configured() is False

    def test_the_opt_in_flag_is_recognised_when_set(self, monkeypatch):
        from tests import conftest

        monkeypatch.setenv(conftest.LLM_INTEGRATION_ENV, "1")
        assert conftest._llm_opted_in() is True

    def test_the_live_provider_test_still_exists(self):
        source = (ML_SERVICE_ROOT / "tests" / "test_llm_explainer.py").read_text(
            encoding="utf-8")

        assert "@pytest.mark.llm" in source
        assert "test_a_live_explanation_for_a_suspicious_alarm_names_no_attack_class" \
            in source
