from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    spring_boot_base_url: str = "http://localhost:8080"
    spring_service_username: str = "ml-service"
    spring_service_password: str = "ml-service-secret"
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    llm_provider: str = "gemini"
    mlflow_tracking_uri: str = "http://localhost:5000"
    models_dir: str = "./models"
    datasets_dir: str = "./datasets"


settings = Settings()