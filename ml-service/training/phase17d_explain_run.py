import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

from app.ml.detection_engine import METHOD_SUPERVISED
from app.services import explanation_eval, llm_explainer
from training.phase17d_explain_sample import (
    MODEL_B,
    features_b,
    iter_rows,
    shap_package,
    to_matrix,
)

OUT = _ML_SERVICE_ROOT / "reports" / "domain_adaptation" / "phase17d" / "llm_explainability"
CONDITIONS = ("with_shap", "no_shap")

MAX_RETRIES = 3
BACKOFF_SECONDS = 2.0
RATE_LIMIT_BACKOFF_SECONDS = 25.0
INTER_CALL_SLEEP_SECONDS = 8.0
TRANSIENT_MARKERS = ("429", "500", "503", "unavailable", "resource_exhausted",
                     "timeout", "deadline", "temporarily", "overloaded")

REQUESTED_MODEL = {"gemini": "gemini-flash-latest", "claude": "claude-sonnet-5"}
GENERATION_PARAMS = {
    "gemini": {"temperature": "provider_default_unset",
               "max_output_tokens": "provider_default_unset",
               "note": "no explicit generation config set; provider defaults apply"},
    "claude": {"temperature": "provider_default_unset", "max_tokens": 400,
               "note": "max_tokens=400 set in llm_explainer; temperature unset "
                       "(provider default)"},
}

FILES = {
    "gemini": {"runs": "explanation_runs.json",
               "tech": "technical_evaluation.json",
               "latency": "latency.json"},
    "claude": {"runs": "explanation_runs_claude.json",
               "tech": "technical_evaluation_claude.json",
               "latency": "latency_claude.json"},
}


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha_text(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def _prompt_template_hash():
    blocks = "\n".join([llm_explainer.PROMPT_VERSION, llm_explainer.ROLE,
                        llm_explainer.EVIDENCE_BOUNDARY, llm_explainer.INVENTION_RULES,
                        llm_explainer.STYLE_RULES])
    return sha_text(blocks)


def _is_transient(error):
    s = str(error).lower()
    return any(m in s for m in TRANSIENT_MARKERS)


def _generate_with_retry(decision, proba, shap_features, provider):
    attempts = []
    for attempt in range(MAX_RETRIES + 1):
        try:
            gen = llm_explainer.generate_explanation(
                predicted_label=decision, confidence=proba,
                top_shap_features=shap_features, provider=provider,
                detection_method=METHOD_SUPERVISED)
            return gen, attempts
        except Exception as error:
            transient = _is_transient(error)
            attempts.append({"attempt": attempt + 1, "error": str(error)[:200],
                             "transient": transient})
            if not transient or attempt == MAX_RETRIES:
                return None, attempts
            if "429" in str(error) or "resource_exhausted" in str(error).lower():
                time.sleep(RATE_LIMIT_BACKOFF_SECONDS * (attempt + 1))
            else:
                time.sleep(BACKOFF_SECONDS * (attempt + 1))
    return None, attempts


def _percentiles(values):
    if not values:
        return {"n": 0, "median": None, "q1": None, "q3": None, "iqr": None,
                "min": None, "max": None}
    s = sorted(values)
    n = len(s)

    def q(p):
        idx = p * (n - 1)
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        return s[lo] + (s[hi] - s[lo]) * (idx - lo)

    return {"n": n, "median": q(0.5), "q1": q(0.25), "q3": q(0.75),
            "iqr": q(0.75) - q(0.25), "min": s[0], "max": s[-1]}


def _vector_at(feats, run_id, flow_index):
    for i, row in iter_rows(run_id):
        if i == flow_index:
            return to_matrix([[row.get(c) for c in feats]], feats)[0]
    raise SystemExit(f"row {flow_index} not found in {run_id}")


def run(provider, conditions, go):
    packages = json.loads((OUT / "evidence_sample.json").read_text(
        encoding="utf-8"))["packages"]
    planned = len(packages) * len(conditions)
    if not go:
        print(f"DRY RUN: {planned} real {provider} calls would be made "
              f"({len(packages)} alerts x {len(conditions)} conditions). "
              f"Re-run with --go to perform them.")
        return {"dry_run": True, "planned_calls": planned, "provider": provider}

    if os.environ.get("IDS_LLM_INTEGRATION") != "1":
        raise SystemExit("real calls require IDS_LLM_INTEGRATION=1 in the environment")

    requested_model = REQUESTED_MODEL[provider]
    gen_params = GENERATION_PARAMS[provider]
    runs_path = OUT / FILES[provider]["runs"]

    feats = features_b()
    model = joblib.load(MODEL_B)
    booster = model.get_booster()

    existing_ok = {}
    if runs_path.exists():
        prior_doc = json.loads(runs_path.read_text(encoding="utf-8"))
        for r in prior_doc.get("records", []):
            if r.get("provider") != provider:
                raise SystemExit(
                    f"refusing to resume: {runs_path.name} holds a non-{provider} "
                    f"record ({r.get('provider')}); providers are never mixed")
            if r.get("parse_status") == "ok":
                existing_ok[(r["alert_id"], r["condition"])] = r

    records = []
    evaluations = []
    for package in packages:
        evidence_hash = sha_text(json.dumps(package, sort_keys=True))
        vec = _vector_at(feats, package["source_run"], package["flow_index"])
        recomputed, shap_latency_ms, decision, proba = shap_package(
            model, booster, feats, vec, package["source_run"], package["flow_index"])
        assert decision == package["decision"], (decision, package["decision"])
        assert recomputed["top_shap_features"] == package["top_shap_features"], \
            f"SHAP mismatch for {package['alert_id']}"

        for condition in conditions:
            prior = existing_ok.get((package["alert_id"], condition))
            if prior is not None:
                records.append(prior)
                evaluations.append({"condition": condition,
                                    **explanation_eval.evaluate(
                                        prior["explanation_text"], package)})
                continue
            shap_features = package["top_shap_features"] if condition == "with_shap" else []
            time.sleep(INTER_CALL_SLEEP_SECONDS)
            rendered = llm_explainer._build_prompt(
                decision, proba, shap_features, detection_method=METHOD_SUPERVISED)
            start = utc_now()
            gen, attempts = _generate_with_retry(decision, proba, shap_features, provider)
            end = utc_now()
            base = {
                "alert_id": package["alert_id"], "source_run": package["source_run"],
                "flow_index": package["flow_index"], "condition": condition,
                "model_decision": decision, "evidence_sha256": evidence_hash,
                "prompt_template_sha256": _prompt_template_hash(),
                "rendered_prompt_sha256": sha_text(rendered),
                "provider": provider, "requested_model": requested_model,
                "generation_params": gen_params, "start_utc": start, "end_utc": end,
                "shap_latency_ms": shap_latency_ms if condition == "with_shap" else None,
                "retries": attempts,
            }
            if gen is None:
                base.update({"resolved_model": None, "llm_latency_ms": None,
                             "total_explanation_latency_ms": None,
                             "response_sha256": None, "explanation_text": None,
                             "parse_status": "failed"})
                records.append(base)
                continue
            text = gen["explanation_text"]
            llm_latency = gen["generation_latency_ms"]
            total = (shap_latency_ms + llm_latency) if condition == "with_shap" \
                else llm_latency
            base.update({"resolved_model": llm_explainer.LAST_RESOLVED_MODEL,
                         "llm_latency_ms": llm_latency,
                         "total_explanation_latency_ms": total,
                         "response_sha256": sha_text(text), "explanation_text": text,
                         "parse_status": "ok"})
            records.append(base)
            evaluations.append({"condition": condition,
                                **explanation_eval.evaluate(text, package)})

    _write_outputs(provider, packages, conditions, records, evaluations)
    n_ok = sum(1 for r in records if r["parse_status"] == "ok")
    n_fail = sum(1 for r in records if r["parse_status"] == "failed")
    n_retries = sum(len(r["retries"]) for r in records)
    resolved = sorted({r["resolved_model"] for r in records if r["resolved_model"]})
    print(f"provider={provider} records={len(records)} ok={n_ok} failed={n_fail} "
          f"retry_attempts={n_retries}")
    print(f"resolved_models={resolved}")
    return {"provider": provider, "records": len(records), "ok": n_ok, "failed": n_fail,
            "retry_attempts": n_retries, "resolved_models": resolved}


def _write_outputs(provider, packages, conditions, records, evaluations):
    with_shap = [e for e in evaluations if e["condition"] == "with_shap"]
    no_shap = [e for e in evaluations if e["condition"] == "no_shap"]

    def lat(cond, key):
        return _percentiles([r[key] for r in records
                             if r["condition"] == cond and r[key] is not None])

    latency = {
        "provider": provider,
        "note": "explanation-layer latency only; separate from frozen ML inference latency",
        "shap_computation_ms": lat("with_shap", "shap_latency_ms"),
        "llm_generation_ms_with_shap": lat("with_shap", "llm_latency_ms"),
        "llm_generation_ms_no_shap": lat("no_shap", "llm_latency_ms"),
        "total_explanation_ms_with_shap": lat("with_shap", "total_explanation_latency_ms"),
        "total_explanation_ms_no_shap": lat("no_shap", "total_explanation_latency_ms"),
    }

    agg_with = explanation_eval.aggregate(with_shap)
    agg_no = explanation_eval.aggregate(no_shap)
    comparable = {
        "note": "compared only on conceptually comparable metrics; direction consistency "
                "and SHAP evidence coverage are with-SHAP only and are not forced to zero "
                "for no-SHAP",
        "prediction_consistency_rate": {
            "with_shap": agg_with.get("prediction_consistency_rate"),
            "no_shap": agg_no.get("prediction_consistency_rate")},
        "structural_completeness_rate": {
            "with_shap": agg_with.get("structural_completeness_rate"),
            "no_shap": agg_no.get("structural_completeness_rate")},
        "unsupported_claim_free_rate": {
            "with_shap": agg_with.get("unsupported_claim_free_rate"),
            "no_shap": agg_no.get("unsupported_claim_free_rate")},
        "with_shap_only": {
            "direction_consistency_rate": agg_with.get("direction_consistency_rate"),
            "direction_claims_checked": agg_with.get("direction_claims_checked"),
            "mean_evidence_coverage": agg_with.get("mean_evidence_coverage")},
    }
    summary = {
        "generated_at": utc_now(), "provider": provider, "n_alerts": len(packages),
        "conditions": list(conditions),
        "aggregate_with_shap": agg_with, "aggregate_no_shap": agg_no,
        "comparable_paired": comparable,
    }
    (OUT / FILES[provider]["runs"]).write_text(
        json.dumps({"generated_at": utc_now(), "provider": provider,
                    "records": records}, indent=1) + "\n", encoding="utf-8")
    (OUT / FILES[provider]["tech"]).write_text(
        json.dumps({"summary": summary, "per_explanation": evaluations}, indent=1) + "\n",
        encoding="utf-8")
    (OUT / FILES[provider]["latency"]).write_text(
        json.dumps(latency, indent=1) + "\n", encoding="utf-8")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--provider", default="claude", choices=["gemini", "claude"])
    p.add_argument("--conditions", default="both",
                   choices=["both", "with_shap", "no_shap"])
    p.add_argument("--go", action="store_true")
    args = p.parse_args()
    conditions = CONDITIONS if args.conditions == "both" else (args.conditions,)
    run(args.provider, conditions, args.go)
    return 0


if __name__ == "__main__":
    sys.exit(main())
