import requests
from fastapi import APIRouter, HTTPException

from app.ml.inference import predict
from app.schemas.prediction import (
    ExplainRequest,
    ExplainResponse,
    PredictionRequest,
    PredictionResponse,
)
from app.services.llm_explainer import generate_all_explanations, generate_explanation
from app.services.spring_client import create_explanation

router = APIRouter(prefix="/api", tags=["prediction"])


@router.post("/predict", response_model=PredictionResponse)
def predict_flow(request: PredictionRequest):
    try:
        result = predict(request.feature_vector, include_shap=request.include_shap)
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/explain", response_model=ExplainResponse)
def explain_alarm(request: ExplainRequest):
    try:
        prediction = predict(request.feature_vector, include_shap=True)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    if request.compare:
        llm_results = generate_all_explanations(
            predicted_label=prediction["predicted_label"],
            confidence=prediction["confidence"],
            top_shap_features=prediction["top_shap_features"],
        )
    else:
        llm_results = [generate_explanation(
            predicted_label=prediction["predicted_label"],
            confidence=prediction["confidence"],
            top_shap_features=prediction["top_shap_features"],
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

    return {
        "predicted_label": prediction["predicted_label"],
        "confidence": prediction["confidence"],
        "explanations": stored,
    }