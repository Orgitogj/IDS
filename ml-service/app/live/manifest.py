from pathlib import Path

import yaml

from app.live import protocol

GROUND_TRUTH_RUN_LEVEL = "run_level_uniform"
GROUND_TRUTH_SELECTOR = "per_flow_selector"
GROUND_TRUTH_MODES = [GROUND_TRUTH_RUN_LEVEL, GROUND_TRUTH_SELECTOR]

UNMATCHED_BENIGN = "BENIGN"
UNMATCHED_UNLABELLED = "UNLABELLED"
UNMATCHED_POLICIES = [UNMATCHED_BENIGN, UNMATCHED_UNLABELLED]

REQUIRED_FIELDS = ["experiment_id", "run_id", "scenario_id", "scenario_description",
                   "expected_binary_label", "ground_truth", "model", "capture", "topology"]


class ManifestError(ValueError):
    pass


class RunManifest:
    def __init__(self, payload, source=None):
        self.source = str(source) if source else None
        self.payload = payload
        self.experiment_id = payload["experiment_id"]
        self.run_id = payload["run_id"]
        self.scenario_id = payload["scenario_id"]
        self.scenario_description = payload["scenario_description"]
        self.expected_binary_label = payload["expected_binary_label"]
        self.expected_family = payload.get("expected_family")
        self.expected_label = payload.get("expected_label")
        self.attribution_mapping_declared = bool(
            payload.get("expected_family") or payload.get("expected_label"))
        self.ground_truth = payload["ground_truth"]
        self.mode = self.ground_truth["mode"]
        self.unmatched_policy = self.ground_truth.get("unmatched_policy",
                                                      UNMATCHED_UNLABELLED)
        self.selector = self.ground_truth.get("attack_selector") or {}
        self.model = payload["model"]
        self.capture = payload["capture"]
        self.capture_timezone = self.capture.get("timestamp_timezone")
        self.timestamp_assumed_utc = bool(
            self.capture.get("timestamp_assumed_utc", False))
        self.topology = payload["topology"]
        self.planned_duration_seconds = payload.get("planned_duration_seconds")
        self.stopping_condition = payload.get("stopping_condition") or {}
        self.min_valid_flows = self.stopping_condition.get("min_valid_flows")
        self.min_services = self.stopping_condition.get("min_distinct_services")
        self.planned_start = payload.get("planned_start")
        self.notes = payload.get("notes")
        self.protocol_version = payload.get("protocol_version", protocol.PROTOCOL_VERSION)
        self.smoke_test = bool(payload.get("smoke_test", False))
        self.exclude_from_thesis_metrics = bool(
            payload.get("exclude_from_thesis_metrics", self.smoke_test))

    def expected_for_flow(self, flow):
        if self.mode == GROUND_TRUTH_RUN_LEVEL:
            return self.expected_binary_label

        if self._matches_selector(flow):
            return "ATTACK"
        if self.unmatched_policy == UNMATCHED_BENIGN:
            return "BENIGN"
        return UNMATCHED_UNLABELLED

    def _matches_selector(self, flow):
        if not self.selector:
            return False

        source = self.selector.get("source_ip")
        if source and str(flow.get("src_ip") or "") != str(source):
            return False

        destination = self.selector.get("destination_ip")
        if destination and str(flow.get("dst_ip") or "") != str(destination):
            return False

        ports = self.selector.get("destination_ports")
        if ports:
            try:
                port = int(float(flow.get("dst_port") or -1))
            except (TypeError, ValueError):
                return False
            if port not in [int(value) for value in ports]:
                return False

        protocols = self.selector.get("protocols")
        if protocols:
            if str(flow.get("protocol") or "") not in [str(value) for value in protocols]:
                return False

        return True

    def to_dict(self):
        payload = dict(self.payload)
        payload["protocol_version"] = self.protocol_version
        payload["attribution_mapping_declared"] = self.attribution_mapping_declared
        payload["manifest_source"] = self.source
        return payload


def validate(payload, source=None):
    if not isinstance(payload, dict):
        raise ManifestError("manifesti duhet te jete nje mapping YAML")

    missing = [field for field in REQUIRED_FIELDS if field not in payload]
    if missing:
        raise ManifestError(f"fusha te detyrueshme mungojne: {', '.join(missing)}")

    label = payload["expected_binary_label"]
    if label not in protocol.EXPECTED_BINARY_LABELS:
        raise ManifestError(f"expected_binary_label i panjohur: {label}")

    ground_truth = payload["ground_truth"]
    if not isinstance(ground_truth, dict) or "mode" not in ground_truth:
        raise ManifestError("ground_truth duhet te kete nje 'mode'")
    if ground_truth["mode"] not in GROUND_TRUTH_MODES:
        raise ManifestError(f"ground_truth.mode i panjohur: {ground_truth['mode']}")

    unmatched = ground_truth.get("unmatched_policy", UNMATCHED_UNLABELLED)
    if unmatched not in UNMATCHED_POLICIES:
        raise ManifestError(f"unmatched_policy i panjohur: {unmatched}")

    if ground_truth["mode"] == GROUND_TRUTH_SELECTOR and not ground_truth.get(
            "attack_selector"):
        raise ManifestError(
            "mode 'per_flow_selector' kerkon nje 'attack_selector'; pa te asnje flow "
            "s'mund te etiketohet dhe e gjithe dritarja do te merrej gabimisht si sulm")

    if label == "ATTACK" and ground_truth["mode"] == GROUND_TRUTH_RUN_LEVEL and not \
            ground_truth.get("capture_is_filtered_to_scenario"):
        raise ManifestError(
            "nje run sulmi nuk mund te perdore ground truth ne nivel run-i pa deklaruar "
            "capture_is_filtered_to_scenario: te etiketosh cdo flow te dritares si ATTACK "
            "prodhon ground truth te pavlefshem kur trafiku eshte i perzier")

    capture = payload["capture"]
    if not isinstance(capture, dict):
        raise ManifestError("capture duhet te jete nje mapping")
    if not capture.get("timestamp_timezone") and not capture.get(
            "timestamp_assumed_utc"):
        raise ManifestError(
            "capture duhet te deklaroje ose timestamp_timezone ose "
            "timestamp_assumed_utc: nje kohe naive nuk riinterpretohet ne heshtje")
    if capture.get("timestamp_timezone"):
        from app.live import capture_time
        capture_time._zone(capture["timestamp_timezone"])

    model = payload["model"]
    if not isinstance(model, dict) or "name" not in model:
        raise ManifestError("model duhet te kete nje 'name'")
    if model["name"] != protocol.FROZEN_PRIMARY_MODEL["name"]:
        raise ManifestError(
            f"modeli i manifestit '{model['name']}' nuk eshte modeli primar i ngrire "
            f"'{protocol.FROZEN_PRIMARY_MODEL['name']}'")
    if model.get("feature_version") != protocol.FROZEN_PRIMARY_MODEL["feature_version"]:
        raise ManifestError(
            f"feature_version duhet te jete "
            f"{protocol.FROZEN_PRIMARY_MODEL['feature_version']}")

    return RunManifest(payload, source=source)


def load(path):
    path = Path(path)
    if not path.exists():
        raise ManifestError(f"manifesti s'u gjet: {path}")
    with open(path, encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    return validate(payload, source=path.name)


def load_all(directory):
    directory = Path(directory)
    manifests = {}
    for path in sorted(directory.glob("*.yaml")):
        manifest = load(path)
        if manifest.run_id in manifests:
            raise ManifestError(
                f"run_id i dyfishuar '{manifest.run_id}': {path.name} perplaset me "
                f"{manifests[manifest.run_id].source}")
        manifests[manifest.run_id] = manifest
    return manifests
