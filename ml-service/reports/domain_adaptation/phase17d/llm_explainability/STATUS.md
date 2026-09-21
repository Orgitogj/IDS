# PK4 / H4 — current status and remaining actions

`H4 status: NOT FULLY TESTED.`

## What is done (this turn)

- Audited the existing SHAP + LLM explanation architecture (reused, not rewritten).
- Froze the PK4/H4 protocol (`protocol.json`, `PROTOCOL.md`) before inspecting any
  explanation quality.
- Added a read-only Model B SHAP path (booster `pred_contribs`) — no change to Model B.
- Built the fixed, pre-registered 12-alert sample (`sample_manifest.json`) and the frozen
  evidence packages (`evidence_sample.json`) with **no ground-truth leakage**.
- Implemented the deterministic technical-groundedness evaluator
  (`app/services/explanation_eval.py`): prediction consistency, feature grounding,
  direction consistency, unsupported-claim detection, evidence coverage, structural
  completeness, plus aggregates.
- Implemented the SHAP-vs-no-SHAP batch runner (`training/phase17d_explain_run.py`) with a
  dry-run default; measured SHAP latency (median ≈ recorded in `sample_manifest.json`).
- Created the human-evaluation instrument and data-entry template. **No human results
  fabricated.**
- Added deterministic tests; default test suite makes **no real LLM calls**.

## Remaining actions before H4 can be concluded

1. **Approve the real-provider batch.** `training/phase17d_explain_run.py --provider claude
   --conditions both --go` with `IDS_LLM_INTEGRATION=1` → **24** Claude calls (12 alerts ×
   {with_shap, no_shap}). This is a small paid run and needs explicit approval.
2. Run the automated technical evaluation over the generated explanations (the runner does
   this and writes `technical_evaluation_claude.json` + `explanation_runs_claude.json`).
3. Populate the human-eval items with the generated explanation texts and collect ratings
   from one or more **real** raters into `human_eval_ratings_template.csv`.
4. Analyze human ratings descriptively (per-dimension medians and ranges); do not claim
   statistical representativeness from a convenience sample.
5. Conclude H4 by combining (a) technical groundedness and (b) human-perceived
   clarity/usefulness — as one of: supported with limitations / partially supported / not
   supported. If human evaluation is not completed, H4 stays partially tested / not fully
   tested regardless of automated results.

## Guardrails still in force

- No new ML model, no retraining, Model A/Model B and threshold 0.50 unchanged, Phase 17D
  results unchanged.
- No ground truth in the LLM evidence.
- No API secrets in git or reports.

---

## Provider amendment 001 — Claude (frozen); final batch BLOCKED on credentials

`H4 status: still NOT FULLY TESTED. Final Claude batch not yet run.`

- Provider amendment frozen and pushed **before any Claude call**: FINAL H4 PROVIDER =
  Claude; frozen sample/prompt/Model B/threshold/top-k/schema unchanged.
- Runner is now provider-scoped and refuses to mix providers (Claude → `*_claude.json`).
- **Blocker:** no Anthropic API key is configured (`anthropic_api_key` empty), so the 24
  real Claude calls, the final technical evaluation, the final latency, and the blinded
  human-evaluation package (which needs the 24 Claude texts) cannot be produced yet.

### Exact action required from the maintainer

Add the Anthropic key — either set env var
`ANTHROPIC_API_KEY` or add a line `anthropic_api_key=<key>` to `C:\IDS\.env` (gitignored;
never commit it). Then run:

`IDS_LLM_INTEGRATION=1 python training/phase17d_explain_run.py --provider claude --conditions both --go`

which performs the 24 Claude calls into `explanation_runs_claude.json` /
`technical_evaluation_claude.json` / `latency_claude.json`. After that I finalize the
technical metrics + latency, build the blinded human-evaluation package from the real
Claude texts, run the tests, and report. Real human ratings are then still required before
H4 can be concluded.

---

## Final Claude batch COMPLETE (credential blocker resolved)

`H4 status: PARTIALLY TESTED / NOT FULLY TESTED.` Final report:
[`RESULTS.md`](RESULTS.md). Manual audit: [`MANUAL_AUDIT.md`](MANUAL_AUDIT.md).

- The Anthropic credential blocker is **resolved** (key supplied via environment; never
  committed).
- Final provider **Claude** (`claude-sonnet-5`): **24/24** responses, **0** failed, **0**
  retries, into the provider-scoped `*_claude.json` files (unmodified).

### Automated metrics (as computed; JSON not edited)

| metric | with SHAP | no SHAP |
|---|---|---|
| prediction consistency | 1.0 | 1.0 |
| unsupported-claim-free | 1.0 | 1.0 |
| structural completeness | 0.9167 (11/12) | 1.0 |
| direction consistency | 17/19 = 0.8947 | n/a (SHAP-only) |
| mean evidence coverage | 0.85 | n/a (SHAP-only) |

Latency (explanation layer only): SHAP median **4.55 ms**; LLM median with-SHAP **9924.00
ms**, no-SHAP **10840.04 ms**; total median with-SHAP **9927.93 ms**, no-SHAP **10840.04
ms**. SHAP is not claimed to make Claude faster — the ~0.91 s median gap is provider
generation variability; SHAP itself added ~4.55 ms.

### Manual audit (separate from the automated JSON)

- Direction: the 2 automated inconsistencies (`eval-v1-benign-001#29`,
  `eval-v1-benign-002#85`, both `totlen_fwd_pkts`) are evaluator false positives; texts
  state `decreases_attack` correctly → **manual 19/19**, automated **17/19** unchanged.
- Structural: `eval-v1-benign-003#229` flagged missing uncertainty is a heuristic false
  negative (uncertainty is present); automated **11/12** unchanged. That explanation is
  genuinely truncated at `max_tokens=400`.

### Human evaluation

**Intentionally not conducted.** No raters/ratings/counts fabricated.
`HUMAN_EVAL_QUESTIONNAIRE.md` and `human_eval_ratings_template.csv` are preserved unchanged
as unused protocol artifacts.

### H4

Per the frozen protocol, H4 is **not** "supported" on automated groundedness alone: the
technical-groundedness and latency limbs are evidenced (small n=12, with documented manual
caveats), the human-perception limb is untested by decision. **H4 remains partially tested /
not fully tested** — the final status for this thesis component.
