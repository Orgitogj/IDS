import argparse
import csv
import difflib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from app.replay.feature_mapping import (
        CICFLOWMETER_TO_CICIDS2017,
        CICIDS2017_TO_CICFLOWMETER,
        CONST_ZERO_IN_TRAINING,
        META_COLUMNS,
    )
    from app.replay.feature_derivation import DERIVATIONS, NOT_DERIVABLE, can_derive
except ImportError:
    from feature_mapping import (
        CICFLOWMETER_TO_CICIDS2017,
        CICIDS2017_TO_CICFLOWMETER,
        CONST_ZERO_IN_TRAINING,
        META_COLUMNS,
    )
    from feature_derivation import DERIVATIONS, NOT_DERIVABLE, can_derive

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_REFERENCE = "reports/training_feature_reference.json"
DEFAULT_OUT = "reports/live_feature_profile.json"
DEFAULT_MARKDOWN = "FEATURE_COMPATIBILITY.md"
DEFAULT_FEATURE_VERSION = "cicids2017-top50-v1"

VERDICT_PENDING = "PENDING_CAPTURE"
VERDICT_CONST_ZERO_OK = "CONST_ZERO_OK"
VERDICT_OK = "OK"
VERDICT_OK_WITH_INVALIDS = "OK_WITH_INVALIDS"
VERDICT_ALL_INVALID = "ALL_INVALID"
VERDICT_MISSING = "MISSING"
VERDICT_DERIVABLE = "MISSING_BUT_DERIVABLE"

RESOLVED_VERDICTS = {VERDICT_OK, VERDICT_OK_WITH_INVALIDS, VERDICT_CONST_ZERO_OK}
UNRESOLVED_VERDICTS = {VERDICT_MISSING, VERDICT_ALL_INVALID}

FLAG_RANGE_SHIFT = "RANGE_SHIFT"
FLAG_SIGN_SHIFT = "SIGN_SHIFT"
FLAG_ZERO_SHIFT = "ZERO_SHIFT"

ZERO_SHIFT_TOLERANCE = 0.25


def _normalise(name: str) -> str:
    return "".join(character for character in name.lower() if character.isalnum())


def _parse_number(raw):
    if raw is None:
        return None, "null"
    text = str(raw).strip()
    if text == "" or text.lower() in {"nan", "none", "null"}:
        return None, "empty"
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None, "non_numeric"
    if math.isnan(number):
        return None, "nan"
    if math.isinf(number):
        return None, "inf"
    return number, None


def _quantile(sorted_values, fraction):
    if not sorted_values:
        return None
    position = fraction * (len(sorted_values) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def read_live_csv(path: Path) -> tuple:
    with open(path, newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        header = [name.strip() for name in (reader.fieldnames or [])]
        rows = [row for row in reader]
    return header, rows


def profile_live_column(rows, column) -> dict:
    values = []
    reasons = {"null": 0, "empty": 0, "non_numeric": 0, "nan": 0, "inf": 0}

    for row in rows:
        number, reason = _parse_number(row.get(column))
        if reason is None:
            values.append(number)
        else:
            reasons[reason] += 1

    total = len(rows)
    values.sort()

    profile = {
        "observed": total,
        "valid": len(values),
        "invalid": total - len(values),
        "invalid_reasons": {key: count for key, count in reasons.items() if count},
        "invalid_fraction": (total - len(values)) / total if total else 0.0,
    }

    if values:
        profile.update({
            "min": values[0],
            "max": values[-1],
            "mean": sum(values) / len(values),
            "p01": _quantile(values, 0.01),
            "p50": _quantile(values, 0.50),
            "p99": _quantile(values, 0.99),
            "zero_fraction": sum(1 for value in values if value == 0) / len(values),
            "negative_fraction": sum(1 for value in values if value < 0) / len(values),
        })

    return profile


def evaluate_feature(feature, reference_stats, live_profile, live_present) -> tuple:
    flags = []

    if not live_present:
        if feature in CONST_ZERO_IN_TRAINING:
            return VERDICT_CONST_ZERO_OK, flags
        return VERDICT_MISSING, flags

    if live_profile["valid"] == 0:
        if feature in CONST_ZERO_IN_TRAINING:
            return VERDICT_CONST_ZERO_OK, flags
        return VERDICT_ALL_INVALID, flags

    low = reference_stats.get("p01")
    high = reference_stats.get("p99")
    median = live_profile.get("p50")
    if low is not None and high is not None and median is not None:
        if median < low or median > high:
            flags.append(FLAG_RANGE_SHIFT)

    if reference_stats.get("negative_fraction", 0.0) == 0.0 and live_profile.get("negative_fraction", 0.0) > 0.0:
        flags.append(FLAG_SIGN_SHIFT)

    reference_zero = reference_stats.get("zero_fraction", 0.0)
    live_zero = live_profile.get("zero_fraction", 0.0)
    if abs(live_zero - reference_zero) > ZERO_SHIFT_TOLERANCE:
        flags.append(FLAG_ZERO_SHIFT)

    if live_profile["invalid"] > 0:
        return VERDICT_OK_WITH_INVALIDS, flags

    return VERDICT_OK, flags


def suggest_alias(feature, unmapped_columns):
    if not unmapped_columns:
        return None
    expected = CICIDS2017_TO_CICFLOWMETER.get(feature, feature)
    normalised = {_normalise(column): column for column in unmapped_columns}
    matches = difflib.get_close_matches(_normalise(expected), list(normalised), n=1, cutoff=0.6)
    if not matches:
        return None
    return normalised[matches[0]]


def build_profile(reference, feature_version, live_header, live_rows) -> dict:
    feature_columns = reference["feature_sets"][reference["base_feature_version"]]
    active_set = set(reference["feature_sets"].get(feature_version, feature_columns))
    has_capture = live_header is not None

    live_columns = set(live_header or [])
    mapped_columns = {
        column for column in live_columns
        if column in CICFLOWMETER_TO_CICIDS2017
    }
    unmapped_columns = sorted(live_columns - mapped_columns - META_COLUMNS)

    entries = []
    counters = {}

    for feature in feature_columns:
        cfm_name = CICIDS2017_TO_CICFLOWMETER.get(feature)
        reference_stats = reference["features"][feature]

        entry = {
            "feature": feature,
            "cicflowmeter_column": cfm_name,
            "in_active_feature_set": feature in active_set,
            "training": True,
            "mapping": "exact" if cfm_name else "none",
            "training_constant_zero": feature in CONST_ZERO_IN_TRAINING,
            "training_zero_fraction": reference_stats.get("zero_fraction"),
            "training_p01": reference_stats.get("p01"),
            "training_p50": reference_stats.get("p50"),
            "training_p99": reference_stats.get("p99"),
        }

        if not has_capture:
            entry["live"] = None
            entry["verdict"] = (
                VERDICT_CONST_ZERO_OK if feature in CONST_ZERO_IN_TRAINING else VERDICT_PENDING
            )
            entry["flags"] = []
        else:
            live_present = cfm_name in live_columns
            live_profile = profile_live_column(live_rows, cfm_name) if live_present else None
            verdict, flags = evaluate_feature(
                feature, reference_stats, live_profile or {"valid": 0, "invalid": 0}, live_present
            )
            entry["live"] = live_profile
            entry["verdict"] = verdict
            entry["flags"] = flags
            if verdict == VERDICT_MISSING:
                entry["suggested_alias"] = suggest_alias(feature, unmapped_columns)

        entries.append(entry)

    if has_capture:
        resolved = {
            entry["feature"] for entry in entries
            if entry["verdict"] in RESOLVED_VERDICTS
        }
        for entry in entries:
            feature = entry["feature"]
            if entry["verdict"] not in UNRESOLVED_VERDICTS:
                continue
            rule = DERIVATIONS.get(feature)
            if rule is None:
                entry["derivation"] = {
                    "derivable": False,
                    "reason": NOT_DERIVABLE.get(feature, "No verified derivation rule exists."),
                }
                continue
            available = can_derive(feature, resolved)
            entry["derivation"] = {
                "derivable": available,
                "inputs": list(rule["inputs"]),
                "missing_inputs": [name for name in rule["inputs"] if name not in resolved],
                "verified_exact_rate": rule["exact_rate"],
                "note": rule["note"],
            }
            if available:
                entry["verdict"] = VERDICT_DERIVABLE

    for entry in entries:
        counters[entry["verdict"]] = counters.get(entry["verdict"], 0) + 1

    blocking = [
        entry["feature"] for entry in entries
        if entry["in_active_feature_set"] and entry["verdict"] in UNRESOLVED_VERDICTS
    ]

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "feature_version": feature_version,
        "active_feature_count": len(active_set),
        "capture": {
            "present": has_capture,
            "rows": len(live_rows or []),
            "columns": len(live_columns),
            "mapped_columns": len(mapped_columns),
            "unmapped_columns": unmapped_columns,
        },
        "reference": {
            "dataset": reference["dataset"]["name"],
            "rows": reference["dataset"]["rows"],
            "sha256": reference["dataset"]["sha256"],
            "generated_at": reference["generated_at"],
        },
        "verdict_counts": counters,
        "blocking_features": blocking,
        "features": entries,
    }


def _format_number(value):
    if value is None:
        return "-"
    if value == 0:
        return "0"
    magnitude = abs(value)
    if magnitude >= 1e6 or magnitude < 1e-3:
        return f"{value:.2e}"
    return f"{value:,.2f}"


def _format_percent(value):
    if value is None:
        return "-"
    return f"{value * 100:.1f}%"


def render_markdown(profile) -> str:
    capture = profile["capture"]
    lines = []

    lines.append("# FEATURE_COMPATIBILITY.md")
    lines.append("")
    lines.append("Generated by `ml-service/app/replay/feature_probe.py`. Do not edit by hand -")
    lines.append("re-run the probe instead.")
    lines.append("")
    lines.append(f"* **Generated:** {profile['generated_at']}")
    lines.append(f"* **Active feature set:** `{profile['feature_version']}` "
                 f"({profile['active_feature_count']} of {len(profile['features'])} features)")
    lines.append(f"* **Training reference:** `{profile['reference']['dataset']}`, "
                 f"{profile['reference']['rows']:,} rows, "
                 f"sha256 `{profile['reference']['sha256'][:16]}...`")

    if capture["present"]:
        lines.append(f"* **Live capture:** {capture['rows']:,} flows, {capture['columns']} columns, "
                     f"{capture['mapped_columns']} of which map to training features")
    else:
        lines.append("* **Live capture:** _none supplied_ - every feature that is not provably "
                     "constant-zero in training is reported as `PENDING_CAPTURE`.")

    lines.append("")
    lines.append("## Verdict summary")
    lines.append("")
    lines.append("| Verdict | Count | Meaning |")
    lines.append("|---|---:|---|")

    meanings = {
        VERDICT_OK: "Present in the capture, every value numeric and finite.",
        VERDICT_OK_WITH_INVALIDS: "Present, but some rows were empty, non-numeric, NaN or infinite.",
        VERDICT_CONST_ZERO_OK: "Constant zero across all training rows - zero-fill is mathematically exact.",
        VERDICT_MISSING: "CICFlowMeter did not emit the mapped column at all.",
        VERDICT_ALL_INVALID: "Column present but no row produced a usable number.",
        VERDICT_DERIVABLE: "Not emitted, but reconstructable from columns the capture does provide.",
        VERDICT_PENDING: "Not yet measured - awaiting a CICFlowMeter capture CSV.",
    }
    for verdict, count in sorted(profile["verdict_counts"].items(), key=lambda item: -item[1]):
        lines.append(f"| `{verdict}` | {count} | {meanings.get(verdict, '')} |")

    lines.append("")
    if profile["blocking_features"]:
        lines.append(f"**{len(profile['blocking_features'])} feature(s) in the active set cannot be "
                     "obtained from this capture:** " +
                     ", ".join(f"`{name}`" for name in profile["blocking_features"]))
    elif capture["present"]:
        lines.append("**Every feature in the active set was obtained from the capture.**")
    else:
        lines.append("_Blocking analysis requires a capture._")

    lines.append("")
    lines.append("## Compatibility matrix")
    lines.append("")
    lines.append("`Set` marks membership of the active feature set. Training percentiles come from "
                 "the full cleaned dataset; live percentiles from the capture.")
    lines.append("")
    lines.append("| Feature | Set | CICFlowMeter column | Mapping | Train p50 | Live p50 | Invalid | Verdict | Flags |")
    lines.append("|---|:-:|---|---|---:|---:|---:|---|---|")

    for entry in profile["features"]:
        live = entry.get("live") or {}
        lines.append(
            "| {feature} | {active} | `{cfm}` | {mapping} | {train_p50} | {live_p50} | {invalid} | `{verdict}` | {flags} |".format(
                feature=entry["feature"],
                active="Y" if entry["in_active_feature_set"] else "",
                cfm=entry["cicflowmeter_column"] or "-",
                mapping=entry["mapping"],
                train_p50=_format_number(entry["training_p50"]),
                live_p50=_format_number(live.get("p50")),
                invalid=_format_percent(live.get("invalid_fraction")),
                verdict=entry["verdict"],
                flags=", ".join(f"`{flag}`" for flag in entry["flags"]) or "",
            )
        )

    recovered = {entry["feature"] for entry in profile["features"]
                 if entry["verdict"] == VERDICT_DERIVABLE}
    active_features = {entry["feature"] for entry in profile["features"]
                       if entry["in_active_feature_set"]}

    lines.append("")
    lines.append("## Verified derivation rules")
    lines.append("")
    lines.append("If CICFlowMeter fails to emit one of these features, it can be reconstructed from "
                 "other columns instead of being zero-filled. Every rule is checked against the "
                 "training dataset by `training/verify_derivations.py`; the rate is the fraction of "
                 "real CICIDS2017 rows the rule reproduces exactly to within 1e-6 relative error.")
    lines.append("")
    lines.append("| Feature | Set | Derived from | Verified exact rate | Applied here | Note |")
    lines.append("|---|:-:|---|---:|:-:|---|")
    for feature, rule in DERIVATIONS.items():
        lines.append("| {feature} | {active} | {inputs} | {rate} | {applied} | {note} |".format(
            feature=feature,
            active="Y" if feature in active_features else "",
            inputs=", ".join(f"`{name}`" for name in rule["inputs"]),
            rate=f"{rule['exact_rate'] * 100:.2f}%",
            applied="Y" if feature in recovered else "",
            note=rule["note"],
        ))

    lines.append("")
    lines.append("Features with no usable derivation:")
    lines.append("")
    for feature, reason in NOT_DERIVABLE.items():
        lines.append(f"* `{feature}` - {reason}")

    unrecoverable = [entry for entry in profile["features"]
                     if entry["verdict"] in {VERDICT_MISSING, VERDICT_ALL_INVALID}]
    if unrecoverable:
        lines.append("")
        lines.append("## Not obtainable from this capture")
        lines.append("")
        lines.append("| Feature | In active set | Why |")
        lines.append("|---|:-:|---|")
        for entry in unrecoverable:
            rule = entry.get("derivation") or {}
            if rule.get("missing_inputs"):
                reason = "Derivation needs " + ", ".join(
                    f"`{name}`" for name in rule["missing_inputs"]) + ", also absent."
            else:
                reason = rule.get("reason", "No verified derivation rule exists.")
            lines.append("| {feature} | {active} | {reason} |".format(
                feature=entry["feature"],
                active="Y" if entry["in_active_feature_set"] else "",
                reason=reason,
            ))

    aliases = [
        (entry["feature"], entry["suggested_alias"])
        for entry in profile["features"]
        if entry.get("suggested_alias")
    ]
    if aliases:
        lines.append("")
        lines.append("## Possible aliases for missing features")
        lines.append("")
        lines.append("The probe found unmapped capture columns whose names resemble a missing feature. "
                     "Confirm the semantics before adding any of these to `feature_mapping.py`.")
        lines.append("")
        lines.append("| Missing feature | Candidate capture column |")
        lines.append("|---|---|")
        for feature, candidate in aliases:
            lines.append(f"| {feature} | `{candidate}` |")

    if capture["unmapped_columns"]:
        lines.append("")
        lines.append("## Capture columns with no training counterpart")
        lines.append("")
        lines.append(", ".join(f"`{column}`" for column in capture["unmapped_columns"]))

    lines.append("")
    lines.append("## Zero-fill policy")
    lines.append("")
    lines.append("Verified over all "
                 f"{profile['reference']['rows']:,} rows of the cleaned dataset: the following "
                 "features are constant zero, so substituting zero at inference time reproduces the "
                 "training distribution exactly and the model can encode no information from them.")
    lines.append("")
    for feature in CONST_ZERO_IN_TRAINING:
        in_set = any(
            entry["feature"] == feature and entry["in_active_feature_set"]
            for entry in profile["features"]
        )
        lines.append(f"* `{feature}`" + (" - **in the active feature set**" if in_set else ""))
    lines.append("")
    lines.append("Every other feature is zero-filled only as a recorded decision, never silently.")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Krahason features e CICFlowMeter live me ato te trajnimit CICIDS2017.")
    parser.add_argument("--live-csv", default=None,
                        help="CSV i prodhuar nga cicflowmeter; nese mungon, matrica del PENDING_CAPTURE")
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--feature-version", default=DEFAULT_FEATURE_VERSION)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--markdown", default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    reference_path = Path(args.reference)
    if not reference_path.is_absolute():
        reference_path = _ML_SERVICE_ROOT / reference_path
    if not reference_path.exists():
        print(f"Referenca s'u gjet: {reference_path}\n"
              f"Xhiro me pare: python -m training.build_feature_reference", file=sys.stderr)
        return 1

    with open(reference_path, encoding="utf-8") as handle:
        reference = json.load(handle)

    if args.feature_version not in reference["feature_sets"]:
        print(f"Feature version '{args.feature_version}' s'ekziston. Ne dispozicion: "
              f"{', '.join(reference['feature_sets'])}", file=sys.stderr)
        return 1

    live_header = None
    live_rows = None
    if args.live_csv:
        live_path = Path(args.live_csv)
        if not live_path.exists():
            print(f"CSV-ja live s'u gjet: {live_path}", file=sys.stderr)
            return 1
        live_header, live_rows = read_live_csv(live_path)
        print(f"Capture: {len(live_rows):,} rreshta, {len(live_header)} kolona")

    profile = build_profile(reference, args.feature_version, live_header, live_rows)

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = _ML_SERVICE_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(profile, handle, indent=1)

    markdown_path = Path(args.markdown)
    if not markdown_path.is_absolute():
        markdown_path = _ML_SERVICE_ROOT.parent / markdown_path
    with open(markdown_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(render_markdown(profile))

    print("\n--- Permbledhje ---")
    for verdict, count in sorted(profile["verdict_counts"].items(), key=lambda item: -item[1]):
        print(f"  {verdict:<20} {count}")
    if profile["blocking_features"]:
        print(f"\nBllokuese ne feature set-in aktiv ({len(profile['blocking_features'])}): "
              f"{', '.join(profile['blocking_features'])}")
    print(f"\nJSON:     {out_path}")
    print(f"Markdown: {markdown_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
