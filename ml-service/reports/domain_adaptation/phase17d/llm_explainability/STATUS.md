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

1. **Approve the real-provider batch.** `training/phase17d_explain_run.py --provider gemini
   --conditions both --go` with `IDS_LLM_INTEGRATION=1` → **24** gemini calls (12 alerts ×
   {with_shap, no_shap}). This is a small paid run and needs explicit approval.
2. Run the automated technical evaluation over the generated explanations (the runner does
   this and writes `technical_evaluation.json` + `explanation_runs.json`).
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

## Real batch attempt 1 (INCOMPLETE — provider quota block)

`H4 status: still NOT FULLY TESTED. The pre-registered 24-call batch did not complete.`

- Provider **gemini**, requested `gemini-flash-latest`, **resolved `gemini-3.8-flash`**
  (captured per response). Generation params: provider defaults (no temperature /
  max_output_tokens set) — a non-determinism limitation.
- Outcome: **9 of 24** calls succeeded; **15 failed**; 65 retry attempts. All failures were
  genuine transient provider errors — **429 RESOURCE_EXHAUSTED** ("exceeded your current
  quota, check your plan and billing details") and some **503 UNAVAILABLE** on the
  experimental `gemini-3.8-flash`. Pacing (8 s between calls) + longer 429 backoff (25 s) +
  3 retries did **not** clear it, so this is a **hard quota/billing cap**, not a per-minute
  rate limit.
- Succeeded split (skewed): benign-FP with_shap 4, benign-FP no_shap 3, PortScan-TP
  with_shap 1, PortScan-TP no_shap 1.
- **No responses fabricated. No provider switch. No prompt/model/param change. No
  cherry-picking.** The frozen sample, prompt hash, Model B hash and threshold are
  unchanged. Provisional technical metrics over the 9 responses are recorded but must **not**
  be read as the H4 result — the batch is incomplete and skewed.
- Human-evaluation package preparation is **deferred** until the batch completes (blinding a
  skewed 9/24 set would not be meaningful).

### Exact remaining action (blocked on the maintainer)

1. Resolve the Gemini quota/billing on the configured API key (enable billing / raise quota
   for the flash model), **or** supply a working Gemini key, **or** authorize a Claude key
   for the fallback path. This is an account/billing change I cannot and must not make.
2. Then re-run (resume — preserves the 9 OK responses, re-attempts only the 15 missing):
   `IDS_LLM_INTEGRATION=1 python training/phase17d_explain_run.py --provider gemini --conditions both --go`
3. I then finalize technical metrics + latency over the full 24, prepare the blinded
   human-eval package from the real texts, and report — H4 stays not-fully-tested until real
   human ratings are also collected.

---

## Provider amendment 001 — Claude (frozen); final batch BLOCKED on credentials

`H4 status: still NOT FULLY TESTED. Final Claude batch not yet run.`

- Provider amendment frozen and pushed **before any Claude call**: FINAL H4 PROVIDER =
  Claude; 24-response batch restarts from zero; Gemini's 9 responses preserved and excluded;
  frozen sample/prompt/Model B/threshold/top-k/schema unchanged.
- Runner is now provider-scoped and refuses to mix providers (Claude → `*_claude.json`).
- **Blocker:** no Anthropic API key is configured (`anthropic_api_key` empty), so the 24
  real Claude calls, the final technical evaluation, the final latency, and the blinded
  human-evaluation package (which needs the 24 Claude texts) cannot be produced yet.

### Exact action required from the maintainer

Add the Anthropic key to the same config the Gemini key uses — either set env var
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
  retries, into the provider-scoped `*_claude.json` files (unmodified). Gemini's 9/24
  attempt remains preserved and excluded.

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
