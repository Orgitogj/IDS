import json

import numpy as np
import pytest

from app.ml.drift import (
    DRIFTED_FRACTION_CRITICAL,
    INVALID_RATE_CRITICAL,
    INVALID_RATE_WARNING,
    STATUS_CRITICAL,
    STATUS_NORMAL,
    STATUS_WARNING,
    DriftMonitor,
    ks_against_reference,
    load_thresholds,
)
from app.ml.feature_validation import STRICT_POLICY, FeatureValidator


@pytest.fixture(scope="module")
def thresholds():
    loaded = load_thresholds()
    if loaded is None:
        pytest.skip("drift_thresholds.json mungon; xhiro training.calibrate_drift_thresholds")
    return loaded


@pytest.fixture
def monitor(top50_features, reference, thresholds):
    return DriftMonitor(top50_features, reference, thresholds, window_size=500)


@pytest.fixture
def validator(top50_features, reference):
    return FeatureValidator(top50_features, reference=reference, policy=STRICT_POLICY)


@pytest.fixture
def realistic_vectors(reference, all_features):
    rng = np.random.default_rng(11)

    def generate(count):
        for _ in range(count):
            yield {
                name: float(reference["features"][name]["quantiles"][
                    rng.integers(0, len(reference["features"][name]["quantiles"]))])
                for name in all_features
            }

    return generate


def test_ks_is_zero_for_a_perfectly_matching_sample():
    percentiles = np.linspace(0.0, 1.0, 101)
    quantiles = np.linspace(0.0, 100.0, 101)
    sample = np.linspace(0.0, 100.0, 1001)
    assert ks_against_reference(sample, quantiles, percentiles) < 0.05


def test_ks_grows_when_the_sample_shifts():
    percentiles = np.linspace(0.0, 1.0, 101)
    quantiles = np.linspace(0.0, 100.0, 101)
    close = ks_against_reference(np.linspace(0.0, 100.0, 500), quantiles, percentiles)
    far = ks_against_reference(np.linspace(200.0, 300.0, 500), quantiles, percentiles)
    assert far > close
    assert far == pytest.approx(1.0, abs=0.01)


def test_ks_handles_a_constant_reference():
    percentiles = np.linspace(0.0, 1.0, 101)
    quantiles = np.zeros(101)
    assert ks_against_reference(np.zeros(10), quantiles, percentiles) == 0.0
    assert ks_against_reference(np.ones(10), quantiles, percentiles) == 1.0


def test_ks_ignores_non_finite_values():
    percentiles = np.linspace(0.0, 1.0, 101)
    quantiles = np.linspace(0.0, 100.0, 101)
    sample = np.array([float("nan"), float("inf"), 50.0, 25.0])
    assert 0.0 <= ks_against_reference(sample, quantiles, percentiles) <= 1.0


def test_ks_of_an_empty_sample_is_zero():
    percentiles = np.linspace(0.0, 1.0, 101)
    quantiles = np.linspace(0.0, 100.0, 101)
    assert ks_against_reference(np.array([]), quantiles, percentiles) == 0.0


def test_calibrated_thresholds_are_far_above_the_asymptotic_value(thresholds):
    for key, window in thresholds["windows"].items():
        assert window["median_feature_p95"] > window["asymptotic_p95_reference"] * 2, key


def test_calibration_records_its_protocol(thresholds):
    assert "null" in thresholds["protocol"]
    assert thresholds["bootstrap_draws"] > 0
    assert set(thresholds["windows"]) == {str(size) for size in thresholds["window_sizes"]}


def test_the_no_drift_fraction_is_small(thresholds):
    for window in thresholds["windows"].values():
        assert window["mean_drifted_fraction"] < 0.10
        assert window["drifted_fraction_thresholds"]["p99"] < DRIFTED_FRACTION_CRITICAL


def test_a_fresh_monitor_reports_nothing_observed(monitor):
    report = monitor.report()
    assert report["observed_flows"] == 0
    assert report["sample_size"] == 0
    assert report["status"] == STATUS_NORMAL


def test_in_distribution_traffic_is_normal(monitor, validator, realistic_vectors):
    for vector in realistic_vectors(300):
        monitor.record(validator.validate(vector))

    report = monitor.report()
    assert report["status"] == STATUS_NORMAL
    assert report["invalid_rate"] == 0.0
    assert report["drifted_fraction"] <= DRIFTED_FRACTION_CRITICAL


def test_a_large_shift_is_reported_as_drift(monitor, validator, reference, top50_features):
    rng = np.random.default_rng(7)
    for _ in range(300):
        vector = {}
        for name in top50_features:
            quantiles = reference["features"][name]["quantiles"]
            vector[name] = float(quantiles[rng.integers(0, len(quantiles))]) * 1000.0 + 1e6
        monitor.record(validator.validate(vector))

    report = monitor.report()
    assert report["drifted_feature_count"] > 0
    assert report["status"] in {STATUS_WARNING, STATUS_CRITICAL}


def test_rejections_raise_the_invalid_rate(monitor, validator, realistic_vectors):
    for index, vector in enumerate(realistic_vectors(200)):
        if index % 10 == 0:
            vector["Init_Win_bytes_backward"] = "abc"
        monitor.record(validator.validate(vector))

    report = monitor.report()
    assert report["invalid_rate"] == pytest.approx(0.10, abs=0.01)
    assert report["status"] == STATUS_CRITICAL
    assert report["rejection_reasons"]["non_numeric"] == 20


def test_a_small_invalid_rate_is_only_a_warning(monitor, validator, realistic_vectors):
    for index, vector in enumerate(realistic_vectors(200)):
        if index % 50 == 0:
            vector["Init_Win_bytes_backward"] = "abc"
        monitor.record(validator.validate(vector))

    report = monitor.report()
    assert INVALID_RATE_WARNING < report["invalid_rate"] <= INVALID_RATE_CRITICAL
    assert report["status"] == STATUS_WARNING


def test_an_unvarying_feed_is_itself_reported_as_drift(monitor, validator, full_vector):
    for _ in range(200):
        monitor.record(validator.validate(dict(full_vector)))

    report = monitor.report()
    assert report["invalid_rate"] == 0.0
    assert report["status"] == STATUS_CRITICAL
    assert report["drifted_fraction"] > DRIFTED_FRACTION_CRITICAL


def test_a_persistently_missing_feature_is_critical(monitor, validator, full_vector):
    for _ in range(100):
        vector = dict(full_vector)
        del vector["Init_Win_bytes_backward"]
        monitor.record(validator.validate(vector))

    report = monitor.report()
    assert report["status"] == STATUS_CRITICAL
    assert report["features"]["Init_Win_bytes_backward"]["missing_rate"] == 1.0
    assert any("missing" in reason for reason in report["reasons"])


def test_derived_features_are_counted(monitor, validator, full_vector):
    for _ in range(50):
        vector = dict(full_vector)
        del vector["Down/Up Ratio"]
        monitor.record(validator.validate(vector))

    report = monitor.report()
    assert report["features"]["Down/Up Ratio"]["derived_rate"] == 1.0
    assert report["accepted_flows"] == 50


def test_rejected_vectors_never_enter_the_sample_window(monitor, validator):
    for _ in range(20):
        monitor.record(validator.validate({}))

    report = monitor.report()
    assert report["observed_flows"] == 20
    assert report["rejected_flows"] == 20
    assert report["sample_size"] == 0


def test_the_window_is_bounded(reference, top50_features, thresholds, validator, full_vector):
    monitor = DriftMonitor(top50_features, reference, thresholds, window_size=50)
    for _ in range(200):
        monitor.record(validator.validate(full_vector))

    report = monitor.report()
    assert report["observed_flows"] == 200
    assert report["sample_size"] == 50


def test_the_nearest_calibration_window_is_chosen(reference, top50_features, thresholds,
                                                  validator, full_vector):
    monitor = DriftMonitor(top50_features, reference, thresholds, window_size=500)
    for _ in range(500):
        monitor.record(validator.validate(full_vector))
    assert monitor.report()["calibration_window"] == 500


def test_reset_clears_every_counter(monitor, validator, full_vector):
    for _ in range(30):
        monitor.record(validator.validate(full_vector))
    monitor.reset()

    report = monitor.report()
    assert report["observed_flows"] == 0
    assert report["rejected_flows"] == 0
    assert report["sample_size"] == 0


def test_the_report_is_json_serialisable(monitor, validator, full_vector):
    for _ in range(20):
        monitor.record(validator.validate(full_vector))
    json.dumps(monitor.report())


def test_the_report_carries_the_contract_fields(monitor, validator, full_vector):
    monitor.record(validator.validate(full_vector))
    report = monitor.report()
    assert set(report) >= {
        "generated_at", "status", "reasons", "observed_flows", "accepted_flows",
        "rejected_flows", "sample_size", "invalid_rate", "rejection_reasons",
        "drifted_feature_count", "drifted_features", "drifted_fraction",
        "calibration_window", "feature_version", "features",
    }
    assert report["status"] in {STATUS_NORMAL, STATUS_WARNING, STATUS_CRITICAL}


def test_a_monitor_without_thresholds_still_reports(reference, top50_features, validator,
                                                     full_vector):
    monitor = DriftMonitor(top50_features, reference, None, window_size=100)
    for _ in range(20):
        monitor.record(validator.validate(full_vector))

    report = monitor.report()
    assert report["calibration_window"] is None
    assert report["drifted_feature_count"] == 0
    assert report["status"] == STATUS_NORMAL
