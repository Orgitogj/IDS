# PK4 / H4 — Human evaluation of IDS explanations (instrument)

Exploratory instrument for rating natural-language explanations of frozen IDS alerts. It
is a small convenience-sample instrument, **not** a statistically representative study.
No participant is required to give personal or sensitive information.

## How to run it

1. Generate the explanations for the 12 pre-registered alerts (see
   `sample_manifest.json`) with the frozen prompt and primary provider — this needs the
   real-provider batch to have been run (`training/phase17d_explain_run.py --go`), which is
   gated on approval and API cost.
2. For each explanation shown, the rater reads **only** the analyst-facing explanation text
   (and, if desired, the same evidence package the model received). Raters are **not** shown
   the ground-truth label.
3. The rater scores each dimension on a fixed **1–5 Likert scale** and may add a short free
   comment.
4. Enter scores in `human_eval_ratings_template.csv` (one row per rater × alert ×
   condition).

## Likert scale (1–5)

`1 = strongly disagree/very poor · 2 = disagree/poor · 3 = neutral · 4 = agree/good ·
5 = strongly agree/excellent`

## Dimensions (rate each explanation)

| key | statement rated |
|---|---|
| `clarity` | The explanation is clear and easy to read. |
| `usefulness` | The explanation would help me act on this alert. |
| `evidence_support` | The explanation appears supported by the evidence it cites. |
| `conciseness` | The explanation is appropriately concise (no padding, no omissions). |
| `confidence` | After reading it, I feel confident I understand what the alert is about. |

Optional free-text: `comments` (what helped or misled you).

## Blind / comparison notes

- If the SHAP vs no-SHAP comparison is evaluated, present the two conditions for the same
  alert in a randomized order per rater and record the `condition` column; do not tell the
  rater which is which.
- Do not reveal the ground-truth label or which model produced the decision beyond what the
  explanation itself states.

## Scope and honesty rules

- Report the exact number of real raters and real ratings. Never invent a participant count
  or any rating.
- With a small convenience sample, report results **descriptively** (per-dimension medians
  and ranges); do not claim statistical significance or representativeness.
- Human-perceived clarity/usefulness is reported **separately** from the automated technical
  groundedness metrics; neither substitutes for the other.
