import time

from anthropic import Anthropic
from google import genai

from app.core.config import settings
from app.ml.detection_engine import METHOD_ANOMALY

PROMPT_VERSION = "v3"

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


ROLE = ("Je nje asistent sigurie qe shpjegon alarme te sistemit IDS per nje administrator "
        "rrjeti. Administratori NUK eshte ekspert machine learning, por e kupton "
        "terminologjine baze te rrjetit.")

EVIDENCE_BOUNDARY = """CFARE DI DHE CFARE NUK DI:
- Ti NUK e ke pare vete trafikun e rrjetit. Nuk ke akses te paketat, te permbajtja e tyre, as te ndonje log.
- E vetmja evidence qe ke eshte ajo e listuar me poshte ne kete mesazh. Asgje tjeter.
- Vlerat e features jane matje statistikore te rrjedhes, te llogaritura nga sistemi; nuk jane permbajtje e paketave."""

INVENTION_RULES = """MOS SHPIK:
- Mos permend adresa IP, porta ose emra pajisjesh qe nuk jane ne evidencen me siper.
- Mos permend protokolle konkrete nese nuk dalin nga evidenca; mos i nxirr nga hamendja.
- Mos pershkruaj permbajtje paketash, komanda, skedare apo payload - nuk i ke pare.
- Mos shto teknika, mjete apo hapa sulmi qe nuk mbeshteten nga matjet e listuara.
- Nese nje detaj nuk eshte ne evidence, mos e permend fare; mos e zevendeso me hamendje."""

STYLE_RULES = """STILI:
- Shkruaj ne shqip te qarte, 3-5 fjali, per nje administrator rrjeti.
- Termat teknike standarde (flow, packet, feature, forward, backward, timeout) mund te mbeten ne anglisht kur perkthimi do ta bente tekstin artificial.
- Pa ekzagjerime dhe pa gjuhe alarmi; teknikisht i sakte dhe i permbajtur."""


def _format_shap_features(top_shap_features):
    return "\n".join(
        f"- {f['feature']}: vlera e matur={f['value']:.2f}, kontribut SHAP={f['shap_contribution']:+.3f}"
        for f in top_shap_features or []
    )


def _format_anomaly_features(top_anomaly_features):
    return "\n".join(
        f"- {f['feature']}: vlera={f['value']:.2f}, tipike per trafikun normal="
        f"{f['baseline_value']:.2f}, kontribut ne anomali={f['anomaly_contribution']:.4f}"
        for f in top_anomaly_features or []
    )


def _confidence_text(confidence):
    if confidence is None:
        return "e padisponueshme"
    return f"{confidence:.1%}"


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

    return f"""{ROLE}

{EVIDENCE_BOUNDARY}

Ky alarm NUK erdhi nga klasifikuesi i mbikeqyrur. Modeli i mbikeqyrur e quajti flow-in trafik normal. Alarmin e ngriti detektori i anomalive, i cili u trajnua VETEM mbi trafik normal dhe nuk njeh asnje lloj sulmi. Prandaj sistemi ka gjetur sjellje te pazakonte qe NUK ia atribuon dot asnje klase te njohur sulmi nga CICIDS2017.{score_text}

{evidence}

Kontributi ne anomali tregon sa e ndikoi secila matje rezultatin e detektorit. Eshte atribuim statistikor i vendimit te modelit, jo shkak i provuar.

{INVENTION_RULES}

RREGULLA TE DETYRUESHME PER KETE RAST:
- Thuaj qartesisht se sistemi zbuloi sjellje te pazakonte por NUK e lidh dot me nje lloj sulmi te njohur.
- MOS emerto asnje lloj sulmi konkret, as si hipoteze, as si mohim, as si shembull. Asnje emer familjeje sulmi nuk mbeshtetet nga evidenca me siper, prandaj asnje emer i tille nuk duhet te shfaqet ne tekst.
- MOS shpik karakteristika qe nuk jane ne listen e features me siper.
- Pershkruaj vetem se cilat matje dalin jashte normales dhe cfare do te thote kjo ne gjuhe rrjeti.
- Sugjero qe kjo kerkon verifikim nga analisti; mos e paraqit si sulm te konfirmuar.

{STYLE_RULES}"""


def _supervised_prompt(predicted_label, confidence, top_shap_features):
    features_text = _format_shap_features(top_shap_features)
    if not features_text:
        features_text = ("(Sistemi nuk dha kontribute features per kete parashikim; ke "
                         "vetem klasifikimin dhe besueshmerine.)")

    return f"""{ROLE}

{EVIDENCE_BOUNDARY}

PARASHIKIMI I MODELIT:
Modeli ML klasifikoi kete flow trafiku si: {predicted_label}
Besueshmeria e modelit per kete klasifikim: {_confidence_text(confidence)}

Ky eshte parashikim i nje modeli statistikor, JO fakt i provuar. Shkruaj gjithmone "modeli e klasifikoi si {predicted_label}" ose "sipas modelit", dhe kurrsesi "kjo rrjedhe ishte {predicted_label}" apo "u konfirmua si {predicted_label}".

Besueshmeria eshte siguria e modelit ne klasen qe zgjodhi. NUK eshte probabiliteti qe sulmi ka ndodhur vertet dhe nuk eshte matje rreziku. Sa me e ulet te jete, aq me te kujdesshme duhet te jene formulimet e tua dhe aq me qarte duhet te kerkosh verifikim nga analisti.

FEATURES ME KONTRIBUTIN ME TE MADH (vlera SHAP):
{features_text}

Vlera e matur eshte matja reale e flow-it. Kontributi SHAP eshte sa e shtyu ajo matje modelin drejt kesaj klase: pozitiv = ne favor te klases, negativ = kunder saj. SHAP shpjegon vendimin e modelit, NUK provon shkakun real te trafikut - mos e paraqit si lidhje shkakesore.

{INVENTION_RULES}

RREGULLA TE DETYRUESHME PER KETE RAST:
- Shpjego pse modeli arriti te ky klasifikim, duke u mbeshtetur vetem te matjet me siper.
- Dallo qarte mes "modeli e klasifikoi si {predicted_label}" dhe "eshte provuar se ishte {predicted_label}".
- Mos e paraqit klasifikimin si incident te konfirmuar; rekomando verifikim nga analisti.

{STYLE_RULES}"""


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


LAST_RESOLVED_MODEL = None


def _generate_with_gemini(prompt):
    global LAST_RESOLVED_MODEL
    client = _get_gemini_client()
    model_name = "gemini-flash-latest"
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
    )
    LAST_RESOLVED_MODEL = getattr(response, "model_version", None)
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
