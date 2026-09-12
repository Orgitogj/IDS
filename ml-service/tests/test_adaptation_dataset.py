import json
from pathlib import Path

import pytest

ML = Path(__file__).resolve().parent.parent
DATA = ML / "reports" / "domain_adaptation" / "data"
PHASE17A_HEAD = "3416fff72c66a5cf96810ff7355372869c4b3f89"

HISTORICAL = {"lab-v1-benign-001", "lab-v1-portscan-001", "lab-v1-ssh-bruteforce-001"}
NEW = {
    "adapt-v1-benign-002", "adapt-v1-benign-003", "adapt-v1-benign-004",
    "adapt-v1-portscan-002", "adapt-v1-portscan-003", "adapt-v1-portscan-004",
    "adapt-v1-ssh-002", "adapt-v1-ssh-003", "adapt-v1-ssh-004",
}


def _manifest():
    p = DATA / "adaptation_manifest.json"
    if not p.exists():
        pytest.skip("adaptation manifest not built")
    return json.load(open(p, encoding="utf-8"))


class TestAdaptationManifest:

    def test_twelve_unique_run_ids(self):
        m = _manifest()
        ids = [r["run_id"] for r in m["runs"]]
        assert len(ids) == 12
        assert len(set(ids)) == 12
        assert set(ids) == HISTORICAL | NEW

    def test_all_runs_role_adaptation(self):
        for r in _manifest()["runs"]:
            assert r["role"] == "adaptation"

    def test_historical_runs_have_no_pcap(self):
        m = {r["run_id"]: r for r in _manifest()["runs"]}
        for rid in HISTORICAL:
            assert m[rid]["packet_capture_available"] is False

    def test_new_runs_have_pcap_and_hashes(self):
        m = {r["run_id"]: r for r in _manifest()["runs"]}
        for rid in NEW:
            assert m[rid]["packet_capture_available"] is True
            assert m[rid]["pcap_sha256"]
            assert m[rid]["flow_csv_sha256"]

    def test_all_runs_accepted(self):
        assert all(r["acceptance_status"] == "ACCEPTED" for r in _manifest()["runs"])
        assert _manifest()["model_b_exists"] is False
        assert _manifest()["final_evaluation_runs_exist"] is False

    def test_class_distribution_matches_expected(self):
        c = json.load(open(DATA / "class_distribution.json", encoding="utf-8"))
        assert c["rebalanced"] is False
        assert c["raw_binary"]["BENIGN"] == 7758
        assert c["raw_binary"]["ATTACK"] == 23806
        assert c["attack_by_family"]["PortScan"] == 23521
        assert c["attack_by_family"]["Brute Force"] == 285


class TestSupportFloors:

    def test_new_runs_meet_support_floors(self):
        for rid in NEW:
            prov = json.load(open(DATA / "runs" / rid / "provenance.json",
                                  encoding="utf-8"))
            assert prov["support_metric"] >= prov["support_floor"]
            assert prov["acceptance_status"] == "ACCEPTED"


class TestRunLevelSplit:

    def test_split_has_no_flow_leak_across_runs(self):
        s = json.load(open(DATA / "model_b_split_proposal.json", encoding="utf-8"))
        train, val = set(s["train_runs"]), set(s["validation_runs"])
        assert not (train & val)
        assert s["final_test_runs"] == []

    def test_split_covers_every_scenario(self):
        s = json.load(open(DATA / "model_b_split_proposal.json", encoding="utf-8"))
        allruns = set(s["train_runs"]) | set(s["validation_runs"])
        for scen in ("benign", "portscan", "ssh"):
            assert any(scen in r for r in allruns)


class TestNoModelBNoEval:

    def test_no_eval_run_exists(self):
        live = ML / "reports" / "live_evaluation" / "runs"
        for d in list(live.glob("eval-v1-*")) if live.exists() else []:
            pytest.fail(f"unexpected eval run: {d}")
        for d in list((DATA / "runs").glob("eval-v1-*")) if (DATA / "runs").exists() else []:
            pytest.fail(f"unexpected eval run: {d}")

    def test_no_model_b_artifact_exists(self):
        models = ML / "models"
        for pat in ("deployment-adapted*", "model_b*", "*deployment-adapted*"):
            hits = list(models.glob(pat))
            assert not hits, f"unexpected Model B artifact: {hits}"

    def test_no_prediction_driven_metadata(self):
        for rid in NEW:
            prov = json.load(open(DATA / "runs" / rid / "provenance.json",
                                  encoding="utf-8"))
            note = prov["model_a_descriptive_only"]["note"]
            assert "do not affect acceptance" in note


class TestFrozenUntouched:

    def test_phase17a_head_traceable(self):
        import subprocess
        out = subprocess.run(["git", "cat-file", "-t", PHASE17A_HEAD],
                             cwd=ML.parent, capture_output=True, text=True)
        assert out.stdout.strip() == "commit"

    def test_frozen_lab_metrics_unchanged(self):
        b = json.load(open(ML / "reports/live_evaluation/runs/lab-v1-benign-001/"
                           "metrics.json", encoding="utf-8"))["binary"]
        assert b["false_positive"] == 0 and b["benign_false_positive_rate_denominator"] == 5407
        p = json.load(open(ML / "reports/live_evaluation/runs/lab-v1-portscan-001/"
                           "metrics.json", encoding="utf-8"))["binary"]
        assert p["true_positive"] == 2 and p["attack_flows"] == 1362
        s = json.load(open(ML / "reports/live_evaluation/runs/lab-v1-ssh-bruteforce-001/"
                           "metrics.json", encoding="utf-8"))["binary"]
        assert s["true_positive"] == 0 and s["attack_flows"] == 69

    def test_random_v2_macro_f1_unchanged(self):
        o = json.load(open(ML / "reports/artifact_evaluation/"
                           "xgb_baseline_cicids2017_v2/metrics.json",
                           encoding="utf-8"))["metrics"]["overall"]
        assert abs(o["macro_f1"] - 0.8805600093815694) < 1e-12
