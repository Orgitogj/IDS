import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

from app.services.groundedness import Evidence, check as check_groundedness

DEFAULT_OUT_DIR = "reports/llm_evaluation"

CSV_COLUMNS = [
    "alarm_id",
    "explanation_id",
    "network_flow_id",
    "ground_truth_label",
    "ground_truth_attack_type",
    "predicted_label",
    "attack_type",
    "detection_method",
    "confidence",
    "anomaly_score",
    "model_name",
    "model_version",
    "feature_version",
    "severity",
    "alarm_status",
    "provider",
    "llm_model",
    "llm_prompt_version",
    "generation_latency_ms",
    "rating",
    "rated_at",
    "generated_at",
    "shap_feature_count",
    "groundedness_grounded",
    "groundedness_finding_count",
    "groundedness_high_severity_count",
    "explanation_text",
]

PROVIDER_BY_MODEL_PREFIX = {"claude": "claude", "gemini": "gemini"}


def provider_for(llm_model):
    name = str(llm_model or "").lower()
    for prefix, provider in PROVIDER_BY_MODEL_PREFIX.items():
        if name.startswith(prefix):
            return provider
    return None


class BackendReader:

    def __init__(self, client):
        self.client = client

    def alarms(self, page_size=200, max_pages=1000):
        collected = []
        page = 0
        while page < max_pages:
            response = self.client._request(
                "GET", f"/api/alarms?page={page}&size={page_size}")
            content = response.get("content", [])
            collected.extend(content)
            if page + 1 >= int(response.get("totalPages", 0) or 0):
                break
            page += 1
        return collected

    def flow(self, flow_id):
        return self.client._request("GET", f"/api/flows/{flow_id}")

    def explanations(self, alarm_id):
        return self.client._request("GET", f"/api/alarms/{alarm_id}/explanations")


def shap_evidence_for(flow, predictor):
    if predictor is None:
        return None, None

    feature_vector = flow.get("featureVector")
    if not feature_vector:
        return None, "flow carries no feature vector"

    try:
        prediction = predictor(feature_vector, flow.get("modelId"))
    except Exception as error:
        return None, f"prediction failed: {error!r}"

    return prediction, None


def build_rows(reader, predictor=None, limit=None):
    rows = []
    skipped = []

    alarms = reader.alarms()
    if limit is not None:
        alarms = alarms[:limit]

    for alarm in alarms:
        alarm_id = alarm.get("id")
        flow_id = alarm.get("networkFlowId")

        try:
            explanations = reader.explanations(alarm_id)
        except Exception as error:
            skipped.append({"alarm_id": alarm_id, "reason": f"explanations: {error!r}"})
            continue

        if not explanations:
            continue

        try:
            flow = reader.flow(flow_id) if flow_id else {}
        except Exception as error:
            skipped.append({"alarm_id": alarm_id, "reason": f"flow: {error!r}"})
            flow = {}

        prediction, reason = shap_evidence_for(flow, predictor)
        if reason:
            skipped.append({"alarm_id": alarm_id, "reason": reason})

        shap_features = (prediction or {}).get("top_shap_features") or []
        anomaly_features = (prediction or {}).get("top_anomaly_features") or []

        evidence = Evidence(
            predicted_label=flow.get("attackType") or flow.get("predictedLabel"),
            confidence=flow.get("predictionConfidence"),
            shap_features=shap_features,
            anomaly_features=anomaly_features,
            anomaly_score=flow.get("anomalyScore"),
        )

        for explanation in explanations:
            text = explanation.get("explanationText", "")
            groundedness = check_groundedness(text, evidence)

            rows.append({
                "alarm_id": alarm_id,
                "explanation_id": explanation.get("id"),
                "network_flow_id": flow_id,
                "ground_truth_label": flow.get("label"),
                "ground_truth_attack_type": flow.get("groundTruthAttackType"),
                "predicted_label": flow.get("predictedLabel"),
                "attack_type": flow.get("attackType"),
                "detection_method": flow.get("detectionMethod"),
                "confidence": flow.get("predictionConfidence"),
                "anomaly_score": flow.get("anomalyScore"),
                "model_name": flow.get("modelName"),
                "model_version": flow.get("modelVersion"),
                "feature_version": flow.get("featureVersion"),
                "severity": alarm.get("severity"),
                "alarm_status": alarm.get("status"),
                "provider": provider_for(explanation.get("llmModel")),
                "llm_model": explanation.get("llmModel"),
                "llm_prompt_version": explanation.get("llmPromptVersion"),
                "generation_latency_ms": explanation.get("generationLatencyMs"),
                "rating": explanation.get("rating"),
                "rated_at": explanation.get("ratedAt"),
                "generated_at": explanation.get("generatedAt"),
                "shap_feature_count": len(shap_features),
                "groundedness_grounded": groundedness["grounded"],
                "groundedness_finding_count": groundedness["finding_count"],
                "groundedness_high_severity_count": groundedness["high_severity_count"],
                "explanation_text": text,
                "shap_evidence": shap_features,
                "anomaly_evidence": anomaly_features,
                "groundedness": groundedness,
            })

    return rows, skipped


def summarise(rows):
    by_provider = {}
    by_version = {}
    ratings = {}
    flagged = 0

    for row in rows:
        provider = row["provider"] or "unknown"
        entry = by_provider.setdefault(
            provider, {"explanations": 0, "rated": 0, "latency_ms_total": 0.0,
                       "flagged": 0})
        entry["explanations"] += 1
        if row["rating"]:
            entry["rated"] += 1
            ratings[row["rating"]] = ratings.get(row["rating"], 0) + 1
        if row["generation_latency_ms"]:
            entry["latency_ms_total"] += float(row["generation_latency_ms"])
        if not row["groundedness_grounded"]:
            entry["flagged"] += 1
            flagged += 1

        version = row["llm_prompt_version"] or "unknown"
        by_version[version] = by_version.get(version, 0) + 1

    for entry in by_provider.values():
        entry["mean_latency_ms"] = (
            entry["latency_ms_total"] / entry["explanations"]
            if entry["explanations"] else None)
        entry.pop("latency_ms_total")

    return {
        "explanations": len(rows),
        "flagged_by_groundedness_heuristic": flagged,
        "by_provider": by_provider,
        "by_prompt_version": by_version,
        "ratings": ratings,
    }


def write_outputs(rows, skipped, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "explanations.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    jsonl_path = out_dir / "explanations.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary_path = out_dir / "summary.json"
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "purpose": "H4 - LLM explanation quality. One row per explanation, with the "
                   "evidence the model was given, the provider, the prompt version, the "
                   "latency, the analyst rating and a deterministic groundedness check.",
        "groundedness_caveat": "The groundedness column is a heuristic entity check, not "
                               "a semantic correctness judgement, and no LLM judge is "
                               "used. See app/services/groundedness.py.",
        "summary": summarise(rows),
        "skipped": skipped,
    }
    with open(summary_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1, ensure_ascii=False)

    return {"csv": csv_path, "jsonl": jsonl_path, "summary": summary_path}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Eksporton cdo shpjegim LLM me evidencen e vet, per vleresimin H4. "
                    "Vetem lexim; nuk shkruan asgje ne backend.")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--limit", type=int, default=None,
                        help="Perpuno vetem N alarmet e para")
    parser.add_argument("--no-shap", action="store_true",
                        help="Mos rillogarit SHAP nga feature vector-i i ruajtur")
    args = parser.parse_args()

    from app.services import spring_client

    predictor = None
    if not args.no_shap:
        from app.ml.inference import load_artifacts, predict as run_prediction

        try:
            load_artifacts()
        except Exception as error:
            print(f"KUJDES: artefaktet s'u ngarkuan ({error}); SHAP nuk rillogaritet.",
                  file=sys.stderr)
        else:
            def predictor(feature_vector, model_id=None):
                return run_prediction(feature_vector, include_shap=True,
                                      model_id=model_id)

    reader = BackendReader(spring_client)

    try:
        rows, skipped = build_rows(reader, predictor=predictor, limit=args.limit)
    except Exception as error:
        print(f"GABIM: backend-i s'u arrit ({error}). A eshte Spring Boot i ndezur?",
              file=sys.stderr)
        return 1

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = _ML_SERVICE_ROOT / out_dir

    paths = write_outputs(rows, skipped, out_dir)
    summary = summarise(rows)

    print(f"Shpjegime te eksportuara : {summary['explanations']}")
    print(f"Te flamuruara nga heuristika: "
          f"{summary['flagged_by_groundedness_heuristic']}")
    for provider, entry in sorted(summary["by_provider"].items()):
        mean = entry["mean_latency_ms"]
        mean_text = f"{mean:.0f} ms" if mean else "n/a"
        print(f"  {provider:<10} {entry['explanations']:>4} shpjegime | "
              f"{entry['rated']:>4} te vleresuara | latence mesatare {mean_text} | "
              f"{entry['flagged']} te flamuruara")
    print(f"Versione prompt-i: {summary['by_prompt_version']}")
    if skipped:
        print(f"U anashkaluan {len(skipped)} alarme (shih summary.json).")
    for label, path in paths.items():
        print(f"U ruajt {label}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
