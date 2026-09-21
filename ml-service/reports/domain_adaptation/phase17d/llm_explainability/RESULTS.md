# PK4 / H4 — SHAP + LLM explanation evaluation: results

Protocol: [`PROTOCOL.md`](PROTOCOL.md) / [`protocol.json`](protocol.json)
(`phase17d-explainability-v1`), provider amendment
[`PROVIDER_AMENDMENT.md`](PROVIDER_AMENDMENT.md). Source results (unmodified):
[`explanation_runs_claude.json`](explanation_runs_claude.json),
[`technical_evaluation_claude.json`](technical_evaluation_claude.json),
[`latency_claude.json`](latency_claude.json). Manual audit:
[`MANUAL_AUDIT.md`](MANUAL_AUDIT.md).

This is an **explainability** evaluation of generated IDS alerts, not a predictive-model
experiment and not a provider benchmark. Conclusions are limited to **automated technical
groundedness, latency, and a documented manual audit**. **No human evaluation was
conducted** (see §6). Model A, Model B, threshold 0.50, the frozen 12-alert sample, the
evidence schema, top-k SHAP = 5, and the v3 prompt are all unchanged.

## 1. Batch

| | |
|---|---|
| Final provider | **Claude** (`claude-sonnet-5`; resolved model `claude-sonnet-5`) |
| Responses | **24 / 24 successful**, 0 failed, 0 retries |
| Design | 12 frozen alerts × {with_shap, no_shap} |
| Sample | 6 benign false-positive alerts + 6 correctly-detected PortScan alerts |
| max_tokens | 400 (temperature unset — provider default; a non-determinism limitation) |
| Prompt template | v3, sha256 `fc6504407d3fabe3ff5afa80b71802d5eb340ceeff81412a4b64b163b32620c9` |
| Evidence sample | sha256 `d20c7ee1f833b050a69974be4247b63bc4f97e018989dcdc918ec5c61cecdad5` |
| Model B | sha256 `c2bb8f0043eb2eb4c9a8d4639e41e86939675a2a0f1d40bf65c3e8ce181cb237` |

## 2. Automated technical groundedness (as computed; not edited)

| metric | with SHAP (n=12) | no SHAP (n=12) |
|---|---|---|
| prediction consistency | 1.0000 | 1.0000 |
| unsupported-claim-free rate | 1.0000 | 1.0000 |
| structural completeness | 0.9167 (11/12) | 1.0000 |
| direction consistency | **17/19 = 0.8947** | n/a (SHAP-only) |
| mean evidence coverage | 0.85 | n/a (SHAP-only) |

- Every explanation stated the correct frozen Model B decision (12/12 both conditions).
- No explanation referenced an entity absent from the evidence (no invented IPs, ports,
  protocols or packet contents) — unsupported-claim-free 12/12 both conditions.
- With SHAP, Claude referenced on average 0.85 of the top-5 supplied features.

## 3. Manual audit (reported separately from §2; source JSON unchanged)

A human read of the three flagged cases (full detail and quotes in
[`MANUAL_AUDIT.md`](MANUAL_AUDIT.md)):

- **Direction consistency:** the two automated "inconsistencies"
  (`eval-v1-benign-001#29`, `eval-v1-benign-002#85`, both `totlen_fwd_pkts`) are
  **evaluator false positives** — the texts explicitly describe the feature as a negative
  contribution pulling *away* from ATTACK, matching the expected `decreases_attack`.
  **Manually audited direction consistency = 19/19.** The automated **17/19** stands as the
  automated figure and is not overwritten.
- **Structural completeness:** the one flagged case (`eval-v1-benign-003#229`, with_shap)
  is a heuristic **false negative** — the explanation does express uncertainty ("besueshmeri
  … te ulet, 56.6%", "nuk duhet trajtuar si diagnoze e sigurt", "parashikim statistikor …
  jo nje konfirmim i nje incidenti real"). The automated **11/12** stands as the automated
  figure.
- **Genuine truncation:** that same with-SHAP explanation is truncated mid-word at the end,
  consistent with the frozen `max_tokens=400` limit — a real limitation, recorded, not
  overridden.

## 4. With-SHAP vs no-SHAP (comparable metrics only)

Compared only on conceptually comparable metrics:

| metric | with SHAP | no SHAP |
|---|---|---|
| prediction consistency | 1.0000 | 1.0000 |
| structural completeness | 0.9167 (11/12; §3 shows the one flag is a heuristic FN) | 1.0000 |
| unsupported-claim-free | 1.0000 | 1.0000 |

**Direction consistency and evidence coverage are SHAP-only metrics and are NOT treated as
zero for the no-SHAP condition** — a no-SHAP explanation has no supplied SHAP evidence to be
consistent with or to cover, so a zero there would be conceptually meaningless and would
artificially favour the SHAP condition. They are reported for with-SHAP only.

On this small set, both conditions are grounded and prediction-consistent; the automated
numbers do not establish a groundedness difference between conditions (n=12; see §7).

## 5. Latency (explanation layer only — separate from frozen ML inference latency)

| distribution | n | median | IQR |
|---|---|---|---|
| SHAP computation | 12 | **4.55 ms** | (see `latency_claude.json`) |
| LLM generation — with SHAP | 12 | 9924.00 ms | |
| LLM generation — no SHAP | 12 | 10840.04 ms | |
| total explanation — with SHAP | 12 | 9927.93 ms | |
| total explanation — no SHAP | 12 | 10840.04 ms | |

**SHAP is not claimed to make Claude faster.** SHAP computation added only ≈ **4.55 ms**
(median) to the explanation layer. The no-SHAP median LLM time is actually ≈ 0.91 s *higher*
than with-SHAP; this ≈0.91 s difference is **provider generation-time variability**, not an
effect of SHAP, and no causal latency claim is made from it. These figures are separate from
the frozen Model A / Model B inference-latency measurements.

## 6. Human evaluation — intentionally not conducted

Human evaluation was **intentionally not conducted** for this thesis component. No raters,
ratings, participant counts, or human-evaluation results exist or are fabricated. The
instrument (`HUMAN_EVAL_QUESTIONNAIRE.md`) and data-entry template
(`human_eval_ratings_template.csv`) are preserved **unchanged** as unused protocol
artifacts, so a real human study could be run later without redesign.

Consequently, human-perceived clarity/usefulness is **not** evidenced here, and the
automated technical groundedness metrics are **not** a substitute for it.

## 7. Limitations

- **n = 12 alerts** (24 explanations). No statistical significance or representativeness is
  claimed; all figures are descriptive.
- **No SSH explanation item:** the frozen Model B generated **no SSH alert** in Phase 17D
  (0/180 SSH detection), so there is no SSH alert to explain. This is a limitation of the
  alert set, not missing data to be repaired.
- **Automated groundedness ≠ human usefulness.** The evaluator is a deterministic heuristic
  (with documented false positives/negatives, §3); it tests grounding against supplied
  evidence, not human clarity.
- **Provider non-determinism:** temperature was unset (provider default); outputs are not
  bit-reproducible.
- **Truncation:** `max_tokens=400` truncated one with-SHAP explanation.

## 8. Final H4 status

**H4 — PARTIALLY TESTED / NOT FULLY TESTED.**

- **Automated technical groundedness (tested):** on 12 frozen alerts × 2 conditions with
  Claude, explanations were 12/12 prediction-consistent and 12/12 free of unsupported
  entity claims in both conditions; with-SHAP direction consistency was 17/19 automated
  (19/19 on manual audit) and mean evidence coverage 0.85; structural completeness 11/12
  automated (the one flag a heuristic false negative). Explanation-layer latency is
  dominated by LLM generation (~10 s median); SHAP adds ~4.55 ms.
- **Human-perceived clarity/usefulness (not tested):** no human evaluation was conducted;
  none is fabricated.

Per the frozen protocol's H4 rule, H4 is **not** concluded as "supported" on automated
groundedness alone. It remains **partially tested**: the technical-groundedness and latency
limbs are evidenced (with the documented manual-audit caveats and the small n), while the
human-perception limb is untested by explicit decision.
