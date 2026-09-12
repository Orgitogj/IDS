import csv
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

from training.pipeline import domain_adaptation as da

OUT = _ML_SERVICE_ROOT / "reports" / "domain_adaptation" / "data"
RUNS = OUT / "runs"
LIVE = _ML_SERVICE_ROOT / "reports" / "live_evaluation" / "runs"

HISTORICAL = {
    "lab-v1-benign-001": "benign",
    "lab-v1-portscan-001": "portscan",
    "lab-v1-ssh-bruteforce-001": "ssh",
}


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def historical_entry(run_id, scenario):
    metrics = json.load(open(LIVE / run_id / "metrics.json", encoding="utf-8"))
    counts = metrics["counts"]
    return {
        "run_id": run_id, "scenario": scenario, "role": da.ADAPTATION,
        "source": "historical accepted Model-A run, registered as adaptation",
        "packet_capture_available": False,
        "pcap_sha256": None,
        "flow_csv_sha256": None,
        "total_flows": counts["flow_count"], "valid_flows": counts["valid_flow_count"],
        "evaluable_flows": counts["evaluable_flow_count"],
        "attack_flows": metrics["binary"].get("attack_flows", 0),
        "benign_flows": metrics["binary"].get("benign_flows", 0),
        "unlabelled_flows": counts["unlabelled_flow_count"],
        "acceptance_status": "ACCEPTED",
        "note": "Model-A historical evaluation files are NOT modified",
    }


def new_entries():
    out = []
    if not RUNS.exists():
        return out
    for d in sorted(RUNS.iterdir()):
        prov = d / "provenance.json"
        if not prov.exists():
            continue
        p = json.load(open(prov, encoding="utf-8"))
        c = p["counts"]
        out.append({
            "run_id": p["run_id"], "scenario": p["scenario"], "role": da.ADAPTATION,
            "source": "new adaptation run",
            "packet_capture_available": p["packet_capture_available"],
            "pcap_sha256": p["pcap_sha256"], "flow_csv_sha256": p["flow_csv_sha256"],
            "total_flows": c["total_flows"], "valid_flows": c["valid_flows"],
            "evaluable_flows": c["evaluable_flows"], "attack_flows": c["attack_flows"],
            "benign_flows": c["benign_flows"], "unlabelled_flows": c["unlabelled_flows"],
            "acceptance_status": p["acceptance_status"],
        })
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    entries = [historical_entry(r, s) for r, s in HISTORICAL.items()] + new_entries()
    accepted = [e for e in entries if e["acceptance_status"] == "ACCEPTED"]

    manifest = {
        "schema_version": 1, "protocol_version": da.PROTOCOL_VERSION,
        "generated_at": utc_now(), "role": da.ADAPTATION,
        "extractor": da.EXTRACTOR, "feature_schema": da.MODEL_A["feature_schema"],
        "model_b_exists": False, "final_evaluation_runs_exist": False,
        "runs": entries, "n_runs": len(entries), "n_accepted": len(accepted),
    }
    with open(OUT / "adaptation_manifest.json", "w", encoding="utf-8") as h:
        json.dump(manifest, h, indent=1)

    with open(OUT / "run_inventory.csv", "w", newline="", encoding="utf-8") as h:
        fn = ["run_id", "scenario", "role", "packet_capture_available",
              "acceptance_status", "total_flows", "valid_flows", "attack_flows",
              "benign_flows", "unlabelled_flows", "flow_csv_sha256", "pcap_sha256"]
        w = csv.DictWriter(h, fieldnames=fn, extrasaction="ignore")
        w.writeheader(); w.writerows(entries)

    per_scen = {}
    for e in accepted:
        per_scen.setdefault(e["scenario"], []).append(e)
    flow_rows = []
    for scen, es in sorted(per_scen.items()):
        supports = [e["benign_flows"] if scen == "benign" else e["attack_flows"]
                    for e in es]
        flow_rows.append({
            "scenario": scen, "run_count": len(es),
            "total_flows": sum(e["total_flows"] for e in es),
            "valid_flows": sum(e["valid_flows"] for e in es),
            "evaluable_flows": sum(e["evaluable_flows"] for e in es),
            "attack_flows": sum(e["attack_flows"] for e in es),
            "benign_flows": sum(e["benign_flows"] for e in es),
            "unlabelled_flows": sum(e["unlabelled_flows"] for e in es),
            "min_support": min(supports), "max_support": max(supports),
            "mean_support": round(statistics.fmean(supports), 1),
            "median_support": statistics.median(supports),
        })
    with open(OUT / "flow_counts.csv", "w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=list(flow_rows[0].keys()))
        w.writeheader(); w.writerows(flow_rows)

    total_benign = sum(e["benign_flows"] for e in accepted)
    total_attack = sum(e["attack_flows"] for e in accepted)
    portscan_attack = sum(e["attack_flows"] for e in accepted
                          if e["scenario"] == "portscan")
    ssh_attack = sum(e["attack_flows"] for e in accepted if e["scenario"] == "ssh")
    class_dist = {
        "schema_version": 1, "role": da.ADAPTATION, "rebalanced": False,
        "raw_binary": {"BENIGN": total_benign, "ATTACK": total_attack},
        "attack_by_family": {"PortScan": portscan_attack, "Brute Force": ssh_attack},
        "note": "raw collected distribution; not rebalanced",
    }
    with open(OUT / "class_distribution.json", "w", encoding="utf-8") as h:
        json.dump(class_dist, h, indent=1)

    with open(OUT / "capture_hashes.json", "w", encoding="utf-8") as h:
        json.dump({e["run_id"]: {"flow_csv_sha256": e["flow_csv_sha256"],
                                 "pcap_sha256": e["pcap_sha256"],
                                 "packet_capture_available": e[
                                     "packet_capture_available"]}
                   for e in entries}, h, indent=1)

    with open(OUT / "validation_summary.json", "w", encoding="utf-8") as h:
        json.dump({"n_runs": len(entries), "n_accepted": len(accepted),
                   "n_invalid": len(entries) - len(accepted),
                   "model_b_exists": False, "final_evaluation_runs_exist": False,
                   "all_new_runs_have_pcap": all(
                       e["packet_capture_available"] for e in entries
                       if e["run_id"] not in HISTORICAL)}, h, indent=1)

    split = split_proposal(per_scen)
    with open(OUT / "model_b_split_proposal.json", "w", encoding="utf-8") as h:
        json.dump(split, h, indent=1)

    print(f"runs registered: {len(entries)} (accepted {len(accepted)})")
    print(f"raw binary: BENIGN={total_benign} ATTACK={total_attack} "
          f"(PortScan={portscan_attack} BruteForce={ssh_attack})")
    for r in flow_rows:
        print(f"  {r['scenario']:<9} runs={r['run_count']} support "
              f"min/med/max={r['min_support']}/{r['median_support']}/{r['max_support']}")
    return 0


def split_proposal(per_scen):
    train, validation = [], []
    for scen, es in sorted(per_scen.items()):
        ordered = sorted(es, key=lambda e: e["run_id"])
        for e in ordered[:-1]:
            train.append(e["run_id"])
        if ordered:
            validation.append(ordered[-1]["run_id"])
    return {
        "schema_version": 1, "protocol_version": da.PROTOCOL_VERSION,
        "rule": ("deterministic run-level split fixed before Model B training: for each "
                 "scenario, the lexicographically-last accepted run is validation, the "
                 "rest are train; no flow-level random splitting"),
        "train_runs": sorted(train), "validation_runs": sorted(validation),
        "final_test_runs": [],
        "note": "final test runs do not exist yet and must be generated post-freeze",
    }


if __name__ == "__main__":
    sys.exit(main())
