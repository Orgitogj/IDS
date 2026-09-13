import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ML = Path(__file__).resolve().parent.parent
P17D = ML / "reports" / "domain_adaptation" / "phase17d"
RUNS = P17D / "runs"
AMEND = P17D / "protocol_amendment_002.json"
SCRIPT = ML / "training" / "phase17d_ssh_capture_v2.sh"

MODEL_A_SHA = "2b7625fc32e5f9e066c3a7b356b8a606c9a1f26e5f2a8d1cc4b6fce4ff2fddfa"
MODEL_B_SHA = "c2bb8f0043eb2eb4c9a8d4639e41e86939675a2a0f1d40bf65c3e8ce181cb237"
SSH_RUNS = ["eval-v1-ssh-001", "eval-v1-ssh-002", "eval-v1-ssh-003"]
ALL_RUNS = [
    "eval-v1-benign-001", "eval-v1-benign-002", "eval-v1-benign-003",
    "eval-v1-portscan-001", "eval-v1-portscan-002", "eval-v1-portscan-003",
    "eval-v1-ssh-001", "eval-v1-ssh-002", "eval-v1-ssh-003",
]


def _amendment():
    if not AMEND.exists():
        pytest.skip("ssh amendment not written")
    return json.load(open(AMEND, encoding="utf-8"))


class TestAmendmentScope:

    def test_amends_phase17d_and_is_ssh_only(self):
        a = _amendment()
        assert a["amends"] == "phase17d-final-eval-v1"
        assert a["amendment_id"] == "phase17d-amendment-002"
        assert "SSH" in a["scope"]
        assert a["phase17d_protocol_head_still_valid"] is True

    def test_no_predictions_and_no_seal(self):
        a = _amendment()
        assert a["discovered_before_scoring"] is True
        assert a["no_predictions_inspected"] is True
        assert a["no_dataset_sealed"] is True


class TestUnchangedInvariants:

    def test_selector_unchanged(self):
        sel = _amendment()["unchanged_and_reaffirmed"]["ssh_ground_truth_selector"]
        assert sel == {"source_ip": "192.168.50.10",
                       "destination_ip": "192.168.50.20",
                       "destination_ports": [22]}

    def test_support_floor_unchanged(self):
        assert _amendment()["unchanged_and_reaffirmed"]["support_floor_ssh"] == 30

    def test_models_threshold_schema_unchanged(self):
        u = _amendment()["unchanged_and_reaffirmed"]
        assert u["model_a_sha256"] == MODEL_A_SHA
        assert u["model_b_sha256"] == MODEL_B_SHA
        assert u["model_b_threshold"] == 0.50
        assert u["feature_schema"] == "deployment-cicflowmeter-76-v1"
        assert u["extractor"] == {"name": "cicflowmeter", "version": "0.5.0"}

    def test_run_ids_unchanged(self):
        assert _amendment()["unchanged_and_reaffirmed"]["final_test_run_ids"] == ALL_RUNS

    def test_frozen_capture_script_not_edited(self):
        u = _amendment()["unchanged_and_reaffirmed"]
        assert u["frozen_capture_script_edited"] is False
        frozen = ML / "training" / "phase17d_capture.sh"
        if frozen.exists():
            digest = hashlib.sha256(frozen.read_bytes()).hexdigest()
            assert digest == u["frozen_capture_script_sha256"]

    def test_model_artifacts_still_match(self):
        for rel, want in (
            ("models/xgb_baseline_cicids2017_v2.joblib", MODEL_A_SHA),
            ("models/model_b/model_b_xgb_weighted_v1.joblib", MODEL_B_SHA),
        ):
            p = ML / rel
            if p.exists():
                assert hashlib.sha256(p.read_bytes()).hexdigest() == want


class TestReplacementProcedure:

    def test_attempt_count_fixed_and_above_floor(self):
        rp = _amendment()["replacement_procedure"]
        assert rp["attempts_per_run"] == 60
        assert rp["attempt_count_is_fixed_and_predeclared"] is True
        assert rp["attempts_per_run"] >= _amendment()[
            "unchanged_and_reaffirmed"]["support_floor_ssh"]

    def test_procedure_independent_of_predictions_and_auth(self):
        rp = _amendment()["replacement_procedure"]
        assert rp["depends_on_predictions"] is False
        assert rp["depends_on_auth_success"] is False

    def test_script_hash_matches_amendment(self):
        if not SCRIPT.exists():
            pytest.skip("ssh v2 script absent")
        digest = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
        assert digest == _amendment()["replacement_procedure"]["script_sha256"]

    def test_script_targets_only_authorized_lab_port_22(self):
        if not SCRIPT.exists():
            pytest.skip("ssh v2 script absent")
        text = SCRIPT.read_text(encoding="utf-8")
        assert "192.168.50.20" in text
        assert "192.168.50.10" in text
        assert "ATTEMPTS=60" in text
        assert "port 22" in text


class TestVersioningAndPreservation:

    def test_attempt_001_provenance_preserved_as_invalid(self):
        for r in SSH_RUNS:
            p = RUNS / r / "provenance.attempt-001.invalid.json"
            if not p.exists():
                pytest.skip(f"attempt-001 archive for {r} not present")
            d = json.load(open(p, encoding="utf-8"))
            assert d["acceptance_status"] == "INVALID_LOW_SUPPORT"

    def test_versioning_rule_keeps_run_ids(self):
        rule = _amendment()["run_versioning_rule"]
        assert rule["final_run_ids_unchanged"] is True
        assert "INVALID_LOW_SUPPORT" in rule["attempt_001_status"]

    def test_benign_and_portscan_not_re_acquired(self):
        u = _amendment()["unchanged_and_reaffirmed"]
        assert "not touched" in u["benign_and_portscan_runs"]

    def test_amendment_commit_predates_attempt_002_data(self):
        repo = ML.parent
        amend_rel = "ml-service/reports/domain_adaptation/phase17d/protocol_amendment_002.json"
        commits = subprocess.run(
            ["git", "log", "--diff-filter=A", "--format=%H", "--", amend_rel],
            cwd=repo, capture_output=True, text=True).stdout.strip().splitlines()
        if not commits:
            pytest.skip("amendment not committed yet")
        amend_add = commits[-1]
        for r in SSH_RUNS:
            prov_rel = (f"ml-service/reports/domain_adaptation/phase17d/runs/"
                        f"{r}/provenance.json")
            adds = subprocess.run(
                ["git", "log", "--diff-filter=A", "--format=%H", "--", prov_rel],
                cwd=repo, capture_output=True, text=True).stdout.strip().splitlines()
            if not adds:
                continue
            data_add = adds[-1]
            ancestor = subprocess.run(
                ["git", "merge-base", "--is-ancestor", amend_add, data_add], cwd=repo)
            assert ancestor.returncode == 0
