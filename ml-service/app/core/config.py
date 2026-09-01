from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    spring_boot_base_url: str = "http://localhost:8080"
    spring_service_username: str = "ml-service"
    spring_service_password: str = ""
    jwt_secret: str = Field(default="", validation_alias="IDS_JWT_SECRET")
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    llm_provider: str = "gemini"
    mlflow_tracking_uri: str = "http://localhost:5000"
    fallback_model_file: str = "xgb_smote_top50features_v1.joblib"
    anomaly_detection_enabled: bool = True
    anomaly_threshold_rate: str = "0.010"
    drift_monitoring_enabled: bool = True
    drift_window_size: int = 1000
    drift_publish_every: int = 500
    models_dir: str = "./models"
    datasets_dir: str = "./datasets"


settings = Settings()