import requests
from fastapi import APIRouter, HTTPException

from app.ml.feature_validation import FeatureValidationError
from app.ml.inference import (
    active_model,
    drift_monitor,
    predict,
    publish_drift_report,
    reload_active,
)
from app.schemas.prediction import (
    ExplainRequest,
    ExplainResponse,
    PredictionRequest,
    PredictionResponse,
)
from app.services.llm_explainer import generate_all_explanations, generate_explanation
from app.services.spring_client import create_explanation

router = APIRouter(prefix="/api", tags=["prediction"])


def _run_prediction(feature_vector: dict, include_shap: bool, model_id=None) -> dict:
    try:
        return predict(feature_vector, include_shap=include_shap, model_id=model_id)
    except FeatureValidationError as error:
        raise HTTPException(status_code=422, detail=error.result.to_dict())
    except requests.exceptions.HTTPError as error:
        raise HTTPException(status_code=404,
                            detail=f"Modeli '{model_id}' s'u gjet ne regjistrin e modeleve.")
    except requests.exceptions.RequestException as error:
        raise HTTPException(status_code=503,
                            detail=f"Regjistri i modeleve s'u arrit: {error}")
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error))


@router.get("/models/active")
def get_active_model():
    try:
        return active_model().identity.to_dict()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error))


@router.post("/models/reload")
def reload_model():
    try:
        return reload_active().identity.to_dict()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error))


@router.get("/drift/report")
def get_drift_report():
    monitor = drift_monitor()
    if monitor is None:
        raise HTTPException(status_code=503,
                            detail="Monitorimi i drift-it eshte i cakivizuar.")
    return monitor.report()


@router.post("/drift/publish")
def publish_drift():
    monitor = drift_monitor()
    if monitor is None:
        raise HTTPException(status_code=503,
                            detail="Monitorimi i drift-it eshte i cakivizuar.")
    report = publish_drift_report()
    return {"status": report["status"], "observed_flows": report["observed_flows"],
            "drifted_feature_count": report["drifted_feature_count"]}


@router.post("/predict", response_model=PredictionResponse)
def predict_flow(request: PredictionRequest):
    return _run_prediction(request.feature_vector, request.include_shap, request.model_id)


@router.post("/explain", response_model=ExplainResponse)
def explain_alarm(request: ExplainRequest):
    prediction = _run_prediction(request.feature_vector, include_shap=True,
                                 model_id=request.model_id)

    if request.compare:
        llm_results = generate_all_explanations(
            predicted_label=prediction["prediction"],
            confidence=prediction["confidence"],
            top_shap_features=prediction["top_shap_features"],
            detection_class=prediction["detection_class"],
        )
    else:
        llm_results = [generate_explanation(
            predicted_label=prediction["prediction"],
            confidence=prediction["confidence"],
            top_shap_features=prediction["top_shap_features"],
            detection_class=prediction["detection_class"],
        )]

    if not llm_results:
        raise HTTPException(status_code=502, detail="Asnje ofrues LLM s'u pergjigj.")

    stored = []
    for llm_result in llm_results:
        try:
            create_explanation(
                alarm_id=request.alarm_id,
                explanation_text=llm_result["explanation_text"],
                llm_model=llm_result["llm_model"],
                llm_prompt_version=llm_result["llm_prompt_version"],
                generation_latency_ms=llm_result["generation_latency_ms"],
            )
        except requests.exceptions.RequestException as error:
            print(f"Ruajtja e shpjegimit ({llm_result['llm_model']}) deshtoi: {error}")
            continue
        stored.append({
            "explanation_text": llm_result["explanation_text"],
            "llm_model": llm_result["llm_model"],
            "llm_prompt_version": llm_result["llm_prompt_version"],
            "generation_latency_ms": llm_result["generation_latency_ms"],
        })

    if not stored:
        raise HTTPException(status_code=502, detail="Shpjegimet s'u ruajten dot ne Spring Boot.")

    response = dict(prediction)
    response.pop("top_shap_features", None)
    response["explanations"] = stored
    return response