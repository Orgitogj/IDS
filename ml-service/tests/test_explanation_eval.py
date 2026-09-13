from app.services import explanation_eval as ee


def package(decision="ATTACK", features=None):
    return {
        "alert_id": "run#1",
        "decision": decision,
        "attack_probability": 0.95,
        "top_shap_features": features if features is not None else [
            {"feature": "flow_duration", "value": 1200.0,
             "shap_contribution": 0.8, "direction": "increases_attack"},
            {"feature": "totlen_fwd_pkts", "value": 2249.0,
             "shap_contribution": -0.5, "direction": "decreases_attack"},
        ],
    }


class TestPredictionConsistency:

    def test_states_the_decision(self):
        r = ee.prediction_consistency("Modeli e klasifikoi si ATTACK.", "ATTACK")
        assert r["consistent"] is True
        assert r["decision_mentioned"] is True

    def test_missing_decision_is_inconsistent(self):
        r = ee.prediction_consistency("Ky flow duket i zakonshem.", "ATTACK")
        assert r["consistent"] is False


class TestFeatureGrounding:

    def test_supplied_features_are_counted(self):
        ev = ee.groundedness.Evidence(shap_features=package()["top_shap_features"])
        r = ee.feature_grounding("flow_duration ishte e larte.", ev)
        assert "flow_duration" in r["referenced_supplied_features"]

    def test_number_not_in_evidence_is_flagged(self):
        ev = ee.groundedness.Evidence(shap_features=package()["top_shap_features"])
        r = ee.feature_grounding("Ishin 99999 pakete ne kete flow.", ev)
        assert r["numbers_not_in_evidence_count"] >= 1


class TestDirectionConsistency:

    def test_consistent_increase_claim(self):
        pkg = package(features=[{"feature": "flow_duration", "value": 1.0,
                                 "shap_contribution": 0.8,
                                 "direction": "increases_attack"}])
        text = "Matja flow_duration e rriti gjasat drejt sulmit."
        r = ee.direction_consistency(text, pkg["top_shap_features"])
        assert r["checked_claims"] == 1
        assert r["consistent_claims"] == 1

    def test_inconsistent_claim_detected(self):
        pkg = package(features=[{"feature": "flow_duration", "value": 1.0,
                                 "shap_contribution": 0.8,
                                 "direction": "increases_attack"}])
        text = "Matja flow_duration e uli gjasat e sulmit."
        r = ee.direction_consistency(text, pkg["top_shap_features"])
        assert r["checked_claims"] == 1
        assert r["inconsistent_claims"] == 1


class TestEvidenceCoverage:

    def test_coverage_ratio(self):
        r = ee.evidence_coverage("flow_duration u rrit.", package()["top_shap_features"])
        assert r["top_k"] == 2
        assert r["covered"] == 1
        assert abs(r["coverage_ratio"] - 0.5) < 1e-9


class TestStructuralCompleteness:

    def test_all_fields_present(self):
        text = ("Modeli e klasifikoi si ATTACK bazuar te matjet e flow-it; "
                "rekomandohet verifikim nga analisti.")
        r = ee.structural_completeness(text, "ATTACK")
        assert r["all_present"] is True

    def test_missing_uncertainty_is_incomplete(self):
        r = ee.structural_completeness("ATTACK sipas matjeve.", "ATTACK")
        assert r["all_present"] is False


class TestEvaluateAndAggregate:

    def test_grounded_explanation(self):
        text = ("Modeli e klasifikoi kete flow si ATTACK; matja flow_duration e rriti "
                "vleresimin drejt sulmit. Rekomandohet verifikim nga analisti.")
        r = ee.evaluate(text, package())
        assert r["prediction_consistency"]["consistent"] is True
        assert r["unsupported_claims"]["grounded"] is True
        assert r["structural_completeness"]["all_present"] is True

    def test_ungrounded_explanation_is_flagged(self):
        text = ("Hosti 10.0.0.5 dergoi payload keqdashes ne portin 4444; "
                "sulm i konfirmuar.")
        r = ee.evaluate(text, package())
        assert r["unsupported_claims"]["grounded"] is False
        assert r["unsupported_claims"]["finding_count"] >= 2

    def test_aggregate_shapes(self):
        good = ee.evaluate("Modeli e klasifikoi si ATTACK; flow_duration; verifikim "
                           "nga analisti.", package())
        agg = ee.aggregate([good])
        assert agg["n"] == 1
        assert 0.0 <= agg["prediction_consistency_rate"] <= 1.0
