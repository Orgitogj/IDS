import copy
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent.parent

SUPERVISED_MODEL_TYPES = ("xgboost", "random_forest", "mlp")
SPLIT_STRATEGIES = ("random", "temporal_global", "temporal_per_class")
OVERSAMPLERS = ("smote", "none")

SCALED_MODEL_TYPES = ("mlp",)

DEFAULTS = {
    "dataset": {
        "path": "datasets/cicids2017_cleaned.parquet",
        "label_column": "Label",
        "timestamp_column": "Timestamp",
    },
    "features": {
        "reference": "reports/training_feature_reference.json",
        "feature_set": "cicids2017-78-v1",
        "columns": None,
    },
    "split": {
        "strategy": "random",
        "test_size": 0.2,
    },
    "balancing": {
        "enabled": True,
        "benign_label": "BENIGN",
        "benign_cap": 200000,
        "rare_class_min": 2000,
        "oversampler": "smote",
        "smote_k_neighbors": 5,
    },
    "model": {
        "type": "xgboost",
        "params": {},
    },
    "output": {
        "models_dir": "models",
        "reports_dir": "reports/training",
        "artifact_name": None,
    },
    "seed": 42,
    "version": "2.0",
    "description": "",
}


class ConfigError(ValueError):
    pass


def _merge(base, override):
    merged = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def resolve_path(value):
    path = Path(value)
    return path if path.is_absolute() else _ML_SERVICE_ROOT / path


@dataclass
class TrainingConfig:
    name: str
    version: str
    description: str
    seed: int
    dataset: dict
    features: dict
    split: dict
    balancing: dict
    model: dict
    output: dict
    source_path: Path = None
    raw: dict = field(default_factory=dict)

    @property
    def artifact_name(self):
        return self.output["artifact_name"] or self.name.replace("-", "_")

    @property
    def model_type(self):
        return self.model["type"]

    @property
    def needs_scaler(self):
        return self.model_type in SCALED_MODEL_TYPES

    @property
    def dataset_path(self):
        return resolve_path(self.dataset["path"])

    @property
    def reference_path(self):
        return resolve_path(self.features["reference"])

    @property
    def models_dir(self):
        return resolve_path(self.output["models_dir"])

    @property
    def reports_dir(self):
        return resolve_path(self.output["reports_dir"]) / self.name

    def to_dict(self):
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "seed": self.seed,
            "dataset": copy.deepcopy(self.dataset),
            "features": copy.deepcopy(self.features),
            "split": copy.deepcopy(self.split),
            "balancing": copy.deepcopy(self.balancing),
            "model": copy.deepcopy(self.model),
            "output": copy.deepcopy(self.output),
        }


def validate(payload):
    if not payload.get("name"):
        raise ConfigError("Konfigurimit i mungon 'name'.")

    model_type = payload["model"]["type"]
    if model_type == "isolation_forest":
        raise ConfigError(
            "IsolationForest ka pipeline-in e vet te kalibruar: "
            "xhiro 'python -m training.build_anomaly_detector'. "
            "Ky pipeline mbulon vetem modele te mbikeqyrura.")
    if model_type not in SUPERVISED_MODEL_TYPES:
        raise ConfigError(
            f"model.type '{model_type}' s'njihet; prit nje nga {SUPERVISED_MODEL_TYPES}.")

    strategy = payload["split"]["strategy"]
    if strategy not in SPLIT_STRATEGIES:
        raise ConfigError(
            f"split.strategy '{strategy}' s'njihet; prit nje nga {SPLIT_STRATEGIES}.")

    test_size = payload["split"]["test_size"]
    if not 0.0 < float(test_size) < 1.0:
        raise ConfigError(f"split.test_size duhet te jete midis 0 dhe 1, jo {test_size}.")

    oversampler = payload["balancing"]["oversampler"]
    if oversampler not in OVERSAMPLERS:
        raise ConfigError(
            f"balancing.oversampler '{oversampler}' s'njihet; prit nje nga {OVERSAMPLERS}.")

    benign_cap = payload["balancing"]["benign_cap"]
    if benign_cap is not None and int(benign_cap) <= 0:
        raise ConfigError("balancing.benign_cap duhet te jete pozitiv ose null.")

    rare_min = payload["balancing"]["rare_class_min"]
    if rare_min is not None and int(rare_min) <= 0:
        raise ConfigError("balancing.rare_class_min duhet te jete pozitiv ose null.")

    if payload["features"]["columns"] is None and not payload["features"]["feature_set"]:
        raise ConfigError("Cakto ose features.feature_set ose features.columns.")

    if int(payload["seed"]) < 0:
        raise ConfigError("seed duhet te jete jo-negativ.")

    return payload


def from_dict(payload, source_path=None):
    merged = validate(_merge(DEFAULTS, payload))
    return TrainingConfig(
        name=merged["name"],
        version=str(merged["version"]),
        description=merged["description"],
        seed=int(merged["seed"]),
        dataset=merged["dataset"],
        features=merged["features"],
        split=merged["split"],
        balancing=merged["balancing"],
        model=merged["model"],
        output=merged["output"],
        source_path=source_path,
        raw=merged,
    )


def load(path):
    config_path = resolve_path(path)
    if not config_path.exists():
        raise ConfigError(f"Konfigurimi s'u gjet: {config_path}")
    with open(config_path, encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    return from_dict(payload, source_path=config_path)
