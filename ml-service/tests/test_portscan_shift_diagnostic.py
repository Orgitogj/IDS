import csv
import json
from pathlib import Path

import numpy as np
import pytest

from training import portscan_shift_diagnostic as diag

ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
DIAG_DIR = (ML_SERVICE_ROOT / "reports" / "live_evaluation" / "diagnostics"
            / "portscan_feature_shift")


class TestShiftMath:

    def test_identical_distributions_have_zero_ks(self):
        rng = np.random.default_rng(0)
        x = rng.normal(size=(500, 1))
        rows = diag.feature_stats(x, x.copy(), ["f"])

        assert rows[0]["ks_statistic"] == pytest.approx(0.0, abs=1e-9)
        assert rows[0]["pct_lab_outside_canon_iqr"] == pytest.approx(50.0, abs=5.0)

    def test_disjoint_distributions_have_ks_one(self):
        rng = np.random.default_rng(1)
        canon = rng.normal(0.0, 1.0, size=(300, 1))
        lab = rng.normal(50.0, 1.0, size=(300, 1))
        rows = diag.feature_stats(canon, lab, ["f"])

        assert rows[0]["ks_statistic"] == pytest.approx(1.0)
        assert rows[0]["pct_lab_outside_canon_p01_p99"] == 100.0
        assert rows[0]["canon_constant"] is False

    def test_a_constant_canonical_feature_reports_no_ks_not_a_crash(self):
        canon = np.zeros((100, 1))
        lab = np.concatenate([np.zeros((50, 1)), np.ones((50, 1))])
        rows = diag.feature_stats(canon, lab, ["f"])

        assert rows[0]["canon_constant"] is True
        assert rows[0]["ks_statistic"] is None
        assert rows[0]["median_ratio"] is None

    def test_median_ratio_is_suppressed_when_canonical_median_is_zero(self):
        canon = np.concatenate([np.zeros((90, 1)), np.ones((10, 1))])
        lab = np.ones((100, 1)) * 5.0
        rows = diag.feature_stats(canon, lab, ["f"])

        assert rows[0]["canon_median"] == 0.0
        assert rows[0]["median_ratio"] is None
        assert rows[0]["ks_statistic"] is not None


@pytest.mark.dataset
class TestDiagnosticArtifacts:

    def _summary(self):
        path = DIAG_DIR / "summary.json"
        if not path.exists():
            pytest.skip("diagnostiku i portscan nuk eshte gjeneruar")
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    def test_the_summary_marks_itself_diagnostic_only(self):
        summary = self._summary()

        assert summary["is_diagnostic_only"] is True
        assert summary["does_not_modify_frozen_results"] is True
        assert summary["no_retraining_no_tuning_no_shap_no_llm"] is True

    def test_supports_match_the_expected_partitions(self):
        summary = self._summary()

        assert summary["canonical_portscan_support"] == 31761
        assert summary["laboratory_portscan_support"] == 1362
        assert summary["n_features"] == 78

    def test_feature_shift_csv_covers_every_feature(self):
        path = DIAG_DIR / "feature_shift.csv"
        if not path.exists():
            pytest.skip("feature_shift.csv mungon")
        with open(path, encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

        assert len(rows) == 78

    def test_the_conclusion_rests_on_a_real_majority_shift(self):
        summary = self._summary()
        overview = summary["shift_overview"]

        assert overview["features_ks_ge_0_5"] >= overview["features_with_ks_computed"] / 2
        assert overview["median_ks_statistic"] > 0.5


class TestFrozenPortScanUntouched:

    def test_the_portscan_run_metrics_are_not_modified_by_the_diagnostic(self):
        path = (ML_SERVICE_ROOT / "reports" / "live_evaluation" / "runs"
                / "lab-v1-portscan-001" / "metrics.json")
        if not path.exists():
            pytest.skip("portscan metrics mungojne")

        with open(path, encoding="utf-8") as handle:
            metrics = json.load(handle)

        assert metrics["binary"]["attack_detection_rate"] == pytest.approx(2 / 1362)
        assert metrics["binary"]["evaluable_flows"] == 1362
