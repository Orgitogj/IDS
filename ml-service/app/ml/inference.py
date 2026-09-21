import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests
import xgboost as xgb

from app.core.config import settings
from app.ml.feature_validation import (
    STRICT_POLICY,
    FeatureValidator,
    FeatureVersionMismatch,
    load_reference,
    resolve_feature_version,
    verify_feature_version,
)
from app.ml.anomaly import load_anomaly_detector
from app.ml.detection_engine import METHOD_ANOMALY, decide
from app.ml.drift import DriftMonitor, load_thresholds
from app.ml.feature_validation import FeatureValidationError
from app.ml.model_registry import fetch_active_identity, fetch_identity_by_id
from app.services import spring_client

MAX_CACHED_MODELS = 4

_loaded = {}
_load_order = []
_active_key = None
_label_encoder = None
_reference = None
_anomaly_detector = None
_drift_monitor = None
_since_publish = 0


class UnsupportedModelError(RuntimeError):
    pass


class LoadedModel:
    def __init__(self, identity, model, label_encoder, feature_columns, validator):
        self.identity = identity
        self.model = model
        self.label_encoder = label_encoder
        self.feature_columns = feature_columns
        self.validator = validator
        self.booster = model.get_booster()


def _models_dir():
    return Path(settings.models_dir)


def _feature_columns_for(model, models_dir, artifact_file=None):
    names = getattr(model, "feature_names_in_", None)
    if names is not None:
        return [str(name) for name in names]

    expected = getattr(model, "n_features_in_", None)

    if artifact_file:
        sidecar = models_dir / f"{Path(artifact_file).stem}_feature_columns.json"
        if sidecar.exists():
            with open(sidecar, encoding="utf-8") as handle:
                columns = [str(name) for name in json.load(handle)]
            if expected is not None and len(columns) != expected:
                raise RuntimeError(
                    f"{sidecar.name} ka {len(columns)} features ndersa modeli pret "
                    f"{expected}.")
            return columns

    with open(models_dir / "feature_columns.json") as handle:
        columns = [str(name) for name in json.load(handle)]

    if expected is not None and len(columns) != expected:
        raise RuntimeError(
            f"Modeli '{artifact_file}' pret {expected} features, por s'ekspozon "
            f"feature_names_in_ dhe s'ka sidecar; feature_columns.json i pergjithshem ka "
            f"{len(columns)}. Refuzoj fallback-un e heshtur - shto "
            f"'{Path(artifact_file or 'model').stem}_feature_columns.json'.")

    return columns


def _evict_if_needed():
    while len(_load_order) > MAX_CACHED_MODELS:
        evictable = [key for key in _load_order if key != _active_key]
        if not evictable:
            return
        oldest = evictable[0]
        _load_order.remove(oldest)
        _loaded.pop(oldest, None)


def _load(identity):
    global _label_encoder

    models_dir = _models_dir()
    artifact = models_dir / identity.artifact_file
    if not artifact.exists():
        raise RuntimeError(f"Artefakti i modelit s'u gjet: {artifact}")

    model = joblib.load(artifact)

    if _label_encoder is None:
        _label_encoder = joblib.load(models_dir / "label_encoder_cicids2017.joblib")

    feature_columns = _feature_columns_for(model, models_dir, identity.artifact_file)

    mismatch = verify_feature_version(feature_columns, identity.feature_version, _reference)
    if mismatch is not None:
        print(f"[inference] REFUZIM: {identity.artifact_file} -> {mismatch['message']}")
        raise FeatureVersionMismatch(mismatch)

    if not identity.feature_version:
        identity.feature_version = resolve_feature_version(feature_columns, _reference)

    validator = FeatureValidator(
        feature_columns,
        reference=_reference,
        feature_version=identity.feature_version,
        policy=STRICT_POLICY,
    )
    identity.feature_version = validator.feature_version

    if not hasattr(model, "get_booster"):
        raise UnsupportedModelError(
            f"Modeli '{identity.name}' ({type(model).__name__}) nuk mbeshtetet nga ml-service: "
            f"lejohen vetem modele XGBoost.")

    loaded = LoadedModel(identity, model, _label_encoder, feature_columns, validator)

    _loaded[identity.artifact_file] = loaded
    if identity.artifact_file in _load_order:
        _load_order.remove(identity.artifact_file)
    _load_order.append(identity.artifact_file)
    _evict_if_needed()

    print(f"[inference] U ngarkua {identity.artifact_file}: {len(feature_columns)} features, "
          f"model={identity.name} v{identity.version}, "
          f"feature_version={identity.feature_version}, burimi={identity.source}")

    return loaded


def anomaly_detector():
    return _anomaly_detector


def drift_monitor():
    return _drift_monitor


def _load_drift_monitor(feature_columns, feature_version=None):
    global _drift_monitor, _since_publish

    _since_publish = 0

    if not settings.drift_monitoring_enabled:
        _drift_monitor = None
        print("[inference] Monitorimi i drift-it eshte i cakivizuar nga konfigurimi.")
        return

    thresholds = load_thresholds()
    if thresholds is None:
        print("[inference] KUJDES: reports/drift_thresholds.json mungon; drift-i do te "
              "raportohet pa pragje te kalibruara (xhiro training.calibrate_drift_thresholds).")

    _drift_monitor = DriftMonitor(feature_columns, _reference, thresholds,
                                  window_size=settings.drift_window_size,
                                  feature_version=feature_version)
    print(f"[inference] Monitorimi i drift-it aktiv: dritare {settings.drift_window_size}, "
          f"publikim cdo {settings.drift_publish_every} flows")


def _load_anomaly_detector():
    global _anomaly_detector

    if not settings.anomaly_detection_enabled:
        _anomaly_detector = None
        print("[inference] Zbulimi i anomalive eshte i cakivizuar nga konfigurimi.")
        return

    _anomaly_detector = load_anomaly_detector(
        _models_dir(), threshold_rate=settings.anomaly_threshold_rate)

    if _anomaly_detector is None:
        print("[inference] KUJDES: artefakti i detektorit te anomalive mungon; "
              "zbulimi hibrid eshte joaktiv (xhiro training.build_anomaly_detector).")
    else:
        print(f"[inference] Detektor anomalish: {_anomaly_detector.artifact_file}, "
              f"feature_version={_anomaly_detector.feature_version}, "
              f"prag={_anomaly_detector.threshold:.6f} "
              f"(shkalla e synuar e flamurimit te BENIGN {_anomaly_detector.threshold_rate})")


def load_artifacts():
    global _active_key, _reference

    _reference = load_reference()
    if _reference is None:
        print("KUJDES: reports/training_feature_reference.json mungon - "
              "validimi i intervaleve eshte i cakivizuar.")

    identity = fetch_active_identity()
    loaded = _load(identity)
    _active_key = identity.artifact_file
    _load_anomaly_detector()
    _load_drift_monitor(loaded.feature_columns, loaded.identity.feature_version)
    return loaded


def reload_active():
    global _active_key

    identity = fetch_active_identity()
    _loaded.pop(identity.artifact_file, None)
    if identity.artifact_file in _load_order:
        _load_order.remove(identity.artifact_file)

    loaded = _load(identity)
    _active_key = identity.artifact_file
    _load_anomaly_detector()
    _load_drift_monitor(loaded.feature_columns, loaded.identity.feature_version)
    return loaded


def active_model():
    if _active_key is None:
        raise RuntimeError("Modeli nuk eshte ngarkuar ende - thirr load_artifacts() ne startup.")
    return _loaded[_active_key]


def model_for(model_id=None):
    if model_id is None:
        return active_model()

    active = active_model()
    if active.identity.model_id and str(active.identity.model_id) == str(model_id):
        return active

    for loaded in _loaded.values():
        if loaded.identity.model_id and str(loaded.identity.model_id) == str(model_id):
            return loaded

    identity = fetch_identity_by_id(model_id)
    cached = _loaded.get(identity.artifact_file)
    if cached is None:
        return _load(identity)
    if cached.identity.model_id is None:
        return _adopt_registry_identity(cached, identity)
    return cached


def _adopt_registry_identity(loaded, identity):
    if identity.feature_version and identity.feature_version != loaded.identity.feature_version:
        return _load(identity)

    identity.feature_version = loaded.identity.feature_version
    loaded.identity = identity
    print(f"[inference] {identity.artifact_file} mori identitetin nga regjistri: "
          f"model_id={identity.model_id}, model={identity.name} v{identity.version}")
    return loaded


def _observe_drift(validation):
    global _since_publish

    _drift_monitor.record(validation)
    _since_publish += 1

    if settings.drift_publish_every > 0 and _since_publish >= settings.drift_publish_every:
        _since_publish = 0
        publish_drift_report()


def publish_drift_report():
    if _drift_monitor is None:
        return None

    report = _drift_monitor.report()
    try:
        spring_client.create_drift_report(report)
    except requests.exceptions.RequestException as error:
        print(f"[inference] Raporti i drift-it s'u dergua dot: {error}")
    return report


def _tree_shap_values(loaded: LoadedModel, X_row: pd.DataFrame, predicted_idx: int) -> np.ndarray:
    contribs = loaded.booster.predict(xgb.DMatrix(X_row), pred_contribs=True)

    if contribs.ndim == 3:
        return contribs[0, predicted_idx, :-1]

    return contribs[0, :-1]


def predict(feature_vector: dict, include_shap: bool = True, model_id=None) -> dict:
    loaded = model_for(model_id)

    validation = loaded.validator.validate(feature_vector)
    if _drift_monitor is not None and loaded.identity.artifact_file == _active_key:
        _observe_drift(validation)
    if not validation.valid:
        raise FeatureValidationError(validation)

    X_row = pd.DataFrame([validation.vector], columns=loaded.feature_columns)

    predicted_idx = loaded.model.predict(X_row)[0]
    predicted_proba = loaded.model.predict_proba(X_row)[0]
    predicted_label = loaded.label_encoder.inverse_transform([predicted_idx])[0]
    confidence = float(predicted_proba[predicted_idx])

    supervised = {"predicted_label": predicted_label, "confidence": confidence}
    anomaly = _anomaly_detector.score(feature_vector) if _anomaly_detector else None
    detection = decide(supervised, anomaly)

    result = {
        "predicted_label": predicted_label,
        "confidence": confidence,
        "top_shap_features": None,
        "top_anomaly_features": None,
        "validation": validation.to_dict(),
    }
    result.update(detection)
    result.update(loaded.identity.to_dict())
    if _anomaly_detector is not None:
        result.update(_anomaly_detector.identity())

    if include_shap:
        shap_for_predicted = _tree_shap_values(loaded, X_row, predicted_idx)

        contributions = sorted(
            zip(loaded.feature_columns, X_row.values[0], shap_for_predicted),
            key=lambda x: abs(x[2]),
            reverse=True,
        )[:5]

        result["top_shap_features"] = [
            {"feature": f, "value": float(v), "shap_contribution": float(s)}
            for f, v, s in contributions
        ]

        if detection["detection_method"] == METHOD_ANOMALY and _anomaly_detector is not None:
            result["top_anomaly_features"] = _anomaly_detector.attribute(feature_vector)

    return result
