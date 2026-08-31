import math

import pytest

from app.replay.feature_derivation import (
    DERIVATIONS,
    MIN_TRUSTED_EXACT_RATE,
    NOT_DERIVABLE,
    can_derive,
    derivable_features,
    derive,
)


def test_every_rule_declares_inputs_and_a_verified_rate():
    for feature, rule in DERIVATIONS.items():
        assert rule["inputs"], feature
        assert 0.0 < rule["exact_rate"] <= 1.0, feature
        assert rule["exact_rate"] >= MIN_TRUSTED_EXACT_RATE, feature
        assert callable(rule["function"]), feature
        assert rule["note"], feature


def test_rules_only_target_real_training_features(all_features):
    for feature in DERIVATIONS:
        assert feature in all_features


def test_rule_inputs_are_real_training_features(all_features):
    for feature, rule in DERIVATIONS.items():
        for name in rule["inputs"]:
            assert name in all_features, f"{feature} -> {name}"


def test_no_rule_derives_a_feature_from_itself():
    for feature, rule in DERIVATIONS.items():
        assert feature not in rule["inputs"]


def test_average_packet_size_is_declared_not_derivable():
    assert "Average Packet Size" in NOT_DERIVABLE
    assert "Average Packet Size" not in DERIVATIONS


def test_derivable_features_matches_the_rule_table():
    assert set(derivable_features()) == set(DERIVATIONS)


def test_segment_sizes_mirror_packet_length_means():
    assert derive("Avg Fwd Segment Size", {"Fwd Packet Length Mean": 37.5}) == 37.5
    assert derive("Avg Bwd Segment Size", {"Bwd Packet Length Mean": 12.25}) == 12.25


def test_subflow_features_mirror_totals():
    values = {
        "Total Fwd Packets": 9,
        "Total Backward Packets": 4,
        "Total Length of Fwd Packets": 512,
        "Total Length of Bwd Packets": 128,
    }
    assert derive("Subflow Fwd Packets", values) == 9
    assert derive("Subflow Bwd Packets", values) == 4
    assert derive("Subflow Fwd Bytes", values) == 512
    assert derive("Subflow Bwd Bytes", values) == 128


def test_down_up_ratio_is_integer_floored():
    assert derive("Down/Up Ratio", {"Total Backward Packets": 7, "Total Fwd Packets": 2}) == 3
    assert derive("Down/Up Ratio", {"Total Backward Packets": 1, "Total Fwd Packets": 2}) == 0


def test_down_up_ratio_guards_against_zero_forward_packets():
    assert derive("Down/Up Ratio", {"Total Backward Packets": 5, "Total Fwd Packets": 0}) is None


def test_packet_length_variance_is_the_square_of_std():
    assert derive("Packet Length Variance", {"Packet Length Std": 4.0}) == 16.0


def test_max_packet_length_takes_the_larger_direction():
    values = {"Fwd Packet Length Max": 100.0, "Bwd Packet Length Max": 250.0}
    assert derive("Max Packet Length", values) == 250.0


def test_min_packet_length_uses_both_directions_when_backward_traffic_exists():
    values = {
        "Fwd Packet Length Min": 60.0,
        "Bwd Packet Length Min": 40.0,
        "Total Backward Packets": 3,
    }
    assert derive("Min Packet Length", values) == 40.0


def test_min_packet_length_ignores_backward_minimum_without_backward_packets():
    values = {
        "Fwd Packet Length Min": 60.0,
        "Bwd Packet Length Min": 0.0,
        "Total Backward Packets": 0,
    }
    assert derive("Min Packet Length", values) == 60.0


def test_rates_convert_microseconds_to_seconds():
    values = {
        "Total Fwd Packets": 6,
        "Total Backward Packets": 4,
        "Total Length of Fwd Packets": 1000,
        "Total Length of Bwd Packets": 500,
        "Flow Duration": 1_000_000,
    }
    assert derive("Flow Packets/s", values) == 10.0
    assert derive("Fwd Packets/s", values) == 6.0
    assert derive("Bwd Packets/s", values) == 4.0
    assert derive("Flow Bytes/s", values) == 1500.0


def test_rates_guard_against_zero_duration():
    values = {
        "Total Fwd Packets": 6,
        "Total Backward Packets": 4,
        "Total Length of Fwd Packets": 1000,
        "Total Length of Bwd Packets": 500,
        "Flow Duration": 0,
    }
    for feature in ["Flow Packets/s", "Fwd Packets/s", "Bwd Packets/s", "Flow Bytes/s"]:
        assert derive(feature, values) is None, feature


def test_flow_iat_mean_divides_by_packet_gaps():
    values = {"Flow Duration": 900.0, "Total Fwd Packets": 6, "Total Backward Packets": 4}
    assert derive("Flow IAT Mean", values) == 100.0


def test_flow_iat_mean_requires_more_than_one_packet():
    values = {"Flow Duration": 900.0, "Total Fwd Packets": 1, "Total Backward Packets": 0}
    assert derive("Flow IAT Mean", values) is None


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), None, "", "abc"])
def test_unusable_inputs_yield_no_derivation(bad):
    assert derive("Avg Fwd Segment Size", {"Fwd Packet Length Mean": bad}) is None


def test_missing_input_yields_no_derivation():
    assert derive("Down/Up Ratio", {"Total Fwd Packets": 4}) is None


def test_unknown_feature_yields_no_derivation():
    assert derive("Not A Feature", {"anything": 1.0}) is None


def test_can_derive_requires_every_input_to_be_available():
    assert can_derive("Down/Up Ratio", {"Total Backward Packets", "Total Fwd Packets"})
    assert not can_derive("Down/Up Ratio", {"Total Fwd Packets"})
    assert not can_derive("Average Packet Size", {"Total Fwd Packets"})


def test_string_inputs_are_accepted_when_numeric():
    assert derive("Avg Fwd Segment Size", {"Fwd Packet Length Mean": "37.5"}) == 37.5


def test_derived_values_are_finite():
    values = {
        "Total Fwd Packets": 3,
        "Total Backward Packets": 2,
        "Total Length of Fwd Packets": 300,
        "Total Length of Bwd Packets": 200,
        "Flow Duration": 500_000,
        "Packet Length Std": 3.0,
        "Fwd Packet Length Mean": 100.0,
        "Bwd Packet Length Mean": 100.0,
        "Fwd Packet Length Max": 150.0,
        "Bwd Packet Length Max": 120.0,
        "Fwd Packet Length Min": 50.0,
        "Bwd Packet Length Min": 40.0,
    }
    for feature in DERIVATIONS:
        result = derive(feature, values)
        assert result is not None, feature
        assert math.isfinite(result), feature
