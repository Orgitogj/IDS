import hashlib
import json
from pathlib import Path

import pytest

ML = Path(__file__).resolve().parent.parent
PHASE17C = ML / "reports" / "domain_adaptation" / "phase17c"


def _protocol():
    p = PHASE17C / "protocol.json"
    if not p.exists():
        pytest.skip("phase 17c protocol not built")
    return json.load(open(p, encoding="utf-8"))


def _metadata():
    p = PHASE17C / "model_b_metadata.json"
    if not p.exists():
        pytest.skip("model b metadata not built")
    return json.load(open(p, encoding="utf-8"))


def _builder():
    pytest.importorskip("xgboost")
    pytest.importorskip("sklearn")
    from training import train_model_b
    return train_model_b


def _matrix_digest(X):
    return hashlib.sha256(X.tobytes()).hexdigest()


class TestPartitionReproducibility:

    def test_partitions_rebuild_to_recorded_counts(self):
        builder = _builder()
        protocol, metadata = _protocol(), _metadata()
        features = protocol["feature_contract"]["feature_list"]

        for key, recorded in (("train_runs", "train_partition"),
                              ("validation_runs", "validation_partition")):
            _, _, _, meta = builder.build_partition(protocol["split"][key], features)
            by_run = {m["run_id"]: m for m in meta}
            for entry in metadata[recorded]:
                rebuilt = by_run[entry["run_id"]]
                assert rebuilt["total_flows"] == entry["total_flows"]
                assert rebuilt["evaluable_flows"] == entry["evaluable_flows"]
                assert rebuilt["attack_flows"] == entry["attack_flows"]
                assert rebuilt["benign_flows"] == entry["benign_flows"]

    def test_capture_hashes_stable(self):
        builder = _builder()
        protocol, metadata = _protocol(), _metadata()
        features = protocol["feature_contract"]["feature_list"]
        _, _, _, meta = builder.build_partition(
            protocol["split"]["train_runs"], features)
        by_run = {m["run_id"]: m["capture_sha256"] for m in meta}
        for entry in metadata["train_partition"]:
            assert by_run[entry["run_id"]] == entry["capture_sha256"]

    def test_feature_matrix_build_is_deterministic(self):
        builder = _builder()
        features = _protocol()["feature_contract"]["feature_list"]
        runs = _protocol()["split"]["validation_runs"]
        first, _, _, _ = builder.build_partition(runs, features)
        second, _, _, _ = builder.build_partition(runs, features)
        assert first.shape == second.shape
        assert _matrix_digest(first) == _matrix_digest(second)

    def test_feature_matrix_width_is_the_frozen_contract(self):
        builder = _builder()
        features = _protocol()["feature_contract"]["feature_list"]
        X, _, _, _ = builder.build_partition(
            _protocol()["split"]["validation_runs"], features)
        assert X.shape[1] == 76

    def test_feature_matrix_is_finite(self):
        numpy = pytest.importorskip("numpy")
        builder = _builder()
        features = _protocol()["feature_contract"]["feature_list"]
        X, _, _, _ = builder.build_partition(
            _protocol()["split"]["validation_runs"], features)
        assert numpy.isfinite(X).all()


class TestClassWeightReproducibility:

    def test_class_weights_recompute_from_train_only(self):
        builder = _builder()
        protocol, metadata = _protocol(), _metadata()
        features = protocol["feature_contract"]["feature_list"]
        _, y_train, _, _ = builder.build_partition(
            protocol["split"]["train_runs"], features)
        weights, counts = builder.class_weights(y_train)
        assert counts[0] == metadata["train_class_counts"]["BENIGN"]
        assert counts[1] == metadata["train_class_counts"]["ATTACK"]
        assert weights[0] == pytest.approx(
            metadata["train_class_weights"]["BENIGN"])
        assert weights[1] == pytest.approx(
            metadata["train_class_weights"]["ATTACK"])

    def test_validation_labels_match_recorded_support(self):
        builder = _builder()
        protocol, metadata = _protocol(), _metadata()
        features = protocol["feature_contract"]["feature_list"]
        _, y_val, scenarios, _ = builder.build_partition(
            protocol["split"]["validation_runs"], features)
        assert int((y_val == 0).sum()) == \
            metadata["validation_class_counts"]["BENIGN"]
        assert int((y_val == 1).sum()) == \
            metadata["validation_class_counts"]["ATTACK"]
        assert int((scenarios == "ssh").sum()) == 69


class TestWilsonInterval:

    def test_wilson_brackets_the_point_estimate(self):
        wilson = _builder().wilson
        for successes, n in ((0, 69), (69, 69), (21, 5407), (1362, 1362)):
            interval = wilson(successes, n)
            assert interval["low"] <= interval["point"] <= interval["high"]
            assert 0.0 <= interval["low"] and interval["high"] <= 1.0

    def test_observed_zero_has_non_zero_upper_bound(self):
        interval = _builder().wilson(0, 69)
        assert interval["point"] == 0.0
        assert interval["high"] > 0.0

    def test_observed_perfect_rate_has_sub_one_lower_bound(self):
        interval = _builder().wilson(69, 69)
        assert interval["point"] == 1.0
        assert interval["low"] < 1.0

    def test_empty_denominator_is_null_not_fabricated(self):
        interval = _builder().wilson(0, 0)
        assert interval["point"] is None
        assert interval["n"] == 0
