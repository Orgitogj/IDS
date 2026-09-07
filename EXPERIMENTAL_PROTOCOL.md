# EXPERIMENTAL_PROTOCOL.md — P0-FINAL freeze

**Status:** APPROVED AND FROZEN (2026-09-06). The four freeze changes are implemented and
tested. No model has been trained; no database has been written.
**Date:** 2026-09-06 · **Branch:** `main` (clean, up to date with `origin/main`)

This document freezes the experiments that will appear in the thesis, **before** any `v2`
model is trained. Companion documents: `IDS_ARCHITECTURE_AUDIT.md` (state),
`EVALUATION.md` (measured results), `ml-service/training/README.md` (how to run).

---

## 0. P0 verification

| Check | Result | Evidence |
|---|---|---|
| P0-1 training pipeline reproducible | **PASS** | Single `seed` reaches split → undersample → SMOTE → estimator. Balancing executes to exactly 653,897 rows on the real dataset, matching two independent v1 artifacts. Pinned by `TestAgainstTheRealDataset`. |
| P0-2 evaluation/registration reproducible | **PASS** | Every metric computed at run time. Harness reproduces `EVALUATION.md` §6's verified anchor to 4 dp on all four metrics. Registration accepts only a validated `EvaluationReport`. |
| P0-3 SHAP/LLM grounded | **PASS** | TreeSHAP for the predicted class, bias excluded. Both providers receive a byte-identical prompt. `v3` carries evidence-boundary, no-invention and style rules on both templates. |
| All tests pass | **PASS** | `443 passed, 1 deselected` (the deselected one is the live-LLM test, deliberately not run). |
| No `v1` artifact modified | **PASS** | Every `models/*_v1.joblib` retains its original mtime (2026-08-12 … 2026-08-21). `find models -newermt 2026-09-06` returns nothing. |
| Nothing written to PostgreSQL | **PASS** | Postgres and the backend were down for the whole of P0-1/2/3. `reregister_experiments` ran in dry-run only; `--commit` additionally requires `--yes`. |
| No known data leakage in the final pipeline | **PASS with one caveat** | Split before resampling and asserted disjoint; balancing receives only `train_idx`; scaler fitted on the balanced training matrix only; label encoder fitted on training labels only; feature sets are fixed lists. **Caveat:** the historical `isolation_forest_cicids2017_v1` used `contamination = test attack rate` and remains contaminated — it is excluded from all final results in favour of `isolation_forest_benign_v2`. |

---

## 1. The `top78` question — resolved

### What was checked

| Question | Finding |
|---|---|
| Trained on those columns in that order? | **Yes.** `feature_names_in_` differs from the 78-set at **all 78 positions**; same 78 features as a set. |
| Is evaluation feeding the training order? | **Yes.** The evaluator builds column positions from each model's own `feature_names_in_`. Predictions from a bare array and from a column-named DataFrame were verified identical. |
| Could this be a schema mismatch? | **No.** Ruled out by the check above. |
| Same training data / balancing? | **Yes.** Root cover is 81,373.9 for *both*, implying 653,897 training rows for both — the same balanced set. |
| Same seed / hyperparameters? | **Yes.** `get_params()` differs in nothing (`missing=nan` compares unequal to itself; not a real difference). Both 100 estimators × 15 classes = 1,500 trees, `random_state=42`, `tree_method=hist`. |
| Why would order alone change the model? | Column order changes tie-breaking in XGBoost's split search: when two candidate splits have equal gain, the lower feature index wins. Permuting columns permutes those ties. |

### How large the difference actually is

Direct comparison of the two models' predictions over the full 565,576-row test set:

```
predictions that differ : 43   (0.0076 %)
agreement               : 99.9924 %
  78-model correct      : 19
  top78 correct         : 23
  both wrong            :  1
```

Net: **+4 correct predictions out of 565,576.** Accuracy differs by +0.000007.

Decomposition of the +0.009135 macro-F1 gap:

| Class | Test support | F1 (78-model) | F1 (top78) | Contribution to macro gap |
|---|---:|---:|---:|---:|
| Infiltration | **7** | 0.7143 | 0.8000 | **+0.00571** |
| Web Attack – Sql Injection | **4** | 0.4444 | 0.5000 | **+0.00370** |
| Web Attack – Brute Force | 301 | 0.7132 | 0.7074 | −0.00039 |
| Bot | 391 | 0.8212 | 0.8225 | +0.00009 |
| all 11 others | — | — | — | ≈ 0 |

**Classes with support ≥ 100 contribute −0.000283** — on every class that can support a
claim, `top78` is fractionally *worse*. The entire visible advantage (103 % of it) comes
from two classes with 7 and 4 test rows, where one prediction flip moves F1 by 0.05–0.09.

A further point: `feature_importances_` is non-zero for only **59 of 78** features. The
last 19 are tied at exactly 0.0 gain, so their order inside the "top-78" ranking is
arbitrary — an artefact of a stable sort, not a modelling decision.

### Verdict

> **HISTORICAL ONLY / EXCLUDE FROM FINAL RESULTS**

Not because the run was invalid, but because it is **not a distinct experiment**: same
dataset, same split, same balanced rows, same hyperparameters, same seed, same 78 features.
Only the column order differs. The measured difference (43 flows, +4 net correct) sits far
below the noise floor that the project has already declared unreportable
(`MIN_SUPPORT_FOR_CLAIM = 100`, `EVALUATION.md` §7).

Presenting `top78` as the best model would mean reporting a tie-breaking artefact as a
finding. It stays in `models/` and in the P0-2 recomputation table as a historical record,
and the RQ3 curve uses the main 78-feature model for its N = 78 point.

**This is itself a thesis-worthy result:** it demonstrates empirically why macro F1 over
15 classes is unsafe as a headline metric on CICIDS2017 — which drives the decision in §6.

---

## 2. Final model set

Cost figures are extrapolations from one measured point (XGBoost, 116,655 balanced rows,
**25.9 s** on this machine: Intel 12-core, Windows 11, Python 3.11.9). They are estimates,
not measurements; the pipeline records the real `train_seconds` in every bundle.

| Model | Research question | Needed? | Est. training cost |
|---|---|---|---|
| **XGBoost + balancing** (`xgb_smote_cicids2017_v2`) | RQ1 primary; the deployed model; base for RQ3, LOFO and H4 evidence | **REQUIRED** | ~2–4 min |
| **XGBoost baseline** (`xgb_baseline_cicids2017_v2`) | Isolates the effect of balancing — the only controlled way to make that claim | **REQUIRED** | ~8–12 min (2.26 M rows) |
| **Random Forest + balancing** (`rf_smote_cicids2017_v2`) | RQ1 needs a second algorithm family under identical treatment; RF is the standard IDS baseline | **REQUIRED** | ~10–20 min |
| **Random Forest baseline** (`rf_baseline_cicids2017_v2`) | Completes a consistent 2×2 (algorithm × balancing) so Table A is single-vintage | **REQUIRED** | ~35–60 min, ~155 MB artifact |
| **MLP + balancing** (`mlp_smote_cicids2017_v2`) | RQ1 third algorithm family (neural); also the only model exercising the scaler path, which demonstrates the fit-on-train-only control | **REQUIRED** | ~5–10 min (early stopping) |
| **Isolation Forest** (`isolation_forest_benign_v2`) | Anomaly / unseen-family experiment | **ALREADY DONE — do not retrain** | — |
| **`xgb_smote_top78features`** | none | **EXCLUDE** (§1) | — |
| Feature-selection variants 10/20/30/50 | RQ3 | **REQUIRED** | ~1–3 min each |

**Total estimated wall time: ~1.5–2.5 hours**, dominated by the RF baseline.

**DECIDED: the Random Forest baseline IS retrained as v2.** Every headline model passes
through the same training pipeline, evaluation pipeline, seed policy, artifact format,
provenance record and latency methodology, so no row of Table A is a mixed vintage.

Deliberately **not** retrained: nothing else. No new algorithms are added; the point is
correctness, not a longer list.

---

## 3. Feature-selection protocol (RQ3)

**Leakage check on the historical ranking: CLEAN.** Notebook cell 53 ranks by
`xgb_smote.feature_importances_`, and `xgb_smote` was fitted in cell 29 on
`X_train_balanced` / `y_train_balanced_encoded`, both derived from the training split
only. No test row influenced the ranking. Verified structurally: each historical top-N set
is an exact prefix of the top-78 importance order, and the sets are strictly nested
(10 ⊂ 20 ⊂ 30 ⊂ 50 ⊂ 78).

### Frozen protocol for v2

| Item | Decision |
|---|---|
| Ranking model | `xgb_smote_cicids2017_v2` — the balanced XGBoost, trained on the training split only |
| Ranking statistic | `XGBClassifier.feature_importances_`, `importance_type` unset → XGBoost 2.1.1 default **gain**, normalised to sum 1.0 |
| Data seen by the ranking | Balanced **training** rows only. Never the test set. |
| Balancing | Identical to the main model: BENIGN → 200,000, non-BENIGN < 2,000 → 2,000 by SMOTE, train only |
| Seed | 42 everywhere |
| Split | Random, stratified, `test_size=0.2`, `random_state=42` |
| Top-N selection | First N of the ranking, descending gain, ties broken by the dataset's column order (deterministic and documented) |
| N values | 10, 20, 30, 50, 78 |
| N = 78 point | The main `xgb_smote_cicids2017_v2` model itself, in dataset column order — **not** a re-ordered retrain |
| New set names | `cicids2017-top{N}-v2`, registered in `training_feature_reference.json` alongside the v1 sets |
| Metrics | §6 |
| Latency | §5 |

**Consequence to accept explicitly:** the v2 ranking is derived from a model trained with a
different SMOTE seed than v1, so `cicids2017-top50-v2` may not equal
`cicids2017-top50-v1`. The overlap must be reported. Since the live agent runs the top-50
model, the agent moves to the v2 feature set together with the v2 model — they ship as a
pair, and `FeatureValidator` will reject a mismatch rather than silently proceed.

**Report alongside the curve:** only 59 of 78 features have non-zero gain. Beyond N ≈ 59
the added features carry no information for this model, which is the honest explanation of
why the curve flattens rather than "more features stop helping".

---

## 4. Random-split protocol (primary experiment)

| Item | Frozen value |
|---|---|
| Dataset | `datasets/cicids2017_cleaned.parquet`, 2,827,876 rows, sha256 `f5b393d6…3d1d` |
| Split | `train_test_split(test_size=0.2, random_state=42, stratify=y)` |
| Train / test | 2,262,300 / 565,576 |
| Stratification | On the 15-class label |
| Seed | **42**, single value, propagated to split → undersample → SMOTE → estimator |
| Balancing | Train only. BENIGN → 200,000; non-BENIGN < 2,000 → 2,000 via SMOTE (`k_neighbors=5`); others untouched → **653,897 rows** |
| Scaler | MLP only; `StandardScaler` fitted on the balanced **training** matrix, applied to test without refitting |
| Label encoder | Fitted on training labels only |
| Feature selection | Ranked from training data only (§3) |
| Test set | **Untouched** — natural distribution, never resampled, reweighted or scaled by a test-fitted transform |
| Disjointness | Asserted at run time (`assert_disjoint`), not assumed |

### Primary metric — FROZEN

| Rank | Metric | Role |
|---|---|---|
| **1** | **Macro F1 over all 15 classes** | **PRIMARY** — model ranking |
| 2 | Macro F1 over classes with test support ≥ 100 | **Robustness / sensitivity analysis** |
| 3 | Accuracy, Macro Precision, Macro Recall, Weighted F1 | Secondary |
| 4 | Per-class Precision / Recall / F1 / Support (+ FPR, FNR) | Detail; small classes marked `insufficient_support` |
| 5 | Binary BENIGN-vs-attack recall and benign FPR | Operational reading |
| 6 | Confusion matrix (CSV + PNG) | Appendix |

**Why the standard metric stays primary.** The very rare classes are a real part of
CICIDS2017, and dropping them from the headline would read as cherry-picking. Standard
Macro F1 is also what the literature reports, so it keeps the work comparable. The
restricted variant is therefore a *sensitivity analysis*, never a replacement.

**What the discussion must state.** Full Macro F1 is statistically unstable on this
dataset: Infiltration (n = 7) and Web Attack – Sql Injection (n = 4) each carry
1/15 = 6.7 % of it, and one prediction flip moves an individual class F1 by 0.05–0.50.
§1 is the worked demonstration — two models differing on 43 of 565,576 flows differ by
+0.009 in full Macro F1, and 103 % of that gap comes from those two classes. Reporting the
support ≥ 100 variant beside it lets a reader see how much of any ranking rests on classes
that cannot support a claim.

**`top78` remains HISTORICAL ONLY / EXCLUDED** despite its higher full Macro F1: it is not
a scientifically distinct configuration — only the column order of the same 78 features
differs — and the gain comes almost entirely from those extremely small classes.

Every run emits both: `metrics.overall.macro_f1` (primary),
`metrics.macro_f1_min_support` (sensitivity), and
`metrics.classes_in_macro_f1_min_support` naming exactly which classes the second counts.

---

## 5. Latency protocol — frozen

Batch and single-flow measure different things and **must never be compared to each
other**. Observed spread on the same model and machine: 0.0077 ms batch vs 37.3 ms
single-flow for the Random Forest — a factor of ~4,800.

### A. Batch throughput (computational cost comparison between models)

| Item | Value |
|---|---|
| Procedure | One `model.predict(X_test)` over the entire test set |
| Batch size | 565,576 (the whole test set) |
| Reported | `ms_per_flow = elapsed / n · 1000`, and `flows_per_second` |
| Warm-up | One discarded `predict` over 1,000 rows |
| Repetitions | 3; report the **median**, and min/max as a spread |
| Includes | Model inference only |
| Excludes | Feature validation, SHAP, HTTP, database, JSON |
| Comparable with | The historical notebook figures (same methodology) |

### B. Single-flow latency (online IDS simulation)

| Item | Value |
|---|---|
| Procedure | `model.predict(X[i:i+1])` one row at a time |
| Sample | 200 rows drawn from the test set with `seed=42` |
| Reported | **mean, median, p95** |
| Warm-up | 20 discarded single-row predictions |
| Repetitions | 1 pass of 200 (the 200 samples are themselves the distribution) |
| Includes | Model inference only |
| Excludes | Feature validation, SHAP, HTTP, database |

### C. End-to-end IDS latency — separate, optional, differently named

If reported at all, measured on the live path and labelled **`end_to_end_alarm_latency`**,
never "inference latency". Components stated separately: CICFlowMeter flow export →
feature mapping and validation → model inference → HTTP POST → persistence → WebSocket.

### Environment recorded with every latency figure

CPU model and physical/logical core count; RAM; OS build; Python version; `numpy`,
`scikit-learn`, `xgboost` versions; the thread count actually used (`n_jobs`); whether the
machine was on mains power. Current environment: Intel64 Family 6 Model 154 (12 logical
cores), Windows 11 build 26200, Python 3.11.9, numpy 2.1.1, scikit-learn 1.5.2,
xgboost 2.1.1.

**Latency is not a reproducibility check.** P0-2 measured 0.0077 ms where the notebook
recorded 0.0054 ms for the same artifact; that is hardware, not disagreement.

### Implementation status — DONE

`training/pipeline/evaluation.py` now implements exactly this: `BATCH_WARMUP_ROWS = 1000`,
`BATCH_REPETITIONS = 3` with the median reported, `SINGLE_FLOW_WARMUP = 20`,
`SINGLE_FLOW_SAMPLES = 200` with mean / median / p95. Both methodology strings are embedded
in every report and name what is excluded. Pinned by `tests/test_protocol_freeze.py`.

**The timed region is model-input-ready inference:** the feature matrix is already built
and, where a scaler applies, already transformed. Feature validation, DataFrame
construction, SHAP, HTTP, database and frontend all sit outside it. **This choice is frozen
and must not change once the final experiments start.**

---

## 6. Temporal evaluation protocol

`training/evaluate.py` implements both splits; both are methodologically valid and answer
different questions.

| Split | Question it answers | Status on CICIDS2017 |
|---|---|---|
| `temporal_global` — sort all rows by time, last 20 % is test | "What happens when a model trained through day N is deployed on day N+1?" | **Degenerate.** Each attack family runs on a single day, so DDoS (128,025) and PortScan (158,804) get **zero training rows** while eight other classes get **zero test rows**. The score mixes the split effect with an unmeasurable class-absence effect. |
| `temporal_per_class` — last 20 % of *each class* by time, per-class test counts copied from the random split | "How much of the random-split score comes from same-burst leakage, with class support held constant?" | **Controlled.** Support is identical class by class to the random split, so the only thing that changes is which rows land on each side. |

### Why the results differ so much

They are not two estimates of one quantity. `temporal_global` changes the *label
distribution* of both sides; `temporal_per_class` holds it fixed and changes only row
membership. The measured optimism of the random split (`EVALUATION.md` §6) — accuracy
0.9988 → 0.9756, macro F1 0.8614 → 0.7818, benign FPR 0.10 % → 2.58 % — comes from the
controlled split, which is the number that means something.

### Frozen decision

* **Primary temporal result: `temporal_per_class`.** This is the quantified optimism of the
  random split and belongs in the thesis as the honesty correction on RQ1.
* **`temporal_global`: reported as a documented degenerate case**, with its zero-support
  classes shown, to demonstrate *why* CICIDS2017 cannot support a true chronological
  holdout. It is evidence about the dataset, not about the model.
* Timestamp repair (12-hour clock, hours 1–5 → 13–17, parser raises on 6 or 7) is carried
  over unchanged and is already independently corroborated twice.
* Existing results are **not** re-run or altered; the frozen protocol applies to the v2
  models.

---

## 7. Leave-One-Family-Out protocol

### Implementation review — methodologically correct

| Aspect | Implementation | Verdict |
|---|---|---|
| What is removed | Every training row of family F | Correct — F is genuinely unseen |
| What remains in test | Only the test rows of F (`test_idx` where label == F) | Correct |
| BENIGN handling | Never excluded. BENIGN cost is fixed by the anomaly detector's calibrated flag rate (1 % / 2 %) from a held-out BENIGN calibration split | Correct — benign cost is controlled rather than measured on the same rows |
| Anomaly detector | Fitted **once** on BENIGN training rows, `contamination="auto"`, thresholds from held-out BENIGN calibration | Correct and identical across families, so families are comparable |
| Leakage | No test row and no attack row touches the detector or its thresholds | **Clean** |
| Supervised failure | `supervised_called_benign_rate` — the fraction of F called BENIGN | Correct |
| Recovery | `anomaly_recovered_from_missed / supervised_missed`, measured **only** on rows the supervised model called BENIGN | Correct — no double counting |
| Low support | Heartbleed, Infiltration, SQL Injection excluded (`MIN_TEST_SUPPORT = 100`) | Correct |
| Balancing | BENIGN capped at 200,000, **no SMOTE** | Deliberate controlled recipe — **must be stated**, since it differs from the production model |

### Measured results (existing, not re-run)

| Family | Test n | Called BENIGN | IF recovery @1 % | IF recovery @2 % | Combined @2 % |
|---|---:|---:|---:|---:|---:|
| DoS slowloris | 1,159 | 0.1717 | 0.0000 | 0.7136 | 0.9508 |
| Web Attack – XSS | 130 | 0.0154 | 0.0000 | 0.5000 | 0.9923 |
| Web Attack – Brute Force | 301 | 0.1262 | 0.0000 | 0.0000 | 0.8738 |
| DoS Hulk | 46,025 | 0.6907 | 0.3239 | 0.5268 | 0.6731 |
| DoS GoldenEye | 2,059 | 0.3584 | 0.0000 | 0.0854 | 0.6722 |
| DoS Slowhttptest | 1,100 | 0.5600 | 0.0097 | 0.0779 | 0.4836 |
| DDoS | 25,605 | 0.7086 | 0.0001 | 0.0002 | 0.2915 |
| Bot | 391 | 1.0000 | 0.0000 | 0.0128 | 0.0128 |
| SSH-Patator | 1,180 | 0.9907 | 0.0000 | 0.0000 | 0.0093 |
| PortScan | 31,761 | 0.9946 | 0.0002 | 0.0003 | 0.0057 |
| FTP-Patator | 1,587 | 0.9950 | 0.0000 | 0.0000 | 0.0050 |

**This is the honest generalization result and it must be reported as it is.** For Bot,
FTP-Patator, SSH-Patator and PortScan the system detects essentially nothing when the
family is unseen (0.5–1.3 % combined). It works for part of the DoS family. Any claim of
"zero-day detection" is unsupportable; the supportable claim is *"the hybrid recovers a
measurable fraction of unseen volumetric and timing-based attacks, and nothing of unseen
scan or brute-force traffic."*

One caveat to state: `combined_detection_rate` counts a flow as detected if the supervised
model assigned it *any* non-BENIGN label, even the wrong one. That is detection without
correct classification — which is why Web Attack – Brute Force reaches 0.87 while its
family is unseen (it is misrouted to a sibling web-attack class).

### Frozen decision

Re-run against the v2 models with the same protocol, `seed=42`, operating points 1 % and
2 %. Report the table above verbatim in structure, plus the per-family predicted-label
breakdown that the report already stores.

---

## 8. Live testbed protocol

**No attacks executed in this phase.** Audit of `app/replay/live_agent.py` only.

### What the agent records today

Per flow: feature validation result (derived / zero-filled / out-of-range / rejected, to
stderr), prediction, confidence or anomaly score, detection method, model identity and
feature version, source/destination IP and port, protocol. Per run: totals for processed,
rejected (with rate) and suspicious flows.

### Gaps that block reproducible live reporting

| # | Gap | Impact |
|---|---|---|
| L-1 | **No experiment/run identifier** on ingested flows | Flows from separate attack runs cannot be separated in the database |
| L-2 | `flowTimestamp = datetime.now(UTC)` — **capture time is discarded** | Cannot align flows to the attack timeline |
| L-3 | **No expected label sent**, although the ingest API already accepts `groundTruthLabel` / `groundTruthAttackType` (the replay uses them) | No live accuracy can be computed |
| L-4 | Validation status is stderr only, **not persisted** | Missing/derived feature counts cannot be reported per experiment |
| L-5 | No record of tool, command, duration, attacker/victim roles | The run is not reproducible from the database alone |

L-3 is the cheapest and highest value: the fields already exist end to end.

### Required record per live experiment (frozen)

**Manifest (declared before the run):** experiment id; attack name and CICIDS2017 class it
is meant to correspond to; tool and exact command line; attacker host/IP; target host/IP
and service; planned start and end time (UTC); expected label; network segment; capture
interface; CICFlowMeter build and version; model artifact + version + feature version;
anomaly detector artifact and threshold rate.

**Per flow (persisted):** experiment id; capture timestamp; ingest timestamp; 5-tuple;
predicted class; confidence; detection method; anomaly score; model id/name/version;
feature version; validation status; count and names of derived, zero-filled and
out-of-range features; rejected yes/no with reason.

**Per run (aggregated):** flow count; rejected count and rate; detection counts by class;
suspicious count; mean/median/p95 end-to-end alarm latency; the drift report published
during the window.

Implementing L-1…L-4 is a P1 task and is **not** in this freeze.

---

## 9. Isolation Forest protocol

Kept methodologically separate from the multiclass comparison at every point. It is a
**binary** BENIGN-vs-attack detector; placing its accuracy/precision/recall/F1 beside a
15-class macro F1 is a category error, and the P0-2 audit excludes it by design.

| Item | Frozen value |
|---|---|
| Artifact | `isolation_forest_benign_v2.joblib` (+ `_calibration.json`) — **already leak-free, not retrained** |
| Training data | BENIGN **training** rows only — 1,453,644 rows |
| Calibration data | Held-out BENIGN split — 363,411 rows, never used for fitting |
| `contamination` | `"auto"` — **never** the test attack rate |
| Threshold | Quantile of the calibration scores at the target benign flag rate; shipped default **1 %** (`0.010`) |
| Evaluation data | The same held-out test set as the classifiers, scored as binary BENIGN vs attack |
| Metrics | Per-family flag rate; benign false-positive rate at each operating point; ROC AUC; **never** macro F1 |
| Operating points | 0.1 %, 0.5 %, 1 %, 2 %, 5 % (already calibrated) |
| Role in hybrid | Consulted **only** when the supervised model says BENIGN. Produces `detection_class = SUSPICIOUS`, `prediction = UNKNOWN`, never a named attack class |
| Attribution | Median-substitution ablation, validated for **ranking** (8.6× separation at k=1), explicitly not additive and not TreeSHAP |

**Limitations to state verbatim in the thesis:** aggregate ROC AUC 0.709 (78 features) —
weak as a standalone detector. Completely blind to PortScan (0.0 % at every threshold up
to 5 %), FTP-Patator and SSH-Patator. Responds to volumetric and timing deviation, i.e.
the DoS family. `max_samples=256` (sklearn default) means each tree sees 256 of the
1.45 M available rows; whether more helps has not been measured.

**Wording rule:** it is not a zero-day detector. The supportable phrase is *"an
unsupervised anomaly detector that flags flows outside the benign profile, with measured
recovery on some unseen attack families and none on others."*

---

## 10. LLM / H4 evaluation protocol

**No live calls in this phase.** Protocol only; implementation is a later task.

### Sampling

| Item | Proposal |
|---|---|
| Alarms | **60**, stratified: 30 `KNOWN_ATTACK` across ≥5 distinct classes, 20 `SUSPICIOUS` (anomaly path), 10 low-confidence (below the MEDIUM severity threshold) |
| Explanations | 60 alarms × 2 providers = **120** |
| Prompt version | **v3 only** for the headline comparison. `v1`/`v2` rows are retained and reported as a version count, never pooled with v3 — different prompts are different treatments |
| Providers | Claude (`claude-sonnet-5`) and Gemini (`gemini-flash-latest`), byte-identical prompts (already guaranteed and tested) |
| Presentation | Blind to provider, randomised order per participant |

### Participants

Minimum **5**, target **8–12**, with network/security background. Below 8, report
descriptive statistics only and state the sample size as a limitation — no significance
testing on n = 5. Each participant rates all 120 explanations, or a balanced block of 60
if fatigue is a concern (state which).

### Rating instrument — replacing HELPFUL / UNCLEAR / INCORRECT

The existing three-point scale is too coarse to compare two providers. Proposed **Likert
1–5** on four dimensions:

| Dimension | Question |
|---|---|
| Clarity | Is the explanation easy to follow? |
| Usefulness | Would it help you triage this alarm? |
| Trust | How much would you rely on it? |
| Perceived understanding | After reading it, do you feel you understand why the system raised this alarm? |

Plus a **factual review** per explanation: *grounded / minor unsupported detail / material
unsupported claim*, with a free-text note. This is the human counterpart to the automatic
check and is the one that can catch a fabricated technique or a wrong causal story.

The existing `ExplanationRating` enum stays as-is for the dashboard; the study instrument
is separate and exported alongside. **No schema migration** — the study collects into its
own sheet keyed by `explanation_id`.

### Automatic measures (already implemented)

* **Groundedness rate** per provider from `deterministic_heuristic_v1`: the share of
  explanations with zero findings, plus high-severity finding counts. Reported as a
  *floor*, with the stated caveat that it checks entities, not semantics.
* **Generation latency** per provider: mean, median, p95, from the stored
  `generation_latency_ms`.
* **Agreement** between the heuristic and the human factual review — this is the number
  that tells you how much the automatic check is worth.

### Provider failures

Recorded, never silently dropped. Report **availability** (successful generations /
attempts) separately from quality; exclude failures from quality statistics and state the
exclusion count. Note the known constraint: the free Gemini tier allowed 20 requests/day
and returned `503` on 466 of 468 attempts during P2-6. **A provider with real quota is a
precondition for this study** — see the checklist.

### Export

`python -m training.export_explanations` already emits every field required (alarm id,
ground truth where available, predicted class, confidence, SHAP evidence, provider, model,
prompt version, explanation, latency, rating, groundedness) as CSV + JSONL + summary.

---

## 11. Final thesis tables

| Table | Content | Columns |
|---|---|---|
| **A — Model comparison** (RQ1) | The 5 v2 models on the random split | Model · Algorithm · Balancing · **Macro F1 (n≥100)** · Macro F1 (all 15) · Accuracy · Macro P · Macro R · Weighted F1 · Benign FPR · Attack recall · Train time (s) · Batch ms/flow · Single-flow median ms |
| **B — Per-class performance** | Best model, all 15 classes | Class · Test support · Precision · Recall · F1 · FPR · FNR · `sufficient_support` flag |
| **C — Feature selection** (RQ3) | N ∈ {10, 20, 30, 50, 78} | N · Features · **Macro F1 (n≥100)** · Macro F1 (all 15) · Accuracy · Batch ms/flow · Single-flow median ms · Train time · Δ vs N=78 · Non-zero-gain features included |
| **D — Temporal generalization** | Random vs temporal_per_class (+ temporal_global as degenerate) | Split · Train n · Test n · **Macro F1 (n≥100)** · Accuracy · Benign FPR · Attack recall · Classes with zero train rows · Classes with zero test rows |
| **E — Leave-one-family-out** | 11 families with support ≥ 100 | Family · Test n · Called BENIGN (supervised miss rate) · Predicted-label breakdown · IF flag rate @1 % / @2 % · Recovery on missed @1 % / @2 % · Combined detection @1 % / @2 % |
| **F — Live testbed** | One row per live experiment | Experiment id · Attack · Tool/command · Source → Target · Duration · Expected label · Flows captured · Flows rejected (rate) · Predicted class distribution · Mean confidence · Detection method split · Derived/zero-filled feature counts · Detected yes/no |
| **G — LLM evaluation** (H4) | Per provider | Provider · Model · Prompt version · Explanations · Availability (success/attempts) · Clarity 1–5 (mean ± SD) · Usefulness · Trust · Perceived understanding · Groundedness rate (heuristic) · Material unsupported claims (human) · Latency mean/median/p95 |
| **H — Isolation Forest** (separate) | Anomaly detector alone, never beside A | Operating point · Benign FPR · Per-family flag rate (11 families) · ROC AUC |

---

## 12. Execution order

Run from `ml-service/`. Every step is a single command; nothing is interactive.

```bash
# 1. the anchor model - everything else depends on its feature ranking
python -m training.train training/configs/xgb_smote_v2.yaml

# 2. feature ranking from that model, training data only; inspect first
python -m training.build_feature_ranking
python -m training.build_feature_ranking --write-reference

# 3. the rest of Table A
python -m training.train training/configs/xgb_baseline_v2.yaml
python -m training.train training/configs/rf_smote_v2.yaml
python -m training.train training/configs/mlp_smote_v2.yaml
python -m training.train training/configs/rf_baseline_v2.yaml       # longest

# 4. Table C - feature selection (configs written after step 2)
python -m training.train training/configs/xgb_smote_top10_v2.yaml
python -m training.train training/configs/xgb_smote_top20_v2.yaml
python -m training.train training/configs/xgb_smote_top30_v2.yaml
python -m training.train training/configs/xgb_smote_top50_v2.yaml

# 5. Table D - temporal generalization
python -m training.evaluate --skip-registered

# 6. Table E - leave-one-family-out
python -m training.leave_one_family_out

# 7. Table H - the anomaly detector, kept separate
python -m training.evaluate_isolation_forest

# 8. recompute every metric in one place, then inspect before any DB write
python -m training.evaluate_artifacts
python -m training.reregister_experiments                            # dry run
python -m training.reregister_experiments --commit -y                # ON YOUR APPROVAL

# 9. Table G input, once explanations exist
python -m training.export_explanations
```

Steps 1–7 are reproducible from configs and seeds alone. The `--commit` in step 8 is the
only database write in the entire programme. Steps for Table F (live testbed) wait on
L-1…L-4; Table G waits on a provider with real quota.

---

## 13. READY FOR FINAL EXPERIMENTS — checklist

Every line must be **TRUE** before the full retraining command is given.

| # | Condition | Status |
|---|---|---|
| 1 | All tests green (`443 passed, 1 deselected`) | ✅ TRUE |
| 2 | No `v1` artifact modified | ✅ TRUE |
| 3 | Nothing written to PostgreSQL by P0 | ✅ TRUE |
| 4 | Balancing reproduces 653,897 rows on the real dataset | ✅ TRUE |
| 5 | Split → balance ordering enforced and test set proven untouched | ✅ TRUE |
| 6 | Scaler / label encoder / feature ranking fitted on training data only | ✅ TRUE |
| 7 | Evaluation harness validated against a known anchor (4 dp on 4 metrics) | ✅ TRUE |
| 8 | No metric can enter the registry by hand | ✅ TRUE |
| 9 | Artifact SHA-256 verified at registration | ✅ TRUE |
| 10 | Prompt `v3` grounding rules on both templates | ✅ TRUE |
| 11 | `top78` excluded from final results, with evidence | ✅ TRUE (§1) |
| 12 | Contaminated `isolation_forest_cicids2017_v1` excluded; `benign_v2` is the detector | ✅ TRUE |
| 13 | Primary metric agreed — full Macro F1 primary, support ≥ 100 as sensitivity (§6) | ✅ TRUE |
| 14 | Final model set agreed — 5 models, RF baseline **is** retrained (§2) | ✅ TRUE |
| 15 | v2 feature ranking agreed; model ↔ feature-set pairing enforced in code (§3) | ✅ TRUE |
| 16 | §5 latency protocol implemented in `evaluation.py` | ✅ TRUE |
| 17 | Disk space for v2 artifacts (~300 MB incl. RF baseline) | ⬜ VERIFY (644 GB free — fine) |
| 18 | Machine on mains power, no other heavy load, for stable latency figures | ⬜ VERIFY AT RUN TIME |
| 19 | Postgres + backend up, for step 14 only | ⬜ NOT REQUIRED UNTIL STEP 14 |
| 20 | LLM provider with real quota, for Table G only | ⬜ BLOCKED — free Gemini tier is 20 req/day |
| 21 | Live testbed gaps L-1…L-4 closed, for Table F only | ⬜ P1 TASK |

**Blocking for full retraining: none.** Preconditions 1–16 are all TRUE.
Items 20 and 21 block only Tables G and F and do not hold up the model training.

---

## 14. Decisions taken (2026-09-06)

1. **Primary metric** — full 15-class Macro F1 is primary; Macro F1 over classes with test
   support ≥ 100 is reported beside it as a robustness/sensitivity analysis. The
   instability of the full metric on n = 4 and n = 7 classes is documented, not engineered
   away. `top78` stays excluded regardless of its higher full Macro F1. (§6, evidence §1)
2. **Model set** — five models retrained as v2: XGBoost baseline, XGBoost balanced,
   Random Forest baseline, Random Forest balanced, MLP balanced. Isolation Forest remains a
   separate experiment and never enters the multiclass table. `top78` excluded. (§2)
3. **Feature ranking** — recomputed from the v2 balanced model, training data only,
   registered as `cicids2017-top{10,20,30,50}-v2` and `cicids2017-78-v2`, recording ranking
   method, source model and its SHA-256, seed, importance values, feature order and the v1
   overlap. Model and feature schema are a versioned pair, enforced in code. (§3)
4. **Latency** — frozen as §5 and implemented. Not to be changed once the final
   experiments begin.

---

## 15. Audit notes from the v2 experiment run (2026-09-06)

### Registry-name collision — resolved

The notebook (cell 15) registered the historical `rf_baseline_cicids2017_v1.joblib` under
the registry name **`rf-baseline-cicids2017-v2`**. The retrained baseline would have taken
the same name, and `ml_models.name` is UNIQUE.

**Resolution:** the *historical* record is untouched — it keeps `rf-baseline-cicids2017-v2`
and its original metadata. The *retrained* model was renamed to
**`rf-baseline-cicids2017-v2-final`** (config, bundle, training report; `renamed_from` and
`rename_reason` recorded in both). The artifact filename stayed
`rf_baseline_cicids2017_v2.joblib` — registry name and artifact stem are independent in
this architecture. No model was retrained for the rename.

Evaluation report directories are now keyed by **artifact stem**, not registry name, so two
artifacts can never share a directory. `assert_no_collisions()` raises `RegistryCollision`
on a duplicate registry name or a duplicate report directory, and `audit_artifact` refuses
to write into a directory whose `metrics.json` belongs to a different artifact.

### Latency outlier on `xgb-smote-top30features-v2`

| Measurement | batch ms/flow | flows/s |
|---|---:|---:|
| First uniform run | **0.013048** | 76,637 |
| Controlled rerun (frozen harness, no concurrent load) | **0.004077** | 245,253 |

The first value is an environmental measurement outlier, not a property of the model — it
sits ~3× above every other XGBoost artifact while the model is identical. The controlled
rerun returns it to the 0.004–0.006 range shared by the whole family. **The controlled
rerun is the figure used in the final table**; the outlier is recorded here so the
discarded value is on the record rather than silently dropped.

### Latency figures were re-measured, not carried over

Every latency number in the final table comes from `training/evaluate_artifacts.py` under
the frozen harness, applied identically to v1 and v2. Latency recorded inside individual
training bundles is *not* used for the table — the anchor's bundle predates the metric
namespacing and would not have been comparable.

---

## 16. Temporal generalization protocol *(PK2 / H2)*

**Namespace:** `ml-service/reports/temporal_evaluation/`, artifacts `*_temporal_v1`,
configs `training/configs/temporal/`. The canonical random-split v2 results in
`reports/artifact_evaluation/` are **frozen and untouched** by this phase.

### 16.1 Motivation

The random split is an *in-distribution* estimate: train and test rows are drawn from the
same five-day capture, so flows from the same attack burst land on both sides. This section
measures what happens when the evaluation is ordered by time instead.

### 16.2 Source of chronology

The `Timestamp` column of `cicids2017_cleaned.parquet`, repaired from CICIDS2017's
**12-hour clock with no AM/PM marker** by `training.evaluate.parse_cicids_timestamps`
(hours 1–5 → 13–17; hours 8–12 unchanged; the parser raises if 6 or 7 ever appears, which
they never do). `source_file` is retained as an independent corroboration of the day and is
**never** used to order rows.

`Timestamp` is **not a feature**. It is excluded from every registered feature set, along
with `Flow ID`, `Source IP`, `Source Port`, `Destination IP`, `Label` and `source_file`, so
no temporal information reaches the classifier as an input.

### 16.3 What the dataset actually permits

Measured, not assumed (`reports/temporal_evaluation/temporal_audit.json`):

| Class | Window | Span |
|---|---|---|
| BENIGN | Mon 08:55 → Fri 17:02 | all five days |
| FTP-Patator | Tue 09:17 → 10:30 | 73 min |
| SSH-Patator | Tue 14:09 → 15:11 | 62 min |
| DoS slowloris / Slowhttptest / Hulk / GoldenEye | Wed 09:01 → 11:19 | one morning |
| Heartbleed | Wed 15:12 → 15:32 | 20 min |
| Web Attack – Brute Force / XSS / Sql Injection | Thu 09:15 → 10:42 | 87 min |
| Infiltration | Thu 14:19 → 15:45 | 86 min |
| Bot | Fri 09:34 → 12:59 | 3.4 h |
| PortScan | Fri 13:05 → 15:23 | 2.3 h |
| DDoS | Fri 15:56 → 16:16 | 20 min |

**No attack family recurs across days.** Every family occupies one contiguous window inside
a single day. This is a property of how CICIDS2017 was generated, and it constrains what
any chronological protocol can measure: a cut at a day boundary makes *every* attack class
in the test period unseen during training. The only attack class that straddles the 80/20
cut is Bot.

### 16.4 The split

Strategy `temporal_global`: sort every row by repaired timestamp, take the last 20 % as
test, then extend the cut forward so no single timestamp value is split across the
boundary. Deterministic; no RNG is involved, so the seed does not affect it.

| | |
|---|---|
| Boundary | `2017-07-07 11:17:00` |
| Train | 2,263,211 rows, Mon 08:55:58 → Fri 11:17:00, **13 classes** |
| Test | 564,665 rows, Fri 11:18:00 → Fri 17:02:00, **4 classes** |
| In both partitions | BENIGN, Bot |
| **Unseen in training** | **DDoS, PortScan — 286,829 rows = 50.8 % of the test set** |
| Absent from test | 11 training classes |

### 16.5 Metrics and the class set each one uses

Because the test period contains classes the model never saw, a single macro F1 would
conflate two different effects. Each figure therefore names its class set explicitly:

| Metric | Class set | Role |
|---|---|---|
| `classes_present_in_temporal_test` | the 4 test classes, **including unseen ones** | **STRICT — primary** |
| `classes_present_in_both_partitions` | BENIGN, Bot | **SEEN-CLASS DIAGNOSTIC** |
| `union_of_train_and_test_classes` | all 15 | completeness only; classes with zero test support score 0 by construction, so it cannot rank models |
| `test_classes_with_support_at_least_100` | test classes ≥ 100 rows | sensitivity analysis |

Nothing is silently dropped: unseen classes stay in the strict metric with the recall of 0
they necessarily have. The seen-class diagnostic is reported **alongside** the strict
result, never instead of it.

Also reported per model: accuracy, macro precision/recall, per-class precision/recall/F1/
support, confusion matrix, BENIGN false-positive rate, number of train and test classes,
unseen classes, unseen test rows, and the unseen fraction of the test set.

### 16.6 Leakage controls

Identical in standard to random-v2, re-verified for the temporal order:

* The split happens **first**, by time, and `assert_disjoint` fails the run otherwise.
* Balancing/SMOTE receives only `train_idx` — pinned by a test that asserts the maximum
  training timestamp never exceeds the minimum test timestamp.
* The scaler is fitted on the balanced temporal **training** matrix only — pinned by a test
  that asserts the row count it sees equals the balanced training size.
* The label encoder is fitted on training labels only.
* Feature sets are fixed registered lists; no selection step learns from the test period.
* No synthetic row can enter the test partition; a test asserts the source feature matrix
  is byte-identical after a run and that test class support is unchanged by balancing.
* The output vocabulary a model can emit is its *training* class set. A class with zero
  training rows is treated explicitly as **unseen**, not as a learned class.

### 16.7 What this protocol is and is not

* **Random split = in-distribution baseline.**
* **Temporal split = time-ordered distribution-shift test.**

Temporal evaluation here is **not** cross-dataset validation, **not** leave-one-family-out,
**not** zero-day detection, and **not** production validation. Those remain separate
experiments. In particular, a model failing on DDoS and PortScan because those families
occur only after the cutoff is an **unseen-label effect**; calling it zero-day detection
would be wrong.

### 16.8 Known limitations

* The strict test period is a single Friday afternoon. It is one cut of one capture, not a
  distribution over cutoffs.
* The seen-class diagnostic covers **two classes** (BENIGN and Bot). Bot has 429 test rows.
  This is a narrow diagnostic and must be described as such.
* 10.88 % of the dataset's feature rows are exact duplicates of another row, and **3.26 %
  of rows sit in duplicate groups that straddle the cutoff**. Under a chronological split
  these are genuinely distinct flows, so this is not preprocessing leakage — but the test
  period is not fully novel with respect to training, and the figure bounds how novel it is.
* Any difference from the random baseline may reflect chronology, attack-family
  composition, unseen labels, class-support changes, or day-specific capture conditions.
  The design separates the unseen-label component; it does not isolate the others.

---

## 17. Leave-One-Family-Out protocol *(PK2 / H2)*

**Namespace:** `ml-service/reports/lofo_evaluation/`, artifacts `models/lofo/`, taxonomy
`cicids2017-families-v1`, protocol `lofo-v1`. Random-v2 (§0–§14) and temporal-v1 (§16)
are **frozen and untouched**.

### 17.1 Why LOFO is needed after the temporal experiment

§16 showed that chronology and unseen-family effects are confounded in CICIDS2017: the
temporal test period contained DDoS and PortScan, both entirely absent from training, and
they were 50.8 % of the test set. Roughly half the temporal macro-F1 drop was unseen-label
arithmetic rather than drift. LOFO isolates the unseen-family effect by holding a family
out deliberately while keeping the split, the test set and everything else fixed.

### 17.2 The existing implementation was Leave-One-*Class*-Out

`training/leave_one_family_out.py` removes a single raw label per fold
(`labels[train_idx] != excluded_family`) and iterates over raw labels. It also drops any
label with test support below 100, which silently excluded Heartbleed, Infiltration and
SQL Injection.

That is not leave-one-*family*-out, and it overstates unseen-family generalisation: holding
out `DoS Hulk` leaves GoldenEye, slowloris and Slowhttptest in training, so near-identical
traffic remains. Measured directly — the old code reported ~31 % of held-out DoS Hulk
detected; with the whole DoS family removed, detection falls to 0.7–3.8 %. The earlier
figure was measuring interpolation inside a family. That script is left in place as the
historical record and is **not** used for these results.

### 17.3 Family taxonomy (`cicids2017-families-v1`)

Derived from the CICIDS2017 capture scenarios; all 14 attack labels map to exactly one
family, and no label is unmapped.

| Family | Member labels | Scenario | Test support | Tier |
|---|---|---|---:|---|
| DoS | Hulk, GoldenEye, slowloris, Slowhttptest | Wed morning, single-source app-layer DoS | 50,343 | high |
| PortScan | PortScan | Fri afternoon, nmap | 31,761 | high |
| DDoS | DDoS | Fri afternoon, LOIC | 25,605 | high |
| Brute Force | FTP-Patator, SSH-Patator | Tue, Patator credential attack | 2,767 | high |
| Web Attack | Brute Force, XSS, Sql Injection | Thu morning, DVWA | 435 | moderate |
| Bot | Bot | Fri morning, Ares C2 | 391 | moderate |
| Infiltration | Infiltration | Thu afternoon | 7 | low / exploratory |
| Heartbleed | Heartbleed | Wed afternoon | 2 | low / exploratory |

**No family is dropped for low support.** Infiltration and Heartbleed are retained and
explicitly tiered `low_exploratory`; no strong conclusion is drawn from them.

**DoS and DDoS are separate families** because CICIDS2017 generated them as separate
scenarios on separate days with different source models. They remain mechanically
adjacent: holding out DDoS leaves four DoS labels in training and vice versa, so detection
of a held-out DDoS family is **not** evidence of generalisation to an unrelated attack
type. This is recorded in `RELATED_FAMILIES` and must be stated wherever those two folds
are discussed.

### 17.4 Fold construction

For each family F, starting from the **canonical random-v2 partition**
(`test_size=0.2, random_state=42, stratified`):

1. remove every row whose label is in F **from TRAIN only**;
2. balance (when the model is a balanced variant) **after** removal;
3. fit the scaler, when used, on the resulting training rows only;
4. fit the label encoder on the surviving training labels only;
5. train;
6. evaluate on the **unchanged** canonical test set.

Asserted programmatically each fold: `held_out_family_rows_in_train == 0` after removal,
and `held_out_family_rows_after_balancing == 0`. Both raise `LofoError` rather than warn.

### 17.5 Metrics — detection is the primary question

A multiclass classifier that never saw family F cannot emit F's label. **Held-out-family
multiclass F1 is therefore not used as the success metric.** Instead:

* **Attack detection** (primary): `prediction != BENIGN` over held-out rows →
  `attack_detection_rate`, `attack_miss_rate`. This says the traffic was flagged as
  malicious; it says nothing about the label being right.
* **Attack attribution** (separate): over held-out rows flagged as attack, the predicted
  label and predicted family distribution, plus the dominant label/family. A dominant label
  here is a **misattribution**, not a correct detection of that class.
* **Binary diagnostic** over the whole canonical test set: binary accuracy, attack
  precision/recall/F1, BENIGN FPR, attack FNR.
* **Known-class stability**: metrics over test rows whose labels survived removal,
  compared against a **matched** random-v2 baseline recomputed from the frozen random-v2
  confusion matrix over exactly the same class subset. Comparing different class sets and
  calling the difference degradation is not permitted.

`benign_false_positive_rate` uses the **same definition** as random-v2 and corrected
temporal: the fraction of true BENIGN rows predicted as some attack class. The opposite
direction is stored separately as `attack_rows_predicted_as_benign_rate`. A regression
test asserts the LOFO and temporal implementations agree numerically.

### 17.6 What LOFO is and is not

**LOFO is a controlled proxy for unseen attack-family behaviour. It is NOT evidence of
arbitrary real-world zero-day detection.** The held-out families are known, documented,
2017-era attacks generated by known tools in one lab capture. A model may detect held-out
traffic as malicious while attributing it to the wrong class; those two outcomes are
reported separately and must never be conflated.

Correct phrasing: *"the model detected the held-out DDoS traffic as malicious but
attributed it primarily to another class"*. Not: *"the model correctly detected DDoS"*.

### 17.7 Limitations

* One dataset, one capture, one split seed.
* DoS/DDoS adjacency (§17.3) means those two folds are not independent.
* Infiltration (n=7) and Heartbleed (n=2) cannot support any statistical claim; they are
  reported for completeness and marked exploratory.
* Confidence statistics, where reported, are descriptive only — the outputs are **not**
  calibrated probabilities, and no rejection threshold is introduced or tuned. Threshold
  rejection is a separate future experiment.
* LOFO says nothing about chronological drift; that is §16. The three PK2 experiments
  (random-v2 benchmark, temporal, LOFO) measure different things and are never merged into
  one metric.
