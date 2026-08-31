import pytest
import requests

from app.ml import model_registry
from app.ml.model_registry import (
    ModelIdentity,
    fallback_identity,
    fetch_active_identity,
    fetch_identity_by_id,
    identity_from_registry,
)

REGISTRY_PAYLOAD = {
    "id": "133f003c-baab-4e11-8b12-21f5f37e2896",
    "algorithm": "XGBoost",
    "name": "xgb-smote-top50features-v1",
    "version": "1.0",
    "featureVersion": "cicids2017-top50-v1",
    "artifactPath": "models/xgb_smote_top50features_v1.joblib",
}


def test_identity_reduces_artifact_path_to_a_filename():
    identity = identity_from_registry(REGISTRY_PAYLOAD)
    assert identity.artifact_file == "xgb_smote_top50features_v1.joblib"


def test_identity_carries_every_registry_field():
    identity = identity_from_registry(REGISTRY_PAYLOAD)
    assert identity.model_id == REGISTRY_PAYLOAD["id"]
    assert identity.name == "xgb-smote-top50features-v1"
    assert identity.version == "1.0"
    assert identity.feature_version == "cicids2017-top50-v1"
    assert identity.algorithm == "XGBoost"
    assert identity.source == "registry"


def test_identity_survives_a_null_feature_version():
    payload = dict(REGISTRY_PAYLOAD, featureVersion=None)
    assert identity_from_registry(payload).feature_version is None


def test_identity_handles_a_windows_style_artifact_path():
    payload = dict(REGISTRY_PAYLOAD, artifactPath="models\\xgb_smote_top50features_v1.joblib")
    assert identity_from_registry(payload).artifact_file.endswith(".joblib")


def test_identity_to_dict_is_stable():
    payload = identity_from_registry(REGISTRY_PAYLOAD).to_dict()
    assert set(payload) == {
        "model_id", "model_name", "model_version", "feature_version",
        "algorithm", "artifact_file", "registry_source",
    }


def test_fallback_identity_is_marked_as_a_fallback():
    identity = fallback_identity()
    assert identity.source == "fallback"
    assert identity.model_id is None
    assert identity.version == "unknown"
    assert identity.artifact_file.endswith(".joblib")


def test_bare_identity_names_itself_after_its_artifact():
    identity = ModelIdentity(artifact_file="some_model_v3.joblib")
    assert identity.name == "some_model_v3"


def test_active_identity_comes_from_the_registry(monkeypatch):
    monkeypatch.setattr(model_registry.spring_client, "get_active_model",
                        lambda: REGISTRY_PAYLOAD)
    identity = fetch_active_identity()
    assert identity.source == "registry"
    assert identity.name == "xgb-smote-top50features-v1"


def test_unreachable_registry_falls_back_instead_of_raising(monkeypatch):
    def boom():
        raise requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr(model_registry.spring_client, "get_active_model", boom)
    identity = fetch_active_identity()
    assert identity.source == "fallback"
    assert identity.model_id is None


def test_malformed_registry_response_falls_back(monkeypatch):
    monkeypatch.setattr(model_registry.spring_client, "get_active_model", lambda: {})
    assert fetch_active_identity().source == "fallback"


def test_lookup_by_id_propagates_registry_errors(monkeypatch):
    def boom(model_id):
        raise requests.exceptions.HTTPError("404")

    monkeypatch.setattr(model_registry.spring_client, "get_model", boom)
    with pytest.raises(requests.exceptions.HTTPError):
        fetch_identity_by_id("00000000-0000-0000-0000-000000000000")


def test_lookup_by_id_returns_a_registry_identity(monkeypatch):
    monkeypatch.setattr(model_registry.spring_client, "get_model",
                        lambda model_id: REGISTRY_PAYLOAD)
    identity = fetch_identity_by_id(REGISTRY_PAYLOAD["id"])
    assert identity.source == "registry"
    assert identity.artifact_file == "xgb_smote_top50features_v1.joblib"
