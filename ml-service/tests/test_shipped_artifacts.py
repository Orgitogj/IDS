import json

import joblib

from app.core.config import settings
from tests.conftest import ML_SERVICE_ROOT, MODELS_DIR

REPLAY_DIR = ML_SERVICE_ROOT / "app" / "replay"
LABEL_ENCODER = "label_encoder_cicids2017.joblib"


def test_the_fallback_model_ships_with_the_repository():
    assert (REPLAY_DIR / settings.fallback_model_file).is_file()
    assert (REPLAY_DIR / LABEL_ENCODER).is_file()
    assert (REPLAY_DIR / "feature_columns.json").is_file()
    assert (MODELS_DIR / "feature_columns.json").is_file()


def test_the_shipped_feature_columns_match_the_models_copy():
    shipped = json.loads((REPLAY_DIR / "feature_columns.json").read_text(encoding="utf-8"))
    models = json.loads((MODELS_DIR / "feature_columns.json").read_text(encoding="utf-8"))
    assert shipped == models


def test_the_shipped_fallback_model_matches_the_registered_feature_sets(reference):
    model = joblib.load(REPLAY_DIR / settings.fallback_model_file)
    encoder = joblib.load(REPLAY_DIR / LABEL_ENCODER)
    columns = json.loads((REPLAY_DIR / "feature_columns.json").read_text(encoding="utf-8"))

    assert hasattr(model, "get_booster")
    assert [str(name) for name in model.feature_names_in_] == \
        reference["feature_sets"]["cicids2017-top50-v1"]
    assert columns == reference["feature_sets"]["cicids2017-78-v1"]
    assert model.n_classes_ == len(encoder.classes_)
