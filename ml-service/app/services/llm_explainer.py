from anthropic import Anthropic
from google import genai

from app.core.config import settings

PROMPT_VERSION = "v1"

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


def _build_prompt(predicted_label, confidence, top_shap_features):
    features_text = "\n".join(
        f"- {f['feature']}: vlera={f['value']:.2f}, kontribut SHAP={f['shap_contribution']:.3f}"
        for f in top_shap_features
    )

    return f"""Je nje asistent sigurie qe shpjegon alarme te sistemit IDS per nje administrator rrjeti. Administratori NUK eshte ekspert machine learning, por e kupton terminologjine baze te rrjetit.

Modeli ML klasifikoi kete flow trafiku si: {predicted_label}
Niveli i besueshmerise: {confidence:.1%}

Features qe kontribuan me shume:
{features_text}

Shkruaj nje shpjegim te shkurter (3-5 fjali) ne shqip qe shpjegon ne gjuhe te thjeshte cfare u zbulua dhe pse, pa xhargon ML."""


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


def generate_explanation(predicted_label, confidence, top_shap_features):
    prompt = _build_prompt(predicted_label, confidence, top_shap_features)

    if settings.llm_provider == "claude":
        explanation_text, model_name = _generate_with_claude(prompt)
    else:
        explanation_text, model_name = _generate_with_gemini(prompt)

    return {
        "explanation_text": explanation_text,
        "llm_model": model_name,
        "llm_prompt_version": PROMPT_VERSION,
    }