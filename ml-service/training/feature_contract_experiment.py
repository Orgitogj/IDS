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

from app.live import compat, lab_runner, manifest as manifest_module, protocol
from app.ml.feature_validation import STRICT_POLICY, FeatureValidator, load_reference
from training.pipeline import families

DATASET = _ML_SERVICE_ROOT / "datasets" / "cicids2017_cleaned.parquet"
CAP = _ML_SERVICE_ROOT / "reports" / "live_evaluation" / "captures"
CFG = _ML_SERVICE_ROOT / "training" / "configs" / "live"
OUT_DIR = (_ML_SERVICE_ROOT / "reports" / "live_evaluation" / "diagnostics"
           / "feature_contract_compatibility")

SCENARIOS = {
    "portscan": {
        "capture": CAP / "lab-v1-portscan-001.csv",
        "manifest": CFG / "lab-v1-portscan-001.yaml",
        "canonical_labels": {"PortScan"},
        "expected_support": 1362, "expected_detected": 2, "expected_benign": 1360,
    },
    "ssh": {
        "capture": CAP / "lab-v1-ssh-bruteforce-001.csv",
        "manifest": CFG / "lab-v1-ssh-bruteforce-001.yaml",
        "canonical_labels": {"SSH-Patator"},
        "canonical_secondary": {"SSH-Patator", "FTP-Patator"},
        "expected_support": 69, "expected_detected": 0, "expected_benign": 69,
    },
}

NEAR_CONSTANT_STD = 1e-9
BENIGN = "BENIGN"


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_model():
    return lab_runner.load_frozen_model(_ML_SERVICE_ROOT / "models")


def selector_matched_vectors(capture, manifest_path, feature_columns):
    manifest = manifest_module.load(manifest_path)
    validator = FeatureValidator(feature_columns, reference=load_reference(None),
                                 feature_version=manifest.model["feature_version"],
                                 policy=STRICT_POLICY)
    vectors, ports = [], []
    with open(capture, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if manifest.expected_for_flow(row) != "ATTACK":
                continue
            v = validator.validate(lab_runner.map_row(row))
            if v.valid:
                vectors.append(v.vector)
                ports.append(row.get("dst_port"))
    return np.asarray(vectors, dtype="float64"), ports


def predict(model, label_encoder, feature_columns, matrix):
    frame = pd.DataFrame(matrix, columns=feature_columns)
    idx = model.predict(frame)
    proba = model.predict_proba(frame)
    labels = label_encoder.inverse_transform(idx)
    confidence = proba.max(axis=1)
    return [str(x) for x in labels], confidence


def prediction_summary(labels, confidence):
    labels = list(labels)
    n = len(labels)
    benign = sum(1 for x in labels if x == BENIGN)
    attack = n - benign
    dist = {}
    for x in labels:
        dist[x] = dist.get(x, 0) + 1
    fam = {}
    for x in labels:
        if x == BENIGN:
            continue
        f = families.family_of(x) or "unmapped"
        fam[f] = fam.get(f, 0) + 1
    conf = np.asarray(confidence, dtype="float64")
    return {
        "support": n,
        "predicted_benign": benign,
        "predicted_attack": attack,
        "detection_rate": float(attack / n) if n else None,
        "predicted_label_distribution": dict(sorted(dist.items(), key=lambda i: -i[1])),
        "predicted_family_distribution": dict(sorted(fam.items(), key=lambda i: -i[1])),
        "confidence_min": float(conf.min()) if n else None,
        "confidence_median": float(np.median(conf)) if n else None,
        "confidence_max": float(conf.max()) if n else None,
    }


def harmonize_matrix(feature_columns, matrix):
    out = np.array(matrix, dtype="float64")
    converted = None
    for r in range(out.shape[0]):
        new, meta = compat.harmonize_vector(feature_columns, out[r].tolist())
        out[r] = new
        converted = meta["converted_features"]
    return out, converted


def canonical_matrix(feature_columns, label_names):
    meta = pd.read_parquet(DATASET, columns=["Label"])
    labels = (meta["Label"].astype(str).str.replace("\x96", "-", regex=False)
              .str.strip().to_numpy())
    _, test_idx = train_test_split(np.arange(len(labels)), test_size=0.2,
                                   random_state=42, stratify=labels)
    test_idx = np.sort(test_idx)
    positions = test_idx[np.isin(labels[test_idx], list(label_names))]
    frame = pd.read_parquet(DATASET, columns=feature_columns)
    return frame.iloc[positions][feature_columns].to_numpy(dtype="float64")


def _pct_outside(values, low, high):
    if low is None or high is None or not np.isfinite(low) or not np.isfinite(high):
        return None
    return float(np.mean((values < low) | (values > high)) * 100.0)


def feature_shift(canon, lab, feature_columns):
    rows = []
    for i, name in enumerate(feature_columns):
        c, l = canon[:, i], lab[:, i]
        c_std = float(np.std(c))
        c_p01, c_p99 = np.percentile(c, [1, 99])
        c_p25, c_p75 = np.percentile(c, [25, 75])
        ks = None if c_std <= NEAR_CONSTANT_STD else float(ks_2samp(c, l).statistic)
        rows.append({
            "feature": name,
            "is_time_feature": name in (set(compat.CONFIRMED_SECONDS_FEATURES)
                                        | set(compat.LIKELY_SECONDS_FEATURES_ALL_ZERO_IN_LAB)),
            "canon_median": float(np.median(c)), "lab_median": float(np.median(l)),
            "ks_statistic": ks,
            "pct_lab_outside_canon_p01_p99": _pct_outside(l, c_p01, c_p99),
            "pct_lab_outside_canon_iqr": _pct_outside(l, c_p25, c_p75),
            "canon_constant": c_std <= NEAR_CONSTANT_STD,
        })
    return rows


def shift_overview(rows, subset=None):
    sel = [r for r in rows if (subset is None or r[subset])]
    ks = [r["ks_statistic"] for r in sel if r["ks_statistic"] is not None]
    outside = [r["pct_lab_outside_canon_p01_p99"] for r in sel
               if r["pct_lab_outside_canon_p01_p99"] is not None]
    return {
        "comparable_features": len(ks),
        "median_ks": float(np.median(ks)) if ks else None,
        "p75_ks": float(np.percentile(ks, 75)) if ks else None,
        "max_ks": float(np.max(ks)) if ks else None,
        "count_ks_ge_0_3": sum(1 for v in ks if v >= 0.3),
        "count_ks_ge_0_5": sum(1 for v in ks if v >= 0.5),
        "count_ks_ge_0_8": sum(1 for v in ks if v >= 0.8),
        "count_ge_50pct_outside": sum(1 for v in outside if v >= 50.0),
        "count_100pct_outside": sum(1 for v in outside if v >= 100.0),
    }


def model_relevant_residual(before_rows, after_rows, feature_columns, model, top_k=15):
    importances = model.feature_importances_
    order = np.argsort(importances)[::-1][:top_k]
    before = {r["feature"]: r for r in before_rows}
    after = {r["feature"]: r for r in after_rows}
    out = []
    for rank_i, pos in enumerate(order):
        name = feature_columns[pos]
        out.append({
            "feature": name, "importance_rank": rank_i,
            "importance": float(importances[pos]),
            "ks_before": before[name]["ks_statistic"],
            "ks_after": after[name]["ks_statistic"],
            "is_time_feature": before[name]["is_time_feature"],
        })
    return out


def contract_audit(model, feature_columns):
    canon = canonical_matrix(feature_columns, None) if False else None
    meta = pd.read_parquet(DATASET, columns=["Label"])
    labels = (meta["Label"].astype(str).str.replace("\x96", "-", regex=False)
              .str.strip().to_numpy())
    _, test_idx = train_test_split(np.arange(len(labels)), test_size=0.2,
                                   random_state=42, stratify=labels)
    test_idx = np.sort(test_idx)
    frame = pd.read_parquet(DATASET, columns=feature_columns)
    canon = frame.iloc[np.sort(test_idx)][feature_columns].to_numpy(dtype="float64")

    ssh_lab, _ = selector_matched_vectors(SCENARIOS["ssh"]["capture"],
                                          SCENARIOS["ssh"]["manifest"], feature_columns)
    ps_lab, _ = selector_matched_vectors(SCENARIOS["portscan"]["capture"],
                                         SCENARIOS["portscan"]["manifest"], feature_columns)
    idx = {c: i for i, c in enumerate(feature_columns)}

    audit = []
    all_time = compat.CONFIRMED_SECONDS_FEATURES + \
        compat.LIKELY_SECONDS_FEATURES_ALL_ZERO_IN_LAB
    for name in all_time + compat.RATE_FEATURES_NOT_CONVERTED:
        i = idx[name]
        c = canon[:, i]
        s = ssh_lab[:, i]
        p = ps_lab[:, i]
        canon_us_scale = float(np.percentile(c, 99)) >= 1e5
        ssh_nz = float(np.mean(s != 0))
        ssh_seconds_scale = ssh_nz > 0 and float(np.percentile(s, 99)) < 1e4

        is_rate = name in compat.RATE_FEATURES_NOT_CONVERTED
        if is_rate:
            status = "SEMANTICS_DIFFER"
            transform = "none"
            note = ("per-second rate already emitted in bytes/s or packets/s by "
                    "cicflowmeter; not double-corrected for the duration unit")
        elif name in compat.CONFIRMED_SECONDS_FEATURES:
            status = "CONFIRMED_UNIT_CONVERSION"
            transform = "seconds_to_microseconds (x1e6)"
            note = ("canonical microseconds scale (p99 %.3g) and laboratory seconds scale "
                    "with non-zero data (ssh p99 %.3g)" % (np.percentile(c, 99),
                                                           np.percentile(s, 99)))
        else:
            status = "LIKELY_UNIT_CONVERSION"
            transform = "none (all-zero in laboratory; no-op, not auto-applied)"
            note = ("canonical microseconds scale but laboratory value is zero in both "
                    "captures; no positive seconds-scale evidence")

        audit.append({
            "feature": name, "schema_position": i,
            "canonical_unit": "microseconds" if not is_rate else "per_second",
            "laboratory_unit": ("seconds" if (not is_rate and status !=
                                              "LIKELY_UNIT_CONVERSION") else
                                ("per_second" if is_rate else "zero/unknown")),
            "canonical_p99": float(np.percentile(c, 99)),
            "canonical_max": float(np.max(c)),
            "ssh_p99": float(np.percentile(s, 99)), "ssh_nonzero_fraction": ssh_nz,
            "portscan_nonzero_fraction": float(np.mean(p != 0)),
            "canonical_microseconds_scale": canon_us_scale,
            "laboratory_seconds_scale_confirmed": bool(ssh_seconds_scale),
            "semantic_status": status,
            "required_transformation": transform,
            "auto_transformed_in_primary": status == "CONFIRMED_UNIT_CONVERSION",
            "note": note,
        })
    return audit


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    model, label_encoder, feature_columns, identity = load_model()

    audit = contract_audit(model, feature_columns)
    with open(OUT_DIR / "contract_audit.csv", "w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=list(audit[0].keys()))
        w.writeheader(); w.writerows(audit)

    transformations = {
        "compatibility_protocol": compat.COMPAT_PROTOCOL,
        "source_feature_semantics": compat.SOURCE_FEATURE_SEMANTICS,
        "target_feature_contract": compat.TARGET_FEATURE_CONTRACT,
        "conversion_factor_seconds_to_microseconds": compat.SECONDS_TO_MICROSECONDS,
        "confirmed_converted_features": compat.CONFIRMED_SECONDS_FEATURES,
        "confirmed_count": len(compat.CONFIRMED_SECONDS_FEATURES),
        "likely_not_auto_converted": compat.LIKELY_SECONDS_FEATURES_ALL_ZERO_IN_LAB,
        "rate_features_not_converted": compat.RATE_FEATURES_NOT_CONVERTED,
        "rationale": ("only features with canonical microseconds scale and positive "
                      "laboratory seconds-scale evidence are auto-converted; prediction "
                      "outcomes never determined the transformation"),
    }
    with open(OUT_DIR / "transformations.json", "w", encoding="utf-8") as h:
        json.dump(transformations, h, indent=1)

    protocol_doc = {
        "compatibility_protocol": compat.COMPAT_PROTOCOL,
        "target_feature_contract": compat.TARGET_FEATURE_CONTRACT,
        "frozen_model": identity,
        "no_retraining": True, "no_tuning": True, "no_threshold_change": True,
        "no_calibration": True,
        "generated_at": utc_now(),
        "description": ("controlled seconds->microseconds harmonization of confirmed "
                        "time features, applied to raw laboratory flow vectors before the "
                        "unchanged frozen classifier; a counterfactual re-prediction, not "
                        "a model change"),
    }
    with open(OUT_DIR / "protocol.json", "w", encoding="utf-8") as h:
        json.dump(protocol_doc, h, indent=1)

    before_after = []
    summary = {"schema_version": 1, "experiment": "feature_contract_compatibility",
               "generated_at": utc_now(), "compatibility_protocol": compat.COMPAT_PROTOCOL,
               "frozen_model": identity, "no_retraining_no_tuning_no_shap_no_llm": True,
               "scenarios": {}}

    for key, spec in SCENARIOS.items():
        matrix, ports = selector_matched_vectors(spec["capture"], spec["manifest"],
                                                 feature_columns)
        orig_labels, orig_conf = predict(model, label_encoder, feature_columns, matrix)
        orig = prediction_summary(orig_labels, orig_conf)

        reproduced = {
            "support_match": orig["support"] == spec["expected_support"],
            "detected_match": orig["predicted_attack"] == spec["expected_detected"],
            "benign_match": orig["predicted_benign"] == spec["expected_benign"],
        }
        reproduced["all_match"] = all(reproduced.values())
        with open(OUT_DIR / f"{key}_original_reproduction.json", "w",
                  encoding="utf-8") as h:
            json.dump({"scenario": key, "expected": {
                "support": spec["expected_support"],
                "detected": spec["expected_detected"],
                "benign": spec["expected_benign"]},
                "reproduced": orig, "checks": reproduced}, h, indent=1)
        if not reproduced["all_match"]:
            print(f"STOP: {key} original reproduction failed: {reproduced}",
                  file=sys.stderr)
            return 2

        harmonized, converted = harmonize_matrix(feature_columns, matrix)
        comp_labels, comp_conf = predict(model, label_encoder, feature_columns,
                                         harmonized)
        comp = prediction_summary(comp_labels, comp_conf)

        with open(OUT_DIR / f"{key}_compatibility_predictions.csv", "w", newline="",
                  encoding="utf-8") as h:
            w = csv.writer(h)
            w.writerow(["flow_index", "dst_port", "original_label", "original_confidence",
                        "compat_label", "compat_confidence"])
            for i in range(len(orig_labels)):
                w.writerow([i + 1, ports[i], orig_labels[i], f"{orig_conf[i]:.6f}",
                            comp_labels[i], f"{comp_conf[i]:.6f}"])

        pp_change = (comp["detection_rate"] - orig["detection_rate"]) * 100.0
        comparison = {
            "scenario": key, "support": orig["support"],
            "original": orig, "compatibility": comp,
            "absolute_detection_change": comp["predicted_attack"] -
            orig["predicted_attack"],
            "detection_rate_change_pp": pp_change,
            "converted_features": converted,
            "note": ("change in detection after feature-contract harmonization; not a "
                     "model improvement and not retraining"),
        }
        with open(OUT_DIR / f"{key}_comparison.json", "w", encoding="utf-8") as h:
            json.dump(comparison, h, indent=1)

        canon = canonical_matrix(feature_columns, spec["canonical_labels"])
        before_rows = feature_shift(canon, matrix, feature_columns)
        after_rows = feature_shift(canon, harmonized, feature_columns)
        with open(OUT_DIR / f"residual_feature_shift_{key}.csv", "w", newline="",
                  encoding="utf-8") as h:
            fn = ["feature", "is_time_feature", "canon_median", "lab_median",
                  "ks_before", "ks_after", "outside_p01_p99_before",
                  "outside_p01_p99_after"]
            w = csv.DictWriter(h, fieldnames=fn); w.writeheader()
            after_by = {r["feature"]: r for r in after_rows}
            for r in before_rows:
                a = after_by[r["feature"]]
                w.writerow({"feature": r["feature"],
                            "is_time_feature": r["is_time_feature"],
                            "canon_median": r["canon_median"],
                            "lab_median": a["lab_median"],
                            "ks_before": r["ks_statistic"], "ks_after": a["ks_statistic"],
                            "outside_p01_p99_before": r["pct_lab_outside_canon_p01_p99"],
                            "outside_p01_p99_after": a["pct_lab_outside_canon_p01_p99"]})

        mrr = model_relevant_residual(before_rows, after_rows, feature_columns, model)

        summary["scenarios"][key] = {
            "support": orig["support"],
            "original_detection_rate": orig["detection_rate"],
            "compatibility_detection_rate": comp["detection_rate"],
            "detection_rate_change_pp": pp_change,
            "absolute_detection_change": comp["predicted_attack"] -
            orig["predicted_attack"],
            "shift_before_all": shift_overview(before_rows),
            "shift_after_all": shift_overview(after_rows),
            "shift_before_time": shift_overview(before_rows, "is_time_feature"),
            "shift_after_time": shift_overview(after_rows, "is_time_feature"),
            "shift_before_nontime": _nontime(before_rows),
            "shift_after_nontime": _nontime(after_rows),
            "model_relevant_residual": mrr,
            "reproduction_verified": reproduced["all_match"],
        }
        if "canonical_secondary" in spec:
            canon2 = canonical_matrix(feature_columns, spec["canonical_secondary"])
            summary["scenarios"][key]["secondary_shift_after_all"] = shift_overview(
                feature_shift(canon2, harmonized, feature_columns))

        before_after.append({"scenario": key, "phase": "original",
                             "detection_rate": orig["detection_rate"],
                             "detected": orig["predicted_attack"],
                             "support": orig["support"]})
        before_after.append({"scenario": key, "phase": "compatibility",
                             "detection_rate": comp["detection_rate"],
                             "detected": comp["predicted_attack"],
                             "support": comp["support"]})

    with open(OUT_DIR / "before_after_summary.csv", "w", newline="",
              encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=["scenario", "phase", "support", "detected",
                                          "detection_rate"])
        w.writeheader(); w.writerows(before_after)
    with open(OUT_DIR / "summary.json", "w", encoding="utf-8") as h:
        json.dump(summary, h, indent=1)

    for key in SCENARIOS:
        sc = summary["scenarios"][key]
        print(f"{key}: reproduced={sc['reproduction_verified']} "
              f"orig_detect={sc['original_detection_rate']:.4f} "
              f"compat_detect={sc['compatibility_detection_rate']:.4f} "
              f"pp_change={sc['detection_rate_change_pp']:+.2f}")
        print(f"    all-feature median KS  before={sc['shift_before_all']['median_ks']:.4f}"
              f" after={sc['shift_after_all']['median_ks']:.4f}")
        print(f"    time median KS         before={sc['shift_before_time']['median_ks']}"
              f" after={sc['shift_after_time']['median_ks']}")
        print(f"    non-time median KS     before={sc['shift_before_nontime']['median_ks']}"
              f" after={sc['shift_after_nontime']['median_ks']}")
    return 0


def _nontime(rows):
    sel = [r for r in rows if not r["is_time_feature"]]
    ks = [r["ks_statistic"] for r in sel if r["ks_statistic"] is not None]
    outside = [r["pct_lab_outside_canon_p01_p99"] for r in sel
               if r["pct_lab_outside_canon_p01_p99"] is not None]
    return {
        "comparable_features": len(ks),
        "median_ks": float(np.median(ks)) if ks else None,
        "count_ks_ge_0_5": sum(1 for v in ks if v >= 0.5),
        "count_ks_ge_0_8": sum(1 for v in ks if v >= 0.8),
        "count_100pct_outside": sum(1 for v in outside if v >= 100.0),
    }


if __name__ == "__main__":
    sys.exit(main())
