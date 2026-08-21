import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap

from app.core.config import settings

_model = None
_label_encoder = None
_feature_columns = None
_explainer = None


def load_artifacts():
    global _model, _label_encoder, _feature_columns, _explainer

    models_dir = Path(settings.models_dir)

    _model = joblib.load(models_dir / "xgb_smote_cicids2017_v1.joblib")
    _label_encoder = joblib.load(models_dir / "label_encoder_cicids2017.joblib")

    with open(models_dir / "feature_columns.json") as f:
        _feature_columns = json.load(f)

    _explainer = shap.TreeExplainer(_model)

    print(f"Model, label encoder, dhe {len(_feature_columns)} feature columns u ngarkuan.")


def predict(feature_vector: dict, include_shap: bool = True) -> dict:
    if _model is None:
        raise RuntimeError("Modeli nuk eshte ngarkuar ende - thirr load_artifacts() ne startup.")

    row = {col: feature_vector.get(col, 0.0) for col in _feature_columns}
    X_row = pd.DataFrame([row], columns=_feature_columns)

    predicted_idx = _model.predict(X_row)[0]
    predicted_proba = _model.predict_proba(X_row)[0]
    predicted_label = _label_encoder.inverse_transform([predicted_idx])[0]
    confidence = float(predicted_proba[predicted_idx])

    result = {
        "predicted_label": predicted_label,
        "confidence": confidence,
        "top_shap_features": None,
    }

    if include_shap:
        shap_values = _explainer.shap_values(X_row)
        shap_for_predicted = shap_values[0, :, predicted_idx]

        contributions = sorted(
            zip(_feature_columns, X_row.values[0], shap_for_predicted),
            key=lambda x: abs(x[2]),
            reverse=True,
        )[:5]

        result["top_shap_features"] = [
            {"feature": f, "value": float(v), "shap_contribution": float(s)}
            for f, v, s in contributions
        ]

    return result