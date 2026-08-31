BENIGN_LABEL = "BENIGN"
UNKNOWN_LABEL = "UNKNOWN"

DETECTION_BENIGN = "BENIGN"
DETECTION_KNOWN_ATTACK = "KNOWN_ATTACK"
DETECTION_SUSPICIOUS = "SUSPICIOUS"

METHOD_SUPERVISED = "SUPERVISED_ML"
METHOD_ANOMALY = "ANOMALY_DETECTION"


def decide(supervised, anomaly=None):
    predicted_label = supervised["predicted_label"]
    confidence = supervised["confidence"]
    anomaly_payload = anomaly.to_dict() if anomaly is not None else None
    anomaly_score = anomaly.anomaly_score if anomaly is not None and anomaly.available else None

    if predicted_label != BENIGN_LABEL:
        return {
            "prediction": predicted_label,
            "detection_class": DETECTION_KNOWN_ATTACK,
            "confidence": confidence,
            "detection_method": METHOD_SUPERVISED,
            "anomaly_score": anomaly_score,
            "supervised_label": predicted_label,
            "supervised_confidence": confidence,
            "anomaly": anomaly_payload,
        }

    if anomaly is not None and anomaly.available and anomaly.is_anomalous:
        return {
            "prediction": UNKNOWN_LABEL,
            "detection_class": DETECTION_SUSPICIOUS,
            "confidence": None,
            "detection_method": METHOD_ANOMALY,
            "anomaly_score": anomaly_score,
            "supervised_label": BENIGN_LABEL,
            "supervised_confidence": confidence,
            "anomaly": anomaly_payload,
        }

    return {
        "prediction": BENIGN_LABEL,
        "detection_class": DETECTION_BENIGN,
        "confidence": confidence,
        "detection_method": METHOD_SUPERVISED,
        "anomaly_score": anomaly_score,
        "supervised_label": BENIGN_LABEL,
        "supervised_confidence": confidence,
        "anomaly": anomaly_payload,
    }


def to_flow_label(detection_class):
    if detection_class == DETECTION_KNOWN_ATTACK:
        return "ATTACK"
    if detection_class == DETECTION_SUSPICIOUS:
        return "UNKNOWN"
    return "BENIGN"
