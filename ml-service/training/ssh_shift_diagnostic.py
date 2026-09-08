import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp
from sklearn.model_selection import train_test_split

_ML_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ML_SERVICE_ROOT))

from app.live import lab_runner, manifest as manifest_module
from app.ml.feature_validation import STRICT_POLICY, FeatureValidator, load_reference

DATASET = _ML_SERVICE_ROOT / "datasets" / "cicids2017_cleaned.parquet"
LAB_CAPTURE = (_ML_SERVICE_ROOT / "reports" / "live_evaluation" / "captures"
               / "lab-v1-ssh-bruteforce-001.csv")
LAB_MANIFEST = (_ML_SERVICE_ROOT / "training" / "configs" / "live"
                / "lab-v1-ssh-bruteforce-001.yaml")
OUT_DIR = (_ML_SERVICE_ROOT / "reports" / "live_evaluation" / "diagnostics"
           / "ssh_feature_shift")
PORTSCAN_SUMMARY = (_ML_SERVICE_ROOT / "reports" / "live_evaluation" / "diagnostics"
                    / "portscan_feature_shift" / "summary.json")

NEAR_CONSTANT_STD = 1e-9

TIME_FEATURES_US = {
    "Flow Duration", "Flow IAT Mean", "Flow IAT Std", "Flow IAT Max", "Flow IAT Min",
    "Fwd IAT Total", "Fwd IAT Mean", "Fwd IAT Std", "Fwd IAT Max", "Fwd IAT Min",
    "Bwd IAT Total", "Bwd IAT Mean", "Bwd IAT Std", "Bwd IAT Max", "Bwd IAT Min",
    "Active Mean", "Active Std", "Active Max", "Active Min",
    "Idle Mean", "Idle Std", "Idle Max", "Idle Min",
}
RATE_FEATURES = {"Flow Bytes/s", "Flow Packets/s", "Fwd Packets/s", "Bwd Packets/s"}
FLAG_FEATURES = {
    "FIN Flag Count", "SYN Flag Count", "RST Flag Count", "PSH Flag Count",
    "ACK Flag Count", "URG Flag Count", "CWE Flag Count", "ECE Flag Count",
    "Fwd PSH Flags", "Bwd PSH Flags", "Fwd URG Flags", "Bwd URG Flags",
}

SAME = "SAME_SEMANTICS_CONFIRMED"
LIKELY = "LIKELY_SAME"
IMPL = "POSSIBLE_IMPLEMENTATION_DIFFERENCE"
UNIT = "UNIT_MISMATCH_SUSPECTED"
UNRESOLVED = "SEMANTICS_UNRESOLVED"


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _test_partition_labels():
    meta = pd.read_parquet(DATASET, columns=["Label"])
    labels = (meta["Label"].astype(str).str.replace("\x96", "-", regex=False)
              .str.strip().to_numpy())
    _, test_idx = train_test_split(np.arange(len(labels)), test_size=0.2,
                                   random_state=42, stratify=labels)
    return labels, np.sort(test_idx)


def canonical_rows(feature_columns, label_names):
    labels, test_idx = _test_partition_labels()
    positions = test_idx[np.isin(labels[test_idx], list(label_names))]
    frame = pd.read_parquet(DATASET, columns=feature_columns)
    return frame.iloc[positions][feature_columns].to_numpy(dtype="float64")


def lab_rows(feature_columns):
    manifest = manifest_module.load(LAB_MANIFEST)
    validator = FeatureValidator(feature_columns, reference=load_reference(None),
                                 feature_version=manifest.model["feature_version"],
                                 policy=STRICT_POLICY)
    rows = []
    with open(LAB_CAPTURE, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if manifest.expected_for_flow(row) != "ATTACK":
                continue
            validation = validator.validate(lab_runner.map_row(row))
            if validation.valid:
                rows.append(validation.vector)
    return np.asarray(rows, dtype="float64")


def _pct_outside(values, low, high):
    if low is None or high is None or not np.isfinite(low) or not np.isfinite(high):
        return None
    return float(np.mean((values < low) | (values > high)) * 100.0)


def _describe(values):
    return {
        "n": int(len(values)),
        "mean": float(np.mean(values)),
        "std": float(np.std(values)),
        "p01": float(np.percentile(values, 1)),
        "p25": float(np.percentile(values, 25)),
        "median": float(np.median(values)),
        "p75": float(np.percentile(values, 75)),
        "p99": float(np.percentile(values, 99)),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "zero_fraction": float(np.mean(values == 0.0)),
    }


def feature_stats(canon, lab, feature_columns):
    rows = []
    for i, name in enumerate(feature_columns):
        c = canon[:, i]
        l = lab[:, i]
        cd = _describe(c)
        ld = _describe(l)
        c_std = cd["std"]

        pooled = np.sqrt((cd["std"] ** 2 + ld["std"] ** 2) / 2.0)
        std_diff = (abs(ld["mean"] - cd["mean"]) / pooled
                    if pooled > NEAR_CONSTANT_STD else None)
        med_diff = ld["median"] - cd["median"]
        med_ratio = (ld["median"] / cd["median"]
                     if abs(cd["median"]) > NEAR_CONSTANT_STD else None)
        canon_constant = c_std <= NEAR_CONSTANT_STD
        ks = None if canon_constant else float(ks_2samp(c, l).statistic)

        rows.append({
            "feature": name,
            "canon_n": cd["n"], "canon_mean": cd["mean"], "canon_std": cd["std"],
            "canon_p01": cd["p01"], "canon_p25": cd["p25"], "canon_median": cd["median"],
            "canon_p75": cd["p75"], "canon_p99": cd["p99"], "canon_min": cd["min"],
            "canon_max": cd["max"], "canon_zero_fraction": cd["zero_fraction"],
            "lab_n": ld["n"], "lab_mean": ld["mean"], "lab_std": ld["std"],
            "lab_p01": ld["p01"], "lab_p25": ld["p25"], "lab_median": ld["median"],
            "lab_p75": ld["p75"], "lab_p99": ld["p99"], "lab_min": ld["min"],
            "lab_max": ld["max"], "lab_zero_fraction": ld["zero_fraction"],
            "ks_statistic": ks,
            "abs_standardized_diff": std_diff,
            "median_diff": med_diff,
            "median_ratio": med_ratio,
            "pct_lab_outside_canon_iqr": _pct_outside(l, cd["p25"], cd["p75"]),
            "pct_lab_outside_canon_p01_p99": _pct_outside(l, cd["p01"], cd["p99"]),
            "canon_constant": canon_constant,
            "lab_constant": ld["std"] <= NEAR_CONSTANT_STD,
        })
    return rows


def semantic_audit(rows):
    audit = []
    for r in rows:
        name = r["feature"]
        cm, lm = r["canon_median"], r["lab_median"]
        ratio = r["median_ratio"]
        note = ""

        if name in TIME_FEATURES_US:
            status = UNIT
            hint = (cm / lm) if (lm not in (0.0, None) and abs(lm) > NEAR_CONSTANT_STD) \
                else None
            if hint is not None and 1e4 <= hint <= 1e8:
                note = (f"canonical/lab median ratio {hint:.3g} is compatible with a "
                        f"microseconds(canonical) vs seconds(lab) time-unit convention")
            elif r["canon_constant"] or r["lab_constant"]:
                status = LIKELY
                note = "time feature but (near-)constant in one population; unit effect masked"
            else:
                note = "time feature; canonical CICFlowMeter is documented in microseconds"
        elif name in RATE_FEATURES:
            status = IMPL
            note = ("per-time rate; magnitude depends on each tool's internal duration "
                    "convention, so not directly comparable in scale")
        elif name in FLAG_FEATURES:
            status = IMPL
            note = "flag counting/segmentation semantics may differ between tools"
        elif name.startswith("Bwd Bulk") or name.startswith("Fwd Bulk") or "Bulk" in name \
                or "Avg" in name and "Bulk" in name:
            status = UNRESOLVED
            note = "bulk-rate feature; aggregation semantics not verified locally"
        else:
            status = LIKELY
            note = "count/length/ratio feature; byte and packet semantics are conventional"

        audit.append({
            "feature": name,
            "category": ("time" if name in TIME_FEATURES_US else
                         "rate" if name in RATE_FEATURES else
                         "flag" if name in FLAG_FEATURES else "other"),
            "semantic_status": status,
            "canon_median": cm,
            "lab_median": lm,
            "median_ratio": ratio,
            "note": note,
        })
    return audit


def rank(rows):
    return sorted(rows, key=lambda r: r["ks_statistic"] if r["ks_statistic"] is not None
                 else -1.0, reverse=True)


def model_relevant(rows, feature_columns, model, audit, top_k=15):
    importances = model.feature_importances_
    order = np.argsort(importances)[::-1]
    by_name = {r["feature"]: r for r in rows}
    audit_by_name = {a["feature"]: a for a in audit}
    ks_rank = {r["feature"]: i for i, r in enumerate(rank(rows))}
    out = []
    for rank_i, pos in enumerate(order[:top_k]):
        name = feature_columns[pos]
        r = by_name[name]
        out.append({
            "feature": name,
            "importance_rank": rank_i,
            "importance": float(importances[pos]),
            "ks_statistic": r["ks_statistic"],
            "ks_shift_rank": ks_rank[name],
            "pct_lab_outside_canon_p01_p99": r["pct_lab_outside_canon_p01_p99"],
            "canon_median": r["canon_median"],
            "lab_median": r["lab_median"],
            "semantic_status": audit_by_name[name]["semantic_status"],
            "substantially_shifted": (r["ks_statistic"] is not None
                                      and r["ks_statistic"] >= 0.5),
        })
    return out


def missed_context(lab, feature_columns, model, label_encoder, rows):
    frame = pd.DataFrame(lab, columns=feature_columns)
    predicted = label_encoder.inverse_transform(model.predict(frame))
    probs = model.predict_proba(frame)
    confidence = probs.max(axis=1)
    benign = predicted == "BENIGN"

    by_name = {r["feature"]: r for r in rows}
    importances = model.feature_importances_
    order = np.argsort(importances)[::-1][:10]
    per_feature = []
    for pos in order:
        name = feature_columns[pos]
        r = by_name[name]
        per_feature.append({
            "feature": name,
            "importance_rank": int(np.where(np.argsort(importances)[::-1] == pos)[0][0]),
            "lab_median": r["lab_median"],
            "canon_p01": r["canon_p01"],
            "canon_p99": r["canon_p99"],
            "pct_lab_outside_canon_p01_p99": r["pct_lab_outside_canon_p01_p99"],
        })

    return {
        "lab_flows": int(len(lab)),
        "predicted_benign": int(benign.sum()),
        "predicted_attack": int((~benign).sum()),
        "confidence_min": float(confidence.min()),
        "confidence_median": float(np.median(confidence)),
        "confidence_max": float(confidence.max()),
        "all_predicted_benign": bool(benign.all()),
        "top_important_feature_position": per_feature,
        "note": ("Every laboratory SSH flow was predicted BENIGN, so there is no "
                 "detected-vs-missed split. Values are descriptive; no causal mechanism "
                 "is asserted."),
    }


def shift_overview(rows):
    ks = [r["ks_statistic"] for r in rows if r["ks_statistic"] is not None]
    outside = [r["pct_lab_outside_canon_p01_p99"] for r in rows
               if r["pct_lab_outside_canon_p01_p99"] is not None]
    return {
        "comparable_features": len(ks),
        "constant_or_non_comparable": len(rows) - len(ks),
        "median_ks": float(np.median(ks)) if ks else None,
        "p75_ks": float(np.percentile(ks, 75)) if ks else None,
        "max_ks": float(np.max(ks)) if ks else None,
        "count_ks_ge_0_3": sum(1 for v in ks if v >= 0.3),
        "count_ks_ge_0_5": sum(1 for v in ks if v >= 0.5),
        "count_ks_ge_0_8": sum(1 for v in ks if v >= 0.8),
        "count_ge_50pct_outside_p01_p99": sum(1 for v in outside if v >= 50.0),
        "count_100pct_outside_p01_p99": sum(1 for v in outside if v >= 100.0),
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    model, label_encoder, feature_columns, identity = lab_runner.load_frozen_model(
        _ML_SERVICE_ROOT / "models")

    canon = canonical_rows(feature_columns, {"SSH-Patator"})
    canon_bf = canonical_rows(feature_columns, {"SSH-Patator", "FTP-Patator"})
    lab = lab_rows(feature_columns)

    rows = feature_stats(canon, lab, feature_columns)
    ranked = rank(rows)
    audit = semantic_audit(rows)
    relevant = model_relevant(rows, feature_columns, model, audit)
    missed = missed_context(lab, feature_columns, model, label_encoder, rows)
    overview = shift_overview(rows)

    rows_bf = feature_stats(canon_bf, lab, feature_columns)
    overview_bf = shift_overview(rows_bf)

    important_shift = sum(1 for r in relevant if r["substantially_shifted"])
    unit_features = [a["feature"] for a in audit if a["semantic_status"] == UNIT]

    portscan = json.load(open(PORTSCAN_SUMMARY, encoding="utf-8")) \
        if PORTSCAN_SUMMARY.exists() else {}
    ps_over = portscan.get("shift_overview", {})
    cross = {
        "portscan": {
            "detection_rate": 2 / 1362,
            "canonical_support": portscan.get("canonical_portscan_support"),
            "lab_support": portscan.get("laboratory_portscan_support"),
            "median_ks": ps_over.get("median_ks_statistic"),
            "features_ks_ge_0_8": ps_over.get("features_ks_ge_0_8"),
            "top15_important_shifted": portscan.get(
                "model_relevant_overview", {}).get("top_k_with_ks_ge_0_5"),
        },
        "ssh": {
            "detection_rate": 0.0,
            "canonical_support": int(canon.shape[0]),
            "lab_support": int(lab.shape[0]),
            "median_ks": overview["median_ks"],
            "features_ks_ge_0_8": overview["count_ks_ge_0_8"],
            "top15_important_shifted": important_shift,
        },
        "classification": None,
    }
    both_high = (overview["median_ks"] is not None and overview["median_ks"] >= 0.5
                 and ps_over.get("median_ks_statistic", 0) >= 0.5)
    cross["classification"] = ("CONSISTENT_CROSS_SCENARIO_SHIFT" if both_high
                               else "MIXED_OR_SCENARIO_SPECIFIC_SHIFT")

    summary = {
        "schema_version": 1,
        "diagnostic": "ssh_feature_shift",
        "generated_at": utc_now(),
        "is_diagnostic_only": True,
        "does_not_modify_frozen_results": True,
        "no_retraining_no_tuning_no_shap_no_llm": True,
        "feature_schema": identity["feature_schema"],
        "model": identity,
        "primary_reference": "SSH-Patator",
        "canonical_ssh_patator_support": int(canon.shape[0]),
        "secondary_reference": "SSH-Patator + FTP-Patator (Brute Force family)",
        "canonical_brute_force_support": int(canon_bf.shape[0]),
        "laboratory_ssh_support": int(lab.shape[0]),
        "ground_truth_note": ("laboratory ground truth is family-level Brute Force; "
                              "SSH-Patator is used here only as the relevant canonical "
                              "reference distribution, not as exact-label ground truth"),
        "n_features": len(feature_columns),
        "shift_overview_primary": overview,
        "shift_overview_secondary_brute_force": overview_bf,
        "semantic_audit_overview": {
            "unit_mismatch_suspected_count": len(unit_features),
            "unit_mismatch_features": unit_features,
            "possible_implementation_difference_count": sum(
                1 for a in audit if a["semantic_status"] == IMPL),
        },
        "model_relevant_overview": {
            "top_k": len(relevant),
            "top_k_substantially_shifted": important_shift,
            "top_feature": relevant[0]["feature"] if relevant else None,
            "top_feature_ks": relevant[0]["ks_statistic"] if relevant else None,
        },
        "confident_miss": missed,
        "cross_scenario": cross,
    }

    with open(OUT_DIR / "summary.json", "w", encoding="utf-8") as h:
        json.dump(summary, h, indent=1)

    fieldnames = list(rows[0].keys())
    with open(OUT_DIR / "feature_shift.csv", "w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=fieldnames)
        w.writeheader(); w.writerows(ranked)
    with open(OUT_DIR / "top_shifted_features.csv", "w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=fieldnames)
        w.writeheader(); w.writerows(ranked[:15])
    with open(OUT_DIR / "model_relevant_shift.csv", "w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=list(relevant[0].keys()))
        w.writeheader(); w.writerows(relevant)
    with open(OUT_DIR / "semantic_audit.csv", "w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=list(audit[0].keys()))
        w.writeheader(); w.writerows(audit)
    with open(OUT_DIR / "cross_scenario_comparison.json", "w", encoding="utf-8") as h:
        json.dump(cross, h, indent=1)

    print(f"canonical SSH-Patator support : {canon.shape[0]}")
    print(f"canonical Brute Force support : {canon_bf.shape[0]}")
    print(f"laboratory SSH support        : {lab.shape[0]}")
    print(f"median KS (primary)           : {overview['median_ks']:.4f}")
    print(f"KS>=0.5 / KS>=0.8             : {overview['count_ks_ge_0_5']} / "
          f"{overview['count_ks_ge_0_8']}  (of {overview['comparable_features']})")
    print(f"unit-mismatch-suspected feats : {len(unit_features)}")
    print(f"top-15 important shifted      : {important_shift}/15")
    print(f"cross-scenario classification : {cross['classification']}")
    print()
    print("top 15 shifted (by KS):")
    for r in ranked[:15]:
        print(f"  {r['feature']:<28} KS={r['ks_statistic']:.4f} "
              f"canon_med={r['canon_median']:.4g} lab_med={r['lab_median']:.4g}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
