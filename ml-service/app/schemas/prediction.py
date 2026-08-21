from typing import Optional

from pydantic import BaseModel, Field


class PredictionRequest(BaseModel):
    feature_vector: dict[str, float] = Field(...)
    include_shap: bool = Field(default=True)


class ShapContribution(BaseModel):
    feature: str
    value: float
    shap_contribution: float


class PredictionResponse(BaseModel):
    predicted_label: str
    confidence: float
    top_shap_features: Optional[list[ShapContribution]] = None


class ExplainRequest(BaseModel):
    alarm_id: str = Field(...)
    feature_vector: dict[str, float] = Field(...)


class ExplainResponse(BaseModel):
    predicted_label: str
    confidence: float
    explanation_text: str
    llm_model: str
    llm_prompt_version: str