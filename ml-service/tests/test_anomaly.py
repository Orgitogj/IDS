import json

import pytest

from app.ml.anomaly import (
    UNAVAILABLE_FEATURES,
    AnomalyDetector,
    AnomalyResult,
    load_anomaly_detector,
)
from tests.conftest import MODELS_DIR

CALIBRATION_FILE = MODELS_DIR / "isolation_forest_benign_v2_calibration.json"
ARTIFACT_FILE = MODELS_DIR / "isolation_forest_benign_v2.joblib"

pytestmark = pytest.mark.artifacts


@pytest.fixture(scope="module")
def detector():
    if not ARTIFACT_FILE.exists() or not CALIBRATION_FILE.exists():
        pytest.skip("artefakti i detektorit te anomalive mungon")
    return load_anomaly_detector(MODELS_DIR)


@pytest.fixture(scope="module")
def calibration():
    if not CALIBRATION_FILE.exists():
        pytest.skip("kalibrimi mungon")
    with open(CALIBRATION_FILE, encoding="utf-8") as handle:
        return json.load(handle)


def test_detector_reports_its_identity(detector):
    identity = detector.identity()
    assert identity["anomaly_artifact_file"] == "isolation_forest_benign_v2.joblib"
    assert identity["anomaly_feature_version"] == "cicids2017-78-v1"
    assert identity["anomaly_threshold_rate"] == 0.01


def test_calibration_records_a_leak_free_protocol(calibration):
    assert calibration["trained_on"] == "BENIGN training rows only"
    assert "no attack row and no test row" in calibration["threshold_selection"]
    assert calibration["calibration_rows"] > 0
    assert calibration["fit_rows"] > 0


def test_calibration_thresholds_increase_with_the_target_rate(calibration):
    thresholds = calibration["thresholds"]
    ordered = [thresholds[key] for key in sorted(thresholds, key=float)]
    assert ordered == sorted(ordered)


def test_calibration_quantiles_are_monotonic(calibration):
    quantiles = calibration["calibration_quantiles"]
    assert quantiles == sorted(quantiles)
    assert len(quantiles) == len(calibration["percentile_grid"])


def test_a_typical_benign_vector_is_not_anomalous(detector, full_vector):
    result = detector.score(full_vector)
    assert result.available
    assert not result.is_anomalous
    assert 0.0 <= result.anomaly_score <= 1.0


def test_the_anomaly_score_is_a_calibrated_percentile(detector, full_vector):
    result = detector.score(full_vector)
    assert result.anomaly_score < 0.5


def test_an_extreme_vector_scores_more_anomalous_than_a_typical_one(detector, full_vector,
                                                                    reference):
    typical = detector.score(full_vector)

    extreme = dict(full_vector)
    for name in ["Flow Duration", "Flow Bytes/s", "Flow Packets/s"]:
        extreme[name] = reference["features"][name]["max"]

    assert detector.score(extreme).anomaly_score > typical.anomaly_score


def test_the_threshold_matches_the_calibration_file(detector, calibration):
    assert detector.threshold == calibration["thresholds"]["0.010"]


def test_is_anomalous_agrees_with_the_threshold(detector, full_vector):
    result = detector.score(full_vector)
    assert result.is_anomalous == (result.raw_score < detector.threshold)


def test_a_missing_feature_makes_the_detector_unavailable(detector, full_vector):
    del full_vector["Idle Max"]
    result = detector.score(full_vector)
    assert not result.available
    assert result.reason == UNAVAILABLE_FEATURES
    assert "Idle Max" in result.missing_features
    assert result.anomaly_score is None


def test_an_invalid_value_makes_the_detector_unavailable(detector, full_vector):
    full_vector["Idle Max"] = float("nan")
    result = detector.score(full_vector)
    assert not result.available
    assert "Idle Max" in result.missing_features


def test_const_zero_features_do_not_block_the_detector(detector, full_vector):
    from app.replay.feature_mapping import CONST_ZERO_IN_TRAINING

    for name in CONST_ZERO_IN_TRAINING:
        del full_vector[name]

    result = detector.score(full_vector)
    assert result.available


def test_an_empty_vector_makes_the_detector_unavailable(detector):
    result = detector.score({})
    assert not result.available
    assert len(result.missing_features) > 0


def test_result_serialises_to_the_api_contract(detector, full_vector):
    payload = detector.score(full_vector).to_dict()
    assert set(payload) == {
        "available", "reason", "raw_score", "anomaly_score",
        "is_anomalous", "missing_features",
    }
    json.dumps(payload)


def test_unavailable_result_serialises_too():
    payload = AnomalyResult(available=False, reason=UNAVAILABLE_FEATURES,
                            missing_features=["X"]).to_dict()
    assert payload["available"] is False
    assert payload["anomaly_score"] is None
    json.dumps(payload)


def test_an_unknown_threshold_rate_is_rejected(calibration):
    import joblib

    with pytest.raises(ValueError, match="s'ekziston"):
        AnomalyDetector(joblib.load(ARTIFACT_FILE), calibration, threshold_rate="0.999")


def test_a_stricter_threshold_flags_fewer_flows(calibration):
    import joblib

    model = joblib.load(ARTIFACT_FILE)
    strict = AnomalyDetector(model, calibration, threshold_rate="0.001")
    loose = AnomalyDetector(model, calibration, threshold_rate="0.050")
    assert strict.threshold < loose.threshold


def test_missing_artifacts_return_no_detector(tmp_path):
    assert load_anomaly_detector(tmp_path) is None
