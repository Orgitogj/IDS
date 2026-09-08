# SSH brute-force feature-distribution shift audit (diagnostic only)

**Phase 16 Part 2C-D1.** Diagnostic only. It does not modify any experiment result, does
not retrain, tune, change thresholds, or the frozen model, and invokes neither SHAP nor an
LLM. It asks:

> Is the complete 78-feature distribution of the laboratory SSH brute-force traffic
> **consistent with** a feature/domain/implementation shift relative to the relevant
> canonical CICIDS2017 SSH traffic?

It **cannot establish causality** and does not attempt to.

## Sources

| | rows | provenance |
|---|---:|---|
| Canonical SSH-Patator (primary) | 1,180 | true `SSH-Patator` rows from the frozen random-v2 test partition |
| Canonical Brute Force (secondary) | 2,767 | `SSH-Patator` + `FTP-Patator`, reported separately |
| Laboratory SSH (this run) | 69 | selector-matched ATTACK flows (`.10→.20:22`) from `lab-v1-ssh-bruteforce-001` |

Excluded exactly as required: the 1 UNLABELLED reverse flow, the aborted setup attempt
(see below), PortScan/benign/smoke flows, all training and synthetic data. Both matrices
use the frozen 78-feature schema `cicids2017-78-v1`.

**Ground-truth note.** The laboratory ground truth is **family-level Brute Force**.
SSH-Patator is used here only as the relevant canonical *reference distribution* because
the scenario targets SSH; it is **not** treated as exact-label ground truth.

## Semantic / unit provenance audit (done before interpreting shift)

The lightweight check reported extreme differences (Flow Duration ≈ 1.06e7 vs ≈ 2). The
audit shows these are not all ordinary drift:

- **13 time features carry a unit-convention mismatch** (`UNIT_MISMATCH_SUSPECTED`): Flow
  Duration and every Flow/Fwd/Bwd IAT feature. Canonical CICFlowMeter expresses these in
  **microseconds** (canonical Flow Duration max ≈ 1.2e8 = the 120-second flow timeout);
  the laboratory `cicflowmeter 0.5.0` emits them in **seconds** (lab Flow Duration
  ≈ 1.5–2.2 for ~2-second auth attempts). The canonical/lab median ratios are ≈ 1e6–5e6,
  compatible with a microseconds-vs-seconds convention. The repository's own derivation
  helper `_per_second(count, duration_us)` divides by `duration_us / 1e6`, i.e. it assumes
  microseconds — but Flow Duration is a *directly mapped* feature, so the seconds-scale
  value reaches the model unconverted. This is a **feature-extraction implementation
  difference**, not evidence that either tool is wrong.
- **16 features** (rates, flags) are `POSSIBLE_IMPLEMENTATION_DIFFERENCE`: per-time rates
  depend on each tool's internal duration convention; flag counts (e.g. PSH Flag Count,
  canonical median 1 vs lab 15) may reflect different counting/segmentation.
- **43 features** are `LIKELY_SAME` semantics (byte counts, packet counts, lengths). Where
  these shift — e.g. Fwd Packet Length Mean 87 → 242, Average Packet Size 85 → 238 — the
  difference is more compatible with genuine content/configuration differences (the lab
  used a legacy `aes128-cbc` / `hmac-sha1` SSH configuration against OpenSSH 4.7) than with
  a unit artifact.
- **6 features** (bulk-rate) are `SEMANTICS_UNRESOLVED` (aggregation not verified locally).

Full per-feature classification in `semantic_audit.csv`.

## 78-feature shift statistics (primary, vs SSH-Patator)

- Comparable (non-constant) features: **53**; constant/non-comparable: 25.
- **Median KS = 0.9983**; p75 KS = 1.0; max KS = 1.0.
- KS ≥ 0.3: 50; **KS ≥ 0.5: 49**; **KS ≥ 0.8: 30**.
- ≥ 50 % of lab values outside canonical p01–p99: 34 features; 100 % outside: 27.

Secondary (vs SSH-Patator + FTP-Patator): median KS = 0.9951, KS ≥ 0.8 = 29 of 54 — the
same picture.

Top-15 shifted features and full table in `top_shifted_features.csv` / `feature_shift.csv`.

## Model-relevant features

Using the frozen XGBoost `feature_importances_` (no SHAP), **12 of the top 15 important
features are substantially shifted** (KS ≥ 0.5), the same definition used for PortScan.

- The single most-important feature, **Idle Mean** (imp 0.239), is constant (0/0) and
  **not** shifted — as in PortScan.
- Unlike PortScan, the second feature, **Bwd Packet Length Std** (imp 0.123), *is* shifted
  here (KS 0.998). SSH shifts more of the model's important signals than PortScan did.
- PSH Flag Count (imp 0.109, KS 1.0) is flagged as a possible implementation difference.

Detail in `model_relevant_shift.csv`.

## Confidently-missed-flow context

All 69 laboratory SSH flows were predicted BENIGN, so there is no detected-vs-missed
split. Prediction confidence is min 0.99995, median 0.99996 — the model is **confident,
not uncertain**. Several top model-important features place the lab flows **entirely
outside** the canonical SSH-Patator p01–p99 band: Bwd Packet Length Std, PSH Flag Count,
Average Packet Size, Bwd Packet Length Mean, Max Packet Length (each 100 % outside). The
confidently-missed flows sit outside canonical SSH regions on multiple model-relevant
features. This is descriptive; no causal mechanism is asserted.

## Cross-scenario comparison

| | PortScan | SSH |
|---|---|---|
| detection rate | 0.00147 | **0.0** |
| canonical support | 31,761 | 1,180 |
| lab support | 1,362 | 69 |
| median KS | 0.7118 | **0.9983** |
| features KS ≥ 0.8 | 24 | 30 |
| top-15 important shifted | 11 | 12 |

Classification: **CONSISTENT_CROSS_SCENARIO_SHIFT** — both scenarios show a large,
model-relevant distribution shift alongside near-total detection failure of a family the
model performs well on in the CIC-tool benchmark. SSH shifts more strongly than PortScan.

## Conclusion

**A — Strong evidence consistent with feature/domain shift.** Support: median KS 0.998,
30 near-disjoint features, 27 features with the whole lab population outside the canonical
p01–p99 band, and 12 of 15 top model-important features shifted, with every flow
confidently misclassified as BENIGN while sitting outside canonical SSH regions on
multiple important features.

**Two shift components coexist and this experiment cannot separate them:**

1. **Feature-extraction implementation shift** — the 13 time features carry a
   microseconds-vs-seconds unit convention difference between the canonical CICFlowMeter
   and `cicflowmeter 0.5.0`.
2. **Dataset domain shift** — genuine content differences in packet-size and flag features
   (LIKELY_SAME semantics) reflecting a different SSH stack, cipher/MAC configuration, and
   traffic-generation tool than CICIDS2017 used.

Both are present; the diagnostic is descriptive and does not attribute the detection
failure to either cause alone. It does not claim either tool is wrong.

## Thesis-safe interpretation (Albanian)

*Analiza diagnostikuese tregon se shpërndarja 78-dimensionale e veçorive për trafikun
laboratorik SSH brute-force ndryshon fuqishëm nga trafiku kanonik SSH-Patator i
CICIDS2017: KS-ja mesatare është 0.998, 30 veçori kanë shpërndarje thuajse të shkëputura,
dhe 12 nga 15 veçoritë më të rëndësishme për modelin janë të zhvendosura, ndërkohë që të
69 fluksat u klasifikuan me besim të lartë si BENIGN. Auditimi semantik dallon dy
komponentë që bashkëjetojnë: një **ndryshim implementimi në nxjerrjen e veçorive** (13
veçori kohore në mikrosekonda te dataset-i kanonik kundrejt sekondave te cicflowmeter
0.5.0) dhe një **zhvendosje domeni të dataset-it** (madhësi paketash dhe flamuj që
pasqyrojnë një konfigurim tjetër SSH dhe një mjet tjetër gjenerimi trafiku). Kjo dëshmi
është **në përputhje me** një hendek gjeneralizimi domeni/implementimi, por analiza nuk
provon shkakësi dhe nuk pretendon se ndonjë mjet është "i gabuar"; të dy komponentët nuk
mund të ndahen me këtë eksperiment.*

## Setup / aborted attempt note

An initial SSH generation loop stopped at **59/72** attempts because the `ssh` client
consumed the password-file lines from the loop's standard input (a shell FD bug, not an
IDS-driven change). Informational identifier: **setup-attempt-ssh-001**. It:

- was a setup/aborted attempt, **not** a thesis run;
- produced **no** thesis ledger metric;
- was identified and discarded **before** any model prediction was evaluated;
- had its capture and attempts log **retained** on the Kali guest under
  `/home/kali/live_agent/archive/ssh_attempt1_*`;
- was followed by the accepted clean 72-attempt run only after the FD bug was fixed
  (`3<`/`4<` dedicated descriptors and `ssh </dev/null`).

The accepted run `lab-v1-ssh-bruteforce-001` is unchanged by this note.

## Outputs

`summary.json`, `feature_shift.csv` (all 78), `top_shifted_features.csv`,
`model_relevant_shift.csv`, `semantic_audit.csv`, `cross_scenario_comparison.json`.
