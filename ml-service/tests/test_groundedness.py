import pytest

from app.services import groundedness as g


def shap_features():
    return [
        {"feature": "Destination Port", "value": 443.0, "shap_contribution": 0.812},
        {"feature": "Flow Duration", "value": 1200.0, "shap_contribution": -0.421},
        {"feature": "Total Fwd Packets", "value": 9.0, "shap_contribution": 0.115},
    ]


def anomaly_features():
    return [
        {"feature": "Idle Max", "value": 98000000.0, "baseline_value": 0.0,
         "anomaly_contribution": 0.0731},
    ]


@pytest.fixture
def evidence():
    return g.Evidence(predicted_label="PortScan", confidence=0.96,
                      shap_features=shap_features())


class TestHallucinatedEntities:

    def test_an_ipv4_address_is_flagged_as_high_severity(self, evidence):
        result = g.check("Hosti 192.168.1.50 dergoi trafik te vazhdueshem.", evidence)

        assert result["grounded"] is False
        assert result["high_severity_count"] == 1
        assert result["findings"][0]["kind"] == g.FINDING_IP_ADDRESS
        assert result["findings"][0]["matched"] == "192.168.1.50"

    def test_several_addresses_are_each_flagged(self, evidence):
        result = g.check("Nga 10.0.0.7 drejt 10.0.0.9 kishte trafik.", evidence)

        assert result["finding_count"] == 2

    def test_an_ipv6_address_is_flagged(self, evidence):
        result = g.check("Burimi ishte fe80::1ff:fe23:4567:890a sipas analizes.", evidence)

        assert any(finding["kind"] == g.FINDING_IP_ADDRESS
                   for finding in result["findings"])

    @pytest.mark.parametrize("text", [
        "Payload permban nje varg te dyshimte.",
        "Permbajtja e paketave tregon komanda te huaja.",
        "Nje exploit code u identifikua brenda rrjedhes.",
    ])
    def test_packet_content_claims_are_flagged(self, evidence, text):
        result = g.check(text, evidence)

        assert result["grounded"] is False
        assert any(finding["kind"] == g.FINDING_PAYLOAD_CLAIM
                   for finding in result["findings"])
        assert result["high_severity_count"] >= 1

    def test_a_protocol_absent_from_the_evidence_is_flagged(self, evidence):
        result = g.check("Trafiku duket si HTTPS i enkriptuar.", evidence)

        assert any(finding["kind"] == g.FINDING_PROTOCOL_NOT_IN_EVIDENCE
                   for finding in result["findings"])

    def test_a_protocol_is_reported_once_not_per_occurrence(self, evidence):
        result = g.check("DNS, dhe perseri DNS, dhe DNS.", evidence)

        protocol_findings = [finding for finding in result["findings"]
                             if finding["kind"] == g.FINDING_PROTOCOL_NOT_IN_EVIDENCE]
        assert len(protocol_findings) == 1


class TestGroundedContentIsNotFlagged:

    def test_a_clean_explanation_passes(self, evidence):
        text = ("Modeli e klasifikoi kete rrjedhe si PortScan. Destination Port dhe Flow "
                "Duration ishin matjet me ndikuese. Kerkohet verifikim nga analisti.")

        assert g.check(text, evidence)["grounded"] is True

    def test_a_port_present_in_the_evidence_is_not_flagged(self, evidence):
        result = g.check("Trafiku shkoi drejt portes 443 ne menyre te perseritur.",
                         evidence)

        assert result["grounded"] is True

    def test_a_port_absent_from_the_evidence_is_flagged(self, evidence):
        result = g.check("Trafiku shkoi drejt portes 8080 ne menyre te perseritur.",
                         evidence)

        assert any(finding["kind"] == g.FINDING_PORT_NOT_IN_EVIDENCE
                   for finding in result["findings"])

    def test_bare_numbers_from_the_evidence_are_never_flagged(self, evidence):
        text = ("Kontributi 0.812 dhe kohezgjatja 1200 jane vlerat kryesore; "
                "9 pako u derguan perpara dhe 3 features u shqyrtuan.")

        assert g.check(text, evidence)["grounded"] is True

    def test_numbers_outside_a_port_context_are_not_treated_as_ports(self, evidence):
        text = "Rrjedha zgjati 8080 mikrosekonda sipas matjes."

        assert g.check(text, evidence)["grounded"] is True

    def test_a_feature_value_written_with_decimals_still_matches(self, evidence):
        result = g.check("Porta 443.0 u perdor.", evidence)

        assert result["grounded"] is True

    def test_a_protocol_named_by_a_feature_is_not_flagged(self):
        evidence = g.Evidence(
            predicted_label="BENIGN",
            shap_features=[{"feature": "DNS Query Count", "value": 4.0,
                            "shap_contribution": 0.2}])

        assert g.check("Numri i kerkesave DNS ishte i larte.", evidence)["grounded"] is True

    def test_an_empty_explanation_is_grounded_by_default(self, evidence):
        assert g.check("", evidence)["grounded"] is True
        assert g.check(None, evidence)["grounded"] is True


class TestEvidenceConstruction:

    def test_anomaly_features_contribute_names_and_numbers(self):
        evidence = g.Evidence(anomaly_features=anomaly_features())

        assert evidence.mentions_term("Idle Max")
        assert evidence.mentions_number(98000000.0)
        assert evidence.mentions_number(0.0731)

    def test_confidence_is_available_as_both_fraction_and_percent(self):
        evidence = g.Evidence(confidence=0.96)

        assert evidence.mentions_number(0.96)
        assert evidence.mentions_number(96.0)

    def test_evidence_is_built_from_a_prediction_payload(self):
        prediction = {
            "prediction": "DDoS",
            "confidence": 0.91,
            "top_shap_features": shap_features(),
            "top_anomaly_features": None,
            "anomaly_score": None,
        }
        evidence = g.evidence_from_prediction(prediction)

        assert evidence.predicted_label == "DDoS"
        assert evidence.mentions_term("Flow Duration")
        assert evidence.mentions_number(443.0)

    def test_a_prediction_without_shap_still_builds(self):
        evidence = g.evidence_from_prediction({"prediction": "BENIGN"})

        assert evidence.feature_names == []
        assert g.check("Nuk ka evidence.", evidence)["grounded"] is True


class TestReportShape:

    def test_the_report_declares_its_method_and_its_limits(self, evidence):
        result = g.check("Trafik normal.", evidence)

        assert result["method"] == "deterministic_heuristic_v1"
        assert "not" in result["caveat"].lower()
        assert "semantically correct" in result["caveat"]

    def test_every_finding_carries_kind_severity_match_and_detail(self, evidence):
        result = g.check("Hosti 192.168.1.50 me payload te dyshimte drejt portes 8080.",
                         evidence)

        assert result["finding_count"] >= 3
        for finding in result["findings"]:
            assert set(finding) == {"kind", "severity", "matched", "detail"}
            assert finding["severity"] in (g.SEVERITY_HIGH, g.SEVERITY_MEDIUM)
            assert finding["matched"]
            assert finding["detail"]

    def test_counts_agree_with_the_findings_list(self, evidence):
        result = g.check("Hosti 10.1.1.1 dhe porta 9999 dhe HTTP.", evidence)

        assert result["finding_count"] == len(result["findings"])
        assert result["high_severity_count"] == sum(
            1 for finding in result["findings"]
            if finding["severity"] == g.SEVERITY_HIGH)
