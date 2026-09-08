# Feature-contract compatibility experiment (`lab-feature-compat-v1`)

**Phase 16 Part B–H.** A controlled, versioned counterfactual. It quantifies how much of
the PortScan and SSH laboratory detection failure is associated with the confirmed
seconds-vs-microseconds feature-contract incompatibility, **while the frozen model
`xgb-baseline-cicids2017-v2` is left completely unchanged** — no retraining, no tuning, no
threshold change, no calibration, no SHAP, no LLM.

The transformation was specified from unit evidence alone; **prediction outcomes never
determined it**.

## 1. Problem discovered

The SSH and PortScan diagnostics found that laboratory `cicflowmeter 0.5.0` and the
canonical CICIDS2017 CICFlowMeter express time features on different scales. Canonical time
features are in **microseconds** (Flow Duration max ≈ 1.2e8 = the 120 s flow timeout);
laboratory time features are in **seconds** (Flow Duration ≈ 1.5–2.7 for ~2 s flows). The
value reaches the frozen model unconverted.

## 2. Exact confirmed contract (`contract_audit.csv`)

**13 CONFIRMED_UNIT_CONVERSION features** — canonical microseconds scale (p99 ≥ 1e5) with
positive laboratory seconds-scale evidence (non-zero, p99 < 1e4):

Flow Duration; Flow IAT Mean/Std/Max; Fwd IAT Total/Mean/Std/Max; Bwd IAT
Total/Mean/Std/Max/Min. Conversion: `value_us = value_seconds × 1_000_000`.

**10 LIKELY_UNIT_CONVERSION features, not auto-converted** — Flow IAT Min, Fwd IAT Min,
Active Mean/Std/Max/Min, Idle Mean/Std/Max/Min: canonical microseconds but **all-zero in
both laboratory captures**, so no positive seconds-scale evidence; converting 0 is a no-op,
excluded from the primary correction to keep it evidence-based.

**4 rate features NOT converted** — Flow Bytes/s, Flow Packets/s, Fwd/Bwd Packets/s:
`cicflowmeter` already emits these per second (lab Flow Bytes/s ≈ 6e4 is bytes/second, not
bytes/µs), so they are **not double-corrected** for the duration unit.

## 3. No retraining

The same artifact (`xgb_baseline_cicids2017_v2.joblib`, SHA
`2b7625fc…fddfa`) and label encoder are used throughout. The compatibility layer
(`app/live/compat.py`) transforms raw flow vectors *before* the unchanged classifier; the
original deployment path is preserved and reproducible. Feature count (78), order, and
schema (`cicids2017-78-v1`) are asserted unchanged; double application is guarded.

## 4. Original-path reproduction (Phase C)

Rebuilt from the raw captures with the original path — reproduced **exactly**:

| scenario | support | detected | BENIGN |
|---|---:|---:|---:|
| PortScan | 1362 | 2 | 1360 |
| SSH | 69 | 0 | 69 |

## 5. PortScan before / after (`portscan_comparison.json`)

| | original | after harmonization |
|---|---:|---:|
| detected | 2 | 2 |
| detection rate | 0.00147 | 0.00147 |
| Δ | | **+0.00 pp** |

## 6. SSH before / after (`ssh_comparison.json`)

| | original | after harmonization |
|---|---:|---:|
| detected | 0 | 0 |
| detection rate | 0.0 | 0.0 |
| Δ | | **+0.00 pp** (absolute, not a relative ratio) |

## 7. Residual feature shift (Phase E)

The harmonization **worked on the time features it targeted** — e.g. SSH Flow Duration KS
**1.000 → 0.518**, Flow IAT Max **1.000 → 0.480** (the unit artifact is removed; a genuine
~5× duration difference, lab ≈ 2 s vs canonical ≈ 10.6 s, remains). But the residual shift
is dominated by **non-time** features, which the unit fix does not touch:

| scenario | all-feature median KS before → after | non-time median KS before → after | non-time features 100 % outside canonical p01–p99 (after) |
|---|---|---|---:|
| PortScan | 0.7118 → 0.7118 | 0.8522 → 0.8522 | 26 |
| SSH | 0.9983 → 0.9949 | 1.0000 → 1.0000 | 30 |

Every top model-important **non-time** feature stays fully disjoint after harmonization —
Bwd Packet Length Std, PSH Flag Count, Average Packet Size, Bwd Packet Length Mean, Max
Packet Length, Total Length of Fwd Packets all KS 1.000 → 1.000 (`model_relevant_residual_shift`
via `summary.json`). PortScan time features were already near-zero KS (single-packet scans
in both populations), so harmonization is a no-op there.

## 8. Scientific interpretation (Phase F)

**PortScan: Classification C** — unit harmonization has essentially no effect (the time
features were never the issue for single-packet scans); residual domain/semantic
differences in non-time features (median KS 0.85, 26 features fully outside canonical
bands) dominate.

**SSH: Classification C** — unit harmonization is a real, confirmed correction that reduces
the time-feature shift (Flow Duration KS 1.0 → 0.52), yet it changes detection by **0.00
pp**, because the classifier's decision is dominated by non-time features (packet sizes,
flags, header/segment sizes) that remain 100 % outside canonical regions (median KS 1.0).

**Combined.** The confirmed unit incompatibility affected the feature values presented to
the classifier, and applying the independently specified unit harmonization changed the
classifier's predictions by 0.00 pp in both scenarios. After harmonization a large
**residual deployment-domain shift remains**, concentrated in non-time features. The
detection failure is therefore **associated with** a broad domain shift rather than
explained by the unit incompatibility alone.

Four quantities are kept separate and never collapsed:
1. **benchmark** (random-v2): PortScan / SSH-Patator strong (Macro F1 0.8806 overall);
2. **original deployment-pipeline**: PortScan 0.00147, SSH 0.0;
3. **feature-contract-corrected**: PortScan 0.00147, SSH 0.0 (unchanged);
4. **residual deployment-domain generalization**: large non-time shift persists.

## 9. Limitation

This experiment corrects a **feature-extraction implementation** difference (the time
unit). It **cannot separate** the remaining feature-extraction-implementation differences
(e.g. flag counting, segmentation) from genuine **dataset domain shift** (different SSH
stack, cipher/MAC, tooling, network). Both may coexist in the residual, and this design
does not isolate them. No claim is made that any tool is wrong or that the entire failure
is caused by the extraction pipeline.

## 10. Albanian thesis subsection

*Problemi i zbuluar: mjeti laboratorik `cicflowmeter 0.5.0` shpreh 13 veçori kohore në
sekonda, ndërsa dataset-i kanonik CICIDS2017 i shpreh në mikrosekonda, dhe vlera i kalon
modelit të ngrirë pa u konvertuar. Korrigjim i kontrolluar: u zbatua një harmonizim i
versionuar (`lab-feature-compat-v1`, `value_us = value_seconds × 1e6`) vetëm mbi 13
veçoritë e konfirmuara, para klasifikuesit të pandryshuar; pa ritrajnim, pa akordim, pa
ndryshim pragu. PortScan para/pas: 2/1362 → 2/1362 (+0.00 pp). SSH para/pas: 0/69 → 0/69
(+0.00 pp). Zhvendosja e mbetur: harmonizimi uli KS-në e veçorive kohore (p.sh. Flow
Duration 1.0 → 0.52), por veçoritë jo-kohore (madhësi paketash, flamuj) mbeten plotësisht
të shkëputura (KS ≈ 1.0, 30 veçori 100% jashtë brezit kanonik për SSH). Interpretim
shkencor: mospërputhja e njësive është reale dhe e konfirmuar, por korrigjimi i saj nuk e
rikthen detektimin; dështimi është **në përputhje me** një zhvendosje të gjerë domeni
vendosjeje, jo i shpjegueshëm vetëm nga njësia. Kufizim: ky eksperiment nuk mund t'i ndajë
plotësisht ndryshimet e implementimit të nxjerrjes së veçorive nga zhvendosja natyrore e
domenit; të dyja mund të bashkëjetojnë në mbetjen.

## Artifacts

`contract_audit.csv`, `transformations.json`, `protocol.json`,
`{portscan,ssh}_original_reproduction.json`, `{portscan,ssh}_compatibility_predictions.csv`,
`{portscan,ssh}_comparison.json`, `residual_feature_shift_{portscan,ssh}.csv`,
`before_after_summary.csv`, `summary.json`. Raw captures are referenced from their existing
provenance, not duplicated.
