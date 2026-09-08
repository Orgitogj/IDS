import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from app.live import protocol

FLOW_FIELDS = [
    "run_id", "experiment_id", "scenario_id", "flow_index",
    "capture_timestamp", "capture_timestamp_source", "capture_timestamp_timezone",
    "ingested_at",
    "source_ip", "destination_ip", "source_port", "destination_port", "protocol",
    "expected_binary_label", "expected_family", "expected_label",
    "predicted_label", "prediction_confidence", "detection_class", "detection_method",
    "anomaly_score", "validation_status", "validation_errors",
    "extra_features_ignored", "feature_schema", "feature_count",
    "model_inference_latency_ms", "production_path_inference_latency_ms",
]


class RunStateError(RuntimeError):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class RunSession:
    def __init__(self, manifest, reports_dir, model_identity=None):
        self.manifest = manifest
        self.run_dir = Path(reports_dir) / "runs" / manifest.run_id
        self.model_identity = dict(model_identity or {})
        self.flows = []
        self.state = {
            "run_id": manifest.run_id,
            "experiment_id": manifest.experiment_id,
            "scenario_id": manifest.scenario_id,
            "protocol_version": manifest.protocol_version,
            "status": protocol.RUN_PLANNED,
            "planned_start": manifest.planned_start,
            "planned_duration_seconds": manifest.planned_duration_seconds,
            "actual_start": None,
            "actual_end": None,
            "flow_count": 0,
            "valid_flow_count": 0,
            "invalid_flow_count": 0,
            "prediction_count": 0,
            "unlabelled_flow_count": 0,
            "abort_reason": None,
            "smoke_test": manifest.smoke_test,
            "exclude_from_thesis_metrics": manifest.exclude_from_thesis_metrics,
        }

    def start(self):
        if self.state["status"] != protocol.RUN_PLANNED:
            raise RunStateError(
                f"vetem nje run ne {protocol.RUN_PLANNED} mund te niset; ky eshte "
                f"{self.state['status']}")
        self.state["status"] = protocol.RUN_RUNNING
        self.state["actual_start"] = utc_now()
        self._write_state()
        return self.state

    def record(self, flow):
        if self.state["status"] != protocol.RUN_RUNNING:
            raise RunStateError(
                f"flows mund te regjistrohen vetem gjate {protocol.RUN_RUNNING}; ky run "
                f"eshte {self.state['status']}")

        entry = dict(flow)
        entry.setdefault("run_id", self.manifest.run_id)
        entry.setdefault("experiment_id", self.manifest.experiment_id)
        entry.setdefault("scenario_id", self.manifest.scenario_id)
        entry["flow_index"] = len(self.flows) + 1
        entry.setdefault("ingested_at", utc_now())

        self.flows.append(entry)
        self.state["flow_count"] += 1
        if entry.get("validation_status") == protocol.STATUS_VALID:
            self.state["valid_flow_count"] += 1
        else:
            self.state["invalid_flow_count"] += 1
        if entry.get("predicted_label") is not None:
            self.state["prediction_count"] += 1
        if entry.get("expected_binary_label") not in protocol.EXPECTED_BINARY_LABELS:
            self.state["unlabelled_flow_count"] += 1
        return entry

    def stop(self):
        if self.state["status"] != protocol.RUN_RUNNING:
            raise RunStateError(
                f"vetem nje run ne {protocol.RUN_RUNNING} mund te ndalet; ky eshte "
                f"{self.state['status']}")
        self.state["actual_end"] = utc_now()
        self._write_state()
        return self.state

    def abort(self, reason):
        self.state["status"] = protocol.RUN_ABORTED
        self.state["abort_reason"] = str(reason)
        if self.state["actual_end"] is None:
            self.state["actual_end"] = utc_now()
        self._write_state()
        return self.state

    def invalidate(self, reason):
        self.state["status"] = protocol.RUN_INVALID
        self.state["abort_reason"] = str(reason)
        if self.state["actual_end"] is None:
            self.state["actual_end"] = utc_now()
        self._write_state()
        return self.state

    def finalize(self):
        if self.state["status"] not in (protocol.RUN_RUNNING, protocol.RUN_ABORTED,
                                        protocol.RUN_INVALID):
            raise RunStateError(
                f"nje run ne {self.state['status']} nuk mund te finalizohet")

        if self.state["status"] == protocol.RUN_RUNNING:
            if self.state["actual_end"] is None:
                self.state["actual_end"] = utc_now()
            self.state["status"] = protocol.RUN_COMPLETED

        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._write_manifest()
        self._write_predictions()
        self._write_state()
        return self.state

    def _write_state(self):
        self.run_dir.mkdir(parents=True, exist_ok=True)
        payload = dict(self.state)
        payload["written_at"] = utc_now()
        payload["model"] = self.model_identity
        with open(self.run_dir / "state.json", "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=1)

    def _write_manifest(self):
        payload = self.manifest.to_dict()
        payload["resolved_model"] = self.model_identity
        with open(self.run_dir / "manifest.json", "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=1)

    def _write_predictions(self):
        with open(self.run_dir / "predictions.csv", "w", newline="",
                  encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FLOW_FIELDS,
                                    extrasaction="ignore")
            writer.writeheader()
            for entry in self.flows:
                row = dict(entry)
                errors = row.get("validation_errors")
                if isinstance(errors, (list, tuple)):
                    row["validation_errors"] = "; ".join(str(item) for item in errors)
                writer.writerow(row)


def load_state(run_dir):
    path = Path(run_dir) / "state.json"
    if not path.exists():
        raise RunStateError(f"state.json mungon ne {run_dir}")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def load_flows(run_dir):
    path = Path(run_dir) / "predictions.csv"
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def is_evaluable(state):
    return state.get("status") in protocol.EVALUABLE_RUN_STATUSES


def interrupted_runs(reports_dir):
    stale = []
    root = Path(reports_dir) / "runs"
    if not root.exists():
        return stale
    for directory in sorted(root.iterdir()):
        if not (directory / "state.json").exists():
            continue
        state = load_state(directory)
        if state.get("status") in (protocol.RUN_RUNNING, protocol.RUN_PLANNED):
            stale.append({"run_id": state.get("run_id"), "status": state.get("status"),
                          "path": str(directory)})
    return stale
