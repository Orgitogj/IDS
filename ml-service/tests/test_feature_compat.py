import pytest

from app.live import compat, protocol

SCHEMA = protocol.FROZEN_PRIMARY_MODEL["feature_version"]


def frozen_columns():
    from app.live import lab_runner
    from pathlib import Path
    models = Path(__file__).resolve().parent.parent / "models"
    if not (models / protocol.FROZEN_PRIMARY_MODEL["artifact_file"]).exists():
        pytest.skip("artefakti v2 mungon")
    _, _, cols, _ = lab_runner.load_frozen_model(models)
    return cols


class TestConfirmedSet:

    def test_confirmed_set_has_exactly_thirteen_features(self):
        assert len(compat.CONFIRMED_SECONDS_FEATURES) == 13
        assert len(set(compat.CONFIRMED_SECONDS_FEATURES)) == 13

    def test_confirmed_set_is_only_time_duration_and_iat_features(self):
        for name in compat.CONFIRMED_SECONDS_FEATURES:
            assert "Duration" in name or "IAT" in name

    def test_rate_features_are_never_in_the_confirmed_set(self):
        for name in compat.RATE_FEATURES_NOT_CONVERTED:
            assert name not in compat.CONFIRMED_SECONDS_FEATURES

    def test_all_zero_lab_features_are_not_auto_converted(self):
        for name in compat.LIKELY_SECONDS_FEATURES_ALL_ZERO_IN_LAB:
            assert name not in compat.CONFIRMED_SECONDS_FEATURES


class TestConversion:

    def _cols(self):
        return [f"f{i}" for i in range(78)]

    def _cols_with_confirmed(self):
        cols = list(compat.CONFIRMED_SECONDS_FEATURES)
        cols += [f"pad{i}" for i in range(78 - len(cols))]
        return cols

    def test_conversion_factor_is_one_million(self):
        assert compat.SECONDS_TO_MICROSECONDS == 1_000_000

    def test_confirmed_features_are_multiplied_by_one_million(self):
        cols = self._cols_with_confirmed()
        vector = [2.0] * 78
        new, meta = compat.harmonize_vector(cols, vector, SCHEMA)
        for name in compat.CONFIRMED_SECONDS_FEATURES:
            assert new[cols.index(name)] == 2.0 * 1_000_000
        assert meta["converted_feature_count"] == 13

    def test_non_confirmed_features_are_unchanged(self):
        cols = self._cols_with_confirmed()
        vector = [float(i) for i in range(78)]
        new, _ = compat.harmonize_vector(cols, vector, SCHEMA)
        for i, name in enumerate(cols):
            if name not in compat.CONFIRMED_SECONDS_FEATURES:
                assert new[i] == vector[i]

    def test_feature_count_and_order_are_preserved(self):
        cols = self._cols_with_confirmed()
        vector = [1.0] * 78
        new, _ = compat.harmonize_vector(cols, vector, SCHEMA)
        assert len(new) == 78

    def test_conversion_is_deterministic(self):
        cols = self._cols_with_confirmed()
        vector = [3.5] * 78
        a, _ = compat.harmonize_vector(cols, vector, SCHEMA)
        b, _ = compat.harmonize_vector(cols, vector, SCHEMA)
        assert a == b

    def test_the_raw_input_vector_is_not_mutated(self):
        cols = self._cols_with_confirmed()
        vector = [2.0] * 78
        original = list(vector)
        compat.harmonize_vector(cols, vector, SCHEMA)
        assert vector == original

    def test_nonfinite_input_is_refused(self):
        cols = self._cols_with_confirmed()
        vector = [1.0] * 78
        vector[cols.index("Flow Duration")] = float("inf")
        with pytest.raises(compat.CompatError):
            compat.harmonize_vector(cols, vector, SCHEMA)

    def test_incompatible_schema_is_refused(self):
        cols = self._cols_with_confirmed()
        with pytest.raises(compat.CompatError):
            compat.harmonize_vector(cols, [1.0] * 78, "cicids2017-top50-v1")

    def test_wrong_feature_count_is_refused(self):
        with pytest.raises(compat.CompatError):
            compat.harmonize_vector(["a", "b"], [1.0, 2.0], SCHEMA)

    def test_missing_confirmed_feature_is_refused(self):
        cols = [f"f{i}" for i in range(78)]
        with pytest.raises(compat.CompatError):
            compat.harmonize_vector(cols, [1.0] * 78, SCHEMA)

    def test_metadata_records_protocol_and_contract(self):
        cols = self._cols_with_confirmed()
        _, meta = compat.harmonize_vector(cols, [1.0] * 78, SCHEMA)
        assert meta["compatibility_protocol"] == "lab-feature-compat-v1"
        assert meta["target_feature_contract"] == SCHEMA
        assert meta["source_feature_semantics"] == "cicflowmeter-0.5.0"
        assert meta["compatibility_applied"] is True


class TestDoubleApplicationGuard:

    def test_record_marker_prevents_double_application(self):
        rec = compat.harmonize_record({"run_id": "x"})
        assert compat.is_applied(rec)
        with pytest.raises(compat.CompatError):
            compat.harmonize_record(rec)

    def test_a_fresh_record_is_not_marked_applied(self):
        assert compat.is_applied({"run_id": "x"}) is False


class TestAgainstFrozenSchema:

    @pytest.mark.artifacts
    def test_confirmed_features_all_exist_in_the_frozen_schema(self):
        cols = frozen_columns()
        for name in compat.CONFIRMED_SECONDS_FEATURES:
            assert name in cols

    @pytest.mark.artifacts
    def test_harmonize_only_changes_the_confirmed_positions(self):
        cols = frozen_columns()
        vector = [1.0] * len(cols)
        new, _ = compat.harmonize_vector(cols, vector, SCHEMA)
        changed = [cols[i] for i in range(len(cols)) if new[i] != vector[i]]
        assert sorted(changed) == sorted(compat.CONFIRMED_SECONDS_FEATURES)

    @pytest.mark.artifacts
    def test_packet_and_flag_features_are_never_converted(self):
        cols = frozen_columns()
        vector = [1.0] * len(cols)
        new, _ = compat.harmonize_vector(cols, vector, SCHEMA)
        for name in ("Fwd Packet Length Mean", "Average Packet Size", "PSH Flag Count",
                     "Total Fwd Packets", "Bwd Header Length", "Flow Bytes/s",
                     "Flow Packets/s"):
            assert new[cols.index(name)] == vector[cols.index(name)]
