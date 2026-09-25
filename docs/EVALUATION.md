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

The live test **skips** on 5xx and 429 rather than failing: a provider outage or an
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

---

## 10. Experiment registration and the historical numbers *(P0-2)*

Produced by `training/evaluate_artifacts.py`; raw output in
`reports/artifact_evaluation/index.json` and `reports/artifact_evaluation/<name>/metrics.json`.

### 10.1 The one set of hand-typed numbers

Notebook cell 17 registered the Random Forest baseline with three metrics written as
literals rather than computed:

```python
record_experiment_result(
    accuracy=0.9986,        # literal
    precision=precision_macro,
    recall=recall_macro,
    f1=0.8724,              # literal
    avg_latency_ms=0.0054,  # literal
    ...)
```

Every other registration in the notebook passed computed variables. Cell 17 is the only
confirmed hand-entry, and it is the only registration whose full API response was echoed
into a notebook output, so it is also the only stored row whose values can be read without
a running database.

### 10.2 Stored versus recomputed

Recomputed from `rf_baseline_cicids2017_v1.joblib` on the historical split
(stratified, `test_size=0.2`, `random_state=42`, 565,576 test rows):

| Field | Stored | Recomputed | Difference | Origin |
|---|---:|---:|---:|---|
| accuracy | 0.998600 | **0.998639** | +0.000039 | hand-typed |
| macro precision | 0.938149 | 0.938149 | 0.000000 | computed |
| macro recall | 0.846629 | 0.846629 | 0.000000 | computed |
| macro F1 | 0.872400 | **0.872388** | −0.000012 | hand-typed |
| avg latency (ms) | 0.005400 | 0.007729 | +0.002329 | hand-typed — **not comparable** |
| sample size | 565,576 | 565,576 | 0 | computed |

**The hand-typed values were not fabricated — they were rounded.** Both differ from the
true value only in the fourth decimal place, which is what a human copying a printed
`:.4f` would produce. The two computed fields reproduce to full double precision, which is
the control that makes the comparison meaningful.

The latency row is **not** evidence of anything. Latency depends on the machine, the
thread count and the load; 0.0054 ms was measured on the notebook's host and 0.0077 ms on
this one. It is reported for completeness and must not be read as a reproducibility check.

### 10.3 The rest of the registry, recomputed

Same split, same encoder, same feature order as each artifact declares. No stored value is
available offline for these rows, so the recomputed figures below are simply the
authoritative ones from now on.

| Registered model | Features | Accuracy | Macro P | Macro R | Macro F1 |
|---|---:|---:|---:|---:|---:|
| xgb-baseline-cicids2017-v1 | 78 | 0.998992 | 0.913647 | 0.862852 | 0.881109 |
| xgb-smote-cicids2017-v1 | 78 | 0.998808 | 0.867056 | 0.897846 | 0.878453 |
| rf-baseline-cicids2017-v2 | 78 | 0.998639 | 0.938149 | 0.846629 | 0.872388 |
| rf-smote-cicids2017-v1 | 78 | 0.998515 | 0.853430 | 0.879200 | 0.864613 |
| mlp-smote-cicids2017-v1 | 78 | 0.977607 | 0.700031 | 0.855349 | 0.703710 |
| xgb-smote-top78features-v1 | 78 | 0.998815 | 0.876183 | 0.907048 | 0.887587 |
| xgb-smote-top50features-v1 | 50 | 0.998801 | 0.868014 | 0.899928 | 0.879436 |
| xgb-smote-top30features-v1 | 30 | 0.996803 | 0.797280 | 0.906234 | 0.827990 |
| xgb-smote-top20features-v1 | 20 | 0.989269 | 0.747796 | 0.897106 | 0.785098 |
| xgb-smote-top10features-v1 | 10 | 0.959364 | 0.671401 | 0.813893 | 0.687340 |

**The harness was validated before these numbers were trusted.** Recomputing
`xgb-smote-cicids2017-v1` reproduces §6's already-verified anchor exactly to four
decimals on all four metrics — accuracy 0.9988, macro F1 0.8785, macro precision 0.8671,
macro recall 0.8978. Independently, predictions from a bare feature array and from a
column-named DataFrame were checked to be identical, which is what rules out a silent
feature-reordering bug in the audit itself.

Two observations worth stating rather than burying:

* **`top50` is not worse than the full 78-feature model** on this split — 0.879436 macro
  F1 against 0.878453. The RQ3 conclusion that the feature reduction is nearly free is
  supported; it is not a trade-off in accuracy terms at 50 features. The cost appears
  between 50 and 30.
* **`xgb-smote-top78features-v1` declares a feature order that matches no registered
  feature set.** It holds all 78 features but ordered by importance rather than by the
  dataset's column order, so it is a *different schema* from
  `xgb-smote-cicids2017-v1` despite having the same members. It is not registered in
  `training_feature_reference.json` and nothing loads it at runtime; it scores highest of
  all ten (0.887587), which is worth knowing before anyone picks a production model.

### 10.4 Isolation Forest is excluded, deliberately

Both isolation forests are audited for existence, loadability and feature schema, and are
then **excluded from the table above**. They are binary BENIGN-versus-attack detectors;
their accuracy, precision, recall and F1 are computed against a two-class problem and
placing them in a column beside a 15-class macro F1 would be a category error. They are
evaluated by `training/evaluate_isolation_forest.py` — see §1–§4.

### 10.5 What may and may not be quoted

**Safe to quote:** every figure in §10.2's *Recomputed* column and in §10.3. Each is
produced by `training/evaluate_artifacts.py` from an artifact whose SHA-256 is recorded in
the report beside the number.

**Do not quote:** the stored `accuracy = 0.9986`, `macro F1 = 0.8724` and
`avg_latency_ms = 0.0054` for the Random Forest baseline. They are hand-entered and, for
latency, not reproducible in principle. Use 0.998639, 0.872388 and a latency measured on
the machine being described.

**Do not compare across latency methodologies.** `avg_latency_ms_batch` (batch predict
over the test set ÷ row count) is the historical methodology and the only one comparable
with the stored numbers. `single_flow_latency` measures one row at a time and is between
30× and 5,000× larger depending on the model — 0.0077 ms batch against 37.3 ms single-flow
for the Random Forest. They are different measurements of different things.

### 10.6 How a result reaches the database now

```
model artifact → evaluate_artifacts.py → metrics.json → EvaluationReport (validated)
              → registration.experiment_payload() → spring_client.create_experiment_result()
```

`spring_client.record_experiment_result(accuracy=..., f1=...)` no longer exists as a
callable path — it raises, pointing at the report-based one. `create_experiment_result`
rejects any payload whose `notes` field does not carry a `provenance=` block, and
`experiment_payload` accepts nothing but a validated `EvaluationReport`. Validation
rejects a report whose macro F1 disagrees with its own confusion matrix, whose per-class
supports do not sum to the row count, whose accuracy disagrees with the sklearn
cross-check, or that carries no artifact SHA-256.

Registration only ever **inserts**. A recomputed row carries, inside its own provenance,
the historical values it supersedes and the fields that were hand-typed, so the old record
is preserved rather than overwritten.

---

## 11. LLM grounding *(P0-3)*

### 11.1 The pipeline as built

```
alarm click → POST :8000/api/explain {alarm_id, feature_vector, compare}
  → predict(): validate → XGBoost → decide() → TreeSHAP for the predicted class
  → _build_prompt() routes on detection_method, not on the label
  → the prompt string is handed to Claude
  → POST :8080/api/alarms/{id}/explanations  (text, llm_model, prompt_version, latency)
  → the dashboard re-GETs and the analyst rates HELPFUL / UNCLEAR / INCORRECT
```

Two properties were already correct and were left alone: the prompt is built **once**
per alarm and handed to the provider unchanged; and
the LLM is never consulted for the verdict, only for the narrative.

### 11.2 What was wrong

P2-6 hardened the *anomaly* template and left the *supervised* one as it was. The
supervised prompt carried a single instruction — "do not invent characteristics not
supported by the data above" — and nothing else. It did not tell the model that it had
never seen the traffic, that it had no packet payload, that the classification was a
prediction rather than an established fact, that the confidence figure is the model's
confidence in a class rather than the probability an attack occurred, or that a SHAP
contribution is an attribution of the model's decision rather than a cause.

### 11.3 What changed

`PROMPT_VERSION` moves `v2 → v3`. Three blocks are now shared verbatim by both templates,
so the anomaly path keeps everything it had and the supervised path gains it:

* **`EVIDENCE_BOUNDARY`** — you have not seen the traffic; you have no access to packets or
  their contents; the only evidence is what is in this message; feature values are
  statistical measurements of the flow, not packet contents.
* **`INVENTION_RULES`** — do not name IP addresses, ports or device names absent from the
  evidence; do not name protocols not derivable from it; do not describe payloads,
  commands or files; do not add techniques or tools; if a detail is not in the evidence,
  omit it rather than guessing.
* **`STYLE_RULES`** — clear Albanian, 3–5 sentences, standard technical terms may stay in
  English where translating would read artificially, no alarmist language.

The supervised template additionally states that the classification is a prediction and
not a proven fact, and requires the wording *"modeli e klasifikoi si X"* over *"kjo rrjedhe
ishte X"*; frames confidence explicitly as the model's confidence in the chosen class,
"not the probability that the attack actually occurred and not a risk measure"; asks for
proportionally more cautious wording as confidence falls; and separates *vlera e matur*
(the measurement) from *kontribut SHAP* (its push toward the class), stating that SHAP
explains the model's decision and does not prove the real cause.

**No new confidence thresholds were introduced.** The existing 0.95/0.85/0.70 thresholds
are *severity* thresholds, and the audit already established that prediction confidence is
not security severity; reusing them for linguistic hedging would import exactly that
confusion. The prompt is given the confidence value and asked to scale its caution to it,
with no numeric bands. This is a deliberate choice, and it means the hedging is a model
behaviour rather than a system guarantee.

Historical explanations are untouched. The unique index is
`(alarm_id, llm_model, llm_prompt_version)`, so `v3` rows sit alongside `v1` and `v2`
instead of replacing them, and registration only ever inserts.

### 11.4 The groundedness check

`app/services/groundedness.py`, method `deterministic_heuristic_v1`. **No LLM judge.** It
builds an allow-list from the evidence actually handed to the model — feature names, every
feature value and SHAP contribution in several rounded forms, the confidence as both
fraction and percentage, the predicted label — and then flags:

| Finding | Severity | Rationale |
|---|---|---|
| IPv4 / IPv6 address | high | The feature vector contains no address. One can never be grounded. |
| Payload or packet-content claim | high | The model receives aggregate flow statistics only. |
| Port number in a port context, absent from the evidence | medium | `Destination Port` may legitimately appear; another port cannot. |
| Protocol name absent from the evidence | medium | The 78-feature set carries no protocol identity. |

The design decision that makes it usable rather than noisy: **only numbers in a port
context are checked**, never every number. An explanation may freely quote `0.812` or
`1200` from the evidence, and does not trip the check; "portes 8080" does, while "portes
443" does not when 443 is a feature value. This is pinned by tests in both directions.

**What it is not.** It cannot tell whether an explanation is *correct*, only whether it
names entities the model could not have been given. A clean result is not evidence of
correctness, and the report says so in its own `caveat` field. It is reported on
`/api/explain` responses and in the H4 export; it does not block or alter any explanation.

### 11.5 The H4 export

`python -m training.export_explanations` (read-only; GET requests only) writes
`reports/llm_evaluation/{explanations.csv, explanations.jsonl, summary.json}`, one row per
explanation: alarm and flow ids, ground-truth label and attack type where the replay
supplied them, predicted class, confidence, detection method, model name/version/feature
version, provider, LLM model, prompt version, latency, analyst rating, the SHAP evidence
recomputed from the stored feature vector, and the groundedness result.

No migration was needed. `explanations` already stores the text, model, prompt version,
latency and rating; the confidence and model identity live on `network_flows`; and the
SHAP evidence is *reconstructed* by re-running the recorded model over the stored feature
vector rather than being duplicated into a new column.

### 11.6 Limitations

* The hedging requirement in §11.3 is an instruction, not an enforced constraint. Nothing
  measures whether a model actually hedges more at 0.42 than at 0.96.
* The groundedness heuristic covers addresses, packet-content claims, ports and a fixed
  list of 19 protocol names. A fabricated *technique* or a wrong causal story passes it
  cleanly. It is a floor, not a ceiling.
* Protocol findings are `medium` because a model inferring "HTTPS" from port 443 is making
  an inference rather than inventing an entity. Whether that should count as ungrounded is
  a judgement call, and it is recorded rather than resolved.
* The v3 prompts have **not** been exercised against a live provider in this phase — no
  API credits were spent, by instruction. The prompt-construction tests are exhaustive but
  they test the prompt, not the model's compliance with it. §8.4's warning still stands:
  the two live generations recorded there are a smoke test, not a compliance rate, and a
  v3 compliance figure requires a provider with real quota.
* `generate_all_explanations` still swallows a provider failure with a printed message, so
  a comparison run can silently yield one provider instead of two. The export makes this
  visible after the fact (`by_provider` counts), but the API response does not.
