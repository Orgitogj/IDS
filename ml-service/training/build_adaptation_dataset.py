import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

from app.live import lab_runner, manifest as manifest_module, protocol
from training.pipeline import domain_adaptation as da

CFG = _ML_SERVICE_ROOT / "training" / "configs" / "live"
OUT = _ML_SERVICE_ROOT / "reports" / "domain_adaptation" / "data"
RUNS = OUT / "runs"

BASE_MANIFEST = {
    "benign": CFG / "lab-v1-benign-001.yaml",
    "portscan": CFG / "lab-v1-portscan-001.yaml",
    "ssh": CFG / "lab-v1-ssh-bruteforce-001.yaml",
}

HISTORICAL = {
    "benign": "lab-v1-benign-001",
    "portscan": "lab-v1-portscan-001",
    "ssh": "lab-v1-ssh-bruteforce-001",
}

SUPPORT_FLOOR = {"benign": 300, "portscan": 300, "ssh": 30}


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path):
    if not Path(path).exists():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def adaptation_manifest(scenario, run_id):
    import yaml
    payload = yaml.safe_load(open(BASE_MANIFEST[scenario], encoding="utf-8"))
    payload["run_id"] = run_id
    payload["scenario_description"] = (
        f"adaptation run for scenario '{payload['scenario_id']}' (role=ADAPTATION); "
        f"same procedure as the historical accepted run")
    payload.pop("stopping_condition", None)
    return manifest_module.validate(payload, source=f"adaptation:{run_id}")


def process(run_id, scenario, capture_csv, pcap_path=None, packet_capture=True,
            capture_started=None, capture_stopped=None):
    model, label_encoder, feature_columns, identity = lab_runner.load_frozen_model(
        _ML_SERVICE_ROOT / "models")
    mani = adaptation_manifest(scenario, run_id)
    validator = lab_runner.build_validator(feature_columns)

    flows = []
    with open(capture_csv, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            record, _ = lab_runner.process_row(row, mani, model, label_encoder,
                                               feature_columns, validator, identity)
            flows.append(record)

    valid = [f for f in flows if f["validation_status"] == protocol.STATUS_VALID]
    evaluable = [f for f in valid
                 if f["expected_binary_label"] in protocol.EXPECTED_BINARY_LABELS]
    attack = [f for f in evaluable if f["expected_binary_label"] == "ATTACK"]
    benign = [f for f in evaluable if f["expected_binary_label"] == "BENIGN"]
    unlabelled = [f for f in flows
                  if f["expected_binary_label"] not in protocol.EXPECTED_BINARY_LABELS]
    model_a_flagged = sum(1 for f in attack
                          if str(f.get("predicted_label")) != "BENIGN")

    floor = SUPPORT_FLOOR[scenario]
    support_metric = len(benign) if scenario == "benign" else len(attack)
    status = "ACCEPTED" if support_metric >= floor else "INVALID_LOW_SUPPORT"

    run_dir = RUNS / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "predictions.csv", "w", newline="", encoding="utf-8") as handle:
        from app.live.session import FLOW_FIELDS
        w = csv.DictWriter(handle, fieldnames=FLOW_FIELDS, extrasaction="ignore")
        w.writeheader()
        for i, f in enumerate(flows, 1):
            row = dict(f)
            row["flow_index"] = i
            errs = row.get("validation_errors")
            if isinstance(errs, (list, tuple)):
                row["validation_errors"] = "; ".join(str(x) for x in errs)
            w.writerow(row)

    provenance = {
        "run_id": run_id, "experiment_id": mani.experiment_id,
        "scenario_id": mani.scenario_id, "scenario": scenario,
        "role": da.ADAPTATION,
        "ground_truth_binary_primary": mani.expected_binary_label,
        "expected_family": mani.expected_family,
        "expected_label": mani.expected_label,
        "extractor": da.EXTRACTOR,
        "feature_schema": identity["feature_schema"],
        "model_a_identity": identity,
        "capture_started_utc": capture_started,
        "capture_stopped_utc": capture_stopped,
        "packet_capture_available": bool(packet_capture),
        "pcap_path": str(pcap_path) if pcap_path else None,
        "pcap_sha256": sha256_file(pcap_path) if pcap_path else None,
        "flow_csv_path": str(capture_csv),
        "flow_csv_sha256": sha256_file(capture_csv),
        "counts": {
            "total_flows": len(flows), "valid_flows": len(valid),
            "evaluable_flows": len(evaluable), "attack_flows": len(attack),
            "benign_flows": len(benign), "unlabelled_flows": len(unlabelled),
        },
        "support_floor": floor, "support_metric": support_metric,
        "acceptance_status": status,
        "model_a_descriptive_only": {
            "note": "Model A predictions are descriptive; they do not affect acceptance",
            "attack_flows_flagged_by_model_a": model_a_flagged,
        },
        "written_at": utc_now(),
    }
    with open(run_dir / "provenance.json", "w", encoding="utf-8") as handle:
        json.dump(provenance, handle, indent=1)
    return provenance


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--scenario", required=True, choices=["benign", "portscan", "ssh"])
    p.add_argument("--capture-csv", required=True)
    p.add_argument("--pcap", default=None)
    p.add_argument("--capture-started", default=None)
    p.add_argument("--capture-stopped", default=None)
    args = p.parse_args()

    prov = process(args.run_id, args.scenario, args.capture_csv, pcap_path=args.pcap,
                   packet_capture=bool(args.pcap),
                   capture_started=args.capture_started,
                   capture_stopped=args.capture_stopped)
    c = prov["counts"]
    print(f"{args.run_id}: status={prov['acceptance_status']} total={c['total_flows']} "
          f"valid={c['valid_flows']} attack={c['attack_flows']} benign={c['benign_flows']} "
          f"unlabelled={c['unlabelled_flows']} support={prov['support_metric']}/"
          f"{prov['support_floor']}")
    print(f"  pcap_sha256={prov['pcap_sha256']}")
    print(f"  csv_sha256={prov['flow_csv_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
