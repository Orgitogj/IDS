# Phase 17D — Final Unseen Paired Evaluation: results

Protocol: [`PROTOCOL.md`](PROTOCOL.md) / [`protocol.json`](protocol.json) (+ amendments
[001](EXTRACTOR_COMPAT.md), [002](SSH_PROCEDURE_AMENDMENT.md),
[003](SSH_ORCHESTRATION_AMENDMENT.md)). Sealed dataset:
[`data/final_test_seal.json`](data/final_test_seal.json) (manifest sha256
`c6914dd0de90922193c26429becccd966efcd235d886a77c2e2b469686c160c1`). Machine-readable
results: [`scenario_results.json`](scenario_results.json),
[`paired_comparison.json`](paired_comparison.json),
[`per_run_results.csv`](per_run_results.csv), [`evaluation_summary.json`](evaluation_summary.json).

Frozen **Model A** (`2b7625fc…`) and frozen primary **Model B**
`model_b_xgb_weighted_v1.joblib` (`c2bb8f00…`) were scored on the **same** 1,180,770
evaluable final-test flows at the pre-registered threshold **0.50**. The dataset was
**sealed before any prediction** was produced. No model was retrained, tuned, or
recalibrated; no run was removed; no threshold or selector was changed.

Model A's binary operational decision = ATTACK for any non-BENIGN multiclass class, else
BENIGN.

## 1. Primary scenario-specific results (Wilson 95%)

### BENIGN — false-positive rate (n = 960; per-run n = 320)

| model | aggregate FP | FPR | 95% Wilson | per-run FPR |
|---|---:|---:|---|---|
| Model A | 0 / 960 | 0.0000 | [0.0000, 0.00399] | 0/320, 0/320, 0/320 |
| **Model B** | 85 / 960 | **0.0885** | [0.0722, 0.1082] | 0.0813, 0.1125, 0.0719 |

### PortScan — detection rate (n = 1,179,630; per-run n = 393,210)

| model | aggregate detected | rate | 95% Wilson |
|---|---:|---:|---|
| Model A | 0 / 1,179,630 | 0.0000 | [0.0000, 3.26e-06] |
| **Model B** | 1,179,630 / 1,179,630 | **1.0000** | [0.99999, 1.0] |

Per-run Model B PortScan detection is 393210/393210 = 1.0 for all three runs; Model A is
0/393210 for all three.

### SSH — detection rate (n = 180; per-run n = 60)

| model | aggregate detected | rate | 95% Wilson |
|---|---:|---:|---|
| Model A | 0 / 180 | 0.0000 | [0.0000, 0.0209] |
| **Model B** | 0 / 180 | **0.0000** | [0.0000, 0.0209] |

Per-run Model B SSH detection is 0/60 for all three runs. **SSH support is small (n = 180
total, 60 per run); an observed 0% is not a true population 0%** — the Wilson upper bound
is ~2.1%. See the SSH caveat in §5.

## 2. Paired Model A vs Model B outcomes

**ATTACK flows (n = 1,179,810 = PortScan 1,179,630 + SSH 180):**

| outcome | count |
|---|---:|
| both detect | 0 |
| Model A only | 0 |
| **Model B only** | **1,179,630** |
| neither | 180 |

The 180 "neither" are the SSH flows. The 1,179,630 "Model B only" are the PortScan flows.

**BENIGN flows (n = 960):**

| outcome | count |
|---|---:|
| both correct (benign) | 875 |
| Model A FP only | 0 |
| **Model B FP only** | **85** |
| both FP | 0 |

## 3. McNemar exact test (secondary paired diagnostic)

- **Attack detection:** discordant pairs b(A-only)=0, c(B-only)=1,179,630 → two-sided exact
  p ≈ 0. Model B detects attacks Model A misses, overwhelmingly.
- **Benign false positives:** b(A-only)=0, c(B-only)=85 → two-sided exact p ≈ 5.2e-26. All
  false positives are Model B's.

These confirm the descriptive direction and do not override it. No other tests were run
(no fishing).

## 4. Secondary pooled metrics (labelled SECONDARY — PortScan dominates flow count)

Because PortScan is 99.9% of the evaluable attack flows, the pooled figures are dominated
by PortScan and are reported only as secondary context. Both models are compared on their
**binary operational** decision; Model A's multiclass Macro F1 is **not** equated with
Model B's binary Macro F1.

| metric | Model A (operational binary) | Model B |
|---|---:|---:|
| confusion (tn/fp/fn/tp) | 960 / 0 / 1,179,810 / 0 | 875 / 85 / 180 / 1,179,630 |
| Macro F1 | 0.0008 | 0.9342 |
| balanced accuracy | 0.5000 | 0.9557 |
| ATTACK recall | 0.0000 | 0.9998 |
| ATTACK precision | 0.0000 | 0.9999 |
| BENIGN FPR | 0.0000 | 0.0885 |
| ROC-AUC (Model B) | — | 0.99991 |
| PR-AUC (Model B) | — | ~1.0000 |

Model A flags nothing in the deployment extractor domain (recall 0), so its pooled binary
scores are near-zero; this is consistent with its frozen historical deployment behaviour.

## 5. Comparison with Phase 17C validation (samples NOT merged)

| quantity | 17C validation (Model B) | 17D final unseen (Model B) | verdict |
|---|---|---|---|
| PortScan detection | 1362/1362 = 1.000 | 1,179,630/1,179,630 = 1.000 | **reproduced** |
| BENIGN FPR | 21/5407 = 0.0039 | 85/960 = 0.0885 | **degraded** |
| SSH detection | 67/69 = 0.971 | 0/180 = 0.000 | **failed to reproduce** |

- **PortScan: reproduced.** Perfect detection on 1.18M fresh unseen scan flows.
- **BENIGN: degraded.** The benign false-positive rate rose from 0.39% (validation) to
  **8.85%** (final) — a ~23× increase, well outside the validation Wilson interval. Model B
  is materially more false-positive-prone on fresh benign traffic than validation implied.
- **SSH: failed to reproduce — but confounded.** Validation SSH detection was 97%; final
  SSH detection is **0%**. This must be read with a strong caveat: the final-test SSH flows
  were generated by the **Amendment 003 `/dev/tcp` banner-exchange procedure**, which was
  adopted only because the frozen hydra procedure and the Amendment 002 procedure could not
  produce usable flows against the legacy Metasploitable2 SSH service. Those v3 flows are
  short TCP-connect + SSH-banner exchanges, **structurally different** from the hydra-driven
  SSH flows Model B was trained and validated on (fuller authentication attempts). The 0%
  SSH result therefore conflates domain generalization with a **change in how the SSH attack
  traffic was generated**, and cannot be interpreted as a clean generalization failure of
  Model B on SSH. It is reported here truthfully and is **not** used to tune or reselect any
  model.

## 6. Operational trade-off (detection gain vs false-positive cost, reported together)

Relative to frozen Model A on the same unseen flows, frozen Model B:

- **PortScan:** detection **0.0% → 100.0%** — a decisive gain on 1.18M flows (McNemar
  p ≈ 0).
- **SSH:** detection **0.0% → 0.0%** — **no** improvement on this fresh set (with the §5
  traffic-generation caveat; n = 180).
- **BENIGN cost:** false-positive rate **0.0% → 8.85%** (85/960; McNemar p ≈ 5.2e-26) — a
  real, non-trivial operational cost. In deployment, ~1 in 11 benign flows would be raised
  as an alert by Model B where Model A raised none.

Net: Model B turns a detector that was effectively blind to deployment-domain PortScan
into a near-perfect PortScan detector, at the price of a benign false-positive rate that
is small in absolute terms but materially higher than validation suggested and far higher
than Model A's. It delivers no SSH benefit on this (differently generated, small-support)
SSH set. The increased detection is **not** an unconditional improvement.

## 7. Integrity

- Dataset **sealed before scoring**; manifest hash verified against the seal before
  scoring ran.
- Model A `2b7625fc…` and Model B `c2bb8f00…` re-verified byte-identical; threshold 0.50.
- Both models scored the **identical** 1,180,770 evaluable flow identities (paired).
- Ground truth from manifest selectors only; prediction fields never entered the
  ground-truth construction.
- `paired_predictions.csv` (1,180,770 rows) kept local (gitignored); sha256
  `8a5494354be7efc3411fab258c85f7928199afb1f61587b7142d859c77959485`.

## 8. Limitations

- SSH final-test traffic-generation differs from the SSH training/validation procedure
  (§5); the SSH result is confounded and support is small (n = 180).
- PortScan dominates the evaluable flows (99.9%), so pooled metrics are PortScan-driven and
  are reported only as secondary.
- Benign, PortScan and SSH share one isolated lab topology and two hosts; the estimate does
  not cover topology or host diversity.
- Model A and Model B solve different primary tasks (multiclass attribution vs binary
  detection); only shared binary operational quantities are compared.
