import requests

from app.core.config import settings


def register_model(algorithm: str, name: str, trained_on_dataset: str,
                   artifact_path: str, trained_at_iso: str,
                   hyperparameters: str = None, feature_set: str = None) -> dict:
    url = f"{settings.spring_boot_base_url}/api/models"
    payload = {
        "algorithm": algorithm,
        "name": name,
        "trainedOnDataset": trained_on_dataset,
        "artifactPath": artifact_path,
        "hyperparameters": hyperparameters,
        "featureSet": feature_set,
        "trainedAt": trained_at_iso,
    }

    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()
    return response.json()


def record_experiment_result(ml_model_id: str, tested_on_dataset: str,
                             accuracy: float, precision: float, recall: float,
                             f1: float, avg_latency_ms: float = None,
                             sample_size: int = None,
                             feature_set_used: str = None,
                             notes: str = None) -> dict:
    url = f"{settings.spring_boot_base_url}/api/experiments"
    payload = {
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
    }

    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()
    return response.json()


def create_explanation(alarm_id: str, explanation_text: str,
                       llm_model: str, llm_prompt_version: str) -> dict:
    url = f"{settings.spring_boot_base_url}/api/alarms/{alarm_id}/explanation"
    payload = {
        "explanationText": explanation_text,
        "llmModel": llm_model,
        "llmPromptVersion": llm_prompt_version,
    }

    response = requests.post(url, json=payload, timeout=15)
    response.raise_for_status()
    return response.json()