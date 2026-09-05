# EVALUATION.md — Anomaly detection, the hybrid engine, and evaluation rigour

Produced by P1-1 (§1–§5), P2-2 (§6–§7) and P2-6 (§8). Every number here comes from a
script in `ml-service/training/` and can be regenerated. Raw output lives in
`ml-service/reports/`.

| Experiment | Script | Output |
|---|---|---|
| Leak-free IF evaluation | `training/evaluate_isolation_forest.py` | `reports/isolation_forest_evaluation.json` |
| Leave-one-family-out | `training/leave_one_family_out.py` | `reports/leave_one_family_out.json` |
| Deployable detector | `training/build_anomaly_detector.py` | `models/isolation_forest_benign_v2*` |
| Random vs temporal split | `training/evaluate.py` | `reports/evaluation_random_vs_temporal.json`, `reports/confusion_matrix_*.csv` / `.png` |
| Anomaly feature baseline | `training/build_anomaly_baseline.py` | `reports/anomaly_feature_baseline.json` |

Dataset: `cicids2017_cleaned.parquet`, 2,827,876 rows. Split `test_size=0.2`,
`random_state=42`, stratified — the same split the notebook used, so numbers are comparable.
§6 measures what that split is worth.

---

## 1. The contamination leak, quantified

The registered `isolation-forest-cicids2017-v1` was fitted with
`contamination = 0.19681`, which is **the attack rate of the test set**. That is test
information used to set a model hyperparameter.

Reproducing it exactly (recall 0.4665, precision 0.3670 — matching the notebook to four
decimals) shows what it bought and what it cost:

| Setting | Attack recall | Precision | **Benign traffic flagged** |
|---|---:|---:|---:|
| Leaked `contamination=0.19681` | 0.4665 | 0.3670 | **19.72 %** |
| Leak-free, threshold at 1 % target | 0.1471 | 0.7823 | 1.00 % |
| Leak-free, threshold at 2 % target | 0.2925 | 0.7807 | 2.01 % |
| Leak-free, threshold at 5 % target | 0.3035 | 0.5960 | 5.04 % |

The leaked configuration flags **one in five benign flows**. It is unusable operationally,
and its headline recall of 0.47 is not a real capability — it is the consequence of being
told the answer.

**Leak-free protocol used from here on:** the Isolation Forest is fitted on BENIGN training
rows only (1,453,644 rows), and the decision threshold is a quantile of the scores of a
held-out BENIGN calibration split (363,411 rows). No attack row and no test row influences
either the model or the threshold.

---

## 2. What the anomaly detector can and cannot see

Per-family flag rate on the test set, 78-feature model, leak-free thresholds:

| Family | Test support | @1 % | @2 % | @5 % |
|---|---:|---:|---:|---:|
| BENIGN *(false positives)* | 454,265 | 1.0 % | 2.0 % | 5.0 % |
| DoS Hulk | 46,025 | **32.5 %** | **59.9 %** | 61.2 % |
| DoS slowloris | 1,159 | **17.4 %** | **47.9 %** | 52.0 % |
| DoS Slowhttptest | 1,100 | 0.6 % | 21.1 % | 26.1 % |
| DDoS | 25,605 | 4.7 % | 16.1 % | 17.3 % |
| DoS GoldenEye | 2,059 | 0.0 % | 3.5 % | 11.7 % |
| **PortScan** | 31,761 | **0.0 %** | **0.0 %** | **0.1 %** |
| **FTP-Patator** | 1,587 | **0.0 %** | **0.0 %** | **0.0 %** |
| **SSH-Patator** | 1,180 | **0.0 %** | **0.0 %** | **0.0 %** |
| Bot | 391 | 0.0 % | 1.3 % | 3.1 % |
| Web Attack – Brute Force | 301 | 0.0 % | 0.0 % | 5.6 % |
| Web Attack – XSS | 130 | 0.0 % | 0.8 % | 0.8 % |
| Infiltration | **7** | 28.6 % | 42.9 % | 71.4 % |
| Web Attack – Sql Injection | **4** | 0.0 % | 0.0 % | 0.0 % |
| Heartbleed | **2** | 100 % | 100 % | 100 % |

Aggregate ROC AUC 0.7087 (78 features) / 0.7337 (top-50). As a stand-alone binary detector
it is weak.

**The shape of the result matters more than the average.** The detector responds to
*volumetric and timing* deviation — the DoS family. It is **completely blind** to PortScan
(31,761 samples, 0.0 % at every threshold), FTP-Patator and SSH-Patator (0.0 % throughout).
Those flows are short, small and regular; in CICIDS2017 feature space they are
indistinguishable from normal traffic by an isolation criterion.

Heartbleed (n=2), Infiltration (n=7) and SQL Injection (n=4) **cannot support any claim**
in either direction. They are listed for completeness and excluded from every conclusion.

The 78-feature model is used in production despite the top-50 model's marginally better
aggregate AUC, because at the operating threshold the 78-feature model is clearly better on
the families that matter (DoS Hulk 32.5 % vs 12.8 % at 1 %).

---

## 3. Does it detect attacks the supervised model has never seen?

This is the experiment that decides whether "unknown attack detection" is a defensible
claim. For each family, XGBoost is **retrained from scratch with every row of that family
removed**, so the family is genuinely unseen. The anomaly detector is unchanged and
BENIGN-only. Recovery is measured *only on the rows the supervised model called BENIGN*.

| Family | Support | XGBoost called it BENIGN | IF recovered @1 % | IF recovered @2 % |
|---|---:|---:|---:|---:|
| DoS Hulk | 46,025 | 69.1 % | **32.4 %** | **52.7 %** |
| DoS slowloris | 1,159 | 17.2 % | 0.0 % | **71.4 %** |
| DoS GoldenEye | 2,059 | 35.8 % | 0.0 % | 8.5 % |
| DoS Slowhttptest | 1,100 | 56.0 % | 1.0 % | 7.8 % |
| Web Attack – XSS | 130 | 1.5 % | 0.0 % | 50.0 % |
| DDoS | 25,605 | 70.9 % | 0.0 % | 0.0 % |
| **PortScan** | 31,761 | **99.5 %** | **0.0 %** | **0.0 %** |
| **FTP-Patator** | 1,587 | **99.5 %** | **0.0 %** | **0.0 %** |
| **SSH-Patator** | 1,180 | **99.1 %** | **0.0 %** | **0.0 %** |
| **Bot** | 391 | **100.0 %** | **0.0 %** | 1.3 % |
| Web Attack – Brute Force | 301 | 12.6 % | 0.0 % | 0.0 % |

*The XGBoost used here is a controlled comparison model (BENIGN capped at 200,000, no SMOTE
— the production balancing recipe is not reproducible until P2-1). It is not the production
artifact.*

### What this establishes

1. **An unseen family is usually invisible to the supervised model.** PortScan, FTP-Patator,
   SSH-Patator and Bot are called BENIGN 99–100 % of the time when removed from training.
   This is the real risk the hybrid is meant to address.
2. **The anomaly detector closes that gap only for DoS-like traffic.** It recovers a third
   of unseen DoS Hulk at a 1 % benign flag rate, and about half at 2 %.
3. **It recovers nothing for scans, brute force or botnet traffic** — precisely the families
   it is most needed for. Every one of those sits at 0.0 %.

### The claim this supports

> The system performs **unknown/anomalous traffic detection**. On CICIDS2017 it recovers a
> measurable fraction of DoS-family attacks that the supervised classifier was never trained
> on (32 % of unseen DoS Hulk at a 1 % benign flag rate). It recovers **none** of the unseen
> PortScan, FTP-Patator, SSH-Patator or Bot traffic.

### The claim this does *not* support

> "Zero-day detection."

There is no evidence for a general capability to detect unseen attacks. The measured
coverage is one attack class out of four tested, and the failures are total (0.0 %), not
marginal. Calling this zero-day detection would misrepresent the evidence.

---

## 4. Steady-state cost, measured

Running the full hybrid over 4,000 randomly sampled real flows, with all families known to
the supervised model:

| True label | Detection class | Count |
|---|---|---:|
| BENIGN | BENIGN | 3,149 |
| attack | KNOWN_ATTACK | 811 |
| BENIGN | **SUSPICIOUS** | **36** |
| BENIGN | KNOWN_ATTACK | 3 |
| attack | BENIGN | 1 |

Observed SUSPICIOUS rate **0.90 %**, against a calibration target of 1.00 % — the
calibration transfers correctly from the held-out split to fresh data.

**All 36 SUSPICIOUS flags were benign.** That is the expected result, and it is the honest
cost statement: when every attack family is already known to the supervised model, the
anomaly branch contributes **no additional detections and a ~1 % false-positive rate**.
Its value is entirely contingent on encountering traffic the supervised model was not
trained on.

At 1 % of flows, a network producing 1 M flows/day yields ~10,000 SUSPICIOUS alarms/day.
**This is why alert correlation (P1-2) is a prerequisite for running the anomaly branch in
anger**, not an optional nicety.

---

## 5. Configuration shipped

| Setting | Value | Reason |
|---|---|---|
| Artifact | `isolation_forest_benign_v2.joblib` | leak-free refit; v1 kept for reproducibility |
| Feature set | `cicids2017-78-v1` | better at the operating threshold on DoS families |
| `n_estimators` | 100 | unchanged from the original experiment |
| `max_samples` | `auto` (256) | the configuration actually evaluated above |
| Threshold | 1 % benign flag rate (`-0.639585`) | best measured recovery per unit of false alarm |
| `anomaly_detection_enabled` | `true` | overridable in `.env` |

`anomaly_score` reported by the API is a **calibrated percentile**, not a raw isolation
score: 0.99 means "more anomalous than 99 % of known-normal traffic". Raw scores are also
returned for debugging.

**The supervised model remains authoritative.** The anomaly branch can only turn a
supervised `BENIGN` into `SUSPICIOUS`; it can never override, downgrade or relabel a
supervised attack verdict, and it never blocks a detection when its features are
unavailable.

---

## 6. How optimistic is the random split? — random vs temporal

`training/evaluate.py` runs **the same model recipe on three splits of the same dataset**
and reports them side by side. This is the P2-2 answer to audit finding L7: the optimism of
the reported numbers is measured, not argued about.

### 6.1 Repairing the timestamps first

CICIDS2017's `Timestamp` column uses a **12-hour clock with no AM/PM marker**, so a temporal
split is impossible until the clock is resolved. Across all 2,827,876 rows the observed
hours are exactly `{1,2,3,4,5,8,9,10,11,12}` — **6 and 7 never occur** — so the repair is
unambiguous: hours 1–5 are the afternoon and become 13–17, hours 8–12 are left alone. The
parser refuses to guess: it raises if hour 6 or 7 ever appears, or if any hour exceeds 12.

Two checks confirm the repair, neither of which was used to build it:

* every `...-Morning...` capture lands in **08:59–12:59** and every `...-Afternoon...`
  capture in **13:00–17:04**. The file names played no part in parsing.
* the four Thursday and Friday captures are **perfectly non-decreasing** in CSV row order
  after the repair (1.0000 of adjacent pairs). Monday, Tuesday and Wednesday are not sorted
  in the source CSVs at all (0.61 / 0.64 / 0.76) — a property of those files, not of the
  repair.

The capture is one working week, and **each attack family runs on a single day**:

| Day | Families present |
|---|---|
| Mon 3 Jul | BENIGN only |
| Tue 4 Jul | FTP-Patator, SSH-Patator |
| Wed 5 Jul | DoS Hulk / GoldenEye / slowloris / Slowhttptest, Heartbleed |
| Thu 6 Jul | Web Attack Brute Force / XSS / Sql Injection, Infiltration |
| Fri 7 Jul | Bot, PortScan, DDoS |

That fact governs everything below.

### 6.2 The three splits

| Split | Construction | Train rows | Test rows |
|---|---|---:|---:|
| `random` | `test_size=0.2, random_state=42, stratify=y` — the split the project already uses | 2,262,300 | 565,576 |
| `temporal_global` | all rows sorted by timestamp, last 20 % is test; rows sharing the boundary minute stay in train | 2,263,211 | 564,665 |
| `temporal_per_class` | last 20 % **of each class** by timestamp, each class's test count taken from the random split | 2,262,300 | 565,576 |

`temporal_per_class` exists because `temporal_global` confounds two effects. It holds every
class's test support **identical** to the random split (asserted by a test), so the only
thing that changes is *which* rows fall on each side — which is exactly the leakage L7
describes.

**Model.** The controlled comparison XGBoost from §3 — BENIGN capped at 200,000 training
rows, no SMOTE, `n_estimators=100`, `tree_method="hist"`, `random_state=42` — trained
separately on each split's training half. The production balancing recipe is still
unreproducible (P2-1), so the production artifact cannot be retrained on a temporal split;
it is evaluated on the random split only, where it reproduces the notebook exactly
(accuracy 0.9988, macro F1 0.8785, macro precision 0.8671, macro recall 0.8978 — all four to
four decimals). That match is what makes the rest of this section trustworthy.

### 6.3 Random split vs temporal split

| Metric | production artifact, `random` | controlled, `random` | controlled, `temporal_per_class` | controlled, `temporal_global` |
|---|---:|---:|---:|---:|
| Accuracy | 0.9988 | 0.9988 | **0.9756** | **0.4903** |
| Macro F1 | 0.8785 | 0.8614 | **0.7818** | **0.1009** |
| Weighted F1 | 0.9988 | 0.9988 | 0.9776 | 0.3587 |
| Macro precision | 0.8671 | 0.8864 | 0.7731 | 0.0744 |
| Macro recall | 0.8978 | 0.8799 | 0.8453 | 0.1660 |
| Attack recall (binary) | 0.9999 | 0.9998 | 0.9968 | 0.2896 |
| **Benign false-positive rate** | 0.0010 | 0.0010 | **0.0258** | 0.0035 |

Per class, random vs temporal per-class — same recipe, same support, different rows:

| Class | Test support | F1 `random` | F1 `temporal` | Δ F1 | Precision `random` → `temporal` |
|---|---:|---:|---:|---:|---|
| BENIGN | 454,265 | 0.999 | 0.987 | −0.013 | 1.000 → 0.999 |
| DoS Hulk | 46,025 | 0.999 | 0.983 | −0.016 | 0.998 → 0.998 |
| PortScan | 31,761 | 0.997 | 0.984 | −0.012 | 0.994 → 0.971 |
| DDoS | 25,605 | 1.000 | **0.830** | **−0.170** | 0.999 → **0.710** |
| DoS GoldenEye | 2,059 | 0.996 | 0.962 | −0.034 | 0.996 → 0.929 |
| FTP-Patator | 1,587 | 1.000 | 0.998 | −0.002 | 1.000 → 1.000 |
| SSH-Patator | 1,180 | 1.000 | 0.991 | −0.009 | 1.000 → 0.999 |
| DoS slowloris | 1,159 | 0.995 | **0.797** | **−0.198** | 0.993 → 0.902 |
| DoS Slowhttptest | 1,100 | 0.990 | 0.850 | −0.140 | 0.989 → 0.744 |
| Bot | 391 | 0.829 | **0.406** | **−0.422** | 0.713 → **0.255** |
| Web Attack – Brute Force | 301 | 0.793 | 0.741 | −0.052 | 0.728 → 0.695 |
| Web Attack – XSS | 130 | 0.359 | 0.320 | −0.040 | 0.487 → 0.342 |
| Infiltration | **7** | *insufficient support* | *insufficient support* | — | — |
| Web Attack – Sql Injection | **4** | *insufficient support* | *insufficient support* | — | — |
| Heartbleed | **2** | *insufficient support* | *insufficient support* | — | — |

Full per-class precision / recall / F1 / FPR / FNR with support beside every number, for all
four runs, is in `reports/evaluation_random_vs_temporal.json`; the confusion matrices are in
`reports/confusion_matrix_<run>.csv` and `.png`.

### 6.4 What this quantifies

1. **The random split is optimistic, and the size of the optimism is now known.** Holding
   every class's test support fixed and changing only which rows are held out, accuracy falls
   0.9988 → 0.9756 and macro F1 0.8614 → 0.7818. The operationally decisive number is the
   benign false-positive rate: **0.10 % → 2.58 %, a 26-fold increase**. On a network producing
   1 M flows/day that is the difference between ~1,000 and ~26,000 false alarms.
2. **The damage is concentrated, not uniform.** Six classes lose less than 0.02 F1. Bot
   (−0.42), DoS slowloris (−0.20), DDoS (−0.17) and DoS Slowhttptest (−0.14) carry almost
   all of it, and they lose it mostly through *precision*: a model trained on the earlier part of
   a burst over-claims those labels on the later part of the same day.
3. **`temporal_global` is a different measurement and must not be quoted as a per-class
   score.** Its accuracy of 0.4903 is dominated by a structural fact: DDoS (128,025 test rows)
   and PortScan (158,804) have **zero training rows**, because both run on Friday afternoon
   and the 80 % cut falls at 2017-07-07 11:17. Eight further classes have **zero test rows**.
   It is the honest number for "train on the past, deploy tomorrow" on a dataset built this
   way, and nothing more.
4. **`temporal_global` independently reproduces §3.** With PortScan unseen, the model called
   **157,367 of 158,804 PortScan rows BENIGN (99.1 %)**; §3's leave-one-family-out run reached
   that conclusion by a completely different route and measured 99.5 %. Unseen DDoS failed
   differently: 46,687 rows called BENIGN and **81,338 called DoS Hulk**, the nearest family
   it had actually seen.

### 6.5 The corrected claim

> On CICIDS2017 with a stratified random split the classifier reaches **0.9988 accuracy and
> 0.8785 macro F1**. That split places flows from the same attack burst on both sides of the
> boundary. Holding class support constant and splitting each class chronologically instead,
> the same recipe reaches **0.9756 accuracy and 0.7818 macro F1**, and its benign
> false-positive rate rises from 0.10 % to 2.58 %. The headline figure is an upper bound, not
> expected field performance.

The `temporal_global` figure is **not** offered as the field number either: on this dataset it
mostly measures attack families the model was never given a chance to learn.

---

## 7. Classes that cannot support a performance claim

The support floor is **100 test rows** — `MIN_SUPPORT_FOR_CLAIM`, the same constant already
used by `evaluate_isolation_forest.py` and `leave_one_family_out.py`. It is not a new
threshold invented for this section.

| Class | Rows in dataset | Rows in the test split | Reported as |
|---|---:|---:|---|
| Heartbleed | 11 | **2** | **insufficient support** |
| Web Attack – Sql Injection | 21 | **4** | **insufficient support** |
| Infiltration | 36 | **7** | **insufficient support** |

The notebook's `classification_report` printed F1 **1.00** for Heartbleed, **0.44** for SQL
Injection and **0.71** for Infiltration. Those are two, four and seven coin flips. This
project reports them as *insufficient support* and draws no conclusion from them **in either
direction** — neither "the model detects Heartbleed perfectly" nor "the model fails on SQL
injection".

How unstable they are, measured rather than asserted:

| Class | Test support | Production artifact, `random` | Controlled, `random` | Controlled, `temporal_per_class` |
|---|---:|---:|---:|---:|
| Heartbleed | 2 | F1 1.000 | F1 0.571 | F1 0.667 |
| Web Attack – Sql Injection | 4 | F1 0.444 | F1 0.667 | F1 0.545 |
| Infiltration | 7 | F1 0.714 | F1 0.727 | F1 0.667 |

Heartbleed moves from 1.000 to 0.571 between two models scoring **the same two rows**.
Nothing in that table is informative about capability.

`reports/evaluation_random_vs_temporal.json` carries `sufficient_support` on every per-class
row and an `insufficient_support_classes` list per run, and a test asserts all three classes
stay flagged in every random-split run. Classes with **zero** test rows are listed separately
as `absent_from_test_classes`, so "not measured" is never confused with "measured badly".

**Bot is the smallest class that clears the floor** (1,956 rows, 391 in test) and should still
be read with its support attached: its precision moves 0.700 → 0.713 → 0.255 across the three
runs above. Web Attack – XSS (130 in test) clears the floor by 30 rows.

---

## 8. Explaining an `UNKNOWN` detection

When the hybrid engine returns `SUSPICIOUS` / `ANOMALY_DETECTION`, the supervised model's
SHAP values explain why XGBoost thought the flow was **BENIGN**. That is the wrong evidence
for an alarm the supervised model did not raise, and until P2-6 it was what the LLM prompt
received. The anomaly branch now carries its own evidence.

### 8.1 Attributing an isolation-forest verdict

`shap` is **not installed and not in `requirements.txt`** (audit §4.4); runtime SHAP comes
from XGBoost's own `pred_contribs`, which has no Isolation Forest equivalent. Rather than add
a dependency, the detector attributes by **median substitution**: each of the 78 features in
turn is replaced with its median over the **1,453,644 BENIGN rows the forest was actually
fitted on**, the flow is re-scored, and the change in score is that feature's contribution.
Cost is one batch of 78 single-row scorings.

The baseline is `reports/anomaly_feature_baseline.json`, rebuilt by
`training/build_anomaly_baseline.py` from the seed and split parameters recorded in the
detector's own calibration file. The reconstruction returned exactly `fit_rows = 1,453,644`,
matching the calibration — so the medians describe the traffic this detector was taught to
call normal, not the dataset at large.

**This is not TreeSHAP and does not claim to be.** The contributions are not additive and do
not sum to any score gap. The claim is narrower and testable: the features it names are the
ones *this detector* is reacting to.

**Worked example**, a real BENIGN flow the hybrid flagged `SUSPICIOUS` at `anomaly_score`
0.9956:

| Evidence source | Top feature | Value | Contribution |
|---|---|---:|---:|
| XGBoost SHAP (what the prompt used to receive) | `Destination Port` | 62,280 | +2.170 |
| Isolation forest attribution (what it receives now) | `Idle Std` | 44,100,000 | +0.0296 |

The two do not even agree on which measurement matters, because they answer different
questions: the SHAP row explains why XGBoost said **BENIGN**, and the alarm was not raised by
XGBoost.

### 8.2 The attribution, tested

Deletion test over **300 flagged flows** drawn from a 60,000-row random sample (208 DoS Hulk,
74 BENIGN, 14 DDoS, 4 DoS slowloris):

| Features replaced with their benign median | Flow returns above the threshold |
|---|---:|
| **top-1 by attribution** | **199 / 300 — 66.3 %** |
| 1 chosen at random | 23 / 300 — 7.7 % |
| **top-3 by attribution** | **273 / 300 — 91.0 %** |
| 3 chosen at random | 77 / 300 — 25.7 % |
| **top-5 by attribution** | **289 / 300 — 96.3 %** |
| 5 chosen at random | 112 / 300 — 37.3 % |

Normalising the single top-attributed feature un-flags two thirds of anomalies, against under
8 % for a randomly chosen feature — an **8.6× separation**. That is the evidence that the
features handed to the LLM are the ones driving the verdict.

### 8.3 The prompt

`PROMPT_VERSION` is `v2`. `_build_prompt` selects the template from the alarm's
**`detection_method`**, not from its predicted label, so a future supervised path that emitted
an `UNKNOWN` label would still get the supervised template, and an anomaly alarm would still
get the anomaly template whatever it was labelled.

The anomaly template states that the supervised model called the flow normal, that the alarm
came from a detector trained **only on normal traffic** which knows no attack types, and that
the system therefore **cannot** attribute the behaviour to any CICIDS2017 class. It forbids
naming an attack type "as hypothesis, as denial, or as example" — the earlier draft listed the
forbidden names, which primes the model to repeat them, so the prohibition is stated by
category instead. Every feature is presented with the benign median beside it, so the model
can say *how far* from normal a measurement is without inventing a magnitude. The LLM still
decides nothing; it only phrases what the detector already concluded.

`v1` explanations remain valid and comparable: the schema's
`(alarm_id, llm_model, llm_prompt_version)` unique constraint keeps them side by side rather
than overwriting them.

### 8.4 Verified

`tests/test_llm_explainer.py` asserts template routing by `detection_method`, that the anomaly
prompt carries isolation-forest evidence and no SHAP evidence, and that it names no CICIDS2017
class. A live test (marked `llm`, skipped when no key is configured) generates a real
explanation for a synthetic `SUSPICIOUS` alarm and asserts the returned Albanian text contains
no attack-class name, checked against 23 name patterns covering all 14 attack classes.

Live verification in this session was limited by the provider, and the limit is reported
rather than hidden: **468 calls were attempted and 466 returned `503 UNAVAILABLE`** from
Gemini; the account's free tier then hit its daily ceiling (`429 RESOURCE_EXHAUSTED`,
20 requests/day), so no further attempts were possible. The **2 generations that did complete
both named no attack class.** Two samples is a smoke test that the path works end to end, not
a rate — no claim is made about how often the model would comply, and the assertion should be
re-run against a provider with real quota before anyone quotes a compliance figure. One of the
two named only the three features it was given (`Idle Max`, `Init_Win_bytes_forward`,
`Flow IAT Std`), stated outright that the system cannot link the deviation to a known attack
type, and asked for analyst verification.

The live test therefore **skips** on 5xx and 429 rather than failing: a provider outage or an
exhausted quota is not a defect in this code, and a test that goes red for it would train
people to ignore red tests.

---

## 9. Known limitations

* The random train/test split over a time-ordered capture inflates every supervised number
  quoted in §1–§5. §6 measures the inflation: accuracy 0.9988 → 0.9756, macro F1
  0.8614 → 0.7818, benign false-positive rate 0.10 % → 2.58 %.
* The comparison XGBoost in §3 and §6 is not the production model; the production balancing
  recipe is unavailable until P2-1 reconstructs it. Until then the temporal-split numbers
  describe that recipe, not the deployed artifact — although on the random split the two
  recipes are within 0.02 macro F1 of each other, which bounds how much that substitution
  can be worth.
* Heartbleed, Infiltration and SQL Injection have 2, 7 and 4 test samples. No conclusion is
  drawn from them — see §7.
* The temporal splits were built from timestamps repaired from a 12-hour clock (§6.1). The
  repair is unambiguous at the hour level and independently corroborated twice, but the
  source data has minute resolution and Monday–Wednesday are unsorted within their files, so
  ordering *inside* a minute is not recoverable and is left as the file order.
* §6 evaluates one seed. The split effect is large (26× on the benign false-positive rate)
  relative to anything a seed change would plausibly produce, but a seed sweep has **not**
  been run and no confidence interval is claimed.
* The anomaly detector's blind spot on scan and brute-force traffic is a property of the
  CICIDS2017 feature space, not a tuning failure. A different threshold does not fix it —
  0.0 % holds at every threshold tested up to 5 %.
* `max_samples=256` means each tree sees 256 rows regardless of the 1.45 M available. This
  is the sklearn default and the configuration that was evaluated; whether a larger sample
  helps has **not** been measured and should not be assumed.
* The anomaly attribution in §8 is a substitution ablation, not TreeSHAP. Its contributions
  do not decompose the score, and it was validated for *ranking* (§8.2), not for magnitude.
* The §8.2 deletion test uses one substitution baseline (the benign median). Whether a
  different reference — a nearest benign neighbour, say — ranks features differently has not
  been measured.
