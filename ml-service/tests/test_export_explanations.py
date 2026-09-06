import csv
import json

import pytest

from training import export_explanations as export


class StubReader:

    def __init__(self, alarms, flows, explanations, fail_on=None):
        self._alarms = alarms
        self._flows = flows
        self._explanations = explanations
        self._fail_on = fail_on or {}
        self.calls = []

    def alarms(self):
        self.calls.append("alarms")
        return self._alarms

    def flow(self, flow_id):
        self.calls.append(f"flow:{flow_id}")
        if self._fail_on.get("flow") == flow_id:
            raise RuntimeError("flow unavailable")
        return self._flows[flow_id]

    def explanations(self, alarm_id):
        self.calls.append(f"explanations:{alarm_id}")
        if self._fail_on.get("explanations") == alarm_id:
            raise RuntimeError("explanations unavailable")
        return self._explanations.get(alarm_id, [])


def flow_payload(**overrides):
    payload = {
        "id": "flow-1",
        "featureVector": {"Destination Port": 443.0, "Flow Duration": 1200.0},
        "label": "ATTACK",
        "groundTruthAttackType": "PortScan",
        "predictedLabel": "ATTACK",
        "attackType": "PortScan",
        "detectionMethod": "SUPERVISED_ML",
        "predictionConfidence": 0.96,
        "anomalyScore": None,
        "modelName": "xgb-smote-top50features-v1",
        "modelVersion": "1.0",
        "featureVersion": "cicids2017-top50-v1",
    }
    payload.update(overrides)
    return payload


def explanation_payload(**overrides):
    payload = {
        "id": "exp-1",
        "explanationText": "Modeli e klasifikoi kete rrjedhe si PortScan.",
        "llmModel": "gemini-flash-latest",
        "llmPromptVersion": "v3",
        "generationLatencyMs": 812.0,
        "rating": "HELPFUL",
        "ratedAt": "2026-09-06T10:00:00Z",
        "generatedAt": "2026-09-06T09:59:00Z",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def reader():
    alarms = [{"id": "alarm-1", "networkFlowId": "flow-1", "severity": "CRITICAL",
               "status": "NEW"}]
    return StubReader(alarms, {"flow-1": flow_payload()},
                      {"alarm-1": [explanation_payload()]})


def fake_predictor(feature_vector, model_id=None):
    return {
        "top_shap_features": [
            {"feature": "Destination Port", "value": 443.0, "shap_contribution": 0.81},
            {"feature": "Flow Duration", "value": 1200.0, "shap_contribution": -0.42},
        ],
        "top_anomaly_features": None,
    }


class TestRowConstruction:

    def test_every_h4_field_is_present(self, reader):
        rows, _ = export.build_rows(reader, predictor=fake_predictor)

        assert len(rows) == 1
        row = rows[0]

        for field in ("alarm_id", "ground_truth_attack_type", "attack_type", "confidence",
                      "provider", "llm_model", "llm_prompt_version",
                      "generation_latency_ms", "rating", "explanation_text"):
            assert field in row

        assert row["alarm_id"] == "alarm-1"
        assert row["ground_truth_attack_type"] == "PortScan"
        assert row["confidence"] == 0.96
        assert row["llm_prompt_version"] == "v3"
        assert row["rating"] == "HELPFUL"

    def test_shap_evidence_is_reconstructed_and_attached(self, reader):
        rows, _ = export.build_rows(reader, predictor=fake_predictor)

        assert rows[0]["shap_feature_count"] == 2
        assert rows[0]["shap_evidence"][0]["feature"] == "Destination Port"

    def test_the_provider_is_derived_from_the_model_name(self):
        assert export.provider_for("gemini-flash-latest") == "gemini"
        assert export.provider_for("claude-sonnet-5") == "claude"
        assert export.provider_for("something-else") is None
        assert export.provider_for(None) is None

    def test_alarms_without_explanations_are_skipped_silently(self):
        reader = StubReader([{"id": "a", "networkFlowId": "f"}], {"f": flow_payload()}, {})
        rows, skipped = export.build_rows(reader)

        assert rows == []
        assert skipped == []

    def test_each_explanation_becomes_its_own_row(self):
        alarms = [{"id": "alarm-1", "networkFlowId": "flow-1"}]
        explanations = {"alarm-1": [
            explanation_payload(id="exp-1", llmModel="gemini-flash-latest"),
            explanation_payload(id="exp-2", llmModel="claude-sonnet-5"),
        ]}
        reader = StubReader(alarms, {"flow-1": flow_payload()}, explanations)

        rows, _ = export.build_rows(reader, predictor=fake_predictor)

        assert len(rows) == 2
        assert {row["provider"] for row in rows} == {"gemini", "claude"}

    def test_the_limit_is_applied_to_alarms(self):
        alarms = [{"id": f"alarm-{i}", "networkFlowId": "flow-1"} for i in range(5)]
        explanations = {f"alarm-{i}": [explanation_payload()] for i in range(5)}
        reader = StubReader(alarms, {"flow-1": flow_payload()}, explanations)

        rows, _ = export.build_rows(reader, limit=2)

        assert len(rows) == 2


class TestGroundednessInTheExport:

    def test_a_clean_explanation_is_not_flagged(self, reader):
        rows, _ = export.build_rows(reader, predictor=fake_predictor)

        assert rows[0]["groundedness_grounded"] is True
        assert rows[0]["groundedness_finding_count"] == 0

    def test_a_hallucinated_address_is_flagged(self):
        alarms = [{"id": "alarm-1", "networkFlowId": "flow-1"}]
        explanations = {"alarm-1": [explanation_payload(
            explanationText="Hosti 192.168.1.50 skanoi rrjetin.")]}
        reader = StubReader(alarms, {"flow-1": flow_payload()}, explanations)

        rows, _ = export.build_rows(reader, predictor=fake_predictor)

        assert rows[0]["groundedness_grounded"] is False
        assert rows[0]["groundedness_high_severity_count"] == 1

    def test_evidence_numbers_are_not_flagged(self):
        alarms = [{"id": "alarm-1", "networkFlowId": "flow-1"}]
        explanations = {"alarm-1": [explanation_payload(
            explanationText="Porta 443 dhe kohezgjatja 1200 ishin vendimtare.")]}
        reader = StubReader(alarms, {"flow-1": flow_payload()}, explanations)

        rows, _ = export.build_rows(reader, predictor=fake_predictor)

        assert rows[0]["groundedness_grounded"] is True


class TestFailureHandling:

    def test_a_missing_predictor_is_recorded_not_fatal(self, reader):
        rows, skipped = export.build_rows(reader, predictor=None)

        assert len(rows) == 1
        assert rows[0]["shap_feature_count"] == 0
        assert skipped == []

    def test_a_failing_prediction_is_recorded_and_the_row_survives(self, reader):
        def broken(feature_vector, model_id=None):
            raise RuntimeError("model unavailable")

        rows, skipped = export.build_rows(reader, predictor=broken)

        assert len(rows) == 1
        assert skipped and "prediction failed" in skipped[0]["reason"]

    def test_a_flow_without_a_feature_vector_is_recorded(self):
        alarms = [{"id": "alarm-1", "networkFlowId": "flow-1"}]
        reader = StubReader(alarms, {"flow-1": flow_payload(featureVector=None)},
                            {"alarm-1": [explanation_payload()]})

        rows, skipped = export.build_rows(reader, predictor=fake_predictor)

        assert len(rows) == 1
        assert skipped[0]["reason"] == "flow carries no feature vector"

    def test_an_unreachable_flow_does_not_lose_the_explanation(self):
        alarms = [{"id": "alarm-1", "networkFlowId": "flow-1"}]
        reader = StubReader(alarms, {"flow-1": flow_payload()},
                            {"alarm-1": [explanation_payload()]},
                            fail_on={"flow": "flow-1"})

        rows, skipped = export.build_rows(reader, predictor=fake_predictor)

        assert len(rows) == 1
        assert any("flow:" in entry["reason"] for entry in skipped)


class TestSummaryAndOutputs:

    def test_the_summary_groups_by_provider_and_prompt_version(self):
        rows = [
            {"provider": "gemini", "rating": "HELPFUL", "generation_latency_ms": 800.0,
             "groundedness_grounded": True, "llm_prompt_version": "v3"},
            {"provider": "claude", "rating": None, "generation_latency_ms": 1200.0,
             "groundedness_grounded": False, "llm_prompt_version": "v3"},
            {"provider": "gemini", "rating": "INCORRECT", "generation_latency_ms": 400.0,
             "groundedness_grounded": True, "llm_prompt_version": "v2"},
        ]
        summary = export.summarise(rows)

        assert summary["explanations"] == 3
        assert summary["flagged_by_groundedness_heuristic"] == 1
        assert summary["by_provider"]["gemini"]["explanations"] == 2
        assert summary["by_provider"]["gemini"]["rated"] == 2
        assert summary["by_provider"]["gemini"]["mean_latency_ms"] == 600.0
        assert summary["by_provider"]["claude"]["flagged"] == 1
        assert summary["by_prompt_version"] == {"v3": 2, "v2": 1}
        assert summary["ratings"] == {"HELPFUL": 1, "INCORRECT": 1}

    def test_csv_jsonl_and_summary_are_written(self, tmp_path, reader):
        rows, skipped = export.build_rows(reader, predictor=fake_predictor)
        paths = export.write_outputs(rows, skipped, tmp_path)

        assert paths["csv"].exists()
        assert paths["jsonl"].exists()
        assert paths["summary"].exists()

        with open(paths["csv"], encoding="utf-8", newline="") as handle:
            written = list(csv.DictReader(handle))
        assert len(written) == 1
        assert written[0]["alarm_id"] == "alarm-1"
        assert list(written[0]) == export.CSV_COLUMNS

        with open(paths["jsonl"], encoding="utf-8") as handle:
            record = json.loads(handle.readline())
        assert record["shap_evidence"][0]["feature"] == "Destination Port"

        with open(paths["summary"], encoding="utf-8") as handle:
            summary = json.load(handle)
        assert summary["summary"]["explanations"] == 1
        assert "not" in summary["groundedness_caveat"].lower()

    def test_the_csv_stays_flat_while_the_jsonl_keeps_the_evidence(self, tmp_path,
                                                                   reader):
        rows, skipped = export.build_rows(reader, predictor=fake_predictor)
        paths = export.write_outputs(rows, skipped, tmp_path)

        with open(paths["csv"], encoding="utf-8", newline="") as handle:
            written = list(csv.DictReader(handle))

        assert "shap_evidence" not in written[0]
        assert "groundedness" not in written[0]
