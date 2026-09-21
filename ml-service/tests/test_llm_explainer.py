import re

import pytest

from app.ml.detection_engine import METHOD_ANOMALY, METHOD_SUPERVISED
from app.services import llm_explainer
from app.services.llm_explainer import (
    PROMPT_VERSION,
    _build_prompt,
    generate_explanation,
)

CICIDS2017_ATTACK_NAMES = [
    r"DoS",
    r"DDoS",
    r"Hulk",
    r"GoldenEye",
    r"Slowhttptest",
    r"slowloris",
    r"PortScan",
    r"port ?scan",
    r"skanim i porteve",
    r"Patator",
    r"FTP",
    r"SSH",
    r"brute[ -]?force",
    r"force bruto",
    r"bot",
    r"botnet",
    r"Heartbleed",
    r"Infiltration",
    r"infiltrim",
    r"SQL",
    r"XSS",
    r"cross[ -]site",
    r"web attack",
]

FORBIDDEN = [re.compile(rf"\b{pattern}\b", re.IGNORECASE) for pattern in CICIDS2017_ATTACK_NAMES]


def attack_names_in(text):
    return sorted({match.group(0) for pattern in FORBIDDEN for match in pattern.finditer(text)})


def shap_features():
    return [
        {"feature": "Flow Duration", "value": 1200.0, "shap_contribution": 0.81},
        {"feature": "Total Fwd Packets", "value": 9.0, "shap_contribution": -0.42},
    ]


def anomaly_features():
    return [
        {"feature": "Idle Max", "value": 98_000_000.0, "baseline_value": 0.0,
         "anomaly_contribution": 0.0731},
        {"feature": "Init_Win_bytes_forward", "value": 65535.0, "baseline_value": 256.0,
         "anomaly_contribution": 0.0412},
        {"feature": "Flow IAT Std", "value": 4_120_000.0, "baseline_value": 1350.0,
         "anomaly_contribution": -0.0188},
    ]


def test_the_prompt_version_is_v3():
    assert PROMPT_VERSION == "v3"


def test_the_anomaly_template_is_chosen_by_detection_method():
    prompt = _build_prompt("UNKNOWN", None, shap_features(),
                           detection_method=METHOD_ANOMALY,
                           top_anomaly_features=anomaly_features())
    assert "detektori i anomalive" in prompt
    assert "CICIDS2017" in prompt


def test_the_supervised_template_is_chosen_by_detection_method_not_by_label():
    prompt = _build_prompt("UNKNOWN", 0.42, shap_features(),
                           detection_method=METHOD_SUPERVISED,
                           top_anomaly_features=anomaly_features())
    assert "Modeli ML klasifikoi kete flow trafiku si: UNKNOWN" in prompt
    assert "detektori i anomalive" not in prompt


def test_a_named_attack_keeps_the_supervised_template():
    prompt = _build_prompt("PortScan", 0.96, shap_features(),
                           detection_method=METHOD_SUPERVISED)
    assert "Modeli ML klasifikoi kete flow trafiku si: PortScan" in prompt
    assert "kontribut SHAP" in prompt


def test_a_missing_detection_method_falls_back_to_the_supervised_template():
    prompt = _build_prompt("DDoS", 0.88, shap_features())
    assert "Modeli ML klasifikoi kete flow trafiku si: DDoS" in prompt


def test_the_anomaly_prompt_carries_isolation_forest_evidence_not_shap():
    prompt = _build_prompt("UNKNOWN", None, shap_features(),
                           detection_method=METHOD_ANOMALY,
                           top_anomaly_features=anomaly_features())
    assert "Isolation Forest" in prompt
    assert "kontribut SHAP" not in prompt
    assert "Idle Max" in prompt
    assert "Flow Duration" not in prompt


def test_the_anomaly_prompt_reports_the_normal_baseline_for_every_feature():
    prompt = _build_prompt("UNKNOWN", None, None,
                           detection_method=METHOD_ANOMALY,
                           top_anomaly_features=anomaly_features())
    assert prompt.count("tipike per trafikun normal=") == len(anomaly_features())


def test_the_anomaly_prompt_forbids_naming_an_attack_type():
    prompt = _build_prompt("UNKNOWN", None, None,
                           detection_method=METHOD_ANOMALY,
                           top_anomaly_features=anomaly_features())
    assert "MOS emerto asnje lloj sulmi konkret" in prompt
    assert "NUK e lidh dot me nje lloj sulmi te njohur" in prompt


def test_the_anomaly_prompt_survives_missing_attribution():
    prompt = _build_prompt("UNKNOWN", None, shap_features(),
                           detection_method=METHOD_ANOMALY,
                           top_anomaly_features=None)
    assert "nuk arriti te nxjerre features konkrete" in prompt
    assert "kontribut SHAP" not in prompt


def test_the_anomaly_prompt_includes_the_anomaly_score_when_present():
    prompt = _build_prompt("UNKNOWN", None, None,
                           detection_method=METHOD_ANOMALY,
                           top_anomaly_features=anomaly_features(),
                           anomaly_score=0.993)
    assert "Rezultati i anomalise: 0.993" in prompt


def test_the_anomaly_prompt_names_no_cicids2017_attack_class(monkeypatch):
    prompt = _build_prompt("UNKNOWN", None, shap_features(),
                           detection_method=METHOD_ANOMALY,
                           top_anomaly_features=anomaly_features())
    assert attack_names_in(prompt) == []


def test_the_forbidden_name_detector_actually_detects(monkeypatch):
    assert attack_names_in("Ky flow duket si nje sulm DDoS klasik.") == ["DDoS"]
    assert attack_names_in("Trafiku eshte i pazakonte por i pashpjegueshem.") == []


def test_the_generated_explanation_records_the_prompt_version(monkeypatch):
    captured = {}

    def fake_claude(prompt):
        captured["prompt"] = prompt
        return "Sistemi vuri re sjellje te pazakonte qe nuk perputhet me profilin normal.", "stub"

    monkeypatch.setattr(llm_explainer, "_generate_with_claude", fake_claude)

    result = generate_explanation("UNKNOWN", None, shap_features(),
                                  detection_method=METHOD_ANOMALY,
                                  top_anomaly_features=anomaly_features(),
                                  anomaly_score=0.991)

    assert result["llm_prompt_version"] == "v3"
    assert "detektori i anomalive" in captured["prompt"]
    assert attack_names_in(result["explanation_text"]) == []


@pytest.mark.llm
def test_a_live_explanation_for_a_suspicious_alarm_names_no_attack_class():
    try:
        result = generate_explanation(
            predicted_label="UNKNOWN",
            confidence=None,
            top_shap_features=shap_features(),
            detection_method=METHOD_ANOMALY,
            top_anomaly_features=anomaly_features(),
            anomaly_score=0.993,
        )
    except Exception as error:
        if "503" in str(error) or "429" in str(error) or "UNAVAILABLE" in str(error):
            pytest.skip(f"ofruesi LLM i padisponueshem perkohesisht: {error}")
        raise

    text = result["explanation_text"]
    assert result["llm_prompt_version"] == "v3"
    assert text.strip()
    assert attack_names_in(text) == [], f"shpjegimi emertoi nje klase sulmi: {text}"


GROUNDING_MARKERS = [
    "NUK e ke pare vete trafikun",
    "Nuk ke akses te paketat",
    "Mos permend adresa IP",
    "Mos pershkruaj permbajtje paketash",
    "Mos shto teknika",
    "E vetmja evidence qe ke eshte ajo e listuar",
]


def supervised_prompt(label="PortScan", confidence=0.96, features=None):
    return _build_prompt(label, confidence,
                         shap_features() if features is None else features,
                         detection_method=METHOD_SUPERVISED)


def anomaly_prompt():
    return _build_prompt("UNKNOWN", None, shap_features(),
                         detection_method=METHOD_ANOMALY,
                         top_anomaly_features=anomaly_features())


@pytest.mark.parametrize("marker", GROUNDING_MARKERS)
def test_the_supervised_prompt_carries_every_grounding_rule(marker):
    assert marker in supervised_prompt()


@pytest.mark.parametrize("marker", GROUNDING_MARKERS)
def test_the_anomaly_prompt_keeps_every_grounding_rule(marker):
    assert marker in anomaly_prompt()


def test_the_supervised_prompt_separates_prediction_from_proven_fact():
    prompt = supervised_prompt("DDoS", 0.88)
    assert "JO fakt i provuar" in prompt
    assert 'modeli e klasifikoi si DDoS' in prompt
    assert 'kurrsesi "kjo rrjedhe ishte DDoS"' in prompt
    assert "eshte provuar se ishte DDoS" in prompt


def test_the_supervised_prompt_frames_confidence_as_model_confidence():
    prompt = supervised_prompt("DDoS", 0.88)
    assert "Besueshmeria eshte siguria e modelit ne klasen qe zgjodhi" in prompt
    assert "NUK eshte probabiliteti qe sulmi ka ndodhur vertet" in prompt
    assert "nuk eshte matje rreziku" in prompt


def test_low_confidence_asks_for_more_cautious_wording():
    prompt = supervised_prompt("Bot", 0.42)
    assert "Sa me e ulet te jete, aq me te kujdesshme" in prompt
    assert "42.0%" in prompt


def test_the_supervised_prompt_states_shap_is_not_causal():
    prompt = supervised_prompt()
    assert "SHAP shpjegon vendimin e modelit, NUK provon shkakun real" in prompt
    assert "mos e paraqit si lidhje shkakesore" in prompt


def test_the_anomaly_prompt_states_attribution_is_not_causal():
    prompt = anomaly_prompt()
    assert "Eshte atribuim statistikor i vendimit te modelit, jo shkak i provuar" in prompt


def test_the_supervised_prompt_distinguishes_measured_value_from_contribution():
    prompt = supervised_prompt()
    assert "vlera e matur=" in prompt
    assert "kontribut SHAP=" in prompt
    assert "Vlera e matur eshte matja reale e flow-it" in prompt
    assert "Kontributi SHAP eshte sa e shtyu ajo matje modelin" in prompt


def test_shap_contributions_keep_their_sign():
    prompt = supervised_prompt()
    assert "kontribut SHAP=+0.810" in prompt
    assert "kontribut SHAP=-0.420" in prompt


def test_no_bias_term_reaches_the_prompt():
    prompt = supervised_prompt()
    for forbidden in ("bias", "BIAS", "base_value", "expected_value", "intercept"):
        assert forbidden not in prompt


def test_the_supervised_prompt_survives_missing_shap_evidence():
    prompt = supervised_prompt(features=[])
    assert "Sistemi nuk dha kontribute features" in prompt
    assert "Modeli ML klasifikoi kete flow trafiku si: PortScan" in prompt


def test_a_missing_confidence_is_stated_not_invented():
    prompt = supervised_prompt("PortScan", None)
    assert "e padisponueshme" in prompt


def test_the_supervised_prompt_asks_for_albanian_and_a_length_budget():
    prompt = supervised_prompt()
    assert "ne shqip te qarte, 3-5 fjali" in prompt
    assert "mund te mbeten ne anglisht" in prompt


def test_both_templates_share_the_same_style_and_invention_rules():
    supervised = supervised_prompt()
    anomaly = anomaly_prompt()
    assert llm_explainer.STYLE_RULES in supervised
    assert llm_explainer.STYLE_RULES in anomaly
    assert llm_explainer.INVENTION_RULES in supervised
    assert llm_explainer.INVENTION_RULES in anomaly
    assert llm_explainer.EVIDENCE_BOUNDARY in supervised
    assert llm_explainer.EVIDENCE_BOUNDARY in anomaly


def test_the_hardened_anomaly_prompt_still_names_no_attack_class():
    assert attack_names_in(anomaly_prompt()) == []


def test_claude_is_the_only_provider(monkeypatch):
    monkeypatch.setattr(llm_explainer, "_generate_with_claude",
                        lambda prompt: ("shpjegim claude", "claude-sonnet-5"))

    results = llm_explainer.generate_all_explanations(
        "PortScan", 0.96, shap_features(), detection_method=METHOD_SUPERVISED)

    assert llm_explainer.PROVIDERS == ("claude",)
    assert [result["provider"] for result in results] == ["claude"]
    assert {result["llm_prompt_version"] for result in results} == {"v3"}


def test_an_unknown_provider_is_refused_instead_of_silently_using_claude(monkeypatch):
    def fail(prompt):
        raise AssertionError("Claude must not answer for another provider")

    monkeypatch.setattr(llm_explainer, "_generate_with_claude", fail)

    with pytest.raises(ValueError, match="nonexistent"):
        generate_explanation("DDoS", 0.9, shap_features(), provider="nonexistent",
                             detection_method=METHOD_SUPERVISED)


def test_the_provider_is_reported_on_every_result(monkeypatch):
    monkeypatch.setattr(llm_explainer, "_generate_with_claude",
                        lambda prompt: ("x", "claude-sonnet-5"))

    result = generate_explanation("DDoS", 0.9, shap_features(), provider="claude",
                                  detection_method=METHOD_SUPERVISED)

    assert result["provider"] == "claude"
    assert result["llm_model"] == "claude-sonnet-5"
    assert result["generation_latency_ms"] >= 0


def test_a_failing_provider_yields_no_results_instead_of_raising(monkeypatch):
    def broken(prompt):
        raise RuntimeError("provider down")

    monkeypatch.setattr(llm_explainer, "_generate_with_claude", broken)

    results = llm_explainer.generate_all_explanations(
        "DDoS", 0.9, shap_features(), detection_method=METHOD_SUPERVISED)

    assert results == []
