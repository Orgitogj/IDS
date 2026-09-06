import threading

import requests

from app.core.config import settings
from app.services.token_provider import TokenProvider

_provider_lock = threading.Lock()
_provider = None


def _get_provider() -> TokenProvider:
    global _provider
    with _provider_lock:
        if _provider is None:
            _provider = TokenProvider(
                settings.spring_boot_base_url,
                settings.spring_service_username,
                settings.spring_service_password,
            )
        return _provider


def _request(method: str, path: str, payload: dict = None, timeout: int = 10) -> dict:
    url = f"{settings.spring_boot_base_url}{path}"
    provider = _get_provider()

    for attempt in range(2):
        headers = provider.authorization_header(force_refresh=attempt > 0)
        response = requests.request(method, url, json=payload, headers=headers, timeout=timeout)

        if response.status_code in (401, 403) and attempt == 0:
            continue

        response.raise_for_status()
        return response.json()

    raise requests.exceptions.HTTPError(f"Autentikimi deshtoi per {path}")


def get_active_model() -> dict:
    return _request("GET", "/api/models/active")


def get_model(model_id: str) -> dict:
    return _request("GET", f"/api/models/{model_id}")


def register_model(algorithm: str, name: str, trained_on_dataset: str,
                   artifact_path: str, trained_at_iso: str,
                   hyperparameters: str = None, feature_set: str = None,
                   version: str = None, feature_version: str = None) -> dict:
    return _request("POST", "/api/models", {
        "algorithm": algorithm,
        "name": name,
        "version": version,
        "featureVersion": feature_version,
        "trainedOnDataset": trained_on_dataset,
        "artifactPath": artifact_path,
        "hyperparameters": hyperparameters,
        "featureSet": feature_set,
        "trainedAt": trained_at_iso,
    })


EXPERIMENT_PAYLOAD_KEYS = ("mlModelId", "testedOnDataset", "featureSetUsed", "accuracy",
                          "precisionScore", "recall", "f1Score", "avgLatencyMs",
                          "sampleSize", "notes")

MANUAL_METRICS_REFUSED = (
    "Metrikat e eksperimenteve nuk pranohen si argumente. Nje rezultat regjistrohet "
    "vetem nga nje raport evaluation i validuar:\n"
    "  from training.pipeline.reporting import EvaluationReport\n"
    "  from training.pipeline.registration import experiment_payload\n"
    "  payload = experiment_payload(EvaluationReport.from_path(path), model_id)\n"
    "  spring_client.create_experiment_result(payload)\n"
    "Ose xhiro: python -m training.reregister_experiments"
)


def create_experiment_result(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise TypeError(MANUAL_METRICS_REFUSED)

    unexpected = [key for key in payload if key not in EXPERIMENT_PAYLOAD_KEYS]
    if unexpected:
        raise ValueError(f"Fusha te panjohura ne payload: {', '.join(sorted(unexpected))}")

    if not str(payload.get("notes", "")).startswith("provenance="):
        raise ValueError(MANUAL_METRICS_REFUSED)

    return _request("POST", "/api/experiments", payload)


def record_experiment_result(*args, **kwargs):
    raise NotImplementedError(MANUAL_METRICS_REFUSED)


def ingest_flow(source_ip: str, destination_ip: str, source_port: int,
                destination_port: int, protocol: str, feature_vector: dict,
                predicted_label: str, prediction_confidence: float,
                flow_timestamp_iso: str, attack_type: str = None,
                dataset_source: str = "CICIDS2017_REPLAY",
                model_id: str = None, model_name: str = None,
                model_version: str = None, feature_version: str = None,
                detection_method: str = None, anomaly_score: float = None,
                ground_truth_label: str = None, ground_truth_attack_type: str = None,
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
        "modelId": model_id,
        "modelName": model_name,
        "modelVersion": model_version,
        "featureVersion": feature_version,
        "detectionMethod": detection_method,
        "anomalyScore": anomaly_score,
        "groundTruthLabel": ground_truth_label,
        "groundTruthAttackType": ground_truth_attack_type,
        "flowTimestamp": flow_timestamp_iso,
        "datasetSource": dataset_source,
    }, timeout=timeout)


def create_drift_report(report: dict, timeout: int = 15) -> dict:
    return _request("POST", "/api/drift/reports", {
        "status": report["status"],
        "featureVersion": report.get("feature_version"),
        "observedFlows": report["observed_flows"],
        "acceptedFlows": report["accepted_flows"],
        "rejectedFlows": report["rejected_flows"],
        "sampleSize": report["sample_size"],
        "invalidRate": report["invalid_rate"],
        "driftedFeatureCount": report["drifted_feature_count"],
        "driftedFraction": report["drifted_fraction"],
        "calibrationWindow": report.get("calibration_window"),
        "reasons": report.get("reasons", []),
        "driftedFeatures": report.get("drifted_features", []),
        "features": report.get("features", {}),
        "generatedAt": report["generated_at"],
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
