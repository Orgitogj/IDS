import json
import os
from pathlib import Path

import pytest

ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ML_SERVICE_ROOT / "models"
DATASET_PATH = ML_SERVICE_ROOT / "datasets" / "cicids2017_cleaned.parquet"
REFERENCE_PATH = ML_SERVICE_ROOT / "reports" / "training_feature_reference.json"
EVALUATION_REPORT_PATH = ML_SERVICE_ROOT / "reports" / "evaluation_random_vs_temporal.json"

ACTIVE_ARTIFACT = "xgb_smote_top50features_v1.joblib"


@pytest.fixture(scope="session")
def reference():
    if not REFERENCE_PATH.exists():
        pytest.skip("training_feature_reference.json mungon; xhiro training.build_feature_reference")
    with open(REFERENCE_PATH, encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="session")
def all_features(reference):
    return list(reference["feature_sets"]["cicids2017-78-v1"])


@pytest.fixture(scope="session")
def top50_features(reference):
    return list(reference["feature_sets"]["cicids2017-top50-v1"])


@pytest.fixture
def full_vector(reference, all_features):
    return {name: reference["features"][name]["p50"] or 0.0 for name in all_features}


@pytest.fixture(scope="session")
def models_available():
    return (MODELS_DIR / ACTIVE_ARTIFACT).exists() and (
        MODELS_DIR / "label_encoder_cicids2017.joblib").exists()


@pytest.fixture(scope="session")
def dataset_available():
    return DATASET_PATH.exists()


@pytest.fixture(scope="session")
def evaluation_report():
    if not EVALUATION_REPORT_PATH.exists():
        pytest.skip("evaluation_random_vs_temporal.json mungon; xhiro training.evaluate")
    with open(EVALUATION_REPORT_PATH, encoding="utf-8") as handle:
        return json.load(handle)


LLM_INTEGRATION_ENV = "IDS_LLM_INTEGRATION"


def _llm_opted_in():
    return os.environ.get(LLM_INTEGRATION_ENV, "").strip().lower() in ("1", "true", "yes")


def _llm_configured():
    if not _llm_opted_in():
        return False
    try:
        from app.core.config import settings
    except Exception:
        return False
    return bool(settings.gemini_api_key or settings.anthropic_api_key)


def pytest_collection_modifyitems(config, items):
    models_ok = (MODELS_DIR / ACTIVE_ARTIFACT).exists()
    dataset_ok = DATASET_PATH.exists()
    report_ok = EVALUATION_REPORT_PATH.exists()
    llm_ok = _llm_configured()

    for item in items:
        if "artifacts" in item.keywords and not models_ok:
            item.add_marker(pytest.mark.skip(reason="artefaktet e modelit mungojne ne models/"))
        if "dataset" in item.keywords and not dataset_ok:
            item.add_marker(pytest.mark.skip(reason="cicids2017_cleaned.parquet mungon"))
        if "report" in item.keywords and not report_ok:
            item.add_marker(pytest.mark.skip(
                reason="reports/evaluation_random_vs_temporal.json mungon"))
        if "llm" in item.keywords and not llm_ok:
            item.add_marker(pytest.mark.skip(reason=(f"testet LLM jane opt-in: kalo -m llm DHE cakto {LLM_INTEGRATION_ENV}=1")))
