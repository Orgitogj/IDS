import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

DEFAULT_DATASET = "datasets/cicids2017_cleaned.parquet"
DEFAULT_OUT = "reports/correlation_windows.json"

BENIGN = "BENIGN"
CANDIDATE_WINDOWS = [30, 60, 120, 300, 600, 1800]
TIMESTAMP_FORMATS = ["%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"]
MIN_FLOWS_FOR_CLAIM = 100


def _clean_label(label):
    return str(label).replace("\x96", "-").strip()


def parse_timestamps(series):
    parsed = pd.to_datetime(series, format=TIMESTAMP_FORMATS[0], errors="coerce")
    missing = parsed.isna()
    if missing.any():
        parsed[missing] = pd.to_datetime(series[missing], format=TIMESTAMP_FORMATS[1],
                                          errors="coerce")
    return parsed


def gap_statistics(frame, keys):
    ordered = frame.sort_values(keys + ["Timestamp"])
    gaps = ordered.groupby(keys, sort=False)["Timestamp"].diff().dt.total_seconds()
    gaps = gaps.dropna()
    if gaps.empty:
        return None
    return {
        "gap_count": int(len(gaps)),
        "p50": float(gaps.quantile(0.50)),
        "p90": float(gaps.quantile(0.90)),
        "p95": float(gaps.quantile(0.95)),
        "p99": float(gaps.quantile(0.99)),
        "max": float(gaps.max()),
        "fraction_under": {
            str(window): float((gaps <= window).mean()) for window in CANDIDATE_WINDOWS
        },
    }


def incident_counts(frame, keys, window_seconds):
    ordered = frame.sort_values(keys + ["Timestamp"])
    gaps = ordered.groupby(keys, sort=False)["Timestamp"].diff().dt.total_seconds()
    starts = gaps.isna() | (gaps > window_seconds)
    return int(starts.sum())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Nxjerr dritaren e korrelacionit nga koherat reale te CICIDS2017.")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.is_absolute():
        dataset_path = _ML_SERVICE_ROOT / dataset_path
    if not dataset_path.exists():
        print(f"Dataset-i s'u gjet: {dataset_path}", file=sys.stderr)
        return 1

    print(f"Duke lexuar {dataset_path.name} ...")
    frame = pd.read_parquet(dataset_path,
                            columns=["Source IP", "Destination IP", "Timestamp", "Label"])
    frame["Label"] = frame["Label"].map(_clean_label)
    frame["Timestamp"] = parse_timestamps(frame["Timestamp"])

    unparsed = int(frame["Timestamp"].isna().sum())
    frame = frame.dropna(subset=["Timestamp"])
    attacks = frame[frame["Label"] != BENIGN].copy()
    print(f"  {len(frame):,} rreshta me kohe te vlefshme ({unparsed:,} te palexueshme), "
          f"{len(attacks):,} sulme")

    per_family = {}
    for family, group in attacks.groupby("Label"):
        if len(group) < MIN_FLOWS_FOR_CLAIM:
            continue
        stats = gap_statistics(group, ["Source IP"])
        if stats is None:
            continue
        stats["flows"] = int(len(group))
        stats["distinct_sources"] = int(group["Source IP"].nunique())
        stats["distinct_targets"] = int(group["Destination IP"].nunique())
        per_family[family] = stats

    print(f"\n{'family':<28}{'flows':>9}{'srcs':>7}{'p50':>9}{'p90':>10}{'p95':>10}{'p99':>12}")
    for family, stats in sorted(per_family.items(), key=lambda item: -item[1]["flows"]):
        print(f"{family:<28}{stats['flows']:>9}{stats['distinct_sources']:>7}"
              f"{stats['p50']:>9.1f}{stats['p90']:>10.1f}{stats['p95']:>10.1f}"
              f"{stats['p99']:>12.1f}")

    print(f"\nSa incidente do te dilnin per (Source IP, familje) me dritare te ndryshme:")
    print(f"{'window(s)':<12}{'incidents':>12}{'flows/incident':>18}{'reduction':>12}")
    collapse = {}
    total_attack_flows = int(len(attacks))
    for window in CANDIDATE_WINDOWS:
        count = incident_counts(attacks, ["Source IP", "Label"], window)
        collapse[str(window)] = {
            "incidents": count,
            "flows_per_incident": total_attack_flows / count if count else 0.0,
            "reduction_factor": total_attack_flows / count if count else 0.0,
        }
        print(f"{window:<12}{count:>12,}{total_attack_flows / count:>18.1f}"
              f"{total_attack_flows / count:>11.0f}x")

    coverage = {
        str(window): float(np.mean([
            stats["fraction_under"][str(window)] for stats in per_family.values()
        ])) for window in CANDIDATE_WINDOWS
    }
    print(f"\nPjesa mesatare e hendeqeve brenda familjeje qe bien brenda dritares:")
    for window in CANDIDATE_WINDOWS:
        print(f"  {window:>5}s -> {coverage[str(window)] * 100:5.1f}%")

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "dataset": dataset_path.name,
        "correlation_key": ["source_ip", "attack_type"],
        "candidate_windows_seconds": CANDIDATE_WINDOWS,
        "min_flows_for_claim": MIN_FLOWS_FOR_CLAIM,
        "total_attack_flows": total_attack_flows,
        "unparsed_timestamps": unparsed,
        "per_family_gap_seconds": per_family,
        "incident_collapse": collapse,
        "mean_gap_coverage": coverage,
        "protocol": "Gaps are the time between consecutive flows of the same attack family "
                    "from the same source IP, taken from the original CICIDS2017 capture "
                    "timestamps. An idle gap larger than the window closes an incident.",
    }

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = _ML_SERVICE_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1)

    print(f"\nU ruajt: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
