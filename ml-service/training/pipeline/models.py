from sklearn.ensemble import RandomForestClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
import xgboost as xgb

TYPE_XGBOOST = "xgboost"
TYPE_RANDOM_FOREST = "random_forest"
TYPE_MLP = "mlp"

ALGORITHM_NAMES = {
    TYPE_XGBOOST: "XGBoost",
    TYPE_RANDOM_FOREST: "RandomForest",
    TYPE_MLP: "NeuralNetwork",
}

DEFAULT_PARAMS = {
    TYPE_XGBOOST: {
        "n_estimators": 100,
        "n_jobs": -1,
        "tree_method": "hist",
        "eval_metric": "mlogloss",
    },
    TYPE_RANDOM_FOREST: {
        "n_estimators": 100,
        "n_jobs": -1,
        "class_weight": None,
    },
    TYPE_MLP: {
        "hidden_layer_sizes": (64, 32),
        "max_iter": 50,
        "early_stopping": True,
        "n_iter_no_change": 5,
    },
}

REQUIRES_SCALER = (TYPE_MLP,)


class ModelError(RuntimeError):
    pass


def resolve_params(model_type, overrides):
    if model_type not in DEFAULT_PARAMS:
        raise ModelError(f"Tip modeli i panjohur: {model_type}")

    params = dict(DEFAULT_PARAMS[model_type])
    params.update(overrides or {})

    if model_type == TYPE_MLP and "hidden_layer_sizes" in params:
        params["hidden_layer_sizes"] = tuple(params["hidden_layer_sizes"])

    return params


def build_model(model_type, params, seed):
    resolved = dict(params)
    resolved["random_state"] = seed

    if model_type == TYPE_XGBOOST:
        return xgb.XGBClassifier(**resolved)
    if model_type == TYPE_RANDOM_FOREST:
        return RandomForestClassifier(**resolved)
    if model_type == TYPE_MLP:
        return MLPClassifier(**resolved)

    raise ModelError(f"Tip modeli i panjohur: {model_type}")


def build_scaler(model_type):
    if model_type in REQUIRES_SCALER:
        return StandardScaler()
    return None


def algorithm_name(model_type):
    return ALGORITHM_NAMES.get(model_type, model_type)


def serialisable_params(params, seed):
    payload = {}
    for key, value in params.items():
        payload[key] = list(value) if isinstance(value, tuple) else value
    payload["random_state"] = seed
    return payload
