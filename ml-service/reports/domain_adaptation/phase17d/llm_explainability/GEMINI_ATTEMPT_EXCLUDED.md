# Gemini batch — INCOMPLETE_PROVIDER_ATTEMPT / EXCLUDED_FROM_FINAL_H4_ANALYSIS

The Gemini explanation batch is **preserved for provenance** and **excluded from the final
H4 analysis**. Do not delete it; do not mix it with the Claude final dataset.

- Provider: gemini, requested `gemini-flash-latest`, resolved `gemini-3.8-flash`.
- Intended **24**, obtained **9**, missing **15** (hard quota/billing block: 429
  RESOURCE_EXHAUSTED, plus some 503 UNAVAILABLE).
- A pre-scoring provider amendment ([`PROVIDER_AMENDMENT.md`](PROVIDER_AMENDMENT.md))
  switched the final provider to Claude for operational reasons only.
- **No Gemini output is used in the final Claude H4 evaluation.**

Preserved Gemini artifacts (unchanged):

- `explanation_runs.json` — 24 records, 9 ok / 15 failed (provider gemini)
- `technical_evaluation.json` — provisional metrics over the 9 (not the H4 result)
- `latency.json` — Gemini latency (excluded from final)
- `batch_config.json` — Gemini batch config and failure status

Final H4 artifacts are the Claude-scoped files (`*_claude.json`).

> This is not a Claude-vs-Gemini comparison. The thesis is not a provider benchmark; the
> Gemini attempt is documented only to explain why the final provider is Claude.
