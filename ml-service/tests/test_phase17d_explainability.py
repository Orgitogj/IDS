import hashlib
import json
from pathlib import Path

import pytest

ML = Path(__file__).resolve().parent.parent
if str(ML) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ML))

from app.services import llm_explainer
from training import phase17d_explain_run

LLM = ML / "reports" / "domain_adaptation" / "phase17d" / "llm_explainability"
MODEL_A_SHA = "2b7625fc32e5f9e066c3a7b356b8a606c9a1f26e5f2a8d1cc4b6fce4ff2fddfa"
MODEL_B_SHA = "c2bb8f0043eb2eb4c9a8d4639e41e86939675a2a0f1d40bf65c3e8ce181cb237"
GT_TOKENS = ("ground_truth", "groundtruth", "label", "expected", "truth")


def _protocol():
    p = LLM / "protocol.json"
    if not p.exists():
        pytest.skip("explainability protocol not written")
    return json.load(open(p, encoding="utf-8"))


def _evidence():
    p = LLM / "evidence_sample.json"
    if not p.exists():
        pytest.skip("evidence sample not built")
    return json.load(open(p, encoding="utf-8"))["packages"]


def _manifest():
    p = LLM / "sample_manifest.json"
    if not p.exists():
        pytest.skip("sample manifest not built")
    return json.load(open(p, encoding="utf-8"))


def _prompt_hash():
    blocks = "\n".join([llm_explainer.PROMPT_VERSION, llm_explainer.ROLE,
                        llm_explainer.EVIDENCE_BOUNDARY, llm_explainer.INVENTION_RULES,
                        llm_explainer.STYLE_RULES])
    return hashlib.sha256(blocks.encode("utf-8")).hexdigest()


class TestEvidenceContract:

    def test_required_fields_present(self):
        for pkg in _evidence():
            for key in ("alert_id", "source_run", "flow_index", "model", "decision",
                        "attack_probability", "shap_base_value", "top_shap_features",
                        "analyst_instruction"):
                assert key in pkg
            assert pkg["model"]["sha256"] == MODEL_B_SHA
            assert pkg["model"]["threshold"] == 0.50

    def test_top_k_is_five(self):
        for pkg in _evidence():
            assert len(pkg["top_shap_features"]) == 5
            for f in pkg["top_shap_features"]:
                assert set(f) == {"feature", "value", "shap_contribution", "direction"}
                assert f["direction"] in ("increases_attack", "decreases_attack")

    def test_no_ground_truth_leakage_in_evidence(self):
        for pkg in _evidence():
            blob = json.dumps(pkg).lower()
            for token in GT_TOKENS:
                assert token not in blob

    def test_direction_matches_sign(self):
        for pkg in _evidence():
            for f in pkg["top_shap_features"]:
                expected = "increases_attack" if f["shap_contribution"] > 0 \
                    else "decreases_attack"
                assert f["direction"] == expected


class TestSample:

    def test_size_and_strata(self):
        m = _manifest()
        assert m["n_total"] == 12
        assert m["n_benign_false_positive_alerts"] == 6
        assert m["n_true_positive_attack_alerts"] == 6
        assert m["seed"] == 42
        assert m["top_k"] == 5

    def test_strata_labels(self):
        strata = {it["stratum"] for it in _manifest()["items"]}
        assert strata == {"benign_false_positive_alert",
                          "correctly_detected_attack_alert"}

    def test_ground_truth_only_in_manifest(self):
        for it in _manifest()["items"]:
            assert it["ground_truth_binary"] in ("ATTACK", "BENIGN")

    def test_manifest_ids_match_evidence(self):
        ev_ids = {p["alert_id"] for p in _evidence()}
        mn_ids = {it["alert_id"] for it in _manifest()["items"]}
        assert ev_ids == mn_ids


class TestPromptAndProtocol:

    def test_prompt_version_v3(self):
        assert llm_explainer.PROMPT_VERSION == "v3"

    def test_prompt_template_hash_stable(self):
        assert _manifest()["prompt_template_sha256"] == _prompt_hash()
        assert _protocol()["prompt"]["template_sha256"] == _prompt_hash()

    def test_top_k_rule_frozen_at_five(self):
        assert _protocol()["shap"]["top_k"] == 5

    def test_provider_primary_is_claude(self):
        p = _protocol()["provider"]
        assert p["primary"] == "claude"
        assert p["primary_model"] == "claude-sonnet-5"
        assert p["real_calls_status"].startswith("NOT YET RUN")

    def test_h4_status_not_fully_tested(self):
        h = _protocol()["h4_status_rule"]
        assert h["current_status"] in ("not fully tested", "partially supported")
        assert h["not_supported_by_fluency_alone"] is True

    def test_human_results_absent(self):
        assert _protocol()["human_evaluation"]["real_results_exist"] is False


class TestFrozenModelsUnchanged:

    def test_model_hashes_unchanged(self):
        for rel, want in (("models/xgb_baseline_cicids2017_v2.joblib", MODEL_A_SHA),
                          ("models/model_b/model_b_xgb_weighted_v1.joblib", MODEL_B_SHA)):
            p = ML / rel
            if p.exists():
                assert hashlib.sha256(p.read_bytes()).hexdigest() == want

    def test_phase17d_seal_unchanged(self):
        seal = ML / "reports/domain_adaptation/phase17d/data/final_test_seal.json"
        if not seal.exists():
            pytest.skip("phase 17d seal absent")
        d = json.load(open(seal, encoding="utf-8"))
        assert d["manifest_sha256"] == \
            "c6914dd0de90922193c26429becccd966efcd235d886a77c2e2b469686c160c1"


class TestNoRealLLMByDefault:

    def test_batch_runner_dry_run_makes_no_calls(self, monkeypatch):
        def boom(*a, **k):
            raise AssertionError("no real LLM call must occur in the default suite")
        monkeypatch.setattr(llm_explainer, "_generate_with_claude", boom)
        result = phase17d_explain_run.run("claude", ("with_shap", "no_shap"), go=False)
        assert result["dry_run"] is True
        assert result["planned_calls"] == 24


class TestProviderAmendment:

    def _amendment(self):
        p = LLM / "PROVIDER_AMENDMENT.json"
        if not p.exists():
            pytest.skip("provider amendment not written")
        return json.load(open(p, encoding="utf-8"))

    def test_final_provider_is_claude(self):
        a = self._amendment()
        assert a["final_h4_provider"] == "claude"
        assert a["amends"] == "phase17d-explainability-v1"
        assert a["no_provider_mixing"] is True

    def test_amendment_preserves_frozen_invariants(self):
        u = self._amendment()["unchanged_and_reaffirmed"]
        assert u["model_b_sha256"] == MODEL_B_SHA
        assert u["model_b_threshold"] == 0.50
        assert u["top_k_shap"] == 5
        assert u["sample_seed"] == 42
        assert u["prompt_template_sha256"] == _prompt_hash()

    def test_requested_claude_model_is_sonnet_5(self):
        assert self._amendment()["provider_freeze"]["requested_claude_model"] == \
            "claude-sonnet-5"
        assert llm_explainer._generate_with_claude.__name__ == "_generate_with_claude"


class TestNoProviderMixing:

    def test_runner_is_claude_only(self):
        assert set(phase17d_explain_run.FILES) == {"claude"}
        assert set(phase17d_explain_run.REQUESTED_MODEL) == {"claude"}
        assert phase17d_explain_run.REQUESTED_MODEL["claude"] == "claude-sonnet-5"

    def test_claude_final_files_are_claude_only_when_present(self):
        p = LLM / "explanation_runs_claude.json"
        if not p.exists():
            pytest.skip("claude batch not run yet")
        d = json.load(open(p, encoding="utf-8"))
        assert {r["provider"] for r in d["records"]} == {"claude"}
        assert len(d["records"]) == 24
