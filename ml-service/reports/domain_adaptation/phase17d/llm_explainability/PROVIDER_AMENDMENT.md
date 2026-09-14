# PK4 / H4 — Provider amendment 001: Claude as sole final provider

Machine-readable twin: [`PROVIDER_AMENDMENT.json`](PROVIDER_AMENDMENT.json). Amends
`phase17d-explainability-v1`. **Frozen before any Claude API call.**

## Decision

**FINAL H4 PROVIDER = Claude.** The final PK4/H4 explainability evaluation uses **Claude
only**, restarting the complete frozen 24-response batch (12 alerts × {with_shap,
no_shap}).

## Reason (operational, not quality-driven)

- Gemini was the pre-registered primary provider.
- The real Gemini batch hit a **hard quota/billing block** (429 RESOURCE_EXHAUSTED) plus
  503s on the resolved `gemini-3.8-flash`.
- **9 of 24** responses were collected; continuing was impossible without a billing/quota
  intervention that is not available.
- The user explicitly chose Claude as the final provider.
- The switch is **operational** (provider availability) — **not** based on any
  explanation-quality comparison.
- The 9 Gemini outputs are **excluded** from the final H4 dataset to avoid mixing provider
  effects.

## Unchanged and reaffirmed

Frozen 12-alert sample and identities · seed 42 · Model A `2b7625fc…` · Model B
`c2bb8f00…` · threshold **0.50** · evidence schema · top-k SHAP **5** · prompt semantic
content (v3, sha256 `fc6504407d3fabe3ff5afa80b71802d5eb340ceeff81412a4b64b163b32620c9`) ·
with-SHAP vs no-SHAP design · automatic evaluation metrics · human-evaluation dimensions ·
the no-ground-truth-leakage rule. The sample was **not** changed after seeing the Gemini
outputs.

## Claude provider freeze

Requested `claude-sonnet-5`; resolved model captured per response (`message.model`);
`max_tokens=400`, temperature unset (provider default); retry policy = 3 retries on
transient errors, 25 s 429-backoff, 8 s inter-call pacing, all logged; anthropic SDK
default timeout; opt-in `IDS_LLM_INTEGRATION=1`.

## No provider mixing

The final Claude batch runs **from zero** into provider-scoped files
(`explanation_runs_claude.json`, `technical_evaluation_claude.json`, `latency_claude.json`).
The runner **refuses to resume** across providers. The Gemini partial artifacts are
preserved and excluded (see `GEMINI_ATTEMPT_EXCLUDED.md`). This thesis is **not** a provider
benchmark; Claude vs Gemini is not reported as a research result.
