import json

import pytest

from app.ml.feature_validation import STRICT_POLICY, FeatureValidator
from app.replay import cicids_replay
from tests.conftest import DATASET_PATH


@pytest.fixture(scope="module")
def dataset_rows():
    if not DATASET_PATH.exists():
        pytest.skip("cicids2017_cleaned.parquet mungon")
    import pyarrow.parquet as pq

    parquet_file = pq.ParquetFile(DATASET_PATH)
    batch = next(parquet_file.iter_batches(batch_size=200))
    return batch.to_pandas()


@pytest.mark.dataset
def test_real_dataset_rows_pass_validation_unchanged(dataset_rows, reference, all_features,
                                                     top50_features):
    validator = FeatureValidator(top50_features, reference=reference, policy=STRICT_POLICY)

    for position in range(min(50, len(dataset_rows))):
        row = dataset_rows.iloc[position]
        vector = {column: float(row[column]) for column in all_features}
        result = validator.validate(vector)

        assert result.valid, f"rreshti {position}: {result.summary()}"
        assert result.missing_features == []
        assert result.invalid_features == []
        assert result.derived_features == []
        assert result.zero_filled_features == []
        assert len(result.vector) == len(top50_features)


@pytest.mark.dataset
def test_replay_supplies_every_feature_the_wide_model_needs(dataset_rows, reference, all_features):
    validator = FeatureValidator(all_features, reference=reference, policy=STRICT_POLICY)
    row = dataset_rows.iloc[0]
    vector = {column: float(row[column]) for column in all_features}

    result = validator.validate(vector)
    assert result.valid
    assert result.to_dict()["unexpected_feature_count"] == 0


@pytest.mark.dataset
def test_replay_rows_carry_no_infinities(dataset_rows, all_features):
    import numpy as np

    values = dataset_rows[all_features].to_numpy(dtype="float64")
    assert not np.isinf(values).any()
    assert not np.isnan(values).any()


@pytest.mark.artifacts
def test_replay_payload_covers_every_feature_both_detectors_need(monkeypatch):
    from app.ml import inference, model_registry
    from app.replay.cicids_replay import _payload_feature_columns

    payload = {
        "id": "133f003c-baab-4e11-8b12-21f5f37e2896",
        "algorithm": "XGBoost",
        "name": "xgb-smote-top50features-v1",
        "version": "1.0",
        "featureVersion": None,
        "artifactPath": "models/xgb_smote_top50features_v1.joblib",
    }
    monkeypatch.setattr(inference, "_loaded", {})
    monkeypatch.setattr(inference, "_load_order", [])
    monkeypatch.setattr(inference, "_active_key", None)
    monkeypatch.setattr(inference, "_label_encoder", None)
    monkeypatch.setattr(inference, "_reference", None)
    monkeypatch.setattr(model_registry.spring_client, "get_active_model", lambda: payload)

    loaded = inference.load_artifacts()
    columns = _payload_feature_columns(loaded)

    for name in loaded.feature_columns:
        assert name in columns, f"supervised model needs {name}"

    detector = inference.anomaly_detector()
    if detector is not None:
        for name in detector.feature_columns:
            assert name in columns, f"anomaly detector needs {name}"

    assert len(columns) == len(set(columns))


def test_label_cleaning_repairs_the_mis_decoded_dash():
    assert cicids_replay._clean_label("Web Attack \x96 XSS") == "Web Attack - XSS"
    assert cicids_replay._clean_label("  BENIGN  ") == "BENIGN"


def test_protocol_numbers_map_to_names():
    assert cicids_replay._protocol_name(6) == "TCP"
    assert cicids_replay._protocol_name(17) == "UDP"
    assert cicids_replay._protocol_name("6") == "TCP"
    assert cicids_replay._protocol_name(99) == "99"
    assert cicids_replay._protocol_name("nonsense") == "UNKNOWN"


def test_timestamp_parsing_accepts_both_dataset_formats():
    assert cicids_replay._parse_timestamp("5/7/2017 8:42:11") is not None
    assert cicids_replay._parse_timestamp("5/7/2017 8:42") is not None
    assert cicids_replay._parse_timestamp("not a date") is None


def test_reference_feature_sets_are_internally_consistent(reference):
    base = reference["feature_sets"][reference["base_feature_version"]]
    assert len(base) == reference["n_features"] == 78

    for version, columns in reference["feature_sets"].items():
        assert len(columns) == len(set(columns)), version
        for column in columns:
            assert column in reference["features"], f"{version}: {column}"


def test_reference_records_dataset_provenance(reference):
    dataset = reference["dataset"]
    assert dataset["rows"] > 0
    assert len(dataset["sha256"]) == 64
    json.dumps(reference["label_distribution"])
