import csv
import json
from pathlib import Path

import numpy as np
import pytest

from training import ssh_shift_diagnostic as diag

ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
DIAG_DIR = (ML_SERVICE_ROOT / "reports" / "live_evaluation" / "diagnostics"
            / "ssh_feature_shift")


class TestSemanticAudit:

    def test_time_features_are_flagged_as_unit_mismatch_with_a_1e6_style_ratio(self):
        cols = ["Flow Duration", "Total Fwd Packets"]
        canon = np.array([[1.0e7, 10.0]] * 200)
        lab = np.array([[2.0, 10.0]] * 60)
        rows = diag.feature_stats(canon, lab, cols)
        audit = {a["feature"]: a for a in diag.semantic_audit(rows)}

        assert audit["Flow Duration"]["semantic_status"] == diag.UNIT
        assert "microseconds" in audit["Flow Duration"]["note"]
        assert audit["Total Fwd Packets"]["semantic_status"] in (diag.SAME, diag.LIKELY)

    def test_flag_features_are_flagged_as_possible_implementation_difference(self):
        cols = ["PSH Flag Count"]
        canon = np.array([[1.0]] * 100)
        lab = np.array([[15.0]] * 40)
        audit = diag.semantic_audit(diag.feature_stats(canon, lab, cols))

        assert audit[0]["semantic_status"] == diag.IMPL

    def test_rate_features_are_flagged_as_possible_implementation_difference(self):
        cols = ["Flow Bytes/s"]
        canon = np.array([[300.0]] * 100)
        lab = np.array([[3000.0]] * 40)
        audit = diag.semantic_audit(diag.feature_stats(canon, lab, cols))

        assert audit[0]["semantic_status"] == diag.IMPL


class TestShiftMath:

    def test_disjoint_distributions_have_ks_one(self):
        rng = np.random.default_rng(3)
        canon = rng.normal(0.0, 1.0, size=(400, 1))
        lab = rng.normal(40.0, 1.0, size=(60, 1))
        rows = diag.feature_stats(canon, lab, ["f"])

        assert rows[0]["ks_statistic"] == pytest.approx(1.0)
        assert rows[0]["pct_lab_outside_canon_p01_p99"] == 100.0

    def test_constant_canonical_feature_reports_no_ks(self):
        canon = np.zeros((100, 1))
        lab = np.concatenate([np.zeros((30, 1)), np.ones((30, 1))])
        rows = diag.feature_stats(canon, lab, ["f"])

        assert rows[0]["canon_constant"] is True
        assert rows[0]["ks_statistic"] is None
        assert rows[0]["median_ratio"] is None


@pytest.mark.dataset
class TestDiagnosticArtifacts:

    def _summary(self):
        path = DIAG_DIR / "summary.json"
        if not path.exists():
            pytest.skip("ssh diagnostic nuk eshte gjeneruar")
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    def test_marks_itself_diagnostic_only(self):
        s = self._summary()
        assert s["is_diagnostic_only"] is True
        assert s["no_retraining_no_tuning_no_shap_no_llm"] is True

    def test_supports_match_expected(self):
        s = self._summary()
        assert s["canonical_ssh_patator_support"] == 1180
        assert s["laboratory_ssh_support"] == 69
        assert s["n_features"] == 78

    def test_ground_truth_stays_family_level(self):
        s = self._summary()
        assert s["primary_reference"] == "SSH-Patator"
        assert "family-level Brute Force" in s["ground_truth_note"]

    def test_unit_mismatch_is_recorded_for_time_features(self):
        s = self._summary()
        assert s["semantic_audit_overview"]["unit_mismatch_suspected_count"] >= 10
        assert "Flow Duration" in s["semantic_audit_overview"]["unit_mismatch_features"]

    def test_cross_scenario_is_consistent(self):
        s = self._summary()
        assert s["cross_scenario"]["classification"] == "CONSISTENT_CROSS_SCENARIO_SHIFT"
        assert s["shift_overview_primary"]["median_ks"] > 0.5

    def test_feature_shift_csv_covers_all_features(self):
        path = DIAG_DIR / "feature_shift.csv"
        if not path.exists():
            pytest.skip("feature_shift.csv mungon")
        with open(path, encoding="utf-8") as handle:
            assert len(list(csv.DictReader(handle))) == 78


class TestFrozenSshUntouched:

    def test_ssh_run_metrics_unchanged_by_diagnostic(self):
        path = (ML_SERVICE_ROOT / "reports" / "live_evaluation" / "runs"
                / "lab-v1-ssh-bruteforce-001" / "metrics.json")
        if not path.exists():
            pytest.skip("ssh metrics mungojne")
        with open(path, encoding="utf-8") as handle:
            b = json.load(handle)["binary"]
        assert b["true_positive"] == 0
        assert b["attack_flows"] == 69
        assert b["attack_detection_rate"] == 0.0
