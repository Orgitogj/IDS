import math

import pytest

from app.ml.feature_validation import (
    PERMISSIVE_POLICY,
    STRICT_POLICY,
    FeatureValidationError,
    FeatureValidator,
    ValidationPolicy,
    load_reference,
    resolve_feature_version,
)
from app.replay.feature_mapping import CONST_ZERO_IN_TRAINING


@pytest.fixture
def validator(reference, top50_features):
    return FeatureValidator(top50_features, reference=reference, policy=STRICT_POLICY)


@pytest.fixture
def wide_validator(reference, all_features):
    return FeatureValidator(all_features, reference=reference, policy=STRICT_POLICY)


def test_feature_version_is_resolved_from_the_reference(validator):
    assert validator.feature_version == "cicids2017-top50-v1"


def test_unregistered_feature_set_is_labelled_as_such(reference):
    validator = FeatureValidator(["Flow Duration", "Protocol"], reference=reference)
    assert validator.feature_version == "unregistered-2-features"


def test_explicit_feature_version_wins(reference, top50_features):
    validator = FeatureValidator(top50_features, reference=reference, feature_version="custom-v9")
    assert validator.feature_version == "custom-v9"


def test_resolve_feature_version_matches_by_order_and_by_set(reference, top50_features):
    assert resolve_feature_version(top50_features, reference) == "cicids2017-top50-v1"
    assert resolve_feature_version(list(reversed(top50_features)), reference) == "cicids2017-top50-v1"
    assert resolve_feature_version(["Flow Duration"], reference) is None
    assert resolve_feature_version(top50_features, None) is None


def test_complete_vector_is_valid(validator, full_vector):
    result = validator.validate(full_vector)
    assert result.valid
    assert result.missing_features == []
    assert result.invalid_features == []
    assert result.vector is not None


def test_output_vector_follows_the_declared_feature_order(validator, full_vector):
    result = validator.validate(full_vector)
    expected = [float(full_vector[name]) for name in validator.feature_columns]
    assert result.vector == expected


def test_output_vector_length_matches_the_feature_set(validator, full_vector):
    result = validator.validate(full_vector)
    assert len(result.vector) == len(validator.feature_columns) == 50


def test_extra_features_are_counted_but_never_fatal(validator, full_vector):
    result = validator.validate(full_vector)
    assert result.valid
    assert result.to_dict()["unexpected_feature_count"] == 78 - 50


def test_missing_non_derivable_feature_is_rejected(validator, full_vector):
    del full_vector["Init_Win_bytes_backward"]
    result = validator.validate(full_vector)
    assert not result.valid
    assert result.missing_features == ["Init_Win_bytes_backward"]
    assert result.vector is None


def test_missing_derivable_feature_is_reconstructed(validator, full_vector):
    del full_vector["Down/Up Ratio"]
    result = validator.validate(full_vector)
    assert result.valid
    assert [entry["feature"] for entry in result.derived_features] == ["Down/Up Ratio"]
    assert result.derived_features[0]["reason"] == "missing"
    assert result.derived_features[0]["verified_exact_rate"] == 1.0


def test_derivation_is_skipped_when_its_inputs_are_unavailable(validator, full_vector):
    del full_vector["Down/Up Ratio"]
    del full_vector["Total Backward Packets"]
    result = validator.validate(full_vector)
    assert not result.valid
    assert set(result.missing_features) == {"Down/Up Ratio", "Total Backward Packets"}


def test_sensor_value_is_preferred_over_derivation(validator, full_vector):
    full_vector["Down/Up Ratio"] = 42.0
    result = validator.validate(full_vector)
    assert result.valid
    assert result.derived_features == []
    index = validator.feature_columns.index("Down/Up Ratio")
    assert result.vector[index] == 42.0


@pytest.mark.parametrize("bad,reason", [
    (float("nan"), "nan"),
    (float("inf"), "inf"),
    (float("-inf"), "inf"),
    ("abc", "non_numeric"),
    ("", "empty"),
    (None, "null"),
])
def test_unusable_values_on_a_non_derivable_feature_are_rejected(validator, full_vector, bad, reason):
    full_vector["Init_Win_bytes_backward"] = bad
    result = validator.validate(full_vector)
    assert not result.valid
    assert result.invalid_features == [{"feature": "Init_Win_bytes_backward", "reason": reason}]
    assert result.missing_features == []


def test_absent_key_and_null_value_are_reported_differently(validator, full_vector):
    absent = dict(full_vector)
    del absent["Init_Win_bytes_backward"]
    nulled = dict(full_vector)
    nulled["Init_Win_bytes_backward"] = None

    absent_result = validator.validate(absent)
    null_result = validator.validate(nulled)

    assert absent_result.missing_features == ["Init_Win_bytes_backward"]
    assert absent_result.invalid_features == []
    assert null_result.missing_features == []
    assert null_result.invalid_features[0]["reason"] == "null"


def test_infinity_is_recovered_when_a_derivation_can_replace_it(validator, full_vector):
    full_vector["Flow Bytes/s"] = float("inf")
    full_vector["Flow Duration"] = 1_000_000
    full_vector["Total Length of Fwd Packets"] = 1000
    full_vector["Total Length of Bwd Packets"] = 500
    result = validator.validate(full_vector)
    assert result.valid
    derived = {entry["feature"]: entry for entry in result.derived_features}
    assert derived["Flow Bytes/s"]["reason"] == "inf"
    index = validator.feature_columns.index("Flow Bytes/s")
    assert result.vector[index] == 1500.0


def test_infinity_is_rejected_when_the_derivation_cannot_run(validator, full_vector):
    full_vector["Flow Bytes/s"] = float("inf")
    full_vector["Flow Duration"] = 0
    result = validator.validate(full_vector)
    assert not result.valid
    assert {"feature": "Flow Bytes/s", "reason": "inf"} in result.invalid_features


def test_numeric_strings_are_accepted(validator, full_vector):
    coerced = {name: str(value) for name, value in full_vector.items()}
    result = validator.validate(coerced)
    assert result.valid
    assert all(isinstance(value, float) for value in result.vector)


def test_booleans_are_accepted_as_numbers(validator, full_vector):
    full_vector["Fwd PSH Flags"] = True
    result = validator.validate(full_vector)
    assert result.valid
    index = validator.feature_columns.index("Fwd PSH Flags")
    assert result.vector[index] == 1.0


def test_empty_vector_is_rejected_and_lists_everything(validator):
    result = validator.validate({})
    assert not result.valid
    assert len(result.missing_features) == 50
    assert result.vector is None


def test_none_input_is_rejected(validator):
    result = validator.validate(None)
    assert not result.valid


def test_const_zero_features_are_filled_not_rejected(wide_validator, full_vector):
    for name in CONST_ZERO_IN_TRAINING:
        del full_vector[name]
    result = wide_validator.validate(full_vector)
    assert result.valid
    assert sorted(result.zero_filled_features) == sorted(CONST_ZERO_IN_TRAINING)
    assert result.missing_features == []
    for name in CONST_ZERO_IN_TRAINING:
        assert result.vector[wide_validator.feature_columns.index(name)] == 0.0


def test_const_zero_fill_can_be_disabled(reference, all_features, full_vector):
    policy = ValidationPolicy("no-fill", allow_const_zero_fill=False)
    validator = FeatureValidator(all_features, reference=reference, policy=policy)
    del full_vector["Bwd PSH Flags"]
    result = validator.validate(full_vector)
    assert not result.valid
    assert result.missing_features == ["Bwd PSH Flags"]


def test_out_of_range_values_warn_without_rejecting(validator, full_vector):
    full_vector["Flow Duration"] = 9.9e12
    result = validator.validate(full_vector)
    assert result.valid
    flagged = [entry["feature"] for entry in result.out_of_range_features]
    assert "Flow Duration" in flagged
    entry = next(e for e in result.out_of_range_features if e["feature"] == "Flow Duration")
    assert entry["value"] == 9.9e12
    assert entry["training_p99"] < entry["value"]


def test_range_check_can_be_disabled(reference, top50_features, full_vector):
    policy = ValidationPolicy("no-range", range_check=False)
    validator = FeatureValidator(top50_features, reference=reference, policy=policy)
    full_vector["Flow Duration"] = 9.9e12
    result = validator.validate(full_vector)
    assert result.valid
    assert result.out_of_range_features == []


def test_validator_works_without_a_reference(top50_features, full_vector):
    validator = FeatureValidator(top50_features, reference=None)
    result = validator.validate(full_vector)
    assert result.valid
    assert result.out_of_range_features == []
    assert validator.feature_version == "unregistered-50-features"


def test_permissive_policy_accepts_an_empty_vector(reference, top50_features):
    validator = FeatureValidator(top50_features, reference=reference, policy=PERMISSIVE_POLICY)
    result = validator.validate({})
    assert result.valid
    assert len(result.missing_features) == 50
    assert len(result.vector) == 50
    assert all(value == 0.0 for value in result.vector)


def test_validate_or_raise_raises_on_invalid(validator):
    with pytest.raises(FeatureValidationError) as excinfo:
        validator.validate_or_raise({})
    assert excinfo.value.result.valid is False
    assert len(excinfo.value.result.missing_features) == 50


def test_validate_or_raise_returns_result_when_valid(validator, full_vector):
    assert validator.validate_or_raise(full_vector).valid


def test_result_dict_is_json_serialisable(validator, full_vector):
    import json
    full_vector["Flow Duration"] = 9.9e12
    payload = validator.validate(full_vector).to_dict()
    json.dumps(payload)
    assert set(payload) == {
        "valid", "feature_version", "policy", "missing_features", "invalid_features",
        "derived_features", "zero_filled_features", "out_of_range_features",
        "unexpected_feature_count", "warnings",
    }


def test_summary_reports_missing_features(validator, full_vector):
    del full_vector["Init_Win_bytes_backward"]
    assert validator.validate(full_vector).summary() == "1 missing"


def test_summary_reports_derivations(validator, full_vector):
    del full_vector["Down/Up Ratio"]
    assert "1 derived" in validator.validate(full_vector).summary()


def test_summary_is_clean_for_an_unremarkable_vector(reference, top50_features, full_vector):
    policy = ValidationPolicy("no-range", range_check=False)
    validator = FeatureValidator(top50_features, reference=reference, policy=policy)
    assert validator.validate(full_vector).summary() == "clean"


def test_every_rejection_produces_a_warning(validator, full_vector):
    del full_vector["Init_Win_bytes_backward"]
    full_vector["Protocol"] = "tcp"
    result = validator.validate(full_vector)
    assert not result.valid
    assert len(result.warnings) >= 2
    joined = " ".join(result.warnings)
    assert "Init_Win_bytes_backward" in joined
    assert "Protocol" in joined


def test_rejected_results_never_expose_a_vector(validator, full_vector):
    del full_vector["Init_Win_bytes_backward"]
    assert validator.validate(full_vector).vector is None


def test_accepted_vectors_are_always_finite_floats(validator, full_vector):
    result = validator.validate(full_vector)
    assert all(isinstance(v, float) and math.isfinite(v) for v in result.vector)


def test_load_reference_returns_none_for_a_missing_path(tmp_path):
    assert load_reference(tmp_path / "nope.json") is None
