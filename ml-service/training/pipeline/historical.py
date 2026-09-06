SOURCE_NOTEBOOK = "notebooks/eda_step1_read.py.ipynb"

ORIGIN_HARDCODED = "hardcoded"
ORIGIN_COMPUTED = "computed"
ORIGIN_UNKNOWN = "unknown"

STORED_RESULTS = {
    "rf-baseline-cicids2017-v2": {
        "notebook_cell": 17,
        "accuracy": {"value": 0.9986, "origin": ORIGIN_HARDCODED},
        "precisionScore": {"value": 0.9381494099629583, "origin": ORIGIN_COMPUTED},
        "recall": {"value": 0.8466290313535187, "origin": ORIGIN_COMPUTED},
        "f1Score": {"value": 0.8724, "origin": ORIGIN_HARDCODED},
        "avgLatencyMs": {"value": 0.0054, "origin": ORIGIN_HARDCODED},
        "sampleSize": {"value": 565576, "origin": ORIGIN_COMPUTED},
        "featureSetUsed": "all_78_features_excluding_identifiers",
        "notes": "Baseline Random Forest v2, pa SMOTE, class_weight=None, 100 estimators",
        "evidence": "Full API response echoed in the notebook output of cell 17.",
    },
}

UNRECOVERABLE_OFFLINE = (
    "Only rf-baseline-cicids2017-v2 echoed its full API response into a notebook output "
    "cell. Every other registration printed just the new row id, so the values actually "
    "stored in experiment_results can only be read from a running database. Pass "
    "--fetch-stored with the backend up to compare those."
)


def stored_for(registry_name):
    return STORED_RESULTS.get(registry_name)


def hardcoded_fields(registry_name):
    stored = stored_for(registry_name)
    if not stored:
        return []
    return sorted(
        key for key, value in stored.items()
        if isinstance(value, dict) and value.get("origin") == ORIGIN_HARDCODED
    )


def stored_value(registry_name, field):
    stored = stored_for(registry_name)
    if not stored:
        return None
    entry = stored.get(field)
    if isinstance(entry, dict):
        return entry.get("value")
    return entry
