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
               / "lab-v1-portscan-001.csv")
LAB_MANIFEST = (_ML_SERVICE_ROOT / "training" / "configs" / "live"
                / "lab-v1-portscan-001.yaml")
OUT_DIR = (_ML_SERVICE_ROOT / "reports" / "live_evaluation" / "diagnostics"
           / "portscan_feature_shift")

NEAR_CONSTANT_STD = 1e-9


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_portscan(feature_columns):
    meta = pd.read_parquet(DATASET, columns=["Label"])
    labels = (meta["Label"].astype(str).str.replace("\x96", "-", regex=False)
              .str.strip().to_numpy())
    idx = np.arange(len(labels))
    _, test_idx = train_test_split(idx, test_size=0.2, random_state=42, stratify=labels)
    test_idx = np.sort(test_idx)
    ps_positions = test_idx[labels[test_idx] == "PortScan"]

    frame = pd.read_parquet(DATASET, columns=feature_columns)
    matrix = frame.iloc[ps_positions][feature_columns].to_numpy(dtype="float64")
    return matrix


def lab_portscan(feature_columns):
    manifest = manifest_module.load(LAB_MANIFEST)
    reference = load_reference(None)
    validator = FeatureValidator(feature_columns, reference=reference,
                                 feature_version=manifest.model["feature_version"],
                                 policy=STRICT_POLICY)

    rows = []
    ports = []
    with open(LAB_CAPTURE, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if manifest.expected_for_flow(row) != "ATTACK":
                continue
            validation = validator.validate(lab_runner.map_row(row))
            if not validation.valid:
                continue
            rows.append(validation.vector)
            ports.append(int(float(row.get("dst_port") or -1)))

    return np.asarray(rows, dtype="float64"), np.asarray(ports)


def _pct_outside(values, low, high):
    if low is None or high is None or not np.isfinite(low) or not np.isfinite(high):
        return None
    return float(np.mean((values < low) | (values > high)) * 100.0)


def feature_stats(canon, lab, feature_columns):
    rows = []
    for i, name in enumerate(feature_columns):
        c = canon[:, i]
        l = lab[:, i]
        c_std = float(np.std(c))
        l_std = float(np.std(l))
        c_p25, c_p75 = np.percentile(c, [25, 75])
        c_p01, c_p99 = np.percentile(c, [1, 99])
        c_mean, l_mean = float(np.mean(c)), float(np.mean(l))
        c_med, l_med = float(np.median(c)), float(np.median(l))

        pooled = np.sqrt((c_std ** 2 + l_std ** 2) / 2.0)
        std_diff = (abs(l_mean - c_mean) / pooled) if pooled > NEAR_CONSTANT_STD else None

        med_diff = l_med - c_med
        med_ratio = (l_med / c_med) if abs(c_med) > NEAR_CONSTANT_STD else None

        canon_constant = c_std <= NEAR_CONSTANT_STD
        if canon_constant:
            ks = None
        else:
            ks = float(ks_2samp(c, l).statistic)

        iqr_low = c_p25 - 0.0
        pct_out_iqr = _pct_outside(l, c_p25, c_p75)
        pct_out_p01_p99 = _pct_outside(l, c_p01, c_p99)

        rows.append({
            "feature": name,
            "canon_n": int(len(c)),
            "canon_median": c_med,
            "canon_mean": c_mean,
            "canon_std": c_std,
            "canon_p25": float(c_p25),
            "canon_p75": float(c_p75),
            "canon_p01": float(c_p01),
            "canon_p99": float(c_p99),
            "lab_n": int(len(l)),
            "lab_median": l_med,
            "lab_mean": l_mean,
            "lab_std": l_std,
            "lab_p25": float(np.percentile(l, 25)),
            "lab_p75": float(np.percentile(l, 75)),
            "abs_standardized_diff": std_diff,
            "median_diff": med_diff,
            "median_ratio": med_ratio,
            "ks_statistic": ks,
            "pct_lab_outside_canon_iqr": pct_out_iqr,
            "pct_lab_outside_canon_p01_p99": pct_out_p01_p99,
            "canon_constant": canon_constant,
            "lab_constant": l_std <= NEAR_CONSTANT_STD,
        })
    return rows


def rank(rows):
    def sort_key(r):
        return r["ks_statistic"] if r["ks_statistic"] is not None else -1.0
    return sorted(rows, key=sort_key, reverse=True)


def model_relevant(rows, feature_columns, model, top_k=15):
    importances = model.feature_importances_
    order = np.argsort(importances)[::-1]
    by_name = {r["feature"]: r for r in rows}
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
            "abs_standardized_diff": r["abs_standardized_diff"],
            "pct_lab_outside_canon_p01_p99": r["pct_lab_outside_canon_p01_p99"],
            "canon_median": r["canon_median"],
            "lab_median": r["lab_median"],
        })
    return out


def prediction_stratified(lab, ports, feature_columns, model, label_encoder):
    frame = pd.DataFrame(lab, columns=feature_columns)
    predicted_idx = model.predict(frame)
    predicted = label_encoder.inverse_transform(predicted_idx)
    detected = predicted != "BENIGN"

    summary = {
        "lab_flows": int(len(lab)),
        "predicted_benign": int((~detected).sum()),
        "predicted_attack": int(detected.sum()),
        "detected_ports": [int(p) for p in ports[detected]],
        "detected_predicted_labels": [str(x) for x in predicted[detected]],
        "note": ("n_detected is tiny; feature values are exploratory only and support no "
                 "statistical inference."),
    }

    detected_rows = []
    for pos in np.flatnonzero(detected):
        detected_rows.append({
            "dst_port": int(ports[pos]),
            "predicted_label": str(predicted[pos]),
        })
    summary["detected_flows"] = detected_rows
    return summary, predicted, detected


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    model, label_encoder, feature_columns, identity = lab_runner.load_frozen_model(
        _ML_SERVICE_ROOT / "models")

    canon = canonical_portscan(feature_columns)
    lab, ports = lab_portscan(feature_columns)

    rows = feature_stats(canon, lab, feature_columns)
    ranked = rank(rows)
    relevant = model_relevant(rows, feature_columns, model)
    strat, predicted, detected = prediction_stratified(
        lab, ports, feature_columns, model, label_encoder)

    ks_values = [r["ks_statistic"] for r in rows if r["ks_statistic"] is not None]
    high_ks = sum(1 for v in ks_values if v >= 0.5)
    very_high_ks = sum(1 for v in ks_values if v >= 0.8)
    median_ks = float(np.median(ks_values)) if ks_values else None

    outside_p = [r["pct_lab_outside_canon_p01_p99"] for r in rows
                 if r["pct_lab_outside_canon_p01_p99"] is not None]
    median_outside = float(np.median(outside_p)) if outside_p else None

    relevant_ks = [r["ks_statistic"] for r in relevant if r["ks_statistic"] is not None]
    relevant_high = sum(1 for v in relevant_ks if v >= 0.5)

    summary = {
        "schema_version": 1,
        "diagnostic": "portscan_feature_shift",
        "generated_at": utc_now(),
        "is_diagnostic_only": True,
        "does_not_modify_frozen_results": True,
        "no_retraining_no_tuning_no_shap_no_llm": True,
        "feature_schema": identity["feature_schema"],
        "model": identity,
        "canonical_portscan_support": int(canon.shape[0]),
        "laboratory_portscan_support": int(lab.shape[0]),
        "n_features": len(feature_columns),
        "shift_overview": {
            "features_with_ks_computed": len(ks_values),
            "features_ks_ge_0_5": high_ks,
            "features_ks_ge_0_8": very_high_ks,
            "median_ks_statistic": median_ks,
            "median_pct_lab_outside_canon_p01_p99": median_outside,
            "constant_canonical_features": sum(1 for r in rows if r["canon_constant"]),
        },
        "model_relevant_overview": {
            "top_k_importance": len(relevant),
            "top_k_with_ks_ge_0_5": relevant_high,
            "top_feature": relevant[0]["feature"] if relevant else None,
            "top_feature_ks": relevant[0]["ks_statistic"] if relevant else None,
        },
        "prediction_stratified": strat,
    }

    with open(OUT_DIR / "summary.json", "w", encoding="utf-8") as h:
        json.dump(summary, h, indent=1)

    fieldnames = list(rows[0].keys())
    with open(OUT_DIR / "feature_shift.csv", "w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(ranked)

    with open(OUT_DIR / "top_shifted_features.csv", "w", newline="",
              encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(ranked[:10])

    with open(OUT_DIR / "model_relevant_shift.csv", "w", newline="",
              encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=list(relevant[0].keys()))
        w.writeheader()
        w.writerows(relevant)

    print(f"canonical PortScan support : {canon.shape[0]}")
    print(f"laboratory PortScan support: {lab.shape[0]}")
    print(f"features KS>=0.5 : {high_ks}/{len(ks_values)}  KS>=0.8: {very_high_ks}")
    print(f"median KS        : {median_ks:.4f}")
    print(f"median % lab outside canon p01-p99: {median_outside:.2f}")
    print(f"top-15 model-important features with KS>=0.5: {relevant_high}/15")
    print()
    print("top 10 shifted features (by KS):")
    for r in ranked[:10]:
        print(f"  {r['feature']:<28} KS={r['ks_statistic']:.4f} "
              f"canon_med={r['canon_median']:.4g} lab_med={r['lab_median']:.4g} "
              f"out_p01_p99={r['pct_lab_outside_canon_p01_p99']:.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
