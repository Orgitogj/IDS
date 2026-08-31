from pathlib import Path

import requests

from app.core.config import settings
from app.services import spring_client


class ModelIdentity:
    def __init__(self, artifact_file, model_id=None, name=None, version=None,
                 feature_version=None, algorithm=None, source="fallback"):
        self.artifact_file = artifact_file
        self.model_id = model_id
        self.name = name or Path(artifact_file).stem
        self.version = version or "unknown"
        self.feature_version = feature_version
        self.algorithm = algorithm
        self.source = source

    def to_dict(self):
        return {
            "model_id": self.model_id,
            "model_name": self.name,
            "model_version": self.version,
            "feature_version": self.feature_version,
            "algorithm": self.algorithm,
            "artifact_file": self.artifact_file,
            "registry_source": self.source,
        }

    def __repr__(self):
        return (f"ModelIdentity(name={self.name}, version={self.version}, "
                f"feature_version={self.feature_version}, source={self.source})")


def _artifact_file(artifact_path):
    return Path(str(artifact_path)).name


def identity_from_registry(payload, source="registry"):
    return ModelIdentity(
        artifact_file=_artifact_file(payload["artifactPath"]),
        model_id=payload.get("id"),
        name=payload.get("name"),
        version=payload.get("version"),
        feature_version=payload.get("featureVersion"),
        algorithm=payload.get("algorithm"),
        source=source,
    )


def fallback_identity():
    return ModelIdentity(artifact_file=settings.fallback_model_file, source="fallback")


def fetch_active_identity():
    try:
        return identity_from_registry(spring_client.get_active_model())
    except requests.exceptions.RequestException as error:
        print(f"[model_registry] Regjistri s'u arrit ({error}); "
              f"po perdoret fallback '{settings.fallback_model_file}'.")
        return fallback_identity()
    except (KeyError, TypeError, ValueError) as error:
        print(f"[model_registry] Pergjigje e paperdorshme nga regjistri ({error!r}); "
              f"po perdoret fallback '{settings.fallback_model_file}'.")
        return fallback_identity()


def fetch_identity_by_id(model_id):
    payload = spring_client.get_model(str(model_id))
    return identity_from_registry(payload)
