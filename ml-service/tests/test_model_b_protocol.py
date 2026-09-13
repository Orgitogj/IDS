import hashlib
import json
from pathlib import Path

import pytest

ML = Path(__file__).resolve().parent.parent
DATA = ML / "reports" / "domain_adaptation" / "data"
PHASE17C = ML / "reports" / "domain_adaptation" / "phase17c"
PHASE17B_HEAD = "38905dacaba658967d68740b458ece54555ff329"

HISTORICAL = ["lab-v1-benign-001", "lab-v1-portscan-001", "lab-v1-ssh-bruteforce-001"]
NEW = [
    "adapt-v1-benign-002", "adapt-v1-benign-003", "adapt-v1-benign-004",
    "adapt-v1-portscan-002", "adapt-v1-portscan-003", "adapt-v1-portscan-004",
    "adapt-v1-ssh-002", "adapt-v1-ssh-003", "adapt-v1-ssh-004",
]

PRIMARY_ID = "model-b-xgb-weighted-v1"
IDENTITY_COLUMNS = ["src_ip", "dst_ip", "src_port", "dst_port", "protocol", "timestamp"]

MODEL_A_HISTORICAL = {
    "benign": {"false_positives": 0, "n": 5407},
    "portscan": {"detected": 2, "n": 1362},
    "ssh": {"detected": 0, "n": 69},
}


def _load(name):
    p = PHASE17C / name
    if not p.exists():
        pytest.skip(f"{name} not built")
    return json.load(open(p, encoding="utf-8"))


def _protocol():
    return _load("protocol.json")


def _metadata():
    return _load("model_b_metadata.json")


def _validation():
    return _load("validation_results.json")


class TestProtocolFrozen:

    def test_phase17b_frozen_head_traceable(self):
        assert _protocol()["phase17b_frozen_head"] == PHASE17B_HEAD
        assert _metadata()["phase17b_frozen_head"] == PHASE17B_HEAD

    def test_protocol_declared_frozen_before_training(self):
        p = _protocol()
        assert p["status"] == "FROZEN_BEFORE_TRAINING"
        assert p["written_before_any_model_fit"] is True

    def test_metadata_pins_protocol_hash(self):
        digest = hashlib.sha256((PHASE17C / "protocol.json").read_bytes()).hexdigest()
        assert _metadata()["protocol_sha256"] == digest


class TestSplitFrozen:

    def test_train_is_exactly_nine_new_runs(self):
        for source in (_protocol()["split"]["train_runs"], _metadata()["train_runs"]):
            assert list(source) == NEW
            assert len(source) == 9

    def test_validation_is_exactly_three_historical_runs(self):
        for source in (_protocol()["split"]["validation_runs"],
                       _metadata()["validation_runs"]):
            assert list(source) == HISTORICAL
            assert len(source) == 3

    def test_run_level_disjointness(self):
        m = _metadata()
        assert not set(m["train_runs"]) & set(m["validation_runs"])

    def test_final_test_remains_empty(self):
        assert _protocol()["split"]["final_test_runs"] == []
        assert _metadata()["final_test_runs"] == []

    def test_split_is_run_level_not_flow_level(self):
        s = _protocol()["split"]
        assert s["granularity"] == "run_level"
        assert s["flow_level_random_splitting"] is False

    def test_split_marked_development_only(self):
        assert _protocol()["split"]["development_only"] is True
        assert _validation()["validation_is_development_only"] is True

    def test_split_matches_frozen_phase17b_proposal(self):
        p = DATA / "model_b_split_proposal.json"
        if not p.exists():
            pytest.skip("phase 17b split proposal not built")
        frozen = json.load(open(p, encoding="utf-8"))
        m = _metadata()
        assert m["train_runs"] == frozen["train_runs"]
        assert m["validation_runs"] == frozen["validation_runs"]
        assert m["final_test_runs"] == frozen["final_test_runs"]


class TestNoFinalEvaluation:

    def test_no_eval_v1_run_in_model_b_partitions(self):
        m = _metadata()
        runs = list(m["train_runs"]) + list(m["validation_runs"]) + \
            list(m["final_test_runs"])
        runs += [e["run_id"] for e in m["train_partition"] + m["validation_partition"]]
        assert not any(str(r).startswith("eval-v1-") for r in runs)

    def test_no_final_test_partition_recorded(self):
        m = _metadata()
        assert m["final_test_runs"] == []
        assert "final_test_partition" not in m

    def test_validation_runs_are_not_called_unseen(self):
        note = _validation()["validation_note"].lower()
        assert "not unseen final evaluation data" in note


class TestLeakageGuards:

    def test_no_validation_flow_enters_training_or_preprocessing_fit(self):
        p = _protocol()["leakage_guards"]
        assert p["preprocessing_fit_partition"] == "TRAIN_ONLY"
        for stage in ("preprocessing fit", "feature selection",
                      "class-weight calculation", "imputation fit", "scaler fit",
                      "hyperparameter fitting", "threshold construction",
                      "model fitting"):
            assert stage in p["validation_must_not_enter"]

    def test_class_weights_derived_from_train_only(self):
        m = _metadata()
        assert m["class_weight_partition"] == "TRAIN_ONLY"
        counts, weights = m["train_class_counts"], m["train_class_weights"]
        total = counts["BENIGN"] + counts["ATTACK"]
        for name in ("BENIGN", "ATTACK"):
            assert weights[name] == pytest.approx(total / (2 * counts[name]))

    def test_class_weights_do_not_match_validation_distribution(self):
        m = _metadata()
        v = m["validation_class_counts"]
        total = v["BENIGN"] + v["ATTACK"]
        for name in ("BENIGN", "ATTACK"):
            assert m["train_class_weights"][name] != pytest.approx(
                total / (2 * v[name]))

    def test_identity_columns_never_enter_features(self):
        features = _protocol()["feature_contract"]["feature_list"]
        for column in IDENTITY_COLUMNS:
            assert column not in features
        assert _metadata()["feature_list"] == features

    def test_labels_are_not_prediction_driven(self):
        assert _protocol()["labelling"]["prediction_driven_labelling"] is False


class TestBalancingPolicy:

    def test_no_smote(self):
        assert _protocol()["balancing"]["smote"] is False
        assert _metadata()["smote"] is False

    def test_no_benign_undersampling(self):
        assert _protocol()["balancing"]["benign_undersampling"] is False
        assert _metadata()["benign_undersampling"] is False

    def test_benign_is_minority_class_in_train(self):
        counts = _metadata()["train_class_counts"]
        assert counts["BENIGN"] < counts["ATTACK"]


class TestThreshold:

    def test_primary_threshold_is_exactly_half(self):
        assert _protocol()["threshold"]["primary"] == 0.50
        assert _metadata()["threshold"] == 0.50
        assert _validation()["threshold"] == 0.50

    def test_threshold_not_tuned(self):
        t = _protocol()["threshold"]
        assert t["tuned_on_validation"] is False
        assert t["tuned_on_final_evaluation"] is False
        assert _validation()["threshold_tuned_on_validation"] is False

    def test_every_reported_result_uses_the_primary_threshold(self):
        for result in _validation()["results"].values():
            assert result["threshold"] == 0.50


class TestFeatureSchema:

    def test_feature_schema_deterministic(self):
        f = _protocol()["feature_contract"]
        assert f["n_features"] == 76
        assert len(f["feature_list"]) == 76
        assert len(set(f["feature_list"])) == 76
        assert _metadata()["n_features"] == 76

    def test_feature_order_matches_capture_schema(self):
        capture = DATA / "captures" / "adapt-v1-benign-002.csv"
        if not capture.exists():
            pytest.skip("adaptation capture not present")
        header = capture.read_text(encoding="utf-8").splitlines()[0].split(",")
        expected = [c for c in header if c not in IDENTITY_COLUMNS]
        assert _protocol()["feature_contract"]["feature_list"] == expected

    def test_deployment_schema_not_converted_to_model_a_contract(self):
        f = _protocol()["feature_contract"]
        assert f["no_conversion_to_model_a_schema"] is True
        assert f["extractor"] == {"name": "cicflowmeter", "version": "0.5.0"}
        assert f["schema_id"] == "deployment-cicflowmeter-76-v1"

    def test_no_train_fitted_feature_selection(self):
        assert "retained" in _protocol()["feature_contract"][
            "constant_feature_policy"]


class TestModelIdentity:

    def test_primary_model_identity_fixed_to_weighted_xgboost(self):
        p = _protocol()
        assert p["selection_and_freeze_rule"]["pre_declared_primary"] == PRIMARY_ID
        assert p["models"]["primary"]["id"] == PRIMARY_ID
        assert p["models"]["primary"]["algorithm"] == "xgboost.XGBClassifier"
        assert p["models"]["primary"]["class_weighting"] is True

    def test_primary_not_selected_post_hoc(self):
        assert _protocol()["selection_and_freeze_rule"][
            "post_hoc_selection_permitted"] is False
        m = _metadata()
        assert m["primary_model_id"] == PRIMARY_ID
        assert m["primary_selected_post_hoc"] is False

    def test_primary_stays_primary_even_if_another_model_scores_higher(self):
        results = _validation()["results"]
        best = max(results, key=lambda k: results[k]["macro_f1"])
        assert _metadata()["primary_model_id"] == PRIMARY_ID
        assert _metadata()["models"][PRIMARY_ID]["role"] == "PRIMARY"
        if best != PRIMARY_ID:
            assert _metadata()["models"][best]["role"] in ("ROBUSTNESS", "ABLATION")

    def test_exactly_three_pre_registered_models(self):
        m = _metadata()["models"]
        assert set(m) == {PRIMARY_ID, "model-b-rf-weighted-v1",
                          "model-b-xgb-unweighted-v1"}
        assert sorted(v["role"] for v in m.values()) == [
            "ABLATION", "PRIMARY", "ROBUSTNESS"]

    def test_no_broad_hyperparameter_optimisation(self):
        p = _protocol()["models"]
        assert p["broad_hyperparameter_optimisation"] is False
        assert p["no_additional_algorithms_after_validation"] is True


class TestArtefactsAndReproducibility:

    def test_hashes_recorded_for_every_model(self):
        for entry in _metadata()["models"].values():
            assert len(entry["artifact_sha256"]) == 64
            int(entry["artifact_sha256"], 16)

    def test_artifact_hash_matches_file_when_present(self):
        for entry in _metadata()["models"].values():
            path = ML / entry["artifact"]
            if not path.exists():
                continue
            assert hashlib.sha256(path.read_bytes()).hexdigest() == \
                entry["artifact_sha256"]

    def test_deterministic_training_with_fixed_seed(self):
        m = _metadata()
        assert m["seed"] == 42
        for entry in m["models"].values():
            assert entry["params"]["random_state"] == 42
        assert _protocol()["reproducibility"]["deterministic"] is True

    def test_environment_recorded(self):
        assert _metadata()["environment"] == _protocol()["reproducibility"][
            "environment"]


class TestPartitionIntegrity:

    def test_partition_counts_match_frozen_phase17b_manifest(self):
        p = DATA / "adaptation_manifest.json"
        if not p.exists():
            pytest.skip("adaptation manifest not built")
        frozen = {r["run_id"]: r for r in json.load(open(p, encoding="utf-8"))["runs"]}
        m = _metadata()
        for entry in m["train_partition"] + m["validation_partition"]:
            expected = frozen[entry["run_id"]]
            assert entry["total_flows"] == expected["total_flows"]
            assert entry["evaluable_flows"] == expected["evaluable_flows"]
            assert entry["attack_flows"] == expected["attack_flows"]
            assert entry["benign_flows"] == expected["benign_flows"]

    def test_validation_support_disclosed(self):
        v = _metadata()["validation_partition"]
        ssh = [e for e in v if e["run_id"] == "lab-v1-ssh-bruteforce-001"][0]
        assert ssh["attack_flows"] == 69

    def test_ssh_small_support_reported_per_scenario(self):
        for result in _validation()["results"].values():
            assert result["per_scenario"]["ssh"]["wilson_95"]["n"] == 69


class TestMetricsReporting:

    def test_every_model_reports_required_primary_metrics(self):
        for result in _validation()["results"].values():
            for key in ("macro_f1", "balanced_accuracy",
                        "attack_recall_detection_rate", "attack_precision",
                        "benign_false_positive_rate", "confusion_matrix"):
                assert result[key] is not None

    def test_per_scenario_wilson_intervals_present(self):
        for result in _validation()["results"].values():
            for scenario in ("benign", "portscan", "ssh"):
                w = result["per_scenario"][scenario]["wilson_95"]
                assert w["n"] > 0
                assert 0.0 <= w["low"] <= w["point"] <= w["high"] <= 1.0

    def test_confusion_matrix_totals_match_validation_support(self):
        counts = _metadata()["validation_class_counts"]
        for result in _validation()["results"].values():
            c = result["confusion_matrix"]
            assert c["true_benign_pred_benign"] + c["true_benign_pred_attack"] == \
                counts["BENIGN"]
            assert c["true_attack_pred_benign"] + c["true_attack_pred_attack"] == \
                counts["ATTACK"]

    def test_auc_reported_or_explicitly_unavailable(self):
        for result in _validation()["results"].values():
            for metric in ("roc_auc", "pr_auc"):
                if result[metric] is None:
                    assert result[f"{metric}_unavailable_reason"]
                else:
                    assert 0.0 <= result[metric] <= 1.0


class TestModelAUnchanged:

    def test_model_a_historical_values_preserved(self):
        assert _protocol()["model_comparison"][
            "frozen_model_a_historical_values"] == MODEL_A_HISTORICAL
        assert _validation()["frozen_model_a_historical"] == MODEL_A_HISTORICAL

    def test_model_a_not_retrained(self):
        assert _protocol()["intended_architecture"]["model_a_policy"] == \
            "Model A is never modified or retrained in Phase 17C"

    def test_multiclass_and_binary_macro_f1_not_equated(self):
        assert "must NOT be compared directly" in _protocol()["model_comparison"][
            "forbidden"]

    def test_model_b_not_described_as_model_a_replacement(self):
        assert "NOT a 15-class replacement" in _protocol()["objective"]["note"]
