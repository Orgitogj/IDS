import threading

import requests

from app.core.config import settings

_token_lock = threading.Lock()
_cached_token = None


def _login() -> str:
    url = f"{settings.spring_boot_base_url}/api/auth/login"
    response = requests.post(url, json={
        "username": settings.spring_service_username,
        "password": settings.spring_service_password,
    }, timeout=10)
    response.raise_for_status()
    return response.json()["token"]


def _get_token(force_refresh: bool = False) -> str:
    global _cached_token
    with _token_lock:
        if _cached_token is None or force_refresh:
            _cached_token = _login()
        return _cached_token


def _request(method: str, path: str, payload: dict = None, timeout: int = 10) -> dict:
    url = f"{settings.spring_boot_base_url}{path}"

    for attempt in range(2):
        headers = {"Authorization": f"Bearer {_get_token(force_refresh=attempt > 0)}"}
        response = requests.request(method, url, json=payload, headers=headers, timeout=timeout)

        if response.status_code in (401, 403) and attempt == 0:
            continue

        response.raise_for_status()
        return response.json()

    raise requests.exceptions.HTTPError(f"Autentikimi deshtoi per {path}")


def register_model(algorithm: str, name: str, trained_on_dataset: str,
                   artifact_path: str, trained_at_iso: str,
                   hyperparameters: str = None, feature_set: str = None) -> dict:
    return _request("POST", "/api/models", {
        "algorithm": algorithm,
        "name": name,
        "trainedOnDataset": trained_on_dataset,
        "artifactPath": artifact_path,
        "hyperparameters": hyperparameters,
        "featureSet": feature_set,
        "trainedAt": trained_at_iso,
    })


def record_experiment_result(ml_model_id: str, tested_on_dataset: str,
                             accuracy: float, precision: float, recall: float,
                             f1: float, avg_latency_ms: float = None,
                             sample_size: int = None,
                             feature_set_used: str = None,
                             notes: str = None) -> dict:
    return _request("POST", "/api/experiments", {
        "mlModelId": ml_model_id,
        "testedOnDataset": tested_on_dataset,
        "featureSetUsed": feature_set_used,
        "accuracy": accuracy,
        "precisionScore": precision,
        "recall": recall,
        "f1Score": f1,
        "avgLatencyMs": avg_latency_ms,
        "sampleSize": sample_size,
        "notes": notes,
    })


def ingest_flow(source_ip: str, destination_ip: str, source_port: int,
                destination_port: int, protocol: str, feature_vector: dict,
                predicted_label: str, prediction_confidence: float,
                flow_timestamp_iso: str, attack_type: str = None,
                dataset_source: str = "CICIDS2017_REPLAY",
                timeout: int = 10) -> dict:
    return _request("POST", "/api/alarms/ingest", {
        "sourceIp": source_ip,
        "destinationIp": destination_ip,
        "sourcePort": source_port,
        "destinationPort": destination_port,
        "protocol": protocol,
        "featureVector": feature_vector,
        "predictedLabel": predicted_label,
        "predictionConfidence": prediction_confidence,
        "attackType": attack_type,
        "flowTimestamp": flow_timestamp_iso,
        "datasetSource": dataset_source,
    }, timeout=timeout)


def create_explanation(alarm_id: str, explanation_text: str,
                       llm_model: str, llm_prompt_version: str,
                       generation_latency_ms: float = None) -> dict:
    return _request("POST", f"/api/alarms/{alarm_id}/explanations", {
        "explanationText": explanation_text,
        "llmModel": llm_model,
        "llmPromptVersion": llm_prompt_version,
        "generationLatencyMs": generation_latency_ms,
    }, timeout=15)
