import hashlib
import json
import time
from pathlib import Path

import joblib
import pandas as pd

from app.live import capture_time, protocol, schema_guard
from app.ml.feature_validation import STRICT_POLICY, FeatureValidator, load_reference
from app.replay.feature_mapping import CICFLOWMETER_TO_CICIDS2017, META_COLUMNS


class FrozenModelError(RuntimeError):
    pass


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_frozen_model(models_dir, expected=None, verify_sha=True):
    expected = expected or protocol.FROZEN_PRIMARY_MODEL
    models_dir = Path(models_dir)
    artifact = models_dir / expected["artifact_file"]

    if not artifact.exists():
        raise FrozenModelError(f"artefakti i ngrire mungon: {artifact}")

    digest = sha256_of(artifact)
    if verify_sha and digest != expected["artifact_sha256"]:
        raise FrozenModelError(
            f"SHA-256 e artefaktit nuk perputhet me metadaten e ngrire. "
            f"pritej {expected['artifact_sha256']}, u gjet {digest}")

    model = joblib.load(artifact)
    label_encoder = joblib.load(models_dir / "label_encoder_cicids2017.joblib")

    names = getattr(model, "feature_names_in_", None)
    if names is None:
        raise FrozenModelError(
            f"{artifact.name} s'ka feature_names_in_; rruga laboratorike kerkon nje "
            f"artefakt me skeme te emertuar qe te garantoje paritetin me trajnimin")

    feature_columns = [str(name) for name in names]

    sidecar = models_dir / f"{artifact.stem}_feature_columns.json"
    if sidecar.exists():
        with open(sidecar, encoding="utf-8") as handle:
            declared = [str(name) for name in json.load(handle)]
        schema_guard.assert_schema(feature_columns, declared,
                                   expected["feature_version"], expected["n_features"])
    elif len(feature_columns) != expected["n_features"]:
        raise FrozenModelError(
            f"modeli ka {len(feature_columns)} features, skema e ngrire pret "
            f"{expected['n_features']}")

    identity = {
        "model_name": expected["name"],
        "model_version": expected["version"],
        "artifact_file": artifact.name,
        "artifact_sha256": digest,
        "feature_schema": expected["feature_version"],
        "feature_count": len(feature_columns),
        "sha_verified": bool(verify_sha),
        "frozen_before_results": True,
    }
    return model, label_encoder, feature_columns, identity


def map_row(row):
    mapped = {}
    for key, value in row.items():
        if key in META_COLUMNS:
            continue
        name = CICFLOWMETER_TO_CICIDS2017.get(key)
        if name:
            mapped[name] = value
    return mapped


def build_validator(feature_columns, reference_path=None, feature_version=None):
    reference = load_reference(reference_path)
    return FeatureValidator(
        feature_columns, reference=reference,
        feature_version=feature_version or protocol.FROZEN_PRIMARY_MODEL["feature_version"],
        policy=STRICT_POLICY)


def predict_vector(model, label_encoder, feature_columns, vector):
    frame = pd.DataFrame([vector], columns=feature_columns)
    start = time.perf_counter()
    predicted_idx = model.predict(frame)[0]
    probabilities = model.predict_proba(frame)[0]
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    label = label_encoder.inverse_transform([predicted_idx])[0]
    return {
        "predicted_label": str(label),
        "prediction_confidence": float(probabilities[predicted_idx]),
        "model_inference_latency_ms": elapsed_ms,
    }


def process_row(row, manifest, model, label_encoder, feature_columns, validator,
                identity, extra_feature_policy=None):
    request_received = time.perf_counter()

    timing = capture_time.resolve(
        row, assume_utc=manifest.timestamp_assumed_utc,
        timezone_name=manifest.capture_timezone)
    expected = manifest.expected_for_flow(row)

    mapped = map_row(row)
    validation = validator.validate(mapped)
    status = schema_guard.status_from_validation(validation, extra_feature_policy)

    record = {
        "run_id": manifest.run_id,
        "experiment_id": manifest.experiment_id,
        "scenario_id": manifest.scenario_id,
        "source_ip": row.get("src_ip"),
        "destination_ip": row.get("dst_ip"),
        "source_port": row.get("src_port"),
        "destination_port": row.get("dst_port"),
        "protocol": row.get("protocol"),
        "expected_binary_label": expected,
        "expected_family": manifest.expected_family,
        "expected_label": manifest.expected_label,
        "predicted_label": None,
        "prediction_confidence": None,
        "feature_schema": identity["feature_schema"],
        "feature_count": identity["feature_count"],
        "model_inference_latency_ms": None,
        "production_path_inference_latency_ms": None,
    }
    record.update(timing)
    record.update(status)

    if record["validation_status"] != protocol.STATUS_VALID:
        record["production_path_inference_latency_ms"] = (
            time.perf_counter() - request_received) * 1000.0
        return record, None

    try:
        prediction = predict_vector(model, label_encoder, feature_columns,
                                    validation.vector)
    except Exception as error:
        record["validation_status"] = protocol.STATUS_MODEL_ERROR
        record["validation_errors"] = [str(error)[:200]]
        record["production_path_inference_latency_ms"] = (
            time.perf_counter() - request_received) * 1000.0
        return record, None

    record.update(prediction)
    record["production_path_inference_latency_ms"] = (
        time.perf_counter() - request_received) * 1000.0

    feature_vector = dict(zip(feature_columns, validation.vector))
    return record, feature_vector
