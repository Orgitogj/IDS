import pytest

from app.replay.feature_mapping import (
    CICFLOWMETER_TO_CICIDS2017,
    CICIDS2017_TO_CICFLOWMETER,
    CONST_ZERO_IN_TRAINING,
    META_COLUMNS,
)
from app.replay.live_agent import map_row_to_feature_vector


def test_mapping_covers_every_training_feature(all_features):
    targets = set(CICFLOWMETER_TO_CICIDS2017.values())
    uncovered = [name for name in all_features if name not in targets]
    assert uncovered == []


def test_mapping_has_no_targets_outside_the_training_set(all_features):
    expected = set(all_features)
    spurious = [name for name in CICFLOWMETER_TO_CICIDS2017.values() if name not in expected]
    assert spurious == []


def test_mapping_is_one_to_one():
    assert len(set(CICFLOWMETER_TO_CICIDS2017.values())) == len(CICFLOWMETER_TO_CICIDS2017)


def test_inverse_mapping_round_trips():
    for source, target in CICFLOWMETER_TO_CICIDS2017.items():
        assert CICIDS2017_TO_CICFLOWMETER[target] == source


def test_const_zero_features_are_real_training_features(all_features):
    for name in CONST_ZERO_IN_TRAINING:
        assert name in all_features


def test_const_zero_features_are_constant_zero_in_the_reference(reference):
    for name in CONST_ZERO_IN_TRAINING:
        stats = reference["features"][name]
        assert stats["constant"] is True
        assert stats["constant_value"] == 0.0


def test_const_zero_list_matches_the_reference_exactly(reference):
    assert sorted(CONST_ZERO_IN_TRAINING) == sorted(reference["constant_zero_features"])


def test_no_const_zero_feature_is_in_the_active_feature_set(top50_features):
    overlap = [name for name in CONST_ZERO_IN_TRAINING if name in top50_features]
    assert overlap == []


def test_map_row_renames_to_cicids_names():
    row = {"dst_port": "443", "flow_duration": "1000", "tot_fwd_pkts": "5"}
    mapped = map_row_to_feature_vector(row)
    assert mapped == {
        "Destination Port": "443",
        "Flow Duration": "1000",
        "Total Fwd Packets": "5",
    }


def test_map_row_drops_meta_columns():
    row = {name: "x" for name in META_COLUMNS}
    row["dst_port"] = "80"
    mapped = map_row_to_feature_vector(row)
    assert mapped == {"Destination Port": "80"}


def test_map_row_ignores_unknown_columns():
    mapped = map_row_to_feature_vector({"fwd_win_scale": "7", "dst_port": "80"})
    assert mapped == {"Destination Port": "80"}


def test_map_row_does_not_invent_values():
    mapped = map_row_to_feature_vector({"dst_port": "80"})
    assert len(mapped) == 1


@pytest.mark.parametrize("column", ["src_ip", "dst_ip", "src_port", "timestamp"])
def test_meta_columns_are_never_features(column, all_features):
    assert CICFLOWMETER_TO_CICIDS2017.get(column) is None
    assert column in META_COLUMNS
