import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.replay.feature_derivation import DERIVATIONS, NOT_DERIVABLE

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_DATASET = "datasets/cicids2017_cleaned.parquet"
DEFAULT_OUT = "reports/derivation_verification.json"
DEFAULT_SAMPLE = 100_000
RELATIVE_TOLERANCE = 1e-6
REGRESSION_MARGIN = 0.01


def _matches(actual, predicted):
    if predicted is None:
        return False
    if math.isnan(actual) or math.isinf(actual):
        return False
    return abs(actual - predicted) <= RELATIVE_TOLERANCE * max(abs(actual), 1.0)


def verify(frame) -> dict:
    results = {}

    for feature, rule in DERIVATIONS.items():
        needed = list(rule["inputs"])
        subset = frame[needed + [feature]]
        records = subset.to_dict("records")

        matched = 0
        comparable = 0
        for record in records:
            actual = record[feature]
            if actual is None or math.isnan(actual) or math.isinf(actual):
                continue
            comparable += 1
            if _matches(actual, rule["function"](record)):
                matched += 1

        measured = matched / comparable if comparable else 0.0
        claimed = rule["exact_rate"]
        regressed = measured < claimed - REGRESSION_MARGIN

        results[feature] = {
            "inputs": needed,
            "claimed_exact_rate": claimed,
            "measured_exact_rate": round(measured, 6),
            "comparable_rows": comparable,
            "matched_rows": matched,
            "regressed": regressed,
            "note": rule["note"],
        }

        status = "REGRESSION" if regressed else "ok"
        print(f"  {feature:<28} claimed={claimed:.4f}  measured={measured:.4f}  [{status}]")

    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verifikon rregullat e derivimit te features kunder dataset-it te trajnimit.")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--sample", type=int, default=DEFAULT_SAMPLE)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    if not dataset_path.is_absolute():
        dataset_path = _ML_SERVICE_ROOT / dataset_path
    if not dataset_path.exists():
        print(f"Dataset-i s'u gjet: {dataset_path}", file=sys.stderr)
        return 1

    needed = set()
    for feature, rule in DERIVATIONS.items():
        needed.add(feature)
        needed.update(rule["inputs"])

    print(f"Duke lexuar {dataset_path.name} ({len(needed)} kolona) ...")
    frame = pd.read_parquet(dataset_path, columns=sorted(needed))
    if args.sample and args.sample < len(frame):
        frame = frame.sample(n=args.sample, random_state=args.seed)
    print(f"  {len(frame):,} rreshta ne kampion\n")

    results = verify(frame)
    regressions = [feature for feature, result in results.items() if result["regressed"]]

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "dataset": dataset_path.name,
        "sample_rows": int(len(frame)),
        "seed": args.seed,
        "relative_tolerance": RELATIVE_TOLERANCE,
        "regression_margin": REGRESSION_MARGIN,
        "derivations": results,
        "not_derivable": NOT_DERIVABLE,
        "regressions": regressions,
    }

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = _ML_SERVICE_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1)

    print(f"\nU ruajt: {out_path}")
    if regressions:
        print(f"REGRESION ne {len(regressions)} rregulla: {', '.join(regressions)}", file=sys.stderr)
        return 1
    print(f"{len(results)} rregulla derivimi u verifikuan, {len(NOT_DERIVABLE)} te padrejtueshme.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
