# PK4 / H4 — SHAP + LLM explanation evaluation protocol (frozen)

Machine-readable twin: [`protocol.json`](protocol.json) (`phase17d-explainability-v1`).
Frozen **before** any explanation quality was inspected. This is an **explainability**
evaluation, not another predictive-model experiment. No new ML model, no retraining, no
threshold/selector/schema change.

## Objective (H4)

Evaluate whether natural-language explanations generated from a frozen IDS decision and
its SHAP evidence are: (1) grounded in the model evidence; (2) factually consistent with
the supplied prediction/features; (3) understandable; (4) useful for interpreting an
alert; (5) generated with acceptable latency.

## Model / explanation path

The alerts are frozen Phase 17D final-test flows. The explained decision is the **frozen
primary Model B** (binary deployment detector) decision. The existing production `/explain`
path (`app/api/predict` → `app/ml/inference.predict`) is tied to **Model A** (multiclass
supervised + anomaly); for the deployment-alert evaluation, a **read-only** Model B SHAP
path was added via the xgboost booster `pred_contribs` (TreeSHAP) — Model B weights,
threshold (0.50), feature schema (`deployment-cicflowmeter-76-v1`) and predictive
behaviour are **unchanged**.

Model A `2b7625fc…` and Model B `c2bb8f00…` re-verified byte-identical.

## SHAP output

TreeSHAP via booster `pred_contribs`; fixed **top-k = 5** (the pre-existing frozen value in
`app/ml/inference.py`, chosen before any explanation quality was seen). Each alert
preserves the base value, the top-5 signed contributions, each feature value, the sign
direction, and the model decision. No post-hoc feature cherry-picking.

## Frozen evidence contract

Each alert's evidence package (`evidence_sample.json`) contains only: `alert_id`,
`source_run`, `flow_index`, `model` identity, `decision`, `attack_probability`,
`shap_base_value`, `top_shap_features` (feature, value, signed contribution, direction),
and an explicit anti-invention `analyst_instruction`. **Ground truth is never in the
evidence package** — it is recorded separately in `sample_manifest.json` for evaluation
only.

## Provider

Primary = **gemini** (`gemini-flash-latest`), the repository's designated default
(`settings.llm_provider`), reused rather than opening a provider competition. Claude
(`claude-sonnet-5`) remains an implementation fallback only. Selection was fixed before any
explanation quality was seen. **Real provider calls have not been run** — they are gated on
approval and API cost (see STATUS).

## Prompt

Reused the existing deployed **v3** template (`app/services/llm_explainer.py`), sha256
`fc6504407d3fabe3ff5afa80b71802d5eb340ceeff81412a4b64b163b32620c9`. It already enforces the
required contract: evidence boundary (the model never saw packets), no invented
IPs/ports/protocols/payloads/tools, model-classification-not-proven-fact, SHAP-is-not-
causal, never override the prediction, confidence framed as model confidence. Deviation:
v3 produces concise prose (3–5 sentences) rather than JSON fields; the recommended
structured fields were not adopted to avoid changing deployed behaviour. Structural
completeness is checked against v3's mandated prose elements.

## Fixed sample (pre-registered)

12 alerts, seed 42 (`sample_manifest.json`): **6 benign false-positive alerts** (sampled
from the 85 benign flows Model B flagged ATTACK) and **6 correctly-detected PortScan attack
alerts** (sampled from the first 2000 selector-matched evaluable flows of
`eval-v1-portscan-001`). Ground truth from manifest selectors, used for evaluation only.
Reusing frozen final-test alerts is legitimate because the predictive models and threshold
are already frozen and no model selection occurs.

## Automated technical groundedness (`app/services/explanation_eval.py`)

Per explanation: prediction consistency, feature grounding, direction consistency,
unsupported-claim detection (reuses the deterministic entity heuristic), evidence coverage,
structural completeness — plus aggregates. These are **not** proof of human usefulness.
Direction consistency abstains on ambiguous prose windows.

## SHAP vs no-SHAP baseline

One controlled comparison (same provider/prompt/sample): condition A = prediction + SHAP
evidence; condition B = prediction only. Runner: `training/phase17d_explain_run.py
--conditions both`. Implemented; pending real calls. Not a prompt-engineering study.

## Latency

SHAP computation (per-alert, recorded in `sample_manifest.json`), LLM generation (per call
in `llm_explainer`), and total (batch runner) — all **separate** from the frozen Model
A/Model B inference-latency measurements.

## Human evaluation

Instrument (`HUMAN_EVAL_QUESTIONNAIRE.md`) + data-entry template
(`human_eval_ratings_template.csv`): 1–5 Likert on clarity, usefulness, evidence support,
conciseness, confidence. **No human results exist yet and none are fabricated.**

## H4 status rule

Technical groundedness and human-perceived clarity/usefulness are reported **separately**.
H4 is never "supported" from fluent text alone. Until real explanations are generated and
real human ratings collected, **H4 remains _not fully tested_** regardless of automated
results.
