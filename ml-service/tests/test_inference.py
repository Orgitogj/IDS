import math

import pytest
import requests

from app.ml import inference, model_registry
from app.ml.feature_validation import FeatureValidationError, FeatureVersionMismatch

pytestmark = pytest.mark.artifacts

TOP50_PAYLOAD = {
    "id": "133f003c-baab-4e11-8b12-21f5f37e2896",
    "algorithm": "XGBoost",
    "name": "xgb-smote-top50features-v1",
    "version": "1.0",
    "featureVersion": None,
    "artifactPath": "models/xgb_smote_top50features_v1.joblib",
}

FULL78_PAYLOAD = {
    "id": "aaaaaaaa-0000-0000-0000-000000000078",
    "algorithm": "XGBoost",
    "name": "xgb-smote-cicids2017-v1",
    "version": "2.0",
    "featureVersion": None,
    "artifactPath": "models/xgb_smote_cicids2017_v1.joblib",
}


@pytest.fixture(autouse=True)
def isolated_inference_state(monkeypatch):
    monkeypatch.setattr(inference, "_loaded", {})
    monkeypatch.setattr(inference, "_load_order", [])
    monkeypatch.setattr(inference, "_active_key", None)
    monkeypatch.setattr(inference, "_label_encoder", None)
    monkeypatch.setattr(inference, "_reference", None)
    yield


def require_artifacts(*names):
    missing = [name for name in names if not (inference._models_dir() / name).exists()]
    if missing:
        pytest.skip(f"{', '.join(missing)} mungon ne models/")


@pytest.fixture
def full78_artifact():
    require_artifacts("xgb_smote_cicids2017_v1.joblib")


@pytest.fixture
def registry_backed(monkeypatch):
    monkeypatch.setattr(model_registry.spring_client, "get_active_model", lambda: TOP50_PAYLOAD)
    monkeypatch.setattr(model_registry.spring_client, "get_model",
                        lambda model_id: FULL78_PAYLOAD)
    return inference.load_artifacts()


def test_startup_loads_the_registry_active_model(registry_backed):
    identity = registry_backed.identity
    assert identity.name == "xgb-smote-top50features-v1"
    assert identity.source == "registry"
    assert len(registry_backed.feature_columns) == 50


def test_feature_version_is_resolved_when_the_registry_omits_it(registry_backed):
    assert registry_backed.identity.feature_version == "cicids2017-top50-v1"


def test_unreachable_registry_still_yields_a_usable_model(monkeypatch):
    def boom():
        raise requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr(model_registry.spring_client, "get_active_model", boom)
    loaded = inference.load_artifacts()
    assert loaded.identity.source == "fallback"
    assert loaded.identity.model_id is None
    assert loaded.model is not None


def test_prediction_carries_the_full_model_identity(registry_backed, full_vector):
    result = inference.predict(full_vector, include_shap=False)
    assert result["model_id"] == TOP50_PAYLOAD["id"]
    assert result["model_name"] == "xgb-smote-top50features-v1"
    assert result["model_version"] == "1.0"
    assert result["feature_version"] == "cicids2017-top50-v1"
    assert result["artifact_file"] == "xgb_smote_top50features_v1.joblib"
    assert result["registry_source"] == "registry"


def test_prediction_declares_its_detection_method(registry_backed, full_vector):
    result = inference.predict(full_vector, include_shap=False)
    assert result["detection_method"] in {"SUPERVISED_ML", "ANOMALY_DETECTION"}
    assert result["detection_class"] in {"BENIGN", "KNOWN_ATTACK", "SUSPICIOUS"}


def test_prediction_reports_an_anomaly_score_when_the_detector_is_loaded(registry_backed,
                                                                         full_vector):
    result = inference.predict(full_vector, include_shap=False)
    if inference.anomaly_detector() is None:
        assert result["anomaly_score"] is None
    else:
        assert 0.0 <= result["anomaly_score"] <= 1.0
        assert result["anomaly"]["available"] is True


def test_prediction_is_a_known_class_with_a_real_confidence(registry_backed, full_vector):
    result = inference.predict(full_vector, include_shap=False)
    assert result["predicted_label"] in set(registry_backed.label_encoder.classes_)
    assert 0.0 <= result["confidence"] <= 1.0


def test_prediction_embeds_its_validation_report(registry_backed, full_vector):
    result = inference.predict(full_vector, include_shap=False)
    assert result["validation"]["valid"] is True
    assert result["validation"]["feature_version"] == "cicids2017-top50-v1"


def test_shap_returns_five_ranked_contributions(registry_backed, full_vector):
    result = inference.predict(full_vector, include_shap=True)
    shap = result["top_shap_features"]
    assert len(shap) == 5
    magnitudes = [abs(entry["shap_contribution"]) for entry in shap]
    assert magnitudes == sorted(magnitudes, reverse=True)
    for entry in shap:
        assert entry["feature"] in registry_backed.feature_columns
        assert math.isfinite(entry["value"])


def test_shap_is_omitted_when_not_requested(registry_backed, full_vector):
    assert inference.predict(full_vector, include_shap=False)["top_shap_features"] is None


def test_invalid_vector_raises_instead_of_predicting(registry_backed):
    with pytest.raises(FeatureValidationError) as excinfo:
        inference.predict({}, include_shap=False)
    assert excinfo.value.result.valid is False


def test_partially_invalid_vector_raises(registry_backed, full_vector):
    full_vector["Init_Win_bytes_backward"] = float("nan")
    with pytest.raises(FeatureValidationError):
        inference.predict(full_vector, include_shap=False)


def test_predicting_before_load_is_an_explicit_error():
    with pytest.raises(RuntimeError):
        inference.active_model()


def test_targeting_another_model_uses_that_model(full78_artifact, registry_backed, full_vector):
    result = inference.predict(full_vector, include_shap=False,
                               model_id=FULL78_PAYLOAD["id"])
    assert result["model_name"] == "xgb-smote-cicids2017-v1"
    assert result["model_version"] == "2.0"
    assert result["feature_version"] == "cicids2017-78-v1"


def test_targeting_the_active_model_by_id_does_not_reload(registry_backed, full_vector):
    before = dict(inference._loaded)
    result = inference.predict(full_vector, include_shap=False,
                               model_id=TOP50_PAYLOAD["id"])
    assert result["model_name"] == "xgb-smote-top50features-v1"
    assert set(inference._loaded) == set(before)


def test_a_targeted_model_is_cached_after_first_use(full78_artifact, registry_backed, full_vector):
    inference.predict(full_vector, include_shap=False, model_id=FULL78_PAYLOAD["id"])
    assert "xgb_smote_cicids2017_v1.joblib" in inference._loaded
    inference.predict(full_vector, include_shap=False, model_id=FULL78_PAYLOAD["id"])
    assert len(inference._loaded) == 2


def test_different_models_can_disagree_on_feature_attribution(full78_artifact, registry_backed, full_vector):
    top50 = inference.predict(full_vector, include_shap=True)
    full78 = inference.predict(full_vector, include_shap=True, model_id=FULL78_PAYLOAD["id"])
    assert top50["feature_version"] != full78["feature_version"]
    assert len(top50["validation"]["missing_features"]) == 0
    assert len(full78["validation"]["missing_features"]) == 0


def test_unknown_model_id_propagates_the_registry_error(registry_backed, full_vector, monkeypatch):
    def boom(model_id):
        raise requests.exceptions.HTTPError("404")

    monkeypatch.setattr(model_registry.spring_client, "get_model", boom)
    with pytest.raises(requests.exceptions.HTTPError):
        inference.predict(full_vector, include_shap=False,
                          model_id="00000000-0000-0000-0000-000000000000")


def test_missing_artifact_is_reported_clearly(monkeypatch):
    payload = dict(TOP50_PAYLOAD, artifactPath="models/does_not_exist.joblib")
    monkeypatch.setattr(model_registry.spring_client, "get_active_model", lambda: payload)
    with pytest.raises(RuntimeError, match="nuk u gjet"):
        inference.load_artifacts()


def test_reload_picks_up_a_changed_active_model(full78_artifact, registry_backed, monkeypatch):
    assert inference.active_model().identity.name == "xgb-smote-top50features-v1"
    monkeypatch.setattr(model_registry.spring_client, "get_active_model", lambda: FULL78_PAYLOAD)
    reloaded = inference.reload_active()
    assert reloaded.identity.name == "xgb-smote-cicids2017-v1"
    assert inference.active_model().identity.name == "xgb-smote-cicids2017-v1"


def test_cache_never_evicts_the_active_model(registry_backed, full_vector, monkeypatch):
    others = [
        ("xgb_smote_top10features_v1.joblib", "10"),
        ("xgb_smote_top20features_v1.joblib", "20"),
        ("xgb_smote_top30features_v1.joblib", "30"),
        ("xgb_smote_top78features_v1.joblib", "78"),
    ]
    require_artifacts(*(artifact for artifact, _ in others))
    for artifact, suffix in others:
        payload = dict(TOP50_PAYLOAD, id=f"bbbbbbbb-0000-0000-0000-0000000000{suffix}",
                       name=f"model-{suffix}", artifactPath=f"models/{artifact}")
        monkeypatch.setattr(model_registry.spring_client, "get_model",
                            lambda model_id, p=payload: p)
        inference.predict(full_vector, include_shap=False, model_id=payload["id"])

    assert len(inference._loaded) <= inference.MAX_CACHED_MODELS
    assert inference._active_key in inference._loaded
    assert inference.active_model().identity.name == "xgb-smote-top50features-v1"


@pytest.fixture
def fallback_then_registry(monkeypatch):
    def boom():
        raise requests.exceptions.ConnectionError("refused")

    calls = []

    def get_model(model_id):
        calls.append(model_id)
        return TOP50_PAYLOAD

    monkeypatch.setattr(model_registry.spring_client, "get_active_model", boom)
    monkeypatch.setattr(model_registry.spring_client, "get_model", get_model)
    inference.load_artifacts()
    return calls


def test_fallback_model_adopts_its_registry_identity(fallback_then_registry, full_vector):
    result = inference.predict(full_vector, include_shap=False, model_id=TOP50_PAYLOAD["id"])
    assert result["model_id"] == TOP50_PAYLOAD["id"]
    assert result["model_name"] == "xgb-smote-top50features-v1"
    assert result["registry_source"] == "registry"
    assert result["feature_version"] == "cicids2017-top50-v1"
    assert inference.active_model().identity.model_id == TOP50_PAYLOAD["id"]


def test_adopted_identity_stops_further_registry_lookups(fallback_then_registry, full_vector):
    for _ in range(3):
        inference.predict(full_vector, include_shap=False, model_id=TOP50_PAYLOAD["id"])
    assert fallback_then_registry == [TOP50_PAYLOAD["id"]]
    assert len(inference._loaded) == 1


def test_adoption_refuses_a_conflicting_feature_version(fallback_then_registry, full_vector,
                                                       monkeypatch):
    payload = dict(TOP50_PAYLOAD, featureVersion="cicids2017-78-v1")
    monkeypatch.setattr(model_registry.spring_client, "get_model", lambda model_id: payload)
    with pytest.raises(FeatureVersionMismatch):
        inference.predict(full_vector, include_shap=False, model_id=payload["id"])
    assert inference.active_model().identity.model_id is None


MLP_PAYLOAD = {
    "id": "cccccccc-0000-0000-0000-0000000000c0",
    "algorithm": "NeuralNetwork",
    "name": "mlp-smote-cicids2017-v1",
    "version": "1.0",
    "featureVersion": None,
    "artifactPath": "models/mlp_smote_cicids2017_v1.joblib",
}


@pytest.fixture
def mlp_artifact():
    require_artifacts("mlp_smote_cicids2017_v1.joblib")


def test_activating_a_model_makes_it_the_default_for_predictions(full78_artifact, registry_backed, full_vector):
    inference.activate(FULL78_PAYLOAD["id"])
    assert inference.active_model().identity.name == "xgb-smote-cicids2017-v1"
    result = inference.predict(full_vector, include_shap=False)
    assert result["model_id"] == FULL78_PAYLOAD["id"]


def test_activating_an_unsupported_model_keeps_the_active_one(registry_backed, mlp_artifact,
                                                              monkeypatch):
    monkeypatch.setattr(model_registry.spring_client, "get_model", lambda model_id: MLP_PAYLOAD)
    with pytest.raises(inference.UnsupportedModelError, match="XGBoost"):
        inference.activate(MLP_PAYLOAD["id"])
    assert inference.active_model().identity.name == "xgb-smote-top50features-v1"
    assert "mlp_smote_cicids2017_v1.joblib" not in inference._loaded


def test_startup_falls_back_when_the_registry_model_is_unsupported(mlp_artifact, monkeypatch):
    monkeypatch.setattr(model_registry.spring_client, "get_active_model", lambda: MLP_PAYLOAD)
    loaded = inference.load_artifacts()
    assert loaded.identity.source == "fallback"
    assert loaded.model is not None
