import time

from anthropic import Anthropic
from google import genai

from app.core.config import settings
from app.ml.detection_engine import METHOD_ANOMALY

PROMPT_VERSION = "v2"

_anthropic_client = None
_gemini_client = None


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = Anthropic(api_key=settings.anthropic_api_key)
    return _anthropic_client


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=settings.gemini_api_key)
    return _gemini_client


def _format_shap_features(top_shap_features):
    return "\n".join(
        f"- {f['feature']}: vlera={f['value']:.2f}, kontribut SHAP={f['shap_contribution']:.3f}"
        for f in top_shap_features or []
    )


def _format_anomaly_features(top_anomaly_features):
    return "\n".join(
        f"- {f['feature']}: vlera={f['value']:.2f}, tipike per trafikun normal="
        f"{f['baseline_value']:.2f}, kontribut ne anomali={f['anomaly_contribution']:.4f}"
        for f in top_anomaly_features or []
    )


def _anomaly_prompt(top_anomaly_features, anomaly_score=None):
    features_text = _format_anomaly_features(top_anomaly_features)
    if not features_text:
        evidence = ("Sistemi nuk arriti te nxjerre features konkrete qe e shpjegojne "
                    "anomaline; ke vetem faktin qe flow-i doli jashte profilit normal.")
    else:
        evidence = ("Features me kontributin me te madh ne kete verdikt, sipas detektorit "
                    f"te anomalive (Isolation Forest):\n{features_text}")

    score_text = ""
    if anomaly_score is not None:
        score_text = (f"\nRezultati i anomalise: {anomaly_score:.3f} "
                      "(percentile kunder trafikut normal te trajnimit).")

    return f"""Je nje asistent sigurie qe shpjegon alarme te sistemit IDS per nje administrator rrjeti. Administratori NUK eshte ekspert machine learning, por e kupton terminologjine baze te rrjetit.

Ky alarm NUK erdhi nga klasifikuesi i mbikeqyrur. Modeli i mbikeqyrur e quajti flow-in trafik normal. Alarmin e ngriti detektori i anomalive, i cili u trajnua VETEM mbi trafik normal dhe nuk njeh asnje lloj sulmi. Prandaj sistemi ka gjetur sjellje te pazakonte qe NUK ia atribuon dot asnje klase te njohur sulmi nga CICIDS2017.{score_text}

{evidence}

Shkruaj nje shpjegim te shkurter (3-5 fjali) ne shqip. RREGULLA TE DETYRUESHME:
- Thuaj qartesisht se sistemi zbuloi sjellje te pazakonte por NUK e lidh dot me nje lloj sulmi te njohur.
- MOS emerto asnje lloj sulmi konkret, as si hipoteze, as si mohim, as si shembull. Asnje emer familjeje sulmi nuk mbeshtetet nga evidenca me siper, prandaj asnje emer i tille nuk duhet te shfaqet ne tekst.
- MOS shpik karakteristika qe nuk jane ne listen e features me siper.
- Pershkruaj vetem se cilat matje dalin jashte normales dhe cfare do te thote kjo ne gjuhe rrjeti.
- Sugjero qe kjo kerkon verifikim nga analisti; mos e paraqit si sulm te konfirmuar."""


def _supervised_prompt(predicted_label, confidence, top_shap_features):
    features_text = _format_shap_features(top_shap_features)
    confidence_text = f"{confidence:.1%}" if confidence is not None else "e padisponueshme"

    return f"""Je nje asistent sigurie qe shpjegon alarme te sistemit IDS per nje administrator rrjeti. Administratori NUK eshte ekspert machine learning, por e kupton terminologjine baze te rrjetit.

Modeli ML klasifikoi kete flow trafiku si: {predicted_label}
Niveli i besueshmerise: {confidence_text}

Features qe kontribuan me shume:
{features_text}

Shkruaj nje shpjegim te shkurter (3-5 fjali) ne shqip qe shpjegon ne gjuhe te thjeshte cfare u zbulua dhe pse, pa xhargon ML. Mos shpik karakteristika qe nuk mbeshteten nga te dhenat me siper."""


def _build_prompt(predicted_label, confidence, top_shap_features, detection_method=None,
                  top_anomaly_features=None, anomaly_score=None):
    if detection_method == METHOD_ANOMALY:
        return _anomaly_prompt(top_anomaly_features, anomaly_score)

    return _supervised_prompt(predicted_label, confidence, top_shap_features)


def _generate_with_claude(prompt):
    client = _get_anthropic_client()
    model_name = "claude-sonnet-5"
    message = client.messages.create(
        model=model_name,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text, model_name


def _generate_with_gemini(prompt):
    client = _get_gemini_client()
    model_name = "gemini-flash-latest"
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
    )
    return response.text, model_name


PROVIDERS = ("claude", "gemini")


def generate_explanation(predicted_label, confidence, top_shap_features, provider=None,
                         detection_method=None, top_anomaly_features=None,
                         anomaly_score=None):
    prompt = _build_prompt(predicted_label, confidence, top_shap_features, detection_method,
                           top_anomaly_features, anomaly_score)
    chosen = provider or settings.llm_provider

    started = time.perf_counter()
    if chosen == "claude":
        explanation_text, model_name = _generate_with_claude(prompt)
    else:
        explanation_text, model_name = _generate_with_gemini(prompt)
    latency_ms = (time.perf_counter() - started) * 1000

    return {
        "explanation_text": explanation_text,
        "llm_model": model_name,
        "llm_prompt_version": PROMPT_VERSION,
        "generation_latency_ms": latency_ms,
        "provider": chosen,
    }


def generate_all_explanations(predicted_label, confidence, top_shap_features,
                              detection_method=None, top_anomaly_features=None,
                              anomaly_score=None):
    results = []
    for provider in PROVIDERS:
        try:
            results.append(
                generate_explanation(predicted_label, confidence, top_shap_features, provider,
                                     detection_method, top_anomaly_features, anomaly_score)
            )
        except Exception as error:
            print(f"Ofruesi {provider} deshtoi: {error}")
    return results
