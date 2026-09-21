import json
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import requests
from fastapi.testclient import TestClient

from app.core.config import settings
from app.ml import inference, model_registry

pytestmark = pytest.mark.artifacts

TEST_JWT_SECRET = "unit-test-secret-key-at-least-32-bytes-long"


def token_for(role="ADMIN", username="tester", secret=TEST_JWT_SECRET):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def auth_headers(role="ADMIN"):
    return {"Authorization": f"Bearer {token_for(role)}"}


JSON_HEADERS = {"Content-Type": "application/json", **auth_headers()}

TOP50_PAYLOAD = {
    "id": "133f003c-baab-4e11-8b12-21f5f37e2896",
    "algorithm": "XGBoost",
    "name": "xgb-smote-top50features-v1",
    "version": "1.0",
    "featureVersion": None,
    "artifactPath": "models/xgb_smote_top50features_v1.joblib",
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", TEST_JWT_SECRET)
    monkeypatch.setattr(inference, "_loaded", {})
    monkeypatch.setattr(inference, "_load_order", [])
    monkeypatch.setattr(inference, "_active_key", None)
    monkeypatch.setattr(inference, "_label_encoder", None)
    monkeypatch.setattr(inference, "_reference", None)
    monkeypatch.setattr(model_registry.spring_client, "get_active_model", lambda: TOP50_PAYLOAD)

    from app.main import app
    with TestClient(app) as test_client:
        yield test_client


def post_predict(client, vector, **extra):
    body = json.dumps({"feature_vector": vector, "include_shap": False, **extra})
    return client.post("/api/predict", content=body, headers=JSON_HEADERS)


def test_health_reports_the_service(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_active_model_endpoint_reports_identity(client):
    body = client.get("/api/models/active", headers=auth_headers()).json()
    assert body["model_name"] == "xgb-smote-top50features-v1"
    assert body["feature_version"] == "cicids2017-top50-v1"
    assert body["registry_source"] == "registry"


def test_valid_vector_returns_a_prediction_with_identity(client, full_vector):
    response = post_predict(client, full_vector)
    assert response.status_code == 200
    body = response.json()
    assert body["model_name"] == "xgb-smote-top50features-v1"
    assert body["model_version"] == "1.0"
    assert body["feature_version"] == "cicids2017-top50-v1"
    assert body["detection_method"] in {"SUPERVISED_ML", "ANOMALY_DETECTION"}
    assert body["detection_class"] in {"BENIGN", "KNOWN_ATTACK", "SUSPICIOUS"}
    assert body["prediction"] == body["predicted_label"] or body["detection_class"] == "SUSPICIOUS"
    assert body["validation"]["valid"] is True


def test_shap_is_returned_when_requested(client, full_vector):
    body = json.dumps({"feature_vector": full_vector, "include_shap": True})
    response = client.post("/api/predict", content=body, headers=JSON_HEADERS)
    assert response.status_code == 200
    assert len(response.json()["top_shap_features"]) == 5


def test_empty_vector_is_rejected_with_a_structured_body(client):
    response = post_predict(client, {})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["valid"] is False
    assert len(detail["missing_features"]) == 50
    assert detail["feature_version"] == "cicids2017-top50-v1"


@pytest.mark.parametrize("bad,reason", [
    (float("nan"), "nan"),
    (float("inf"), "inf"),
    ("abc", "non_numeric"),
    (None, "null"),
    ("", "empty"),
])
def test_unusable_values_are_rejected_with_a_reason(client, full_vector, bad, reason):
    full_vector["Init_Win_bytes_backward"] = bad
    response = post_predict(client, full_vector)
    assert response.status_code == 422
    assert response.json()["detail"]["invalid_features"] == [
        {"feature": "Init_Win_bytes_backward", "reason": reason}
    ]


def test_missing_non_derivable_feature_is_rejected(client, full_vector):
    del full_vector["Init_Win_bytes_backward"]
    response = post_predict(client, full_vector)
    assert response.status_code == 422
    assert response.json()["detail"]["missing_features"] == ["Init_Win_bytes_backward"]


def test_missing_derivable_feature_is_reconstructed(client, full_vector):
    del full_vector["Down/Up Ratio"]
    response = post_predict(client, full_vector)
    assert response.status_code == 200
    derived = response.json()["validation"]["derived_features"]
    assert [entry["feature"] for entry in derived] == ["Down/Up Ratio"]


def test_unknown_model_id_is_a_not_found(client, full_vector, monkeypatch):
    def boom(model_id):
        raise requests.exceptions.HTTPError("404")

    monkeypatch.setattr(model_registry.spring_client, "get_model", boom)
    response = post_predict(client, full_vector,
                            model_id="00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_unreachable_registry_during_lookup_is_a_service_error(client, full_vector, monkeypatch):
    def boom(model_id):
        raise requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr(model_registry.spring_client, "get_model", boom)
    response = post_predict(client, full_vector,
                            model_id="00000000-0000-0000-0000-000000000000")
    assert response.status_code == 503


def test_reload_endpoint_returns_the_new_identity(client):
    response = client.post("/api/models/reload", headers=auth_headers("ADMIN"))
    assert response.status_code == 200
    assert response.json()["model_name"] == "xgb-smote-top50features-v1"


def test_explain_rejects_an_invalid_vector_before_calling_an_llm(client, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("the LLM must not be called for an invalid vector")

    monkeypatch.setattr("app.api.predict.generate_explanation", fail)
    monkeypatch.setattr("app.api.predict.generate_all_explanations", fail)

    body = json.dumps({"alarm_id": "00000000-0000-0000-0000-000000000000",
                       "feature_vector": {}})
    response = client.post("/api/explain", content=body, headers=JSON_HEADERS)
    assert response.status_code == 422


def test_explain_reports_an_unavailable_llm_provider_as_a_bad_gateway(client, monkeypatch,
                                                                    full_vector):
    def overloaded(*args, **kwargs):
        raise RuntimeError("503 UNAVAILABLE. This model is currently experiencing high demand.")

    monkeypatch.setattr("app.api.predict.generate_explanation", overloaded)

    body = json.dumps({"alarm_id": "00000000-0000-0000-0000-000000000000",
                       "feature_vector": full_vector})
    response = client.post("/api/explain", content=body, headers=JSON_HEADERS)
    assert response.status_code == 502
    assert "LLM" in response.json()["detail"]


def test_malformed_request_body_is_a_client_error(client):
    response = client.post("/api/predict", content="{not json", headers=JSON_HEADERS)
    assert response.status_code == 422


def test_missing_feature_vector_field_is_a_client_error(client):
    response = client.post("/api/predict", content=json.dumps({"include_shap": True}),
                           headers=JSON_HEADERS)
    assert response.status_code == 422


def test_predict_without_a_token_is_rejected(client, full_vector):
    body = json.dumps({"feature_vector": full_vector, "include_shap": False})
    response = client.post("/api/predict", content=body,
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 401


def test_predict_with_a_foreign_signature_is_rejected(client, full_vector):
    forged = token_for(role="ADMIN", secret="a-different-secret-of-sufficient-length")
    body = json.dumps({"feature_vector": full_vector, "include_shap": False})
    response = client.post("/api/predict", content=body,
                           headers={"Content-Type": "application/json",
                                    "Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_predict_accepts_every_operational_role(client, full_vector):
    for role in ("ANALYST", "ADMIN", "SERVICE"):
        body = json.dumps({"feature_vector": full_vector, "include_shap": False})
        response = client.post("/api/predict", content=body,
                               headers={"Content-Type": "application/json",
                                        **auth_headers(role)})
        assert response.status_code == 200, role


def test_model_reload_is_admin_only(client):
    for role in ("ANALYST", "SERVICE"):
        response = client.post("/api/models/reload", headers=auth_headers(role))
        assert response.status_code == 403, role


def test_drift_publish_is_closed_to_analysts(client):
    response = client.post("/api/drift/publish", headers=auth_headers("ANALYST"))
    assert response.status_code == 403


def test_explain_without_a_token_never_reaches_the_llm(client, monkeypatch, full_vector):
    def fail(*args, **kwargs):
        raise AssertionError("the LLM must not be called for an unauthenticated request")

    monkeypatch.setattr("app.api.predict.generate_explanation", fail)
    monkeypatch.setattr("app.api.predict.generate_all_explanations", fail)

    body = json.dumps({"alarm_id": "00000000-0000-0000-0000-000000000000",
                       "feature_vector": full_vector})
    response = client.post("/api/explain", content=body,
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 401


def test_service_without_a_configured_secret_refuses(client, monkeypatch, full_vector):
    monkeypatch.setattr(settings, "jwt_secret", "")
    body = json.dumps({"feature_vector": full_vector, "include_shap": False})
    response = client.post("/api/predict", content=body, headers=JSON_HEADERS)
    assert response.status_code == 503


def test_health_stays_open_without_a_token(client):
    response = client.get("/health")
    assert response.status_code == 200


@pytest.mark.parametrize("algorithm", ["HS384", "HS512"])
def test_hmac_variants_spring_never_signs_with_are_rejected(client, full_vector, algorithm):
    payload = {
        "sub": "tester",
        "role": "ANALYST",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    token = jwt.encode(payload, TEST_JWT_SECRET, algorithm=algorithm)
    body = json.dumps({"feature_vector": full_vector, "include_shap": False})
    response = client.post("/api/predict", content=body,
                           headers={"Content-Type": "application/json",
                                    "Authorization": f"Bearer {token}"})
    assert response.status_code == 401, algorithm


def test_a_token_without_an_issued_at_claim_is_rejected(client, full_vector):
    payload = {
        "sub": "tester",
        "role": "ANALYST",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    token = jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")
    body = json.dumps({"feature_vector": full_vector, "include_shap": False})
    response = client.post("/api/predict", content=body,
                           headers={"Content-Type": "application/json",
                                    "Authorization": f"Bearer {token}"})
    assert response.status_code == 401


FULL78_PAYLOAD = {
    "id": "aaaaaaaa-0000-0000-0000-000000000078",
    "algorithm": "XGBoost",
    "name": "xgb-smote-cicids2017-v1",
    "version": "2.0",
    "featureVersion": None,
    "artifactPath": "models/xgb_smote_cicids2017_v1.joblib",
}

MLP_PAYLOAD = {
    "id": "cccccccc-0000-0000-0000-0000000000c0",
    "algorithm": "NeuralNetwork",
    "name": "mlp-smote-cicids2017-v1",
    "version": "1.0",
    "featureVersion": None,
    "artifactPath": "models/mlp_smote_cicids2017_v1.joblib",
}


def test_activate_endpoint_switches_the_active_model(client, monkeypatch):
    monkeypatch.setattr(model_registry.spring_client, "get_model",
                        lambda model_id: FULL78_PAYLOAD)
    response = client.post(f"/api/models/{FULL78_PAYLOAD['id']}/activate",
                           headers=auth_headers("SERVICE"))
    assert response.status_code == 200
    assert response.json()["model_name"] == "xgb-smote-cicids2017-v1"

    active = client.get("/api/models/active", headers=auth_headers("ANALYST"))
    assert active.json()["model_id"] == FULL78_PAYLOAD["id"]


def test_activate_endpoint_refuses_an_unsupported_model(client, monkeypatch):
    if not (inference._models_dir() / "mlp_smote_cicids2017_v1.joblib").exists():
        pytest.skip("mlp_smote_cicids2017_v1.joblib mungon ne models/")
    monkeypatch.setattr(model_registry.spring_client, "get_model", lambda model_id: MLP_PAYLOAD)

    response = client.post(f"/api/models/{MLP_PAYLOAD['id']}/activate",
                           headers=auth_headers("ADMIN"))
    assert response.status_code == 422
    assert "XGBoost" in response.json()["detail"]

    active = client.get("/api/models/active", headers=auth_headers("ANALYST"))
    assert active.json()["model_name"] == "xgb-smote-top50features-v1"


def test_activate_endpoint_reports_an_unknown_model_as_not_found(client, monkeypatch):
    def boom(model_id):
        raise requests.exceptions.HTTPError("404")

    monkeypatch.setattr(model_registry.spring_client, "get_model", boom)
    response = client.post("/api/models/00000000-0000-0000-0000-000000000000/activate",
                           headers=auth_headers("ADMIN"))
    assert response.status_code == 404


def test_activate_endpoint_is_closed_to_analysts(client):
    response = client.post(f"/api/models/{FULL78_PAYLOAD['id']}/activate",
                           headers=auth_headers("ANALYST"))
    assert response.status_code == 403
