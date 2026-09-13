import hashlib
import json
from pathlib import Path

import pytest

ML = Path(__file__).resolve().parent.parent
if str(ML) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ML))

P17D = ML / "reports" / "domain_adaptation" / "phase17d"
AMEND = P17D / "protocol_amendment_003.json"
SCRIPT = ML / "training" / "phase17d_ssh_capture_v3.sh"

from training import build_final_eval_dataset as bfe

MODEL_A_SHA = "2b7625fc32e5f9e066c3a7b356b8a606c9a1f26e5f2a8d1cc4b6fce4ff2fddfa"
MODEL_B_SHA = "c2bb8f0043eb2eb4c9a8d4639e41e86939675a2a0f1d40bf65c3e8ce181cb237"


def _amendment():
    if not AMEND.exists():
        pytest.skip("amendment 003 not written")
    return json.load(open(AMEND, encoding="utf-8"))


def _script():
    if not SCRIPT.exists():
        pytest.skip("v3 script absent")
    return SCRIPT.read_text(encoding="utf-8")


class TestAmendment003Scope:

    def test_scope_and_supersession(self):
        a = _amendment()
        assert a["amends"] == "phase17d-final-eval-v1"
        assert a["amendment_id"] == "phase17d-amendment-003"
        assert a["supersedes_procedure_of"] == "phase17d-amendment-002"
        assert "orchestration" in a["scope"].lower()

    def test_no_scoring_or_seal(self):
        a = _amendment()
        assert a["discovered_before_scoring"] is True
        assert a["no_predictions_inspected"] is True
        assert a["no_dataset_sealed"] is True

    def test_attempt_002_failure_documented(self):
        e = _amendment()["attempt_002_failure_evidence"]
        assert e["pcap_bytes"] == 24
        assert e["packets"] == 0
        assert e["syn_to_dst_port_22"] == 0
        assert e["reported_metadata_ssh_attempts"] == 60


class TestUnchangedInvariants:

    def test_selector_floor_models_threshold_schema(self):
        u = _amendment()["unchanged_and_reaffirmed"]
        assert u["ssh_ground_truth_selector"] == {
            "source_ip": "192.168.50.10", "destination_ip": "192.168.50.20",
            "destination_ports": [22]}
        assert u["support_floor_ssh"] == 30
        assert u["model_a_sha256"] == MODEL_A_SHA
        assert u["model_b_sha256"] == MODEL_B_SHA
        assert u["model_b_threshold"] == 0.50
        assert u["feature_schema"] == "deployment-cicflowmeter-76-v1"
        assert u["extractor"] == {"name": "cicflowmeter", "version": "0.5.0"}

    def test_model_artifacts_still_match(self):
        for rel, want in (
            ("models/xgb_baseline_cicids2017_v2.joblib", MODEL_A_SHA),
            ("models/model_b/model_b_xgb_weighted_v1.joblib", MODEL_B_SHA),
        ):
            p = ML / rel
            if p.exists():
                assert hashlib.sha256(p.read_bytes()).hexdigest() == want


class TestV3ScriptGuards:

    def test_script_hash_matches_amendment(self):
        digest = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
        assert digest == _amendment()["replacement_procedure"]["script_sha256"]

    def test_tcpdump_readiness_checked_before_attempts(self):
        text = _script()
        assert "listening on" in text
        assert "kill -0" in text
        ready_idx = text.index("listening on")
        loop_idx = text.index("/dev/tcp")
        assert ready_idx < loop_idx

    def test_guaranteed_tcp_connect_primitive(self):
        text = _script()
        assert "/dev/tcp/" in text
        assert "192.168.50.20" in text and "192.168.50.10" in text
        assert "PORT=22" in text

    def test_pcap_growth_verified_and_fails_closed(self):
        text = _script()
        assert "-le 24" in text
        assert "exit 4" in text

    def test_csv_nonempty_verified_and_fails_closed(self):
        text = _script()
        assert "csv_no_rows" in text or "CSV_ROWS" in text
        assert "exit 5" in text

    def test_success_result_only_after_verifications(self):
        text = _script()
        assert text.index("exit 4") < text.index("PHASE17D_CAPTURE_RESULT")
        assert text.index("exit 5") < text.index("PHASE17D_CAPTURE_RESULT")

    def test_reports_actual_connections_not_only_constant(self):
        text = _script()
        assert "ssh_connections_opened=" in text
        assert "OPENED=$((OPENED + 1))" in text

    def test_fixed_attempt_count_default_60(self):
        text = _script()
        assert "PHASE17D_SSH_ATTEMPTS:-60" in text


class TestCaptureIntegrityHelper:

    def test_pcap_has_records_header_only_is_false(self, tmp_path):
        p = tmp_path / "empty.pcap"
        p.write_bytes(b"\x00" * 24)
        assert bfe.pcap_has_records(str(p)) is False

    def test_pcap_has_records_with_payload_is_true(self, tmp_path):
        p = tmp_path / "nonempty.pcap"
        p.write_bytes(b"\x00" * 25)
        assert bfe.pcap_has_records(str(p)) is True

    def test_pcap_has_records_missing_is_none(self, tmp_path):
        assert bfe.pcap_has_records(str(tmp_path / "nope.pcap")) is None
        assert bfe.pcap_has_records(None) is None

    def test_empty_capture_status_constant_used(self):
        src = (ML / "training" / "build_final_eval_dataset.py").read_text(
            encoding="utf-8")
        assert "INVALID_EMPTY_CAPTURE" in src
        assert "capture_nonempty" in src
