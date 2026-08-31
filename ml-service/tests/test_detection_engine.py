import pytest

from app.ml.anomaly import AnomalyResult
from app.ml.detection_engine import (
    DETECTION_BENIGN,
    DETECTION_KNOWN_ATTACK,
    DETECTION_SUSPICIOUS,
    METHOD_ANOMALY,
    METHOD_SUPERVISED,
    decide,
    to_flow_label,
)


def supervised(label, confidence=0.9):
    return {"predicted_label": label, "confidence": confidence}


def anomalous(score=0.995):
    return AnomalyResult(available=True, raw_score=-0.62, anomaly_score=score,
                         is_anomalous=True)


def normal(score=0.10):
    return AnomalyResult(available=True, raw_score=-0.41, anomaly_score=score,
                         is_anomalous=False)


def unavailable():
    return AnomalyResult(available=False, reason="anomaly_features_unavailable",
                         missing_features=["Idle Max"])


def test_a_named_attack_is_a_known_attack():
    result = decide(supervised("PortScan", 0.96), normal())
    assert result["prediction"] == "PortScan"
    assert result["detection_class"] == DETECTION_KNOWN_ATTACK
    assert result["detection_method"] == METHOD_SUPERVISED
    assert result["confidence"] == 0.96


def test_the_supervised_verdict_wins_even_when_the_anomaly_score_is_low():
    result = decide(supervised("DDoS", 0.71), normal(score=0.02))
    assert result["detection_class"] == DETECTION_KNOWN_ATTACK
    assert result["detection_method"] == METHOD_SUPERVISED


def test_a_known_attack_still_reports_its_anomaly_score():
    result = decide(supervised("DoS Hulk", 0.99), anomalous(0.97))
    assert result["detection_class"] == DETECTION_KNOWN_ATTACK
    assert result["anomaly_score"] == 0.97


def test_benign_with_a_normal_score_is_benign():
    result = decide(supervised("BENIGN", 0.99), normal())
    assert result["prediction"] == "BENIGN"
    assert result["detection_class"] == DETECTION_BENIGN
    assert result["detection_method"] == METHOD_SUPERVISED
    assert result["confidence"] == 0.99


def test_benign_with_an_anomalous_score_becomes_suspicious():
    result = decide(supervised("BENIGN", 0.88), anomalous(0.993))
    assert result["prediction"] == "UNKNOWN"
    assert result["detection_class"] == DETECTION_SUSPICIOUS
    assert result["detection_method"] == METHOD_ANOMALY
    assert result["anomaly_score"] == 0.993


def test_a_suspicious_detection_reports_no_confidence():
    result = decide(supervised("BENIGN", 0.88), anomalous())
    assert result["confidence"] is None


def test_a_suspicious_detection_preserves_the_supervised_view():
    result = decide(supervised("BENIGN", 0.88), anomalous())
    assert result["supervised_label"] == "BENIGN"
    assert result["supervised_confidence"] == 0.88


def test_benign_stays_benign_when_the_detector_is_unavailable():
    result = decide(supervised("BENIGN", 0.97), unavailable())
    assert result["detection_class"] == DETECTION_BENIGN
    assert result["anomaly_score"] is None
    assert result["anomaly"]["available"] is False
    assert result["anomaly"]["missing_features"] == ["Idle Max"]


def test_an_attack_is_still_detected_when_the_detector_is_unavailable():
    result = decide(supervised("PortScan", 0.95), unavailable())
    assert result["detection_class"] == DETECTION_KNOWN_ATTACK
    assert result["anomaly_score"] is None


def test_the_engine_works_with_no_anomaly_detector_at_all():
    result = decide(supervised("BENIGN", 0.97), None)
    assert result["detection_class"] == DETECTION_BENIGN
    assert result["anomaly"] is None
    assert result["anomaly_score"] is None

    attack = decide(supervised("Bot", 0.80), None)
    assert attack["detection_class"] == DETECTION_KNOWN_ATTACK


def test_an_unavailable_detector_can_never_raise_a_suspicious_verdict():
    result = decide(supervised("BENIGN", 0.5), unavailable())
    assert result["detection_class"] != DETECTION_SUSPICIOUS


@pytest.mark.parametrize("detection_class,expected", [
    (DETECTION_KNOWN_ATTACK, "ATTACK"),
    (DETECTION_SUSPICIOUS, "UNKNOWN"),
    (DETECTION_BENIGN, "BENIGN"),
])
def test_detection_classes_map_onto_the_stored_flow_label(detection_class, expected):
    assert to_flow_label(detection_class) == expected


def test_every_decision_carries_the_contract_fields():
    for anomaly in [normal(), anomalous(), unavailable(), None]:
        for label in ["BENIGN", "PortScan"]:
            result = decide(supervised(label), anomaly)
            assert set(result) >= {
                "prediction", "detection_class", "confidence", "detection_method",
                "anomaly_score", "supervised_label", "supervised_confidence", "anomaly",
            }
            assert result["detection_method"] in {METHOD_SUPERVISED, METHOD_ANOMALY}
