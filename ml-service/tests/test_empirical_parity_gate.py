import json
from pathlib import Path

import pytest

ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
D = ML_SERVICE_ROOT / "reports" / "live_evaluation" / "diagnostics" / \
    "empirical_extractor_parity"


def _prov():
    path = D / "tooling_provenance.json"
    if not path.exists():
        pytest.skip("tooling_provenance.json mungon")
    with open(path, encoding="utf-8") as h:
        return json.load(h)


class TestPhase16FGate:

    def test_gate_not_met_and_no_traffic(self):
        p = _prov()
        assert p["gate_met"] is False
        assert p["status"] == "BLOCKED_BEFORE_TRAFFIC"
        assert p["no_traffic_generated"] is True
        assert p["no_pcap_captured"] is True
        assert p["no_fabricated_parity"] is True

    def test_java_8_unavailable_is_recorded(self):
        p = _prov()
        assert p["available_toolchain"]["kali_java_8_available"] is False
        assert p["build_requirements"]["source_target_compatibility"].startswith("1.8")

    def test_no_empirical_parity_files_were_fabricated(self):
        for name in ("feature_parity.csv", "prediction_parity.csv",
                     "flow_matching.csv", "flow_matching_summary.json"):
            assert not (D / name).exists(), f"unexpected fabricated artifact: {name}"

    def test_exact_2017_identity_not_claimed(self):
        p = _prov()
        assert p["java_cicflowmeter_source"][
            "exact_2017_dataset_extractor_identity_claimed"] is False


class TestFrozenIntact:

    def test_ssh_and_portscan_metrics_intact(self):
        for run, tp, af in (("lab-v1-ssh-bruteforce-001", 0, 69),
                            ("lab-v1-portscan-001", 2, 1362)):
            path = (ML_SERVICE_ROOT / "reports" / "live_evaluation" / "runs" / run
                    / "metrics.json")
            with open(path, encoding="utf-8") as h:
                b = json.load(h)["binary"]
            assert b["true_positive"] == tp and b["attack_flows"] == af
