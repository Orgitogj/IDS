import time

from anthropic import Anthropic
from google import genai

from app.core.config import settings

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


def _build_prompt(predicted_label, confidence, top_shap_features, detection_class=None):
    features_text = "\n".join(
        f"- {f['feature']}: vlera={f['value']:.2f}, kontribut SHAP={f['shap_contribution']:.3f}"
        for f in top_shap_features
    )

    if detection_class == "SUSPICIOUS":
        return f"""Je nje asistent sigurie qe shpjegon alarme te sistemit IDS per nje administrator rrjeti. Administratori NUK eshte ekspert machine learning, por e kupton terminologjine baze te rrjetit.

Sistemi NUK e klasifikoi dot kete flow si ndonje nga sulmet e njohura te CICIDS2017. Modeli i mbikeqyrur e quajti trafik normal, ndersa detektori i anomalive e shenoi si te pazakonte krahasuar me trafikun normal te trajnimit.

Features qe e bejne kete flow te pazakonte:
{features_text}

Shkruaj nje shpjegim te shkurter (3-5 fjali) ne shqip. RREGULLA TE DETYRUESHME:
- Thuaj qartesisht se sistemi zbuloi sjellje te pazakonte por NUK e lidh dot me nje lloj sulmi te njohur.
- MOS emerto asnje lloj sulmi konkret dhe MOS shpik karakteristika qe nuk mbeshteten nga te dhenat me siper.
- Sugjero qe kjo kerkon verifikim nga analisti; mos e paraqit si sulm te konfirmuar."""

    confidence_text = f"{confidence:.1%}" if confidence is not None else "e padisponueshme"

    return f"""Je nje asistent sigurie qe shpjegon alarme te sistemit IDS per nje administrator rrjeti. Administratori NUK eshte ekspert machine learning, por e kupton terminologjine baze te rrjetit.

Modeli ML klasifikoi kete flow trafiku si: {predicted_label}
Niveli i besueshmerise: {confidence_text}

Features qe kontribuan me shume:
{features_text}

Shkruaj nje shpjegim te shkurter (3-5 fjali) ne shqip qe shpjegon ne gjuhe te thjeshte cfare u zbulua dhe pse, pa xhargon ML. Mos shpik karakteristika qe nuk mbeshteten nga te dhenat me siper."""


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
                         detection_class=None):
    prompt = _build_prompt(predicted_label, confidence, top_shap_features, detection_class)
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
                              detection_class=None):
    results = []
    for provider in PROVIDERS:
        try:
            results.append(
                generate_explanation(predicted_label, confidence, top_shap_features, provider,
                                     detection_class)
            )
        except Exception as error:
            print(f"Ofruesi {provider} deshtoi: {error}")
    return results