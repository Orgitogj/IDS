import json

from training.pipeline.reporting import (
    ARTIFACT_ABSENT,
    ARTIFACT_MISMATCH,
    ARTIFACT_OK,
    EvaluationReport,
)

NOTES_PREFIX = "provenance="
MAX_NOTES_CHARS = 8000


class RegistrationError(RuntimeError):
    pass


class ArtifactHashMismatch(RegistrationError):
    pass


def build_notes(report, extra=None):
    provenance = report.provenance()
    if extra:
        provenance.update(extra)
    encoded = json.dumps(provenance, ensure_ascii=False, sort_keys=True)
    if len(encoded) > MAX_NOTES_CHARS:
        provenance.pop("hyperparameters", None)
        encoded = json.dumps(provenance, ensure_ascii=False, sort_keys=True)
    return NOTES_PREFIX + encoded


def experiment_payload(report, ml_model_id, extra_provenance=None):
    if not isinstance(report, EvaluationReport):
        raise RegistrationError(
            "experiment_payload pranon vetem nje EvaluationReport te validuar. "
            "Ngarko raportin me EvaluationReport.from_path(...); metrikat s'jepen dot "
            "me dore.")

    overall = report.overall

    return {
        "mlModelId": str(ml_model_id),
        "testedOnDataset": report.dataset_name,
        "featureSetUsed": report.feature_version,
        "accuracy": float(overall["accuracy"]),
        "precisionScore": float(overall["macro_precision"]),
        "recall": float(overall["macro_recall"]),
        "f1Score": float(overall["macro_f1"]),
        "avgLatencyMs": report.batch_latency_ms,
        "sampleSize": int(report.sample_size),
        "notes": build_notes(report, extra_provenance),
    }


def check_artifact(report, models_dir, allow_mismatch=False):
    status, actual = report.verify_artifact(models_dir)

    if status == ARTIFACT_OK:
        return status, actual

    if status == ARTIFACT_ABSENT:
        message = (f"Artefakti '{report.artifact_file}' s'gjendet ne {models_dir}; "
                   "metrikat s'lidhen dot me nje artefakt konkret.")
    else:
        message = (f"SHA256 i '{report.artifact_file}' ndryshon nga ai i regjistruar ne "
                   f"raport.\n  raporti : {report.artifact_sha256}\n  ne disk : {actual}\n"
                   "  Artefakti ka ndryshuar qe kur u llogaritur raporti; rillogarit "
                   "metrikat perpara se t'i regjistrosh.")

    if allow_mismatch:
        return status, actual

    raise ArtifactHashMismatch(message)


def resolve_model_id(models, report, explicit_name=None):
    wanted = explicit_name or report.name
    by_name = {entry.get("name"): entry for entry in models}

    if wanted in by_name:
        return by_name[wanted]["id"], by_name[wanted]

    artifact = report.artifact_file
    for entry in models:
        registered = str(entry.get("artifactPath", "")).replace("\\", "/").split("/")[-1]
        if registered == artifact:
            return entry["id"], entry

    return None, None


def register(report, ml_model_id, client, models_dir, dry_run=True,
             allow_mismatch=False, extra_provenance=None):
    status, actual = check_artifact(report, models_dir, allow_mismatch=allow_mismatch)
    payload = experiment_payload(report, ml_model_id, extra_provenance)

    if dry_run:
        return {"written": False, "artifact_status": status, "artifact_sha256": actual,
                "payload": payload, "response": None}

    response = client.create_experiment_result(payload)
    return {"written": True, "artifact_status": status, "artifact_sha256": actual,
            "payload": payload, "response": response}
