from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class PredictionRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    feature_vector: dict[str, Any] = Field(...)
    include_shap: bool = Field(default=True)
    model_id: Optional[str] = Field(default=None)


class ShapContribution(BaseModel):
    feature: str
    value: float
    shap_contribution: float


class AnomalyContribution(BaseModel):
    feature: str
    value: float
    baseline_value: float
    anomaly_contribution: float


class FeatureValidationReport(BaseModel):
    valid: bool
    feature_version: str
    policy: str
    missing_features: list[str] = Field(default_factory=list)
    invalid_features: list[dict[str, Any]] = Field(default_factory=list)
    derived_features: list[dict[str, Any]] = Field(default_factory=list)
    zero_filled_features: list[str] = Field(default_factory=list)
    out_of_range_features: list[dict[str, Any]] = Field(default_factory=list)
    unexpected_feature_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class ModelIdentityFields(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_id: Optional[str] = None
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    feature_version: Optional[str] = None
    algorithm: Optional[str] = None
    artifact_file: Optional[str] = None
    registry_source: Optional[str] = None


class AnomalyReport(BaseModel):
    available: bool
    reason: Optional[str] = None
    raw_score: Optional[float] = None
    anomaly_score: Optional[float] = None
    is_anomalous: bool = False
    missing_features: list[str] = Field(default_factory=list)


class DetectionFields(ModelIdentityFields):
    prediction: str
    detection_class: str
    confidence: Optional[float] = None
    detection_method: str
    anomaly_score: Optional[float] = None
    supervised_label: str
    supervised_confidence: float
    anomaly: Optional[AnomalyReport] = None
    anomaly_artifact_file: Optional[str] = None
    anomaly_feature_version: Optional[str] = None
    anomaly_threshold_rate: Optional[float] = None
    anomaly_threshold: Optional[float] = None
    anomaly_attribution_method: Optional[str] = None
    top_anomaly_features: Optional[list[AnomalyContribution]] = None


class PredictionResponse(DetectionFields):
    predicted_label: str
    top_shap_features: Optional[list[ShapContribution]] = None
    validation: Optional[FeatureValidationReport] = None


class ExplainRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    alarm_id: str = Field(...)
    feature_vector: dict[str, Any] = Field(...)
    compare: bool = Field(default=False)
    model_id: Optional[str] = Field(default=None)


class GroundednessFinding(BaseModel):
    kind: str
    severity: str
    matched: str
    detail: str


class GroundednessReport(BaseModel):
    grounded: bool
    finding_count: int
    high_severity_count: int
    findings: list[GroundednessFinding] = Field(default_factory=list)
    method: str
    caveat: str


class GeneratedExplanation(BaseModel):
    explanation_text: str
    llm_model: str
    llm_prompt_version: str
    generation_latency_ms: float
    provider: Optional[str] = None
    groundedness: Optional[GroundednessReport] = None


class ExplainResponse(DetectionFields):
    predicted_label: str
    explanations: list[GeneratedExplanation]
    validation: Optional[FeatureValidationReport] = None