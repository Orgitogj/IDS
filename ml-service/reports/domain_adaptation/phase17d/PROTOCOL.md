# Phase 17D — Final Unseen Paired Evaluation (pre-registered)

**Status: FROZEN BEFORE CAPTURE.**
Machine-readable twin: [`protocol.json`](protocol.json) (`phase17d-final-eval-v1`).

This document was written and frozen **before any final-evaluation traffic was
generated**, and committed and pushed **before the first final run was captured**. No
model, threshold, selector, metric, traffic procedure, acceptance criterion, or analysis
rule may be changed after looking at final-test predictions.

`PHASE17C_FINAL_HEAD = fb1a232ebaea1d053e5f65686bbfec26ba8f2362`

This is **the final major ML/generalization experiment** for the thesis. There is no
Phase 17E, no new attack families, and no additional models.

---

## 1. Objective

Evaluate **frozen Model A** and **frozen primary Model B** on the **same** newly acquired,
previously unseen laboratory flows, and compare them as a paired operational binary
detector.

---

## 2. Final test runs — exactly 9, newly acquired after Model B freeze

| scenario | runs |
|---|---|
| BENIGN | `eval-v1-benign-001`, `eval-v1-benign-002`, `eval-v1-benign-003` |
| PortScan | `eval-v1-portscan-001`, `eval-v1-portscan-002`, `eval-v1-portscan-003` |
| SSH brute force | `eval-v1-ssh-001`, `eval-v1-ssh-002`, `eval-v1-ssh-003` |

These runs are acquired **after** Model B was frozen and must not overlap any adaptation
or Phase 17C validation run. **No additional scenarios** — no FTP, no DoS, no WebAttack,
no Telnet, no new attack families.

---

## 3. Authorized laboratory only

Existing isolated owned laboratory only:

- Kali **192.168.50.10** → Metasploitable2 **192.168.50.20**
- VirtualBox internal network **`ids-lab`**, capture interface **Kali `eth0`**
- Runs are sequential. No other host, address, subnet, or external system is targeted.

---

## 4. Capture requirements (per run)

tcpdump PCAP · cicflowmeter 0.5.0 CSV · same capture window · SHA-256 for PCAP · SHA-256
for CSV · capture timestamps · scenario identity · source/destination · extractor
identity/version · traffic-procedure identity · ground-truth selector · acceptance status
· provenance. Completed captures are copied to the host promptly. **PCAPs may remain
gitignored; hashes and provenance are tracked.**

---

## 5. Pre-registered support floors

| scenario | floor |
|---|---|
| each BENIGN run | ≥ **300** valid evaluable BENIGN flows |
| each PortScan run | ≥ **300** selector-matched ATTACK flows |
| each SSH run | ≥ **30** selector-matched ATTACK flows |

Acceptance depends **only** on capture integrity, predefined ground truth, minimum
support, and predefined protocol compliance. Acceptance **must not** depend on Model A or
Model B predictions, probability/confidence, whether detection looks good or bad, or the
desired thesis outcome.

If a run fails a support or capture-quality requirement, the failure is recorded and the
run is re-acquired with the **same predefined traffic procedure**. The procedure is never
changed based on model performance.

---

## 6. Ground truth (frozen, prediction-independent)

Labels come only from the pre-declared scenario manifests
(`training/configs/live/*.yaml`) via `app/live/manifest.py: expected_for_flow` — the
identical rule used by the adaptation protocol. **Prediction fields are never exposed to
the ground-truth construction code**, and flows are never labelled by temporal proximity.

- **BENIGN** — `run_level_uniform` BENIGN, from a clean benign window with no attack
  procedure running.
- **PortScan** — per-flow selector, frozen directional rule
  `192.168.50.10 → 192.168.50.20`; reverse/unrelated flows remain **UNLABELLED**.
- **SSH** — per-flow selector `192.168.50.10 → 192.168.50.20` port **22**; same frozen
  controlled SSH authentication-attempt scenario as adaptation.

---

## 7. Critical blinding rule

Acquire, validate, hash, and **seal all 9 runs before examining any prediction**. During
acquisition, prediction outputs are **not** inspected to decide whether another run is
needed. Order: (1) acquire all runs, (2) validate support, (3) hash files, (4) freeze the
final-test manifest, (5) only then begin prediction and comparative evaluation.

---

## 8. Frozen models

**Model A** — the exact existing frozen multiclass model and its deployment inference
path. Not retrained, not modified; feature contract `cicids2017-78-v1` (78 features) and
decision rule unchanged. Artifact SHA-256
`2b7625fc32e5f9e066c3a7b356b8a606c9a1f26e5f2a8d1cc4b6fce4ff2fddfa`.

> Binary operational rule: Model A predicts **ATTACK** when its frozen multiclass
> prediction is any non-BENIGN class, **BENIGN** when it predicts BENIGN. Multiclass
> attribution is kept separately.

**Model B** — exactly `models/model_b/model_b_xgb_weighted_v1.joblib`, SHA-256
`c2bb8f0043eb2eb4c9a8d4639e41e86939675a2a0f1d40bf65c3e8ce181cb237`, threshold
**0.50** (`P(ATTACK) ≥ 0.50 → ATTACK`), feature schema `deployment-cicflowmeter-76-v1`
(76 features). Not retrained, not tuned, not calibrated; threshold not modified.

RF and unweighted XGB remain Phase 17C **secondary evidence** and are **not** used as
alternate final models even if they score better. The final paired comparison is
**FROZEN MODEL A vs FROZEN PRIMARY MODEL B**.

---

## 9. Paired evaluation

Both models score the **exact same evaluable flows**. Per-flow record: `run_id`,
`scenario`, `ground_truth`, Model A predicted class, Model A binary operational decision,
Model B binary decision, Model B attack probability, correctness for each model.

---

## 10. Metrics

**Primary results are scenario-specific** (PortScan dwarfs SSH in flow count, so no single
pooled attack metric is primary). For each scenario, and for **each of the 3 runs
separately**, report per model:

- **BENIGN** — false positives / evaluable benign flows, FPR, Wilson 95% CI
- **PortScan** — detected / evaluable attack flows, detection rate, Wilson 95% CI
- **SSH** — detected / evaluable attack flows, detection rate, Wilson 95% CI
  (the SSH sample size is never hidden)

**Secondary (pooled, labelled SECONDARY because PortScan dominates):** confusion matrix,
Macro F1, balanced accuracy, ATTACK recall, ATTACK precision, BENIGN FPR, and — for
Model B where mathematically valid — ROC-AUC and PR-AUC. Model A multiclass Macro F1 is
**not** compared against Model B binary Macro F1 as though they were the same task.

---

## 11. Paired Model A vs Model B analysis

Because both models score the same flows, paired outcome counts are constructed.

- **ATTACK scenarios:** both detect · Model A only · Model B only · neither
- **BENIGN:** both correctly benign · Model A FP only · Model B FP only · both FP

**McNemar's exact test** may be reported as a secondary paired diagnostic where
appropriate and correctly implemented. It does not override the descriptive results, and
there is no fishing across many tests.

---

## 12. Comparison with development validation

Compare final unseen results **descriptively** with Phase 17C validation; the samples are
**not merged**. Whether the very high validation performance reproduced on fresh unseen
runs is reported honestly as one of: reproduced · partially reproduced · degraded · failed
to reproduce. The interpretation is not rewritten to force support for H2.

---

## 13. Operational trade-off

Explicitly assess whether Model B substantially improves PortScan/SSH detection relative
to Model A, and at what cost in BENIGN false positives — **both sides reported together**.
Increased detection alone is not described as an unconditional improvement.

---

## 14. No post-hoc tuning

After final-test predictions are visible: no retraining, no threshold change, no removing
difficult runs, no selector change, no feature-schema change, no traffic-procedure change,
no class-weight change, no promoting RF, no new model, no rerun because results are
disappointing. If a genuine software bug is found: **STOP**, document it before changing
anything, and decide whether the whole affected evaluation must be rerun. Never silently
patch after seeing results.

---

## 15. Freeze

After all 9 runs satisfy the predefined acquisition criteria, a final-test manifest is
created with all 9 run IDs, scenario, timestamps, PCAP/CSV hashes, extractor version,
total/evaluable flows, ATTACK/BENIGN/UNLABELLED counts, selector/provenance, and
acceptance decision. No adaptation or validation run may appear. The dataset identity
(manifest SHA-256) is frozen **before** scoring. Neither model is retrained after this
point.

---

## 16. Reproducibility

Seed 42, deterministic scoring. Python 3.11.9 · numpy 2.1.1 · pandas 2.2.3 · scipy 1.17.1
· scikit-learn 1.5.2 · xgboost 2.1.1 · joblib 1.4.2.
