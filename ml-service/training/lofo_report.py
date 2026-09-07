import json
import sys
from pathlib import Path

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

from training.pipeline import families

REPORTS = _ML_SERVICE_ROOT / "reports" / "lofo_evaluation"

MODEL_LABELS = {
    "xgb_baseline": "XGB baseline",
    "xgb_balanced": "XGB balanced",
    "rf_baseline": "RF baseline",
    "rf_balanced": "RF balanced",
}
MODEL_ORDER = ["xgb_baseline", "xgb_balanced", "rf_baseline", "rf_balanced"]


def load_folds():
    folds = {}
    for path in sorted(REPORTS.glob("lofo_*/metrics.json")):
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        folds[(payload["held_out_family"], payload["model_key"])] = payload
    return folds
