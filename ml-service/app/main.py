from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.predict import router as predict_router
from app.core.config import settings
from app.ml.inference import load_artifacts

app = FastAPI(
    title="IDS ML Service",
    description="Microservice ML per IDS - zbulim sulmesh/anomalish ne trafik rrjeti",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(predict_router)


@app.on_event("startup")
def startup_event():
    load_artifacts()


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "ids-ml-service",
        "spring_boot_url": settings.spring_boot_base_url,
    }