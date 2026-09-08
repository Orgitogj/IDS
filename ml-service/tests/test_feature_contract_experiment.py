import json
from pathlib import Path

import pytest

ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
D = ML_SERVICE_ROOT / "reports" / "live_evaluation" / "diagnostics" / \
    "feature_contract_compatibility"


def _load(name):
    path = D / name
    if not path.exists():
        pytest.skip(f"{name} nuk eshte gjeneruar")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


class TestReproduction:

    def test_portscan_original_reproduces_exactly(self):
        r = _load("portscan_original_reproduction.json")
        assert r["checks"]["all_match"] is True
        assert r["reproduced"]["support"] == 1362
        assert r["reproduced"]["predicted_attack"] == 2
        assert r["reproduced"]["predicted_benign"] == 1360

    def test_ssh_original_reproduces_exactly(self):
        r = _load("ssh_original_reproduction.json")
        assert r["checks"]["all_match"] is True
        assert r["reproduced"]["support"] == 69
        assert r["reproduced"]["predicted_attack"] == 0
        assert r["reproduced"]["predicted_benign"] == 69


class TestCounterfactual:

    def test_portscan_detection_change_is_recorded_as_pp(self):
        c = _load("portscan_comparison.json")
        assert c["support"] == 1362
        assert "detection_rate_change_pp" in c
        assert c["compatibility"]["support"] == 1362

    def test_ssh_detection_change_is_recorded_as_pp(self):
        c = _load("ssh_comparison.json")
        assert c["support"] == 69
        assert "detection_rate_change_pp" in c

    def test_only_confirmed_features_were_converted(self):
        from app.live import compat
        c = _load("ssh_comparison.json")
        assert sorted(c["converted_features"]) == sorted(
            compat.CONFIRMED_SECONDS_FEATURES)


class TestResidualShift:

    def test_summary_splits_time_and_nontime_shift(self):
        s = _load("summary.json")
        for key in ("portscan", "ssh"):
            sc = s["scenarios"][key]
            assert "shift_before_time" in sc and "shift_after_time" in sc
            assert "shift_before_nontime" in sc and "shift_after_nontime" in sc
            assert sc["reproduction_verified"] is True

    def test_nontime_residual_remains_after_harmonization(self):
        s = _load("summary.json")
        ssh = s["scenarios"]["ssh"]
        assert ssh["shift_after_nontime"]["median_ks"] is not None
        assert ssh["shift_after_nontime"]["median_ks"] >= 0.5


class TestFrozenNotMutated:

    def test_portscan_run_metrics_unchanged(self):
        path = (ML_SERVICE_ROOT / "reports" / "live_evaluation" / "runs"
                / "lab-v1-portscan-001" / "metrics.json")
        with open(path, encoding="utf-8") as handle:
            b = json.load(handle)["binary"]
        assert b["true_positive"] == 2 and b["attack_flows"] == 1362

    def test_ssh_run_metrics_unchanged(self):
        path = (ML_SERVICE_ROOT / "reports" / "live_evaluation" / "runs"
                / "lab-v1-ssh-bruteforce-001" / "metrics.json")
        with open(path, encoding="utf-8") as handle:
            b = json.load(handle)["binary"]
        assert b["true_positive"] == 0 and b["attack_flows"] == 69
        assert b["attack_detection_rate"] == 0.0
