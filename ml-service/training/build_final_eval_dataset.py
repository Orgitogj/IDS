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

from app.live import lab_runner, protocol
from training.build_adaptation_dataset import adaptation_manifest

OUT = _ML_SERVICE_ROOT / "reports" / "domain_adaptation" / "phase17d"
RUNS = OUT / "runs"
DATA = OUT / "data"
EXTRACTOR = {"name": "cicflowmeter", "version": "0.5.0"}

BENIGN_RUNS = ["eval-v1-benign-001", "eval-v1-benign-002", "eval-v1-benign-003"]
PORTSCAN_RUNS = ["eval-v1-portscan-001", "eval-v1-portscan-002", "eval-v1-portscan-003"]
SSH_RUNS = ["eval-v1-ssh-001", "eval-v1-ssh-002", "eval-v1-ssh-003"]
FINAL_RUNS = BENIGN_RUNS + PORTSCAN_RUNS + SSH_RUNS
SCENARIO_OF = ({r: "benign" for r in BENIGN_RUNS}
               | {r: "portscan" for r in PORTSCAN_RUNS}
               | {r: "ssh" for r in SSH_RUNS})

SUPPORT_FLOOR = {"benign": 300, "portscan": 300, "ssh": 30}

ADAPTATION_AND_VALIDATION = {
    "lab-v1-benign-001", "lab-v1-portscan-001", "lab-v1-ssh-bruteforce-001",
    "adapt-v1-benign-002", "adapt-v1-benign-003", "adapt-v1-benign-004",
    "adapt-v1-portscan-002", "adapt-v1-portscan-003", "adapt-v1-portscan-004",
    "adapt-v1-ssh-002", "adapt-v1-ssh-003", "adapt-v1-ssh-004",
}


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path):
    if path is None or not Path(path).exists():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def flow_is_valid(status):
    return status["validation_status"] == protocol.STATUS_VALID


def process(run_id, capture_csv, pcap_path=None, capture_started=None,
            capture_stopped=None, capture_attempt=1,
            traffic_procedure="phase17d_capture.sh"):
    scenario = SCENARIO_OF[run_id]
    _, _, feature_columns, _ = lab_runner.load_frozen_model(_ML_SERVICE_ROOT / "models")
    mani = adaptation_manifest(scenario, run_id)
    validator = lab_runner.build_validator(feature_columns)

    total = valid = attack = benign = unlabelled = 0
    with open(capture_csv, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            total += 1
            expected = mani.expected_for_flow(row)
            mapped = lab_runner.map_row(row)
            validation = validator.validate(mapped)
            status = lab_runner.schema_guard.status_from_validation(validation, None)
            is_valid = flow_is_valid(status)
            if is_valid:
                valid += 1
            if is_valid and expected in protocol.EXPECTED_BINARY_LABELS:
                if expected == "ATTACK":
                    attack += 1
                else:
                    benign += 1
            elif expected not in protocol.EXPECTED_BINARY_LABELS:
                unlabelled += 1

    floor = SUPPORT_FLOOR[scenario]
    support_metric = benign if scenario == "benign" else attack
    acceptance = "ACCEPTED" if support_metric >= floor else "INVALID_LOW_SUPPORT"

    csv_path = Path(capture_csv)
    csv_repr = (str(csv_path.relative_to(_ML_SERVICE_ROOT)).replace("\\", "/")
                if csv_path.is_absolute() and _ML_SERVICE_ROOT in csv_path.parents
                else str(capture_csv))

    provenance = {
        "run_id": run_id,
        "experiment_id": mani.experiment_id,
        "scenario_id": mani.scenario_id,
        "scenario": scenario,
        "role": "final_test",
        "capture_attempt": capture_attempt,
        "traffic_procedure": traffic_procedure,
        "ground_truth_binary_primary": mani.expected_binary_label,
        "expected_family": mani.expected_family,
        "expected_label": mani.expected_label,
        "ground_truth_mode": mani.mode,
        "attack_selector": mani.selector,
        "extractor": EXTRACTOR,
        "capture_started_utc": capture_started,
        "capture_stopped_utc": capture_stopped,
        "packet_capture_available": bool(pcap_path),
        "pcap_path": str(pcap_path) if pcap_path else None,
        "pcap_sha256": sha256_file(pcap_path),
        "flow_csv_path": csv_repr,
        "flow_csv_sha256": sha256_file(capture_csv),
        "counts": {
            "total_flows": total,
            "valid_flows": valid,
            "evaluable_flows": attack + benign,
            "attack_flows": attack,
            "benign_flows": benign,
            "unlabelled_flows": unlabelled,
        },
        "support_floor": floor,
        "support_metric": support_metric,
        "acceptance_status": acceptance,
        "acceptance_basis": ("capture integrity + predefined ground truth + minimum "
                             "support; independent of any model prediction"),
        "written_at": utc_now(),
    }
    run_dir = RUNS / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "provenance.json", "w", encoding="utf-8") as handle:
        json.dump(provenance, handle, indent=1)
    return provenance


def _load_provenances():
    provs = {}
    for run_id in FINAL_RUNS:
        path = RUNS / run_id / "provenance.json"
        if not path.exists():
            raise SystemExit(f"missing provenance for {run_id}; process it first")
        provs[run_id] = json.load(open(path, encoding="utf-8"))
    return provs


def seal():
    provs = _load_provenances()

    assert len(FINAL_RUNS) == 9, FINAL_RUNS
    for scenario, runs in {"benign": BENIGN_RUNS, "portscan": PORTSCAN_RUNS,
                           "ssh": SSH_RUNS}.items():
        assert len(runs) == 3, (scenario, runs)
    overlap = set(FINAL_RUNS) & ADAPTATION_AND_VALIDATION
    assert not overlap, f"final runs overlap adaptation/validation: {overlap}"

    not_accepted = [r for r in FINAL_RUNS
                    if provs[r]["acceptance_status"] != "ACCEPTED"]
    if not_accepted:
        raise SystemExit(f"cannot seal; runs not ACCEPTED: {not_accepted}")

    runs_entries = []
    inventory_rows = []
    capture_hashes = {}
    totals = {"total": 0, "evaluable": 0, "attack": 0, "benign": 0, "unlabelled": 0}
    for run_id in FINAL_RUNS:
        p = provs[run_id]
        c = p["counts"]
        runs_entries.append({
            "run_id": run_id,
            "scenario": p["scenario"],
            "scenario_id": p["scenario_id"],
            "role": "final_test",
            "capture_started_utc": p["capture_started_utc"],
            "capture_stopped_utc": p["capture_stopped_utc"],
            "extractor": p["extractor"],
            "ground_truth_mode": p["ground_truth_mode"],
            "attack_selector": p["attack_selector"],
            "ground_truth_binary_primary": p["ground_truth_binary_primary"],
            "expected_family": p["expected_family"],
            "pcap_sha256": p["pcap_sha256"],
            "flow_csv_sha256": p["flow_csv_sha256"],
            "total_flows": c["total_flows"],
            "valid_flows": c["valid_flows"],
            "evaluable_flows": c["evaluable_flows"],
            "attack_flows": c["attack_flows"],
            "benign_flows": c["benign_flows"],
            "unlabelled_flows": c["unlabelled_flows"],
            "support_floor": p["support_floor"],
            "support_metric": p["support_metric"],
            "acceptance_status": p["acceptance_status"],
        })
        capture_hashes[run_id] = {
            "flow_csv_sha256": p["flow_csv_sha256"],
            "pcap_sha256": p["pcap_sha256"],
            "packet_capture_available": p["packet_capture_available"],
        }
        inventory_rows.append([
            run_id, p["scenario"], "final_test", p["packet_capture_available"],
            p["acceptance_status"], c["total_flows"], c["valid_flows"],
            c["evaluable_flows"], c["attack_flows"], c["benign_flows"],
            c["unlabelled_flows"], p["support_metric"], p["support_floor"],
            p["flow_csv_sha256"], p["pcap_sha256"],
        ])
        totals["total"] += c["total_flows"]
        totals["evaluable"] += c["evaluable_flows"]
        totals["attack"] += c["attack_flows"]
        totals["benign"] += c["benign_flows"]
        totals["unlabelled"] += c["unlabelled_flows"]

    manifest = {
        "schema_version": 1,
        "protocol_version": "phase17d-final-eval-v1",
        "role": "final_test",
        "generated_at": utc_now(),
        "extractor": EXTRACTOR,
        "final_test_run_ids": list(FINAL_RUNS),
        "n_runs": len(FINAL_RUNS),
        "scenarios": {"benign": BENIGN_RUNS, "portscan": PORTSCAN_RUNS,
                      "ssh": SSH_RUNS},
        "disjoint_from_adaptation_and_validation": True,
        "raw_binary_distribution": {
            "BENIGN": totals["benign"], "ATTACK": totals["attack"]},
        "totals": totals,
        "runs": runs_entries,
    }

    DATA.mkdir(parents=True, exist_ok=True)
    manifest_bytes = (json.dumps(manifest, indent=1, sort_keys=True) + "\n").encode()
    (DATA / "final_test_manifest.json").write_bytes(manifest_bytes)
    manifest_sha = sha256_bytes(manifest_bytes)

    seal_doc = {
        "schema_version": 1,
        "protocol_version": "phase17d-final-eval-v1",
        "sealed": True,
        "sealed_at": utc_now(),
        "manifest_sha256": manifest_sha,
        "manifest_file": "data/final_test_manifest.json",
        "manifest_hash_algorithm": "sha256 over json.dumps(indent=1, sort_keys=True)+\\n",
        "final_test_run_ids": list(FINAL_RUNS),
        "n_runs": len(FINAL_RUNS),
        "all_accepted": True,
        "disjoint_from_adaptation_and_validation": True,
        "raw_binary_distribution": {
            "BENIGN": totals["benign"], "ATTACK": totals["attack"]},
        "sealed_before_prediction": True,
    }
    (DATA / "final_test_seal.json").write_text(
        json.dumps(seal_doc, indent=1) + "\n", encoding="utf-8")

    with open(DATA / "capture_hashes.json", "w", encoding="utf-8") as handle:
        json.dump(capture_hashes, handle, indent=1)

    with open(DATA / "run_inventory.csv", "w", newline="", encoding="utf-8") as handle:
        w = csv.writer(handle)
        w.writerow([
            "run_id", "scenario", "role", "packet_capture_available",
            "acceptance_status", "total_flows", "valid_flows", "evaluable_flows",
            "attack_flows", "benign_flows", "unlabelled_flows", "support_metric",
            "support_floor", "flow_csv_sha256", "pcap_sha256"])
        w.writerows(inventory_rows)

    return manifest, seal_doc


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("process")
    pr.add_argument("--run-id", required=True, choices=FINAL_RUNS)
    pr.add_argument("--capture-csv", required=True)
    pr.add_argument("--pcap", default=None)
    pr.add_argument("--capture-started", default=None)
    pr.add_argument("--capture-stopped", default=None)
    pr.add_argument("--attempt", type=int, default=1)
    pr.add_argument("--procedure", default="phase17d_capture.sh")
    sub.add_parser("seal")
    args = p.parse_args()

    if args.cmd == "process":
        prov = process(args.run_id, args.capture_csv, pcap_path=args.pcap,
                       capture_started=args.capture_started,
                       capture_stopped=args.capture_stopped,
                       capture_attempt=args.attempt,
                       traffic_procedure=args.procedure)
        c = prov["counts"]
        print(f"{args.run_id}: {prov['acceptance_status']} total={c['total_flows']} "
              f"valid={c['valid_flows']} attack={c['attack_flows']} "
              f"benign={c['benign_flows']} unlabelled={c['unlabelled_flows']} "
              f"support={prov['support_metric']}/{prov['support_floor']}")
        return 0

    if args.cmd == "seal":
        _, seal_doc = seal()
        print(f"SEALED n_runs={seal_doc['n_runs']} "
              f"BENIGN={seal_doc['raw_binary_distribution']['BENIGN']} "
              f"ATTACK={seal_doc['raw_binary_distribution']['ATTACK']} "
              f"manifest_sha256={seal_doc['manifest_sha256']}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
