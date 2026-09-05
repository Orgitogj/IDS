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


def test_the_prompt_version_is_v2():
    assert PROMPT_VERSION == "v2"


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

    def fake_gemini(prompt):
        captured["prompt"] = prompt
        return "Sistemi vuri re sjellje te pazakonte qe nuk perputhet me profilin normal.", "stub"

    monkeypatch.setattr(llm_explainer, "_generate_with_gemini", fake_gemini)

    result = generate_explanation("UNKNOWN", None, shap_features(), provider="gemini",
                                  detection_method=METHOD_ANOMALY,
                                  top_anomaly_features=anomaly_features(),
                                  anomaly_score=0.991)

    assert result["llm_prompt_version"] == "v2"
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
    assert result["llm_prompt_version"] == "v2"
    assert text.strip()
    assert attack_names_in(text) == [], f"shpjegimi emertoi nje klase sulmi: {text}"
