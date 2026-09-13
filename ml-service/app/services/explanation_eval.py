import re

from app.services import groundedness

DECISION_TERMS = {
    "ATTACK": ["attack", "sulm", "malinj", "keqdashës", "keqdashes", "i dyshimt",
               "i dyshimte"],
    "BENIGN": ["benign", "normal", "i padëmshëm", "i pademshem", "beninj"],
}

INCREASE_TERMS = ["rrit", "në favor", "ne favor", "shtyu", "shtyn", "më të larta",
                  "me te larta", "e lartë", "e larte", "drejt sulmit", "pro sulmit",
                  "increase", "higher", "toward attack"]
DECREASE_TERMS = ["uli", "ulur", "ulet", "uleta", "ulën", "ulen", "kundër", "kunder",
                  "më të ulëta", "me te uleta", "e ulët", "e ulet", "larg sulmit",
                  "decrease", "lower", "against attack", "toward benign"]


def _mentions(text, term):
    return term.lower() in (text or "").lower()


def _feature_window(text, feature, radius=90):
    low = (text or "").lower()
    fl = feature.lower()
    idx = low.find(fl)
    if idx < 0:
        return None
    start = max(0, idx - radius)
    end = min(len(low), idx + len(fl) + radius)
    return low[start:end]


def prediction_consistency(text, decision):
    decision = str(decision)
    other = "BENIGN" if decision == "ATTACK" else "ATTACK"
    decision_hit = any(_mentions(text, t) for t in DECISION_TERMS.get(decision, []))
    other_hit = any(_mentions(text, t) for t in DECISION_TERMS.get(other, []))
    consistent = decision_hit and not (other_hit and not decision_hit)
    return {
        "decision": decision,
        "decision_mentioned": decision_hit,
        "opposite_mentioned": other_hit,
        "consistent": bool(decision_hit),
    }


def feature_grounding(text, evidence):
    referenced = [f for f in evidence.feature_names if _mentions(text, f)]
    number_findings = []
    for match in groundedness.NUMBER.finditer(text or ""):
        value = groundedness._parse_number(match.group(0))
        if value is None:
            continue
        if abs(value) < 1 and value != 0:
            continue
        if not evidence.mentions_number(value):
            number_findings.append(match.group(0))
    return {
        "referenced_supplied_features": referenced,
        "referenced_count": len(referenced),
        "numbers_not_in_evidence": number_findings[:10],
        "numbers_not_in_evidence_count": len(number_findings),
    }


def direction_consistency(text, shap_features):
    per_feature = []
    checked = consistent = 0
    for f in shap_features or []:
        window = _feature_window(text, str(f["feature"]))
        if window is None:
            per_feature.append({"feature": f["feature"], "mentioned": False,
                                "claim": None, "expected": f.get("direction"),
                                "consistent": None})
            continue
        inc = any(t in window for t in INCREASE_TERMS)
        dec = any(t in window for t in DECREASE_TERMS)
        if inc == dec:
            claim = None
        else:
            claim = "increases_attack" if inc else "decreases_attack"
        ok = None
        if claim is not None:
            checked += 1
            ok = claim == f.get("direction")
            if ok:
                consistent += 1
        per_feature.append({"feature": f["feature"], "mentioned": True,
                            "claim": claim, "expected": f.get("direction"),
                            "consistent": ok})
    return {
        "checked_claims": checked,
        "consistent_claims": consistent,
        "inconsistent_claims": checked - consistent,
        "per_feature": per_feature,
    }


def evidence_coverage(text, shap_features):
    names = [str(f["feature"]) for f in shap_features or []]
    covered = [n for n in names if _mentions(text, n)]
    return {
        "top_k": len(names),
        "covered": len(covered),
        "coverage_ratio": (len(covered) / len(names)) if names else None,
        "covered_features": covered,
    }


def structural_completeness(text, decision):
    low = (text or "").lower()
    has_decision = any(_mentions(text, t) for t in DECISION_TERMS.get(str(decision), [])) \
        or "modeli" in low
    has_evidence_ref = any(term in low for term in
                           ["feature", "matj", "vlera", "kontribut", "shap"])
    has_uncertainty = any(term in low for term in
                          ["verifik", "analist", "pasigur", "kujdes", "duhet kontrolluar",
                           "rekomand"])
    present = {"decision_statement": bool(has_decision),
               "evidence_reference": bool(has_evidence_ref),
               "uncertainty_or_action": bool(has_uncertainty)}
    return {"fields_present": present, "all_present": all(present.values())}


def evaluate(explanation_text, evidence_package):
    ev = groundedness.Evidence(
        predicted_label=evidence_package.get("decision"),
        confidence=evidence_package.get("attack_probability"),
        shap_features=evidence_package.get("top_shap_features"),
    )
    decision = evidence_package.get("decision")
    shap = evidence_package.get("top_shap_features")
    unsupported = groundedness.check(explanation_text, ev)
    pred = prediction_consistency(explanation_text, decision)
    grounding = feature_grounding(explanation_text, ev)
    direction = direction_consistency(explanation_text, shap)
    coverage = evidence_coverage(explanation_text, shap)
    structure = structural_completeness(explanation_text, decision)
    return {
        "alert_id": evidence_package.get("alert_id"),
        "prediction_consistency": pred,
        "feature_grounding": grounding,
        "direction_consistency": direction,
        "unsupported_claims": unsupported,
        "evidence_coverage": coverage,
        "structural_completeness": structure,
        "method": "deterministic_technical_groundedness_v1",
        "caveat": ("Automated technical checks only. They test grounding against the "
                   "supplied evidence, not human clarity or usefulness, and a clean "
                   "result is not proof of a correct or useful explanation."),
    }


def aggregate(results):
    n = len(results)
    if n == 0:
        return {"n": 0}
    pred_ok = sum(1 for r in results if r["prediction_consistency"]["consistent"])
    struct_ok = sum(1 for r in results if r["structural_completeness"]["all_present"])
    unsupported_clean = sum(1 for r in results if r["unsupported_claims"]["grounded"])
    dir_checked = sum(r["direction_consistency"]["checked_claims"] for r in results)
    dir_ok = sum(r["direction_consistency"]["consistent_claims"] for r in results)
    cov = [r["evidence_coverage"]["coverage_ratio"] for r in results
           if r["evidence_coverage"]["coverage_ratio"] is not None]
    return {
        "n": n,
        "prediction_consistency_rate": pred_ok / n,
        "structural_completeness_rate": struct_ok / n,
        "unsupported_claim_free_rate": unsupported_clean / n,
        "direction_claims_checked": dir_checked,
        "direction_consistency_rate": (dir_ok / dir_checked) if dir_checked else None,
        "mean_evidence_coverage": (sum(cov) / len(cov)) if cov else None,
    }
