# PK4 / H4 — manual audit of automated evaluator findings (Claude batch)

Auditable record of every case where a human reading of the Claude explanation text
differs from the deterministic automated evaluator. **The source JSON metrics are not
altered.** The automated numbers stand as reported; this document records manual
interpretation *alongside* them, never in place of them.

Provider: Claude (`claude-sonnet-5`), 24/24 responses. Evaluator:
`app/services/explanation_eval.py` (`deterministic_technical_groundedness_v1`), whose own
caveat states it is heuristic and not proof of semantic correctness.

## A. Direction-consistency false positives (2)

Automated with-SHAP direction consistency = **17/19 = 0.8947** (unchanged). Both
"inconsistent" claims are **evaluator false positives**; the explanations state the correct
direction.

| alert_id | feature | expected (SHAP sign) | evaluator recorded | manual reading |
|---|---|---|---|---|
| eval-v1-benign-001#29 | totlen_fwd_pkts | decreases_attack (SHAP −) | increases_attack | **decreases_attack** ✓ |
| eval-v1-benign-002#85 | totlen_fwd_pkts | decreases_attack (SHAP −) | increases_attack | **decreases_attack** ✓ |

Evidence from the texts:

- `eval-v1-benign-001#29`: "…totlen_fwd_pkts=2249.00 … **KUNDER klasifikimit ATTACK**, pra
  kane pasur nje …" — explicitly *against* the ATTACK class.
- `eval-v1-benign-002#85`: "totlen_fwd_pkts=2183.00 **ka pasur kontribut negativ (−5.378),
  pra ne fakt e ka tirur pak modelin larg klases ATTACK**" — explicitly a negative
  contribution pulling *away* from ATTACK.

Cause: the evaluator scores a fixed ±90-character window around the feature name with
increase/decrease keyword lists; here other nearby directional words (referring to *other*
features in the same sentence) collided, so the window-based classifier mislabelled the
claim. This is exactly the abstention/ambiguity limitation documented in the evaluator's
`direction_consistency` and caveat.

**Manually audited direction consistency = 19/19.** This is reported **separately** from
the unchanged automated **17/19**; the automated JSON is not edited.

## B. Structural-completeness false negative (1)

Automated with-SHAP structural completeness = **11/12 = 0.9167** (unchanged). The one
flagged case is a **heuristic false negative** for the `uncertainty_or_action` field.

- `eval-v1-benign-003#229` (with_shap): evaluator recorded
  `uncertainty_or_action = False`. The text in fact carries explicit uncertainty:
  "besueshmeri relativisht te ulet, 56.6%", "**nuk duhet trajtuar si diagnoze e sigurt**",
  "Ky eshte thjesht **nje parashikim statistikor** … **jo nje konfirmim i nje incidenti
  real**".
- Cause: the heuristic looks for tokens such as `verifik*`, `analist`, `pasigur`, `kujdes`,
  `rekomand`; this explanation expresses uncertainty with different phrasing, so the token
  match missed it. Manual reading: uncertainty **is** present.

## C. Genuine truncation (not an evaluator error)

The same explanation, `eval-v1-benign-003#229` (with_shap), is **genuinely truncated** at
the end:

> "…jo nje konfirmim i nje incidenti real, k"

This is consistent with the frozen **`max_tokens=400`** generation limit (a real property
of the output, recorded as a limitation — not overridden). The no_shap explanation for the
same alert ends cleanly, so the truncation is specific to the longer with-SHAP text.

## D. What was NOT changed

- The three Claude JSON outputs (`explanation_runs_claude.json`,
  `technical_evaluation_claude.json`, `latency_claude.json`) are **unmodified**.
- The automated metrics (17/19 direction, 11/12 structural) remain the reported automated
  figures. The manual figures (19/19 direction; uncertainty present in benign-003#229) are
  recorded here as a separate, clearly labelled human audit.
- No re-run, no prompt/model/threshold/sample/SHAP change.
