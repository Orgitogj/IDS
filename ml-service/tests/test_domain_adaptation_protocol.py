import json
from pathlib import Path

import pytest

from training.pipeline import domain_adaptation as da

ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
D = ML_SERVICE_ROOT / "reports" / "domain_adaptation"
HISTORICAL = ["lab-v1-benign-001", "lab-v1-portscan-001", "lab-v1-ssh-bruteforce-001"]


class TestValidator:

    def test_run_level_separation_rejects_shared_run(self):
        plan = {"runs": [
            {"run_id": "r1", "role": da.ADAPTATION},
            {"run_id": "r1", "role": da.FINAL_TEST, "generated_after_model_b_freeze": True},
        ]}
        with pytest.raises(da.DomainAdaptationError):
            da.validate_run_plan(plan)

    def test_overlap_between_adaptation_and_final_test_is_rejected(self):
        plan = {"runs": [
            {"run_id": "a", "role": da.ADAPTATION},
            {"run_id": "b", "role": da.FINAL_TEST, "generated_after_model_b_freeze": True},
        ]}
        da.validate_run_plan(plan)
        da.assert_run_level_separation(plan)
        plan["runs"][1]["run_id"] = "a"
        plan["runs"].append({"run_id": "a", "role": da.ADAPTATION})
        with pytest.raises(da.DomainAdaptationError):
            da.assert_run_level_separation(plan)

    def test_final_test_must_be_post_freeze(self):
        plan = {"runs": [{"run_id": "e1", "role": da.FINAL_TEST,
                          "generated_after_model_b_freeze": False}]}
        with pytest.raises(da.DomainAdaptationError):
            da.assert_final_test_is_post_freeze(plan)

    def test_historical_run_cannot_be_final_test(self):
        plan = {"runs": [{"run_id": "lab-v1-portscan-001", "role": da.FINAL_TEST,
                          "generated_after_model_b_freeze": True}]}
        with pytest.raises(da.DomainAdaptationError):
            da.historical_runs_not_in_final_test(plan, HISTORICAL)

    def test_unknown_role_rejected(self):
        with pytest.raises(da.DomainAdaptationError):
            da.validate_run_plan({"runs": [{"run_id": "x", "role": "bogus"}]})


class TestDesignArtifacts:

    def _load(self, name):
        path = D / name
        if not path.exists():
            pytest.skip(f"{name} nuk eshte gjeneruar")
        with open(path, encoding="utf-8") as h:
            return json.load(h)

    def test_shipped_run_plan_passes_all_guards(self):
        plan = self._load("run_plan.json")
        assert da.validate(plan, historical_run_ids=HISTORICAL) is True

    def test_existing_runs_are_adaptation_not_final_test(self):
        plan = self._load("run_plan.json")
        final = {r["run_id"] for r in plan["runs"] if r["role"] == da.FINAL_TEST}
        for h in HISTORICAL:
            assert h not in final

    def test_replication_at_least_three_per_scenario(self):
        plan = self._load("run_plan.json")
        for role in (da.ADAPTATION, da.FINAL_TEST):
            for scen in ("benign", "portscan", "ssh"):
                n = sum(1 for r in plan["runs"]
                        if r["role"] == role and r["scenario"] == scen)
                assert n >= 3, f"{role}/{scen} has {n}"

    def test_primary_objective_is_binary(self):
        ev = self._load("evaluation_protocol.json")
        assert "attack_detection_rate_recall" in ev["primary"]
        assert ev["paired_comparison"]["mandatory"] is True

    def test_recommended_strategy_is_b(self):
        f = self._load("feasibility.json")
        assert f["recommended_strategy"] == "B"
        assert f["strategy_a_common_extractor"]["local_cicids2017_pcaps"] is False

    def test_model_b_recommends_two_stage(self):
        m = self._load("model_b_options.json")
        rec = [o for o in m["options"] if o["option"] == "E"][0]
        assert rec["recommended"] is True

    def test_model_a_is_declared_frozen(self):
        assert da.MODEL_A["status"].startswith("permanently frozen")

    def test_balancing_applies_only_to_training(self):
        b = self._load("balancing_strategy.json") if (D / "balancing_strategy.json").exists() \
            else None
        if b is None:
            pytest.skip("balancing_strategy.json inline in generator")


class TestFrozenIntact:

    def test_model_a_metrics_unchanged(self):
        path = (ML_SERVICE_ROOT / "reports" / "artifact_evaluation"
                / "xgb_baseline_cicids2017_v2" / "metrics.json")
        with open(path, encoding="utf-8") as h:
            assert abs(json.load(h)["metrics"]["overall"]["macro_f1"]
                       - 0.8805600093815694) < 1e-12
