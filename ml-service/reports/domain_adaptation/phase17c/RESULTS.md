# Phase 17C — Model B training and validation results

Protocol: [`PROTOCOL.md`](PROTOCOL.md) · [`protocol.json`](protocol.json)
(`phase17c-model-b-v1`, frozen before any fit).

Machine-readable results: [`validation_results.json`](validation_results.json) ·
[`model_b_metadata.json`](model_b_metadata.json)

> **Development validation only.** The three historical runs below are a *development*
> validation partition. They are **not** unseen final evaluation data and must never be
> described as such. No `eval-v1-*` run exists; no final-test traffic was acquired or used.

---

## 1. Partitions

Run-level split, reused verbatim from frozen Phase 17B. No flow was randomly split
across runs.

**TRAIN — 9 new adaptation runs**

| run | total | evaluable | ATTACK | BENIGN | unlabelled |
|---|---:|---:|---:|---:|---:|
| adapt-v1-benign-002 | 775 | 775 | 0 | 775 | 0 |
| adapt-v1-benign-003 | 806 | 806 | 0 | 806 | 0 |
| adapt-v1-benign-004 | 770 | 770 | 0 | 770 | 0 |
| adapt-v1-portscan-002 | 8878 | 7531 | 7531 | 0 | 1347 |
| adapt-v1-portscan-003 | 8917 | 7711 | 7711 | 0 | 1206 |
| adapt-v1-portscan-004 | 8068 | 6917 | 6917 | 0 | 1151 |
| adapt-v1-ssh-002 | 72 | 72 | 72 | 0 | 0 |
| adapt-v1-ssh-003 | 72 | 72 | 72 | 0 | 0 |
| adapt-v1-ssh-004 | 72 | 72 | 72 | 0 | 0 |
| **total** | **28430** | **24726** | **22375** | **2351** | **3704** |

**VALIDATION — 3 historical adaptation runs (untouched)**

| run | total | evaluable | ATTACK | BENIGN | unlabelled |
|---|---:|---:|---:|---:|---:|
| lab-v1-benign-001 | 5407 | 5407 | 0 | 5407 | 0 |
| lab-v1-portscan-001 | 2178 | 1362 | 1362 | 0 | 816 |
| lab-v1-ssh-bruteforce-001 | 70 | 69 | 69 | 0 | 1 |
| **total** | **7655** | **6838** | **1431** | **5407** | **817** |

**FINAL TEST — empty.**

Every count reproduces the frozen Phase 17B manifest exactly. Labels come only from the
pre-declared scenario manifests; Model A predictions were not consulted.

---

## 2. Class balancing

TRAIN is ATTACK-heavy and PortScan-dominated, so **BENIGN is the minority class** —
benign undersampling was therefore *not* performed. No SMOTE.

Inverse-frequency weights, computed on **TRAIN only**
(`w_c = n_total / (2 * n_c)`, n_total = 24726):

| class | TRAIN support | weight |
|---|---:|---:|
| BENIGN (0) | 2351 | **5.258613356018715** |
| ATTACK (1) | 22375 | **0.552536312849162** |

Validation was left untouched and naturally distributed.

---

## 3. Validation results — threshold 0.50 (pre-registered)

| model | role | Macro F1 | Bal. acc | ATTACK recall | ATTACK prec. | BENIGN FPR | ROC-AUC | PR-AUC |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **`model-b-xgb-weighted-v1`** | **PRIMARY** | **0.9949** | **0.9974** | **0.9986** | **0.9855** | **0.003884** | 0.99883 | 0.99369 |
| `model-b-rf-weighted-v1` | robustness | 0.9976 | 0.9990 | 1.0000 | 0.9924 | 0.002034 | 1.00000 | 1.00000 |
| `model-b-xgb-unweighted-v1` | ablation | 0.9833 | 0.9924 | 0.9986 | 0.9501 | 0.013871 | 0.99924 | 0.99435 |

Confusion matrices (rows = truth, cols = prediction):

| model | TB→B | TB→A | TA→B | TA→A |
|---|---:|---:|---:|---:|
| `model-b-xgb-weighted-v1` (primary) | 5386 | 21 | 2 | 1429 |
| `model-b-rf-weighted-v1` | 5396 | 11 | 0 | 1431 |
| `model-b-xgb-unweighted-v1` | 5332 | 75 | 2 | 1429 |

Overall Wilson 95% intervals:

| model | BENIGN FPR | ATTACK detection rate |
|---|---|---|
| primary XGB weighted | 21/5407 = 0.003884 [0.002542, 0.005930] | 1429/1431 = 0.998602 [0.994918, 0.999617] |
| RF weighted | 11/5407 = 0.002034 [0.001136, 0.003639] | 1431/1431 = 1.000000 [0.997323, 1.000000] |
| XGB unweighted | 75/5407 = 0.013871 [0.011081, 0.017351] | 1429/1431 = 0.998602 [0.994918, 0.999617] |

---

## 4. Per-scenario diagnostics (Wilson 95%)

### PRIMARY — `model-b-xgb-weighted-v1`

| scenario | quantity | count | rate | 95% Wilson |
|---|---|---:|---:|---|
| BENIGN | false-positive rate | 21 / 5407 | 0.003884 | [0.002542, 0.005930] |
| PortScan | detection rate | 1362 / 1362 | 1.000000 | [0.997187, 1.000000] |
| SSH | detection rate | 67 / 69 | 0.971014 | [0.900334, 0.992015] |

### ROBUSTNESS — `model-b-rf-weighted-v1`

| scenario | quantity | count | rate | 95% Wilson |
|---|---|---:|---:|---|
| BENIGN | false-positive rate | 11 / 5407 | 0.002034 | [0.001136, 0.003639] |
| PortScan | detection rate | 1362 / 1362 | 1.000000 | [0.997187, 1.000000] |
| SSH | detection rate | 69 / 69 | 1.000000 | [0.947263, 1.000000] |

### ABLATION — `model-b-xgb-unweighted-v1`

| scenario | quantity | count | rate | 95% Wilson |
|---|---|---:|---:|---|
| BENIGN | false-positive rate | 75 / 5407 | 0.013871 | [0.011081, 0.017351] |
| PortScan | detection rate | 1362 / 1362 | 1.000000 | [0.997187, 1.000000] |
| SSH | detection rate | 67 / 69 | 0.971014 | [0.900334, 0.992015] |

> **SSH support is small: n = 69.** The intervals above are correspondingly wide — the RF
> observation of 69/69 has a Wilson lower bound of only 0.947, and a *perfect observed
> rate is not evidence of a perfect population rate*. Equally, an observed zero would
> never be a true population zero. SSH conclusions remain support-limited.

---

## 5. Shared operational comparison with frozen Model A

Model A performs **multiclass attribution**; Model B performs **binary attack
detection**. These are different tasks, so their Macro F1 values are **not** compared.
Only shared operational quantities on the same three historical scenarios are compared.

Frozen Model A historical values are quoted as recorded; they were not recomputed and no
Model A file was modified.

| scenario | quantity | frozen Model A | Model B primary (XGB weighted) |
|---|---|---|---|
| BENIGN | false positives | 0 / 5407 (0.000000) | 21 / 5407 (0.003884) |
| PortScan | detected | 2 / 1362 (0.001468) | 1362 / 1362 (1.000000) |
| SSH | detected | 0 / 69 (0.000000) | 67 / 69 (0.971014) |

Model B converts a near-total deployment-domain detection failure into near-complete
detection, at the cost of a small but non-zero benign false-positive rate (0.39%, Wilson
[0.25%, 0.59%]) where Model A had none observed.

> Caveat: Model A's benign 0/5407 is unsurprising for a model that flagged almost nothing
> at all in this domain (2/1362 PortScan, 0/69 SSH). A detector that rarely fires trivially
> achieves a low false-positive rate, so the FPR comparison should be read together with
> the detection columns, not on its own.

---

## 6. Model selection

**The pre-declared primary Model B is `model-b-xgb-weighted-v1`, and it remains the
primary.**

The Random Forest scored higher on this validation partition (Macro F1 0.9976 vs 0.9949,
SSH 69/69 vs 67/69, BENIGN FPR 0.002034 vs 0.003884). Under the pre-registered freeze
rule this **does not** promote it: selecting whichever algorithm happened to win
validation is exactly the post-hoc selection the protocol forbids. The Random Forest
result is recorded as **robustness evidence** that the deployment-domain binary task is
learnable by more than one algorithm family, not as a model choice.

The ablation confirms the class-weighting decision: removing TRAIN-only weighting raises
the benign false-positive rate roughly 3.6× (0.013871 vs 0.003884) with no gain in
detection.

---

## 7. Artefacts

| role | id | artefact | SHA-256 |
|---|---|---|---|
| **PRIMARY** | `model-b-xgb-weighted-v1` | `models/model_b/model_b_xgb_weighted_v1.joblib` | `c2bb8f0043eb2eb4c9a8d4639e41e86939675a2a0f1d40bf65c3e8ce181cb237` |
| robustness | `model-b-rf-weighted-v1` | `models/model_b/model_b_rf_weighted_v1.joblib` | `d469d31234df0b2f0aa2e5e05fe95acbe195ff191ae6e5c5377017dc5c746811` |
| ablation | `model-b-xgb-unweighted-v1` | `models/model_b/model_b_xgb_unweighted_v1.joblib` | `d077369270af89c931f6ad3c16611a5ccc542528cd6d55b8d1252a3e1f7da943` |

Protocol SHA-256: `22952b8b2136e85a8645e2bd7cb1623c49f942fdda0334ff8ac80d6187ec9cbc`

Binaries are kept local and gitignored, matching the existing repository convention for
`ml-service/models/*.joblib`; their hashes and full configuration are tracked here.
Retraining reproduces all three artefacts **bitwise identically** (verified).

---

## 8. Feature contract as used

`deployment-cicflowmeter-76-v1` — 76 numeric features from `cicflowmeter 0.5.0`, fixed
order, identity columns (`src_ip`, `dst_ip`, `src_port`, `dst_port`, `protocol`,
`timestamp`) excluded. Data was **not** converted back to the historical Java
CICFlowMeter `cicids2017-78-v1` contract.

In TRAIN, 16 of the 76 features are constant. They were **retained**, because the feature
list is fixed a priori and dropping them would introduce a train-fitted feature-selection
step:

```
fwd_seg_size_min  flow_iat_min  fwd_iat_min  fwd_urg_flags  bwd_urg_flags
urg_flag_cnt  ece_flag_cnt  active_max  active_min  active_mean  active_std
idle_max  idle_min  idle_mean  idle_std  cwr_flag_count
```

No NaN or ±inf values were observed in either partition; the fixed `0.0` replacement rule
was therefore a no-op in practice.

---

## 9. Limitations

- Validation is **development-only** and reuses the three historical runs. It gives no
  unseen-data estimate; that requires the Phase 17D final evaluation, which does not exist.
- SSH support is **n = 69** (validation) and 216 flows (train). All SSH conclusions are
  support-limited.
- TRAIN attack traffic is **94.8% PortScan** (22375 ATTACK flows, of which 22159 PortScan).
  Model B's attack concept is dominated by scanning behaviour; generalisation to other
  attack families is unevidenced.
- Train and validation come from the same isolated laboratory topology and the same
  two hosts, so the estimate does not cover topology shift.
- The three validation runs were already used for Model A's historical deployment
  evaluation, so they are not naive data in the broader project sense.
