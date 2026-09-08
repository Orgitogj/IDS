import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

from app.live import compat, lab_runner

OUT_DIR = (_ML_SERVICE_ROOT / "reports" / "live_evaluation" / "diagnostics"
           / "extractor_parity")
COMPAT = (_ML_SERVICE_ROOT / "reports" / "live_evaluation" / "diagnostics"
          / "feature_contract_compatibility")

IDENTICAL = "IDENTICAL_SEMANTICS_CONFIRMED"
LIKELY = "LIKELY_EQUIVALENT"
UNIT = "UNIT_DIFFERENCE_ONLY"
AGGREGATION = "AGGREGATION_DIFFERENCE"
DIRECTION = "FLOW_DIRECTION_DIFFERENCE"
FLAG = "FLAG_DEFINITION_DIFFERENCE"
TIMEOUT = "TIMEOUT_DEPENDENT"
IMPL = "IMPLEMENTATION_DIFFERENCE"
UNRESOLVED = "UNRESOLVED"

PY = "cicflowmeter-0.5.0 (python, source-verified)"
JAVA = "CICFlowMeter (java, CICIDS2017; documented, not locally executable)"

LEN_PACKET = ("python uses len(packet) = full captured frame incl. Ethernet/IP/TCP "
              "headers; the original tool's packet-length basis is documented but not "
              "locally verifiable")
HEADER_IP_ONLY = ("python _header_size = IP header only (ihl*4), excludes the TCP "
                  "header; original header length conventionally includes the transport "
                  "header")
FLAG_PKT_COUNT = ("python counts packets bearing the flag (substring match on scapy "
                  "flag string), both directions; original flag-count semantics/"
                  "segmentation differ (e.g. canonical PSH median 1 vs lab 15)")
SUBFLOW_COPY = ("python copies subflow_* directly from flow totals (no subflow "
                "segmentation); original derives subflow values from subflow windows")
SEG_DUP = ("python sets segment-size-avg = mean packet length; inherits the len(packet) "
           "basis")
CWR_QUIRK = ("python sets cwr_flag_count = fwd_urg_flags (a source-level quirk), not an "
             "actual CWR count")
IAT_SECONDS = ("python derives durations/IAT from scapy packet.time in seconds; canonical "
               "is microseconds (confirmed by lab-feature-compat-v1)")


def finding(status, evidence, note=""):
    return {"semantic_status": status, "python_evidence": evidence, "note": note}


FINDINGS = {}


def _set(names, status, evidence, note=""):
    for n in names:
        FINDINGS[n] = finding(status, evidence, note)


_set(["Flow Duration", "Flow IAT Mean", "Flow IAT Std", "Flow IAT Max",
      "Fwd IAT Total", "Fwd IAT Mean", "Fwd IAT Std", "Fwd IAT Max",
      "Bwd IAT Total", "Bwd IAT Mean", "Bwd IAT Std", "Bwd IAT Max", "Bwd IAT Min"],
     UNIT, IAT_SECONDS, "confirmed and corrected by lab-feature-compat-v1")
_set(["Flow IAT Min", "Fwd IAT Min"], UNIT, IAT_SECONDS,
     "all-zero in laboratory captures; unit applies but unverifiable from lab data")
_set(["Active Mean", "Active Std", "Active Max", "Active Min",
      "Idle Mean", "Idle Std", "Idle Max", "Idle Min"], TIMEOUT,
     "python active/idle use an activity timeout (constants.py) and packet.time seconds",
     "all-zero in laboratory short flows; timeout convention and unit both differ")

_set(["Fwd Packet Length Max", "Fwd Packet Length Min", "Fwd Packet Length Mean",
      "Fwd Packet Length Std", "Bwd Packet Length Max", "Bwd Packet Length Min",
      "Bwd Packet Length Mean", "Bwd Packet Length Std", "Max Packet Length",
      "Min Packet Length", "Packet Length Mean", "Packet Length Std",
      "Packet Length Variance", "Total Length of Fwd Packets",
      "Total Length of Bwd Packets", "Average Packet Size"], IMPL, LEN_PACKET,
     "candidate explanation for a large part of the packet-length residual shift")
_set(["Avg Fwd Segment Size", "Avg Bwd Segment Size"], IMPL, SEG_DUP)
_set(["Subflow Fwd Bytes", "Subflow Bwd Bytes"], AGGREGATION, SUBFLOW_COPY,
     "also inherits the len(packet) basis")
_set(["Subflow Fwd Packets", "Subflow Bwd Packets"], AGGREGATION, SUBFLOW_COPY)

_set(["Fwd Header Length", "Bwd Header Length", "Fwd Header Length.1",
      "min_seg_size_forward", "Fwd Seg Size Min"], IMPL, HEADER_IP_ONLY)

_set(["FIN Flag Count", "SYN Flag Count", "RST Flag Count", "PSH Flag Count",
      "ACK Flag Count", "URG Flag Count", "ECE Flag Count", "Fwd PSH Flags",
      "Bwd PSH Flags", "Fwd URG Flags", "Bwd URG Flags"], FLAG, FLAG_PKT_COUNT)
_set(["CWE Flag Count"], IMPL, CWR_QUIRK, "source-level quirk in python cicflowmeter")

_set(["Total Fwd Packets", "Total Backward Packets"], LIKELY,
     "python counts packets per direction; equivalent up to flow-segmentation differences")
_set(["act_data_pkt_fwd", "Fwd Act Data Packets"], LIKELY,
     "python counts forward packets with non-empty payload")
_set(["Init_Win_bytes_forward", "Init_Win_bytes_backward",
      "Init Fwd Win Bytes", "Init Bwd Win Bytes"], LIKELY,
     "python uses TCP window of first packet per direction")
_set(["Down/Up Ratio", "Fwd Packets/s", "Bwd Packets/s"], LIKELY,
     "python computes per-second rate = count/duration_seconds")
_set(["Flow Packets/s"], LIKELY,
     "python packets/second = total/duration_seconds; per-second in both tools")
_set(["Flow Bytes/s"], IMPL,
     "python bytes/second numerator uses len(packet) full-frame bytes",
     "per-second in both, but byte basis inherits the len(packet) difference")

_set(["Fwd Avg Bytes/Bulk", "Fwd Avg Packets/Bulk", "Fwd Avg Bulk Rate",
      "Bwd Avg Bytes/Bulk", "Bwd Avg Packets/Bulk", "Bwd Avg Bulk Rate",
      "Fwd Bytes/Bulk Avg", "Fwd Packet/Bulk Avg", "Fwd Bulk Rate Avg",
      "Bwd Bytes/Bulk Avg", "Bwd Packet/Bulk Avg", "Bwd Bulk Rate Avg"], UNRESOLVED,
     "python has its own bulk-detection logic; original bulk semantics not locally "
     "verifiable", "near-zero in both populations")


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def residual_ks(scenario):
    path = COMPAT / f"residual_feature_shift_{scenario}.csv"
    out = {}
    if not path.exists():
        return out
    with open(path, encoding="utf-8") as handle:
        for r in csv.DictReader(handle):
            def num(x):
                return None if x in ("", "None") else float(x)
            out[r["feature"]] = {
                "ks_before": num(r["ks_before"]), "ks_after": num(r["ks_after"]),
                "outside_after": num(r["outside_p01_p99_after"]),
            }
    return out


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    model, _, feature_columns, identity = lab_runner.load_frozen_model(
        _ML_SERVICE_ROOT / "models")

    availability = {
        "generated_at": utc_now(),
        "case": "CASE_C",
        "case_description": ("no exact accepted-run PCAP was retained; the accepted runs "
                             "used cicflowmeter live capture (-i eth0 -c csv) which writes "
                             "CSV only, not packets"),
        "retained_pcap_portscan": False,
        "retained_pcap_ssh": False,
        "pcap_search": ("only metasploit-framework sample/test pcaps exist on the Kali "
                        "guest; none correspond to lab-v1-portscan-001 or "
                        "lab-v1-ssh-bruteforce-001"),
        "cicflowmeter_live_mode_writes_pcap": False,
        "java_cicflowmeter_available": False,
        "java_cicflowmeter_note": ("no CICFlowMeter jar or source in the repository or "
                                   "host; a JRE (openjdk 17) exists but no extractor; "
                                   "installing an external binary was out of scope"),
        "python_cicflowmeter_source_available": True,
        "python_cicflowmeter_source_retained_at": (
            "reports/live_evaluation/diagnostics/extractor_parity/"
            "cicflowmeter_0_5_0_source/"),
        "same_pcap_empirical_parity_possible": False,
        "audit_type": "source_and_semantic_implementation_audit_only",
    }
    with open(OUT_DIR / "availability_audit.json", "w", encoding="utf-8") as h:
        json.dump(availability, h, indent=1)

    versions = {
        "python_extractor": {"name": "cicflowmeter", "version": "0.5.0",
                             "evidence": PY, "constants": {"EXPIRED_UPDATE": 240,
                             "CLUMP_TIMEOUT": 1, "ACTIVE_TIMEOUT": 5,
                             "PACKETS_PER_GC": 1000}},
        "java_extractor": {"name": "CICFlowMeter", "version": "unavailable_locally",
                           "evidence": JAVA},
        "canonical_dataset": "CICIDS2017 (features produced by the original CICFlowMeter)",
    }
    with open(OUT_DIR / "extractor_versions.json", "w", encoding="utf-8") as h:
        json.dump(versions, h, indent=1)

    ssh_ks = residual_ks("ssh")
    ps_ks = residual_ks("portscan")

    rows = []
    for name in feature_columns:
        f = FINDINGS.get(name, finding(UNRESOLVED, "not individually audited", ""))
        s = ssh_ks.get(name, {})
        p = ps_ks.get(name, {})
        rows.append({
            "feature": name,
            "semantic_status": f["semantic_status"],
            "python_side_evidence": f["python_evidence"],
            "java_side": "documented, not locally verifiable",
            "note": f["note"],
            "ssh_residual_ks_after": s.get("ks_after"),
            "ssh_outside_p01_p99_after": s.get("outside_after"),
            "portscan_residual_ks_after": p.get("ks_after"),
        })

    with open(OUT_DIR / "semantic_parity.csv", "w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    from collections import Counter
    status_counts = Counter(r["semantic_status"] for r in rows)

    importances = model.feature_importances_
    order = importances.argsort()[::-1][:15]
    model_relevant = []
    for rank_i, pos in enumerate(order):
        name = feature_columns[pos]
        r = next(x for x in rows if x["feature"] == name)
        model_relevant.append({
            "feature": name, "importance_rank": rank_i,
            "importance": float(importances[pos]),
            "semantic_status": r["semantic_status"],
            "ssh_residual_ks_after": r["ssh_residual_ks_after"],
        })
    with open(OUT_DIR / "model_relevant_parity.csv", "w", newline="",
              encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=list(model_relevant[0].keys()))
        w.writeheader(); w.writerows(model_relevant)

    implementation_like = {IMPL, AGGREGATION, FLAG, DIRECTION, TIMEOUT, UNIT}
    mr_impl = sum(1 for m in model_relevant
                  if m["semantic_status"] in implementation_like)

    summary = {
        "schema_version": 1, "diagnostic": "extractor_parity",
        "generated_at": utc_now(), "case": "CASE_C",
        "same_pcap_empirical_parity_possible": False,
        "audit_type": "source_and_semantic_implementation_audit_only",
        "frozen_model": identity,
        "no_retraining_no_tuning_no_shap_no_llm": True,
        "n_features": len(feature_columns),
        "semantic_status_counts": dict(status_counts),
        "model_relevant_top15_with_implementation_difference": mr_impl,
        "interpretation": {
            "portscan": "B_source_evidence_D_empirical",
            "ssh": "B_source_evidence_D_empirical",
            "explanation": ("source-verified implementation differences plausibly explain "
                            "part of the residual non-time shift (packet-length basis, "
                            "header-length basis, subflow copy, flag-count semantics), but "
                            "same-PCAP empirical parity could not be performed, so the "
                            "implementation vs true-domain split cannot be quantified"),
        },
        "five_distinct_concepts": {
            "1_benchmark": "random-v2 Macro F1 0.8805600093815694",
            "2_original_lab": "PortScan 2/1362 (0.00147); SSH 0/69 (0.0)",
            "3_unit_corrected": "PortScan 2/1362; SSH 0/69 (unchanged)",
            "4_extractor_implementation_difference": ("source-confirmed on packet-length, "
                                                      "header-length, subflow, flag, CWR; "
                                                      "magnitude not empirically isolated"),
            "5_residual_traffic_domain_difference": ("cannot be separated from concept 4 "
                                                     "with retained evidence"),
        },
    }
    with open(OUT_DIR / "summary.json", "w", encoding="utf-8") as h:
        json.dump(summary, h, indent=1)

    print(f"CASE: {availability['case']} (same-PCAP empirical parity possible: "
          f"{availability['same_pcap_empirical_parity_possible']})")
    print(f"features classified: {len(rows)}")
    for k, v in sorted(status_counts.items(), key=lambda i: -i[1]):
        print(f"  {k:<34} {v}")
    print(f"top-15 model-important with an implementation-class difference: {mr_impl}/15")
    return 0


if __name__ == "__main__":
    sys.exit(main())
