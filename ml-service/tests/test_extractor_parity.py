import csv
import json
from pathlib import Path

import pytest

from training import extractor_parity_audit as audit

ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
D = ML_SERVICE_ROOT / "reports" / "live_evaluation" / "diagnostics" / "extractor_parity"


class TestClassificationLogic:

    def test_residual_ks_parses_none_and_floats(self, tmp_path):
        p = tmp_path / "residual_feature_shift_x.csv"
        p.write_text("feature,is_time_feature,canon_median,lab_median,ks_before,"
                     "ks_after,outside_p01_p99_before,outside_p01_p99_after\n"
                     "A,False,1,2,0.5,0.4,10,20\n"
                     "B,True,0,0,,,,\n", encoding="utf-8")
        import training.extractor_parity_audit as m
        orig = m.COMPAT
        m.COMPAT = tmp_path
        try:
            out = m.residual_ks("x")
        finally:
            m.COMPAT = orig
        assert out["A"]["ks_after"] == 0.4
        assert out["B"]["ks_after"] is None

    def test_packet_length_features_are_implementation_difference(self):
        for name in ("Average Packet Size", "Max Packet Length",
                     "Total Length of Fwd Packets", "Bwd Packet Length Mean"):
            assert audit.FINDINGS[name]["semantic_status"] == audit.IMPL
            assert "len(packet)" in audit.FINDINGS[name]["python_evidence"]

    def test_time_features_are_unit_difference_only(self):
        for name in ("Flow Duration", "Flow IAT Mean", "Bwd IAT Max"):
            assert audit.FINDINGS[name]["semantic_status"] == audit.UNIT

    def test_psh_flag_count_is_flag_definition_difference(self):
        assert audit.FINDINGS["PSH Flag Count"]["semantic_status"] == audit.FLAG

    def test_cwr_quirk_is_implementation_difference(self):
        assert audit.FINDINGS["CWE Flag Count"]["semantic_status"] == audit.IMPL
        assert "cwr" in audit.FINDINGS["CWE Flag Count"]["python_evidence"].lower()

    def test_subflow_is_aggregation_difference(self):
        assert audit.FINDINGS["Subflow Fwd Packets"]["semantic_status"] == \
            audit.AGGREGATION


@pytest.mark.dataset
class TestArtifacts:

    def _summary(self):
        path = D / "summary.json"
        if not path.exists():
            pytest.skip("extractor parity nuk eshte gjeneruar")
        with open(path, encoding="utf-8") as h:
            return json.load(h)

    def test_case_is_c_no_empirical_parity(self):
        s = self._summary()
        assert s["case"] == "CASE_C"
        assert s["same_pcap_empirical_parity_possible"] is False
        assert s["audit_type"] == "source_and_semantic_implementation_audit_only"

    def test_availability_records_no_retained_pcap(self):
        path = D / "availability_audit.json"
        if not path.exists():
            pytest.skip("availability audit mungon")
        with open(path, encoding="utf-8") as h:
            a = json.load(h)
        assert a["retained_pcap_portscan"] is False
        assert a["retained_pcap_ssh"] is False
        assert a["python_cicflowmeter_source_available"] is True

    def test_all_78_features_classified(self):
        path = D / "semantic_parity.csv"
        if not path.exists():
            pytest.skip("semantic_parity.csv mungon")
        with open(path, encoding="utf-8") as h:
            rows = list(csv.DictReader(h))
        assert len(rows) == 78
        assert all(r["semantic_status"] for r in rows)

    def test_majority_of_important_features_show_implementation_class_difference(self):
        s = self._summary()
        assert s["model_relevant_top15_with_implementation_difference"] >= 8

    def test_five_concepts_are_kept_distinct(self):
        s = self._summary()
        assert len(s["five_distinct_concepts"]) == 5

    def test_retained_python_source_present(self):
        src = D / "cicflowmeter_0_5_0_source" / "cicflowmeter" / "features" / \
            "packet_length.py"
        if not src.exists():
            pytest.skip("burimi i ruajtur mungon")
        assert "len(packet)" in src.read_text(encoding="utf-8")


class TestFrozenNotMutated:

    def test_ssh_and_portscan_metrics_intact(self):
        for run, tp, af in (("lab-v1-ssh-bruteforce-001", 0, 69),
                            ("lab-v1-portscan-001", 2, 1362)):
            path = (ML_SERVICE_ROOT / "reports" / "live_evaluation" / "runs" / run
                    / "metrics.json")
            with open(path, encoding="utf-8") as h:
                b = json.load(h)["binary"]
            assert b["true_positive"] == tp and b["attack_flows"] == af
