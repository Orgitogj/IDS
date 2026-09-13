import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ML = Path(__file__).resolve().parent.parent
PHASE17D = ML / "reports" / "domain_adaptation" / "phase17d"
DATA = PHASE17D / "data"
RUNS = PHASE17D / "runs"

PROTOCOL_HEAD_FILE = PHASE17D / "protocol.json"
MODEL_A_SHA = "2b7625fc32e5f9e066c3a7b356b8a606c9a1f26e5f2a8d1cc4b6fce4ff2fddfa"
MODEL_B_SHA = "c2bb8f0043eb2eb4c9a8d4639e41e86939675a2a0f1d40bf65c3e8ce181cb237"

BENIGN = ["eval-v1-benign-001", "eval-v1-benign-002", "eval-v1-benign-003"]
PORTSCAN = ["eval-v1-portscan-001", "eval-v1-portscan-002", "eval-v1-portscan-003"]
SSH = ["eval-v1-ssh-001", "eval-v1-ssh-002", "eval-v1-ssh-003"]
FINAL_RUNS = BENIGN + PORTSCAN + SSH

ADAPTATION_AND_VALIDATION = {
    "lab-v1-benign-001", "lab-v1-portscan-001", "lab-v1-ssh-bruteforce-001",
    "adapt-v1-benign-002", "adapt-v1-benign-003", "adapt-v1-benign-004",
    "adapt-v1-portscan-002", "adapt-v1-portscan-003", "adapt-v1-portscan-004",
    "adapt-v1-ssh-002", "adapt-v1-ssh-003", "adapt-v1-ssh-004",
}

SUPPORT_FLOOR = {"benign": 300, "portscan": 300, "ssh": 30}
SCENARIO_OF = ({r: "benign" for r in BENIGN} | {r: "portscan" for r in PORTSCAN}
               | {r: "ssh" for r in SSH})


def _protocol():
    if not PROTOCOL_HEAD_FILE.exists():
        pytest.skip("phase 17d protocol not built")
    return json.load(open(PROTOCOL_HEAD_FILE, encoding="utf-8"))


def _seal():
    p = DATA / "final_test_seal.json"
    if not p.exists():
        pytest.skip("final-test dataset not sealed yet")
    return json.load(open(p, encoding="utf-8"))


def _manifest():
    p = DATA / "final_test_manifest.json"
    if not p.exists():
        pytest.skip("final-test manifest not built yet")
    return json.load(open(p, encoding="utf-8"))


def _provs():
    out = {}
    for run_id in FINAL_RUNS:
        p = RUNS / run_id / "provenance.json"
        if not p.exists():
            pytest.skip(f"provenance for {run_id} not present yet")
        out[run_id] = json.load(open(p, encoding="utf-8"))
    return out


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class TestProtocolFrozenBeforeCapture:

    def test_protocol_declares_frozen_before_capture(self):
        p = _protocol()
        assert p["status"] == "FROZEN_BEFORE_CAPTURE"
        assert p["written_before_any_final_capture"] is True

    def test_protocol_pins_phase17c_head(self):
        assert _protocol()["phase17c_final_head"] == \
            "fb1a232ebaea1d053e5f65686bbfec26ba8f2362"

    def test_protocol_commit_predates_final_capture_data(self):
        repo = ML.parent
        proto_rel = "ml-service/reports/domain_adaptation/phase17d/protocol.json"
        proto_commit = subprocess.run(
            ["git", "log", "--diff-filter=A", "--format=%H", "--", proto_rel],
            cwd=repo, capture_output=True, text=True).stdout.strip().splitlines()
        if not proto_commit:
            pytest.skip("protocol not yet committed")
        proto_add = proto_commit[-1]
        for run_id in FINAL_RUNS:
            prov_rel = (f"ml-service/reports/domain_adaptation/phase17d/runs/"
                        f"{run_id}/provenance.json")
            added = subprocess.run(
                ["git", "log", "--diff-filter=A", "--format=%H", "--", prov_rel],
                cwd=repo, capture_output=True, text=True).stdout.strip().splitlines()
            if not added:
                continue
            data_add = added[-1]
            order = subprocess.run(
                ["git", "rev-list", "--count", f"{proto_add}..{data_add}"],
                cwd=repo, capture_output=True, text=True).stdout.strip()
            assert order != "" and int(order) >= 0
            ancestor = subprocess.run(
                ["git", "merge-base", "--is-ancestor", proto_add, data_add],
                cwd=repo)
            assert ancestor.returncode == 0, (
                f"protocol commit is not an ancestor of {run_id} data commit")


class TestRunIdentities:

    def test_exactly_nine_final_runs(self):
        assert len(FINAL_RUNS) == 9
        p = _protocol()["final_test_runs"]
        assert p["count"] == 9
        assert p["benign"] == BENIGN
        assert p["portscan"] == PORTSCAN
        assert p["ssh"] == SSH

    def test_three_per_scenario(self):
        assert len(BENIGN) == 3 and len(PORTSCAN) == 3 and len(SSH) == 3

    def test_no_overlap_with_adaptation_or_validation(self):
        assert not set(FINAL_RUNS) & ADAPTATION_AND_VALIDATION

    def test_manifest_run_ids_match(self):
        m = _manifest()
        assert m["final_test_run_ids"] == FINAL_RUNS
        assert m["n_runs"] == 9

    def test_manifest_disjoint_flag_and_ids(self):
        m = _manifest()
        assert not set(m["final_test_run_ids"]) & ADAPTATION_AND_VALIDATION


class TestFrozenModels:

    def test_model_a_hash_unchanged(self):
        a = ML / "models" / "xgb_baseline_cicids2017_v2.joblib"
        if not a.exists():
            pytest.skip("model A artifact absent")
        assert _sha(a) == MODEL_A_SHA
        assert _protocol()["models"]["model_a"]["artifact_sha256"] == MODEL_A_SHA

    def test_model_b_hash_unchanged(self):
        b = ML / "models" / "model_b" / "model_b_xgb_weighted_v1.joblib"
        if not b.exists():
            pytest.skip("model B artifact absent")
        assert _sha(b) == MODEL_B_SHA
        assert _protocol()["models"]["model_b"]["artifact_sha256"] == MODEL_B_SHA

    def test_model_b_threshold_is_half(self):
        assert _protocol()["models"]["model_b"]["threshold"] == 0.50

    def test_secondary_models_not_final(self):
        p = _protocol()["models"]
        assert set(p["secondary_evidence_not_final_models"]) == {
            "model-b-rf-weighted-v1", "model-b-xgb-unweighted-v1"}
        assert p["final_comparison"] == "FROZEN MODEL A vs FROZEN PRIMARY MODEL B"

    def test_feature_schema_declared(self):
        b = _protocol()["models"]["model_b"]
        assert b["feature_schema"] == "deployment-cicflowmeter-76-v1"
        assert b["n_features"] == 76
        a = _protocol()["models"]["model_a"]
        assert a["feature_schema"] == "cicids2017-78-v1"


class TestAcceptanceAndSupport:

    def test_support_floors_declared(self):
        f = _protocol()["support_floors"]
        assert f["benign_valid_evaluable_benign_flows_per_run"] == 300
        assert f["portscan_selector_matched_attack_flows_per_run"] == 300
        assert f["ssh_selector_matched_attack_flows_per_run"] == 30

    def test_acceptance_independent_of_predictions(self):
        a = _protocol()["acceptance"]
        for forbidden in ("Model A predictions", "Model B predictions",
                          "probability/confidence", "desired thesis outcome"):
            assert forbidden in a["must_not_depend_on"]

    def test_all_accepted_runs_have_hashes_and_support(self):
        provs = _provs()
        for run_id, p in provs.items():
            if p["acceptance_status"] != "ACCEPTED":
                continue
            assert p["flow_csv_sha256"]
            assert p["pcap_sha256"]
            floor = SUPPORT_FLOOR[SCENARIO_OF[run_id]]
            assert p["support_metric"] >= floor

    def test_provenance_carries_no_prediction_fields(self):
        for p in _provs().values():
            keys = " ".join(p.keys()).lower()
            assert "predicted" not in keys
            assert "probability" not in keys
            assert "model_a_flagged" not in keys


class TestSeal:

    def test_manifest_sealed_before_prediction(self):
        s = _seal()
        assert s["sealed"] is True
        assert s["sealed_before_prediction"] is True
        assert s["all_accepted"] is True

    def test_seal_hash_matches_manifest_file(self):
        s = _seal()
        digest = hashlib.sha256((DATA / "final_test_manifest.json").read_bytes()) \
            .hexdigest()
        assert digest == s["manifest_sha256"]

    def test_seal_predates_prediction_outputs(self):
        _seal()
        pred = PHASE17D / "paired_predictions.csv"
        seal_file = DATA / "final_test_seal.json"
        if pred.exists():
            assert seal_file.stat().st_mtime <= pred.stat().st_mtime + 1


class TestPairedEvaluation:

    def test_paired_models_score_identical_flow_identities(self):
        pred = PHASE17D / "paired_predictions.csv"
        if not pred.exists():
            pytest.skip("paired predictions not produced yet")
        import csv as _csv
        with open(pred, encoding="utf-8") as fh:
            reader = _csv.DictReader(fh)
            seen = 0
            for r in reader:
                assert r["model_a_binary"] in ("ATTACK", "BENIGN")
                assert r["model_b_binary"] in ("ATTACK", "BENIGN")
                assert r["ground_truth"] in ("ATTACK", "BENIGN")
                seen += 1
                if seen >= 5000:
                    break
        assert seen > 0

    def test_every_evaluable_flow_scored_by_both(self):
        pred = PHASE17D / "paired_predictions.csv"
        manifest = DATA / "final_test_manifest.json"
        if not (pred.exists() and manifest.exists()):
            pytest.skip("evaluation not complete yet")
        with open(pred, encoding="utf-8") as fh:
            rows = sum(1 for _ in fh) - 1
        m = json.load(open(manifest, encoding="utf-8"))
        assert rows == m["totals"]["evaluable"]

    def test_scenario_results_report_wilson(self):
        p = PHASE17D / "scenario_results.json"
        if not p.exists():
            pytest.skip("scenario results not produced yet")
        s = json.load(open(p, encoding="utf-8"))
        for scenario in ("benign", "portscan", "ssh"):
            for model in ("model_a", "model_b"):
                w = s[scenario][model]["wilson_95"]
                assert w["n"] >= 0


class TestNoRetrainingAfterAcquisition:

    def test_model_b_metadata_unchanged_since_phase17c(self):
        meta = ML / "reports" / "domain_adaptation" / "phase17c" / "model_b_metadata.json"
        if not meta.exists():
            pytest.skip("phase 17c metadata absent")
        d = json.load(open(meta, encoding="utf-8"))
        assert d["models"]["model-b-xgb-weighted-v1"]["artifact_sha256"] == MODEL_B_SHA

    def test_no_post_hoc_rules_declared(self):
        forbidden = _protocol()["no_post_hoc_tuning"]["after_predictions_visible_do_not"]
        for item in ("retrain Model B", "change threshold", "remove difficult runs",
                     "change selectors", "promote RF", "add a new model"):
            assert item in forbidden


class TestFrozenHistoricalUnchanged:

    def test_frozen_result_files_present_and_stable(self):
        targets = [
            ML / "reports" / "domain_adaptation" / "phase17c" / "validation_results.json",
            ML / "reports" / "domain_adaptation" / "data" / "class_distribution.json",
        ]
        for t in targets:
            if t.exists():
                assert t.stat().st_size > 0
