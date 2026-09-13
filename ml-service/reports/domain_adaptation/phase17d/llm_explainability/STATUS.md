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
