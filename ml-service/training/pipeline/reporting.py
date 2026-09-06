import hashlib
import json
from pathlib import Path

from training.build_feature_reference import sha256_of

REPORT_SCHEMA_VERSION = 1

KIND_TRAINING_RUN = "training_run"
KIND_ARTIFACT_EVALUATION = "artifact_evaluation"
KNOWN_KINDS = (KIND_TRAINING_RUN, KIND_ARTIFACT_EVALUATION)

REQUIRED_TOP_LEVEL = ("schema_version", "name", "artifact_file", "metrics", "dataset",
                      "split", "timings")
REQUIRED_OVERALL = ("accuracy", "macro_precision", "macro_recall", "macro_f1", "rows")
BOUNDED_METRICS = ("accuracy", "macro_precision", "macro_recall", "macro_f1",
                   "weighted_f1")

MACRO_F1_TOLERANCE = 1e-6
ACCURACY_TOLERANCE = 1e-9

ARTIFACT_OK = "ok"
ARTIFACT_MISMATCH = "mismatch"
ARTIFACT_ABSENT = "absent"
ARTIFACT_UNVERIFIABLE = "unverifiable"


class EvaluationReportError(ValueError):
    pass


def sha256_of_payload(payload):
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class EvaluationReport:

    def __init__(self, payload, source_path=None):
        self.payload = payload
        self.source_path = Path(source_path) if source_path else None
        self.validate()

    @classmethod
    def from_path(cls, path):
        report_path = Path(path)
        if not report_path.exists():
            raise EvaluationReportError(f"Raporti s'u gjet: {report_path}")
        try:
            with open(report_path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except json.JSONDecodeError as error:
            raise EvaluationReportError(f"{report_path.name}: JSON i pavlefshem ({error})")
        if not isinstance(payload, dict):
            raise EvaluationReportError(f"{report_path.name}: pritej nje objekt JSON.")
        return cls(payload, source_path=report_path)

    def validate(self):
        payload = self.payload

        missing = [key for key in REQUIRED_TOP_LEVEL if key not in payload]
        if missing:
            raise EvaluationReportError(
                f"Raportit i mungojne fushat: {', '.join(missing)}")

        if payload["schema_version"] != REPORT_SCHEMA_VERSION:
            raise EvaluationReportError(
                f"schema_version {payload['schema_version']} s'mbeshtetet "
                f"(pritej {REPORT_SCHEMA_VERSION}).")

        kind = payload.get("report_kind")
        if kind not in KNOWN_KINDS:
            raise EvaluationReportError(
                f"report_kind '{kind}' s'njihet; prit nje nga {KNOWN_KINDS}.")

        if not payload.get("artifact_sha256"):
            raise EvaluationReportError(
                "Raportit i mungon artifact_sha256; s'verifikohet dot cilit artefakt "
                "i perkasin keto metrika.")

        metrics = payload["metrics"]
        if not isinstance(metrics, dict) or "overall" not in metrics:
            raise EvaluationReportError("metrics.overall mungon.")

        overall = metrics["overall"]
        absent = [key for key in REQUIRED_OVERALL if overall.get(key) is None]
        if absent:
            raise EvaluationReportError(
                f"metrics.overall s'ka: {', '.join(absent)}")

        for key in BOUNDED_METRICS:
            value = overall.get(key)
            if value is None:
                continue
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise EvaluationReportError(f"metrics.overall.{key} s'eshte numer.")
            if not 0.0 <= float(value) <= 1.0:
                raise EvaluationReportError(
                    f"metrics.overall.{key}={value} eshte jashte intervalit [0,1].")

        per_class = metrics.get("per_class")
        if not isinstance(per_class, dict) or not per_class:
            raise EvaluationReportError("metrics.per_class mungon ose eshte bosh.")

        support = sum(int(row.get("support", 0)) for row in per_class.values())
        if support != int(overall["rows"]):
            raise EvaluationReportError(
                f"Shuma e support-it per klase ({support}) s'perputhet me "
                f"metrics.overall.rows ({overall['rows']}).")

        derived = metrics.get("macro_f1_from_confusion_matrix")
        if derived is not None:
            if abs(float(derived) - float(overall["macro_f1"])) > MACRO_F1_TOLERANCE:
                raise EvaluationReportError(
                    f"macro_f1 {overall['macro_f1']} s'perputhet me vleren e nxjerre nga "
                    f"matrica e konfuzionit ({derived}); raporti eshte i paperputhshem.")

        sklearn_accuracy = overall.get("accuracy_sklearn")
        if sklearn_accuracy is not None:
            if abs(float(sklearn_accuracy) - float(overall["accuracy"])) > ACCURACY_TOLERANCE:
                raise EvaluationReportError(
                    f"accuracy {overall['accuracy']} s'perputhet me accuracy_sklearn "
                    f"({sklearn_accuracy}).")

        timings = payload["timings"]
        if not isinstance(timings, dict) or "latency_methodology" not in timings:
            raise EvaluationReportError(
                "timings.latency_methodology mungon; latenca duhet te jete e "
                "dokumentuar per te mos u krahasuar me metodologji tjeter.")

        return True

    @property
    def name(self):
        return self.payload["name"]

    @property
    def report_kind(self):
        return self.payload["report_kind"]

    @property
    def artifact_file(self):
        return self.payload["artifact_file"]

    @property
    def artifact_sha256(self):
        return self.payload["artifact_sha256"]

    @property
    def overall(self):
        return self.payload["metrics"]["overall"]

    @property
    def sample_size(self):
        return int(self.overall["rows"])

    @property
    def dataset_name(self):
        return self.payload["dataset"].get("name")

    @property
    def feature_version(self):
        return self.payload.get("feature_version")

    @property
    def subsampled(self):
        return bool(self.payload["dataset"].get("subsampled"))

    @property
    def batch_latency_ms(self):
        return self.payload["timings"].get("avg_latency_ms_batch")

    @property
    def single_flow_latency(self):
        model_latency = self.payload["timings"].get("model_inference_latency") or {}
        return (model_latency.get("single_flow")
                or self.payload["timings"].get("single_flow_latency"))

    @property
    def production_path_latency(self):
        return self.payload["timings"].get("production_path_inference_latency")

    def report_sha256(self):
        return sha256_of_payload(self.payload)

    def verify_artifact(self, models_dir):
        artifact = Path(models_dir) / self.artifact_file
        if not artifact.exists():
            return ARTIFACT_ABSENT, None
        actual = sha256_of(artifact)
        if actual != self.artifact_sha256:
            return ARTIFACT_MISMATCH, actual
        return ARTIFACT_OK, actual

    def provenance(self):
        payload = self.payload
        return {
            "experiment_name": self.name,
            "report_kind": self.report_kind,
            "model_artifact": self.artifact_file,
            "model_artifact_sha256": self.artifact_sha256,
            "model_version": payload.get("version"),
            "algorithm": payload.get("algorithm"),
            "dataset": payload["dataset"].get("name"),
            "dataset_sha256": payload["dataset"].get("sha256"),
            "dataset_subsampled": self.subsampled,
            "feature_set": self.feature_version,
            "n_features": payload.get("n_features"),
            "split_strategy": payload["split"].get("strategy"),
            "split_test_size": payload["split"].get("test_size"),
            "seed": payload.get("seed"),
            "balancing_strategy": (payload.get("balancing") or {}).get("strategy"),
            "balancing_rows_after": (payload.get("balancing") or {}).get("rows_after"),
            "hyperparameters": payload.get("model_params"),
            "trained_at": payload.get("trained_at") or payload.get("generated_at"),
            "evaluated_at": payload.get("evaluated_at") or payload.get("generated_at"),
            "config_source": payload.get("config_source"),
            "metrics_report": self.source_path.as_posix() if self.source_path else None,
            "metrics_report_sha256": self.report_sha256(),
            "latency_methodology": payload["timings"].get("latency_methodology"),
            "batch_latency_ms": self.batch_latency_ms,
            "model_inference_single_flow_latency": self.single_flow_latency,
            "production_path_inference_latency": self.production_path_latency,
        }
