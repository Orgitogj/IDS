# Phase 17C — Model B Training Protocol (pre-registered)

**Status: FROZEN BEFORE TRAINING.**
Machine-readable twin: [`protocol.json`](protocol.json) (`phase17c-model-b-v1`).

This document was written and frozen **before any model was fitted**, so that model
choices cannot be changed after seeing validation results.

`PHASE17B_FROZEN_HEAD = 38905dacaba658967d68740b458ece54555ff329`

---

## 1. Objective

Train a **deployment-domain binary IDS**:

| class | value |
|---|---|
| BENIGN | 0 |
| ATTACK | 1 |

This is **Model B** — a binary deployment-adapted detector.
It is **not** a 15-class replacement for frozen Model A.

Longer-term intended architecture:

- **Stage 1** — Model B: binary deployment-domain detector
- **Stage 2** — frozen Model A: multiclass attribution for flows flagged by Model B

Model A is **not** modified or retrained in Phase 17C.

---

## 2. Train / validation split

The frozen Phase 17B run-level split is used verbatim. Splitting is **run-level**;
individual flows are **never** randomly split across runs.

**TRAIN — 9 new adaptation runs**

```
adapt-v1-benign-002    adapt-v1-portscan-002    adapt-v1-ssh-002
adapt-v1-benign-003    adapt-v1-portscan-003    adapt-v1-ssh-003
adapt-v1-benign-004    adapt-v1-portscan-004    adapt-v1-ssh-004
```

**VALIDATION — 3 historical adaptation runs**

```
lab-v1-benign-001    lab-v1-portscan-001    lab-v1-ssh-bruteforce-001
```

**FINAL TEST — empty.** Final-test runs do not exist yet.

> This split is **development-only**. The three historical validation runs are **not**
> unseen final evaluation data, and must never later be described as such.

### Leakage guards

All preprocessing parameters are learned from **TRAIN only**. Validation flows never enter:

- preprocessing fit · feature selection · class-weight calculation · imputation fit
- scaler fit · hyperparameter fitting · threshold construction · model fitting

Validation remains untouched and naturally distributed.

### Labelling

Labels come only from the pre-declared scenario manifest
(`app/live/manifest.py: expected_for_flow`) — run-level uniform for benign, per-flow
selector for portscan/ssh. **Model A predictions never influence Model B labels.**
Flows that are neither BENIGN nor ATTACK are **UNLABELLED** and are excluded from
training and from every metric denominator.

---

## 3. Feature contract

Model B uses the **same deployment-domain extractor contract as the adaptation data**:
`cicflowmeter 0.5.0`.

- Schema id: `deployment-cicflowmeter-76-v1`
- **76 numeric features**, fixed order (capture CSV column order minus identity columns)
- Numeric conversion: `pandas.to_numeric(errors="coerce")`
- NaN / ±inf → `0.0` by a **fixed constant rule** (no train-fitted imputer)
- No scaler — tree ensembles are scale-invariant, so no train-fitted scaler is introduced
- Constant features are **retained, not dropped**: the feature list is fixed a priori and
  does not depend on observed variance, so no train-fitted feature-selection step exists

### Excluded identity / provenance columns

```
src_ip   dst_ip   src_port   dst_port   protocol   timestamp
```

`src_ip`, `dst_ip` and `dst_port` **are literally the ground-truth attack selector** for
the portscan and ssh scenarios. Admitting them as features would let the model memorise
the labelling rule and the fixed laboratory topology rather than flow behaviour.
`src_port` and `timestamp` are non-behavioural provenance. `protocol` is excluded with
them because the selector schema may key on it.

> The deployment rows are **not** mapped back into the historical Java CICFlowMeter
> `cicids2017-78-v1` contract. Model B exists specifically to learn the deployment
> extractor domain.

---

## 4. Class-distribution decision

The actual TRAIN distribution is ATTACK-heavy and dominated by PortScan.

**No benign undersampling.** The earlier design considered benign undersampling *before
the real adaptation distribution was known*. It is no longer scientifically justified,
because BENIGN is the **minority** class in the acquired training data. This is a
pre-training protocol refinement based **solely on observed class support**, not on model
predictions.

**No SMOTE** in the primary Phase 17C experiment.

**Primary balancing method — TRAIN-ONLY inverse-frequency binary class weighting:**

```
w_c = n_total_train / (n_classes * n_c_train)
```

- **XGBoost** — explicit per-row `sample_weight` vector computed from the TRAIN
  partition, rather than silently altering validation data.
- **Random Forest** — `class_weight="balanced"`, the same inverse-frequency rule computed
  on the fitted (TRAIN) partition.

Validation remains untouched and naturally distributed.

---

## 5. Pre-registered models

Exactly three models. No additional algorithms may be added after looking at validation
results, and no broad automated hyperparameter optimisation is run.

| role | id | algorithm | weighting |
|---|---|---|---|
| **PRIMARY Model B** | `model-b-xgb-weighted-v1` | `XGBClassifier` | yes |
| ROBUSTNESS | `model-b-rf-weighted-v1` | `RandomForestClassifier` | yes |
| ABLATION | `model-b-xgb-unweighted-v1` | `XGBClassifier` | no |

**XGBoost:** `n_estimators=100`, `tree_method="hist"`, `objective="binary:logistic"`,
`eval_metric="logloss"`, `n_jobs=-1`, `random_state=42`

**Random Forest:** `n_estimators=100`, `n_jobs=-1`, `random_state=42`,
`class_weight="balanced"`

Hyperparameters are reused from the existing frozen IDS pipeline configs
(`training/configs/xgb_baseline_v2.yaml`, `training/configs/rf_baseline_v2.yaml`):
seed 42, 100 estimators, `hist`, `n_jobs=-1`. Only the objective/eval metric required for
binary classification was adapted (`mlogloss` → `logloss`).

---

## 6. Primary threshold

```
P(ATTACK) >= 0.50  ->  ATTACK
P(ATTACK) <  0.50  ->  BENIGN
```

The primary threshold is pre-registered at **exactly 0.50** and is **not tuned on
validation**. A clearly labelled threshold-sensitivity analysis may be produced later as a
**secondary diagnostic only**; it must not replace the pre-registered primary threshold
during Phase 17C. No threshold may be selected on final evaluation, because final
evaluation does not exist yet.

---

## 7. Metrics

Reported on the untouched historical validation runs.

**Primary binary metrics:** Macro F1 · balanced accuracy · ATTACK recall (detection rate)
· ATTACK precision · BENIGN false-positive rate · confusion matrix

**Also:** ROC-AUC and PR-AUC *if mathematically valid* · per-scenario results

A partition containing a single ground-truth class yields `null` AUC with an explicit
reason, rather than a fabricated number.

**Per-scenario validation must include**, each with a **95% Wilson interval**:

| scenario | quantity |
|---|---|
| BENIGN | false-positive rate |
| PortScan | detection rate |
| SSH | detection rate |

> The small SSH support (**n = 69** in historical validation) must be reported, never
> hidden. An **observed zero must never be interpreted as a true population zero** — the
> Wilson upper bound is reported alongside it.

---

## 8. Model comparison

Compared: frozen Model A historical deployment behaviour · XGB Model B weighted ·
RF Model B weighted · XGB Model B unweighted ablation.

**Model A and Model B solve different primary tasks** — Model A does multiclass
attribution, Model B does binary attack detection. Therefore **multiclass Macro F1 must
not be compared directly against binary Macro F1 as if they were the same task.**

For the three historical validation scenarios, comparison uses shared **operational**
quantities only: benign FPR · attack detection rate · scenario-level detection.

Frozen Model A historical values (never overwritten, never recomputed differently):

| scenario | value |
|---|---|
| BENIGN | 0 / 5407 false positives |
| PortScan | 2 / 1362 detected |
| SSH | 0 / 69 detected |

---

## 9. Model selection / freeze rule

**XGBoost weighted is the pre-declared PRIMARY Model B.** Whichever algorithm happens to
win validation does **not** become the primary. Random Forest is robustness evidence;
unweighted XGBoost is an ablation.

If the weighted XGBoost performs poorly, that is **reported truthfully** rather than
silently promoting another model.

After training and validation, the primary artefact is frozen together with its exact
feature contract, configuration, SHA-256 hashes, training-run identities and threshold.
Robustness/ablation artefacts are preserved separately and never confused with the
primary Model B.

---

## 10. Out of scope for Phase 17C

Creating `eval-v1-*` runs · acquiring or using final-test traffic · the final paired
Model A vs Model B evaluation · modifying frozen Model A · LLM/SHAP human-study work ·
claiming Phase 17 solves H4 · updating thesis final conclusions · fabricating missing
results.

---

## 11. Reproducibility

Seed `42`, deterministic. Python 3.11.9 · numpy 2.1.1 · pandas 2.2.3 · scipy 1.17.1 ·
scikit-learn 1.5.2 · xgboost 2.1.1 · joblib 1.4.2
