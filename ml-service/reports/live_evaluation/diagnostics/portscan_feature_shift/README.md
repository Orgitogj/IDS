# PortScan feature-distribution shift audit (diagnostic only)

**Phase 16 Part 2B-D1.** This is a *diagnostic*. It does not modify any experiment
result, does not retrain, does not tune, does not change thresholds or the frozen model,
and invokes neither SHAP nor an LLM. It asks one question:

> Is the observed laboratory PortScan detection failure **consistent with** a
> feature-distribution shift between canonical CICIDS2017 PortScan flows and the
> laboratory selector-matched PortScan flows?

It can support or weaken the shift hypothesis. It **cannot establish causality** and does
not attempt to.

## Sources

| | rows | provenance |
|---|---:|---|
| Canonical PortScan | 31,761 | true `PortScan` rows from the frozen random-v2 test partition (`train_test_split(test_size=0.2, random_state=42, stratify=labels)`), read from `cicids2017_cleaned.parquet` |
| Laboratory PortScan | 1,362 | selector-matched ATTACK flows (`.10→.20`) from `lab-v1-portscan-001`, re-derived from the raw capture through the same map + strict-validate path used at run time |

Excluded exactly as required: the 816 UNLABELLED reverse flows, all training data, synthetic
data, smoke-test rows. Both matrices use the frozen 78-feature schema `cicids2017-78-v1` in
artifact order.

## Method

Per feature: canonical and laboratory `n / median / mean / std / p25 / p75`, plus
robust shift indicators — two-sample KS statistic, absolute standardized mean difference
(guarded against zero pooled std), median difference and ratio (ratio suppressed when the
canonical median is ~0), and the percentage of laboratory values falling outside the
canonical IQR and outside the canonical 1st–99th-percentile band. 17 features are
constant in canonical PortScan (std ≈ 0); KS is not defined for them and is reported as
null rather than a misleading value.

Model relevance uses the frozen XGBoost `feature_importances_` (read-only; no SHAP). We do
**not** claim importance proves causality — only whether features the model leans on are
also among the shifted ones.

## Headline numbers

- Non-constant features compared: **61 / 78** (17 canonical-constant).
- **35 / 61** features have KS ≥ 0.5; **24 / 61** have KS ≥ 0.8 (near-disjoint).
- **Median KS across comparable features = 0.712.**
- The eight most-shifted features have **KS ≈ 1.0** with **100 %** of laboratory values
  outside the canonical p01–p99 band.
- **11 / 15** top model-important features have KS ≥ 0.5.

## The nuance that matters

The two single most-important features are **not** shifted:

| rank | feature | importance | KS |
|---:|---|---:|---:|
| 0 | Idle Mean | 0.239 | 0.002 |
| 1 | Bwd Packet Length Std | 0.123 | 0.001 |

Both are ~0 in canonical and laboratory alike. But from rank 2 downward the model's
important features are heavily shifted — PSH Flag Count (KS 0.9995), Average Packet Size
(0.9996), Max Packet Length (0.9994), Total Length of Fwd Packets (0.9998), Fwd Packet
Length Min/Max (1.000/0.9996), Bwd Header Length (0.715), Bwd Packet Length Mean (0.712).
So the failure is not explained by the top two signals alone; it is consistent with the
model losing the *ensemble* of secondary signals it normally combines.

## Semantic tells consistent with implementation / domain shift

These are observations, not proof of cause:

- **Forward packet size.** Canonical PortScan medians for Fwd Packet Length Min/Mean,
  Min Packet Length, Avg Fwd Segment Size are ~0; laboratory medians are ~58 bytes. The
  laboratory forward flows carry a payload-length profile the canonical PortScan flows did
  not record.
- **Flow timing.** Flow Duration and Flow IAT Mean/Max/Min have canonical median ~47 (µs)
  versus laboratory median 0 — near-instantaneous single-exchange flows.
- **Backward direction.** Bwd Header Length and Total Backward Packets are ~0 in the
  laboratory forward flows, consistent with the direction-splitting already seen in the
  selector audit (the target's RST is tracked as a separate reverse flow).
- **PSH flag.** Canonical PortScan median PSH Flag Count is 1; laboratory is 0.

Identical feature names do **not** imply identical feature semantics between the original
CICIDS2017 feature-generation pipeline and `cicflowmeter 0.5.0` (Python). The pattern is
**consistent with implementation/domain shift**; we do not claim the Python implementation
is wrong, and we do not assert "caused by CICFlowMeter-vs-cicflowmeter".

## Prediction-stratified (exploratory only)

Of 1,362 laboratory flows the frozen model flagged 2 (destination ports 9 and 12), both as
FTP-Patator. With n = 2 no inference is drawn; the values are recorded for completeness
only.

## Conclusion

**A — Strong evidence consistent with feature/domain shift**, with two stated caveats:
causality is not established, and the two single highest-importance features are not
shifted. The strength rests on median KS 0.71 across comparable features, 24 features with
near-disjoint distributions, whole-band separation on the most-shifted features, and 11 of
15 top model-important features shifted.

## Outputs

- `summary.json` — machine-readable overview and prediction-stratified block
- `feature_shift.csv` — all 78 features, ranked by KS
- `top_shifted_features.csv` — the 10 most shifted
- `model_relevant_shift.csv` — top-15 model-important features with their shift
