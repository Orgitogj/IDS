import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

from app.live import capture_source, capture_time, lab_runner, protocol
from app.ml.feature_validation import CONST_ZERO_IN_TRAINING, DERIVATIONS, _parse
from app.replay.feature_mapping import CICFLOWMETER_TO_CICIDS2017, META_COLUMNS

REPORTS = _ML_SERVICE_ROOT / "reports" / "live_evaluation"

VERDICT_PASS = "PASS"
VERDICT_PASS_WITH_DERIVATION = "PASS_WITH_DERIVATION"
VERDICT_BLOCKED = "BLOCKED"


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def profile(capture_path, models_dir, sample_limit=None, timezone_name=None):
    model, _, feature_columns, identity = lab_runner.load_frozen_model(models_dir)
    del model

    report = capture_source.column_report(capture_path)
    rows = report["rows"]
    if sample_limit:
        rows = rows[:sample_limit]

    mapped_names = {}
    unmapped_columns = []
    for column in report["columns"]:
        if column in META_COLUMNS:
            continue
        target = CICFLOWMETER_TO_CICIDS2017.get(column)
        if target:
            mapped_names.setdefault(target, []).append(column)
        else:
            unmapped_columns.append(column)

    required = list(feature_columns)
    present_raw = [name for name in required if name in mapped_names]
    missing_raw = [name for name in required if name not in mapped_names]
    duplicate_mappings = {name: columns for name, columns in mapped_names.items()
                          if len(columns) > 1}
    extra_mapped = sorted(set(mapped_names) - set(required))

    derivable = [name for name in missing_raw if name in DERIVATIONS and all(
        source in mapped_names for source in DERIVATIONS[name]["inputs"])]
    const_zero = [name for name in missing_raw
                  if name in CONST_ZERO_IN_TRAINING and name not in derivable]
    undecidable = [name for name in missing_raw
                   if name not in derivable and name not in const_zero]

    value_issues = {"non_numeric": {}, "nan": {}, "inf": {}, "empty": {}, "null": {}}
    inspected = 0
    for row in rows:
        inspected += 1
        for name in required:
            columns = mapped_names.get(name)
            if not columns:
                continue
            raw = row.get(columns[0])
            _, reason = _parse(raw)
            if reason is None:
                continue
            bucket = value_issues.get(reason)
            if bucket is None:
                bucket = value_issues.setdefault(reason, {})
            bucket[name] = bucket.get(name, 0) + 1

    timestamp_present = any(column in report["columns"]
                            for column in capture_time.CAPTURE_COLUMNS)
    timestamp_parsed = 0
    timestamp_failed = 0
    for row in rows:
        resolved = capture_time.resolve(row, assume_utc=not timezone_name,
                                        timezone_name=timezone_name)
        if resolved["capture_timestamp_source"] == protocol.CAPTURE_TIME_EXACT:
            timestamp_parsed += 1
        else:
            timestamp_failed += 1

    selector_fields = {field: field in report["columns"]
                       for field in ("src_ip", "dst_ip", "src_port", "dst_port",
                                     "protocol")}

    if undecidable:
        verdict = VERDICT_BLOCKED
    elif derivable or const_zero:
        verdict = VERDICT_PASS_WITH_DERIVATION
    else:
        verdict = VERDICT_PASS

    return {
        "schema_version": 1,
        "experiment_type": "live_lab",
        "report_kind": "real_capture_feature_profile",
        "protocol_version": protocol.PROTOCOL_VERSION,
        "generated_at": utc_now(),
        "smoke_test": True,
        "exclude_from_thesis_metrics": True,
        "note": ("Setup and profiling capture only. It produces no thesis metric and no "
                 "prediction is scored from it."),
        "model": identity,
        "feature_schema": identity["feature_schema"],
        "required_feature_count": len(required),
        "capture": {
            "path": report["path"],
            "row_count": report["row_count"],
            "rows_inspected": inspected,
            "column_count": report["column_count"],
            "duplicate_columns_in_capture": report["duplicate_columns"],
            "malformed_lines": report["malformed_lines"],
        },
        "presence": {
            "present_raw_count": len(present_raw),
            "missing_raw_count": len(missing_raw),
            "present_raw": present_raw,
            "missing_raw": missing_raw,
        },
        "derivation": {
            "derivable_from_other_columns": derivable,
            "const_zero_in_training": const_zero,
            "not_defensibly_obtainable": undecidable,
            "policy": ("Missing features are reported here as missing. This profile "
                       "never patches a value; derivation and constant-zero fill are "
                       "listed as what the strict validator would do, so the decision "
                       "stays explicit."),
        },
        "extra": {
            "unmapped_capture_columns": unmapped_columns,
            "mapped_but_not_in_schema": extra_mapped,
            "duplicate_mappings": duplicate_mappings,
            "policy": protocol.EXTRA_FEATURE_POLICY,
        },
        "values": {key: dict(sorted(value.items())) for key, value in value_issues.items()
                   if value},
        "ordering": {
            "frozen_schema_order": required,
            "ordering_is_enforced_by": ("projection onto feature_names_in_ of the frozen "
                                        "artifact; capture column order is irrelevant"),
        },
        "timestamp": {
            "capture_column_present": timestamp_present,
            "rows_with_exact_capture_time": timestamp_parsed,
            "rows_falling_back_to_approximation": timestamp_failed,
            "candidate_columns": capture_time.CAPTURE_COLUMNS,
            "declared_timezone": timezone_name or "UTC (assumed)",
        },
        "ground_truth_selector_fields": selector_fields,
        "verdict": verdict,
    }


def summarise(report):
    lines = []
    lines.append(f"verdict                     {report['verdict']}")
    lines.append(f"feature schema              {report['feature_schema']}")
    lines.append(f"required features           {report['required_feature_count']}")
    lines.append(f"capture rows                {report['capture']['row_count']}")
    lines.append(f"capture columns             {report['capture']['column_count']}")
    lines.append(f"present (raw)               {report['presence']['present_raw_count']}")
    lines.append(f"missing (raw)               {report['presence']['missing_raw_count']}")
    lines.append(f"  derivable                 {len(report['derivation']['derivable_from_other_columns'])}")
    lines.append(f"  const-zero in training    {len(report['derivation']['const_zero_in_training'])}")
    lines.append(f"  NOT obtainable            {len(report['derivation']['not_defensibly_obtainable'])}")
    lines.append(f"duplicate capture columns   {report['capture']['duplicate_columns_in_capture']}")
    lines.append(f"unmapped capture columns    {len(report['extra']['unmapped_capture_columns'])}")
    lines.append(f"timestamp column present    {report['timestamp']['capture_column_present']}")
    lines.append(f"rows with exact capture ts  {report['timestamp']['rows_with_exact_capture_time']}")
    for reason, counts in report["values"].items():
        lines.append(f"value issue {reason:<15} {sum(counts.values())} across {len(counts)} feature(s)")
    if report["derivation"]["not_defensibly_obtainable"]:
        lines.append("")
        lines.append("BLOCKED - these required features are not present and not derivable:")
        for name in report["derivation"]["not_defensibly_obtainable"]:
            lines.append(f"  - {name}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Profilizim i nje kapjeje reale kunder skemes se ngrire 78-feature")
    parser.add_argument("--capture", required=True)
    parser.add_argument("--models-dir", default="models")
    parser.add_argument("--reports-dir", default=str(REPORTS))
    parser.add_argument("--sample-limit", type=int, default=None)
    parser.add_argument("--timezone", default=None)
    parser.add_argument("--out", default="feature_profile.json")
    args = parser.parse_args()

    report = profile(args.capture, args.models_dir, args.sample_limit,
                     timezone_name=args.timezone)
    print(summarise(report))

    directory = Path(args.reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / args.out
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)
    print(f"\nU ruajt: {path}")

    return 0 if report["verdict"] != VERDICT_BLOCKED else 2


if __name__ == "__main__":
    sys.exit(main())
