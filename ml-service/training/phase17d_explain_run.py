import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

from app.ml.detection_engine import METHOD_SUPERVISED
from app.services import explanation_eval, llm_explainer

OUT = _ML_SERVICE_ROOT / "reports" / "domain_adaptation" / "phase17d" / "llm_explainability"
CONDITIONS = ("with_shap", "no_shap")


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _shap_for_condition(package, condition):
    if condition == "with_shap":
        return package["top_shap_features"]
    return []


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

    records = []
    evaluations = []
    for package in packages:
        for condition in conditions:
            gen = llm_explainer.generate_explanation(
                predicted_label=package["decision"],
                confidence=package["attack_probability"],
                top_shap_features=_shap_for_condition(package, condition),
                provider=provider,
                detection_method=METHOD_SUPERVISED,
            )
            text = gen["explanation_text"]
            ev = explanation_eval.evaluate(text, package)
            records.append({
                "alert_id": package["alert_id"],
                "condition": condition,
                "provider": gen["provider"],
                "llm_model": gen["llm_model"],
                "llm_prompt_version": gen["llm_prompt_version"],
                "generation_latency_ms": gen["generation_latency_ms"],
                "response_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "explanation_text": text,
            })
            evaluations.append({"condition": condition, **ev})

    with_shap_eval = [e for e in evaluations if e["condition"] == "with_shap"]
    no_shap_eval = [e for e in evaluations if e["condition"] == "no_shap"]
    summary = {
        "generated_at": utc_now(),
        "provider": provider,
        "n_alerts": len(packages),
        "conditions": list(conditions),
        "aggregate_with_shap": explanation_eval.aggregate(with_shap_eval),
        "aggregate_no_shap": explanation_eval.aggregate(no_shap_eval) if no_shap_eval
        else None,
    }
    (OUT / "explanation_runs.json").write_text(
        json.dumps({"records": records}, indent=1) + "\n", encoding="utf-8")
    (OUT / "technical_evaluation.json").write_text(
        json.dumps({"summary": summary, "per_explanation": evaluations}, indent=1) + "\n",
        encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--provider", default="gemini", choices=["gemini", "claude"])
    p.add_argument("--conditions", default="both",
                   choices=["both", "with_shap", "no_shap"])
    p.add_argument("--go", action="store_true")
    args = p.parse_args()
    conditions = CONDITIONS if args.conditions == "both" else (args.conditions,)
    run(args.provider, conditions, args.go)
    return 0


if __name__ == "__main__":
    sys.exit(main())
