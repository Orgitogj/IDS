import json
from pathlib import Path

import joblib
import numpy as np

from app.ml.feature_validation import PERMISSIVE_POLICY, FeatureValidator

DEFAULT_ARTIFACT = "isolation_forest_benign_v2.joblib"
DEFAULT_CALIBRATION = "isolation_forest_benign_v2_calibration.json"

UNAVAILABLE_NOT_LOADED = "anomaly_detector_not_loaded"
UNAVAILABLE_FEATURES = "anomaly_features_unavailable"


class AnomalyResult:
    def __init__(self, available, reason=None, raw_score=None, anomaly_score=None,
                 is_anomalous=False, missing_features=None):
        self.available = available
        self.reason = reason
        self.raw_score = raw_score
        self.anomaly_score = anomaly_score
        self.is_anomalous = is_anomalous
        self.missing_features = missing_features or []

    def to_dict(self):
        return {
            "available": self.available,
            "reason": self.reason,
            "raw_score": self.raw_score,
            "anomaly_score": self.anomaly_score,
            "is_anomalous": self.is_anomalous,
            "missing_features": list(self.missing_features),
        }


class AnomalyDetector:
    def __init__(self, model, calibration, threshold_rate="0.010"):
        if threshold_rate not in calibration["thresholds"]:
            raise ValueError(
                f"Pragu '{threshold_rate}' s'ekziston; ne dispozicion: "
                f"{', '.join(calibration['thresholds'])}")

        self.model = model
        self.calibration = calibration
        self.feature_columns = calibration["feature_columns"]
        self.feature_version = calibration["feature_version"]
        self.artifact_file = calibration["artifact_file"]
        self.threshold_rate = threshold_rate
        self.threshold = calibration["thresholds"][threshold_rate]
        self._percentiles = np.asarray(calibration["percentile_grid"], dtype="float64")
        self._quantiles = np.asarray(calibration["calibration_quantiles"], dtype="float64")
        self.validator = FeatureValidator(
            self.feature_columns,
            reference=None,
            feature_version=self.feature_version,
            policy=PERMISSIVE_POLICY,
        )

    def identity(self):
        return {
            "anomaly_artifact_file": self.artifact_file,
            "anomaly_feature_version": self.feature_version,
            "anomaly_threshold_rate": float(self.threshold_rate),
            "anomaly_threshold": self.threshold,
        }

    def _to_anomaly_score(self, raw_score):
        position = float(np.interp(raw_score, self._quantiles, self._percentiles))
        return round(1.0 - min(max(position, 0.0), 1.0), 6)

    def score(self, raw_features):
        validation = self.validator.validate(raw_features)

        blocking = list(validation.missing_features) + [
            entry["feature"] for entry in validation.invalid_features
        ]
        if blocking:
            return AnomalyResult(available=False, reason=UNAVAILABLE_FEATURES,
                                 missing_features=blocking)

        row = np.asarray([validation.vector], dtype="float64")
        raw_score = float(self.model.score_samples(row)[0])

        return AnomalyResult(
            available=True,
            raw_score=raw_score,
            anomaly_score=self._to_anomaly_score(raw_score),
            is_anomalous=raw_score < self.threshold,
        )


def load_anomaly_detector(models_dir, artifact=DEFAULT_ARTIFACT,
                          calibration=DEFAULT_CALIBRATION, threshold_rate="0.010"):
    models_path = Path(models_dir)
    artifact_path = models_path / artifact
    calibration_path = models_path / calibration

    if not artifact_path.exists() or not calibration_path.exists():
        return None

    with open(calibration_path, encoding="utf-8") as handle:
        calibration_payload = json.load(handle)

    return AnomalyDetector(joblib.load(artifact_path), calibration_payload, threshold_rate)
