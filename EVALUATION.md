# EVALUATION.md — Anomaly detection and the hybrid engine

Produced by P1-1. Every number here comes from a script in `ml-service/training/` and can be
regenerated. Raw output lives in `ml-service/reports/`.

| Experiment | Script | Output |
|---|---|---|
| Leak-free IF evaluation | `training/evaluate_isolation_forest.py` | `reports/isolation_forest_evaluation.json` |
| Leave-one-family-out | `training/leave_one_family_out.py` | `reports/leave_one_family_out.json` |
| Deployable detector | `training/build_anomaly_detector.py` | `models/isolation_forest_benign_v2*` |

Dataset: `cicids2017_cleaned.parquet`, 2,827,876 rows. Split `test_size=0.2`,
`random_state=42`, stratified — the same split the notebook used, so numbers are comparable.

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

## 6. Known limitations

* The random train/test split over a time-ordered capture inflates every supervised number
  quoted here. P2-2 will report a temporal split alongside it.
* The comparison XGBoost in §3 is not the production model; the production balancing recipe
  is unavailable until P2-1 reconstructs it.
* Heartbleed, Infiltration and SQL Injection have 2, 7 and 4 test samples. No conclusion is
  drawn from them.
* The anomaly detector's blind spot on scan and brute-force traffic is a property of the
  CICIDS2017 feature space, not a tuning failure. A different threshold does not fix it —
  0.0 % holds at every threshold tested up to 5 %.
* `max_samples=256` means each tree sees 256 rows regardless of the 1.45 M available. This
  is the sklearn default and the configuration that was evaluated; whether a larger sample
  helps has **not** been measured and should not be assumed.
