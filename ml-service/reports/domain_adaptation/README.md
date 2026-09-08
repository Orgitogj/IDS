# Deployment-domain adaptation — feasibility and protocol design (Phase 17A)

**Design and feasibility only.** No training, no traffic, no SHAP, no LLM, no PostgreSQL,
no frozen result modified. Model A (`xgb-baseline-cicids2017-v2`) stays permanently frozen;
any adapted model is Model B (`deployment-adapted-v1`), not yet created.

Central question: *can part of the observed deployment generalization gap be reduced when
training and deployment share a consistent feature-extraction environment?*

## Three problems kept distinct

1. **Benchmark generalization** — Model A is strong on the random-v2 split (Macro F1 0.8806).
2. **Feature-extraction implementation mismatch** — Phase 16E: source-verified differences
   between the original Java CICFlowMeter and python `cicflowmeter 0.5.0` (packet-length
   basis, header basis, subflow, flags), aligned with model-important features.
3. **True deployment-domain shift** — different services, ciphers, tooling, network.

Phase 16 findings (not rewritten here): excellent benchmark; near-total lab attack-detection
failure (PortScan 2/1362, SSH 0/69); confirmed seconds-vs-microseconds unit incompatibility
whose correction changed detection by 0 pp; large non-time residual shift; source audit
linking residual shift to extractor implementation differences; empirical Java/Python
same-PCAP parity not quantifiable.

## Strategy feasibility

- **Strategy A (common extractor — re-extract CICIDS2017 with python cfm): IMPRACTICAL NOW.**
  No raw CICIDS2017 PCAPs are local (only the published Java-CICFlowMeter flow CSVs and the
  derived parquet). It would need a ~50 GB official download and solves an unsolved
  flow-level label-transfer problem (python cfm re-segments flows, so original labels do
  not map 1:1). Retained as future work — it is the only route that would *isolate* the
  extractor effect.
- **Strategy B (lab-domain adaptation): PRACTICAL, RECOMMENDED.** Train Model B on lab flows
  extracted with python `cicflowmeter 0.5.0`, evaluate on NEW lab runs extracted the same
  way. Train and deployment share the extractor by construction. It answers the mitigation
  question directly, but fixes extractor-consistency and domain-match together and so cannot
  isolate the extractor effect alone.

**Recommendation: Strategy B primary; Strategy A documented as future work.**

## Primary objective: binary

Primary = **binary BENIGN vs ATTACK**; secondary = family attribution where defensible;
tertiary = exact CICIDS2017 label only when independently justified. PortScan has a
defensible exact mapping; SSH only a family-level (Brute Force) mapping. Ground truth is
never inferred from Model A predictions.

## Recommended architecture: two-stage

**Stage 1** = deployment-adapted binary detector (Model B). **Stage 2** = frozen Model A for
multiclass attribution of flows Stage 1 flags malicious. This keeps Model A frozen (no
catastrophic forgetting, full comparability), matches the lab's binary ground truth, runs
Stage 2 only on flagged flows (latency), and reports detection and attribution separately.

## Model B options

Recommended: **Option E (two-stage)** with **Option A binary XGBoost** as the Stage-1
detector and **Option B binary Random Forest** as a robustness check. Rejected: Option C
(fine-tune Model A — catastrophic forgetting, unfair comparison), Option D (common-extractor
retrain — needs Strategy A). Details in `model_b_options.json`.

## Run partition (run-level separation)

`run_plan.json` proposes, all run-level separated (never random flow splits):

- **Adaptation (12 runs):** the 3 existing accepted runs reused as adaptation only, plus
  new `adapt-v1-{benign,portscan,ssh}-{002..004}`.
- **Final test (9 runs, post-freeze):** new `eval-v1-{benign,portscan,ssh}-{001..003}`,
  generated only after Model B is frozen.

Validated by `training/pipeline/domain_adaptation.py`: unique IDs, no run shared across
roles, final-test runs flagged post-freeze, no historical Model-A run used as Model-B test.

## Existing 5407 / 1362 / 69 flows

Role decision: **adaptation data for Model B** (their Model A results stay frozen historical
evidence). They may never simultaneously be final unseen Model-B test evidence. SSH's 69
flows are too few to split, so used whole for adaptation; calibration draws from a validation
slice of adaptation, never final test.

## Replication

≥3 adaptation and ≥3 final-test runs per scenario, across different sessions/time windows,
no prediction-driven repetition. Final results report run-level mean/median/range/std, not a
single pooled number. Minimum eval support: benign 300, portscan 300, ssh 30 valid flows.

## Balancing

Adaptation/training only; never the test distribution. Primary = **class weights**
(`scale_pos_weight`); comparison = controlled benign undersampling; SMOTE only if
independently justified (random-v2 showed SMOTE is not universally beneficial).

## Evaluation (pre-registered)

Primary: attack detection rate/recall, benign FPR (same definition as random-v2 / temporal /
lofo / live), binary Macro F1. Secondary: precision, accuracy, per-run detection, confidence,
family attribution. Every rate reports its denominator. **Paired same-flow comparison is
mandatory:** each eval run → one capture → same extraction → Model A and Model B predictions
on identical flows. Model B is not required to "win", only to be measured fairly. Thresholds
fixed before viewing final results.

## Calibration / OOD (design only)

Optional reliability track (SSH predicted BENIGN at confidence ~1.0): probability
calibration, OOD score, UNKNOWN/SUSPICIOUS state, existing Isolation Forest — learned only
from adaptation/validation, kept separate from primary supervised detection, no silent
threshold changes.

## Leakage guards

Enumerated in `leakage_guards.json` and enforced by the validator + tests: run-level
separation, unique IDs, no adaptation run in test, no test labels/thresholds/scalers in
tuning, no prediction-based deletion, no silent overwrite, model/schema/extractor pinning.

## Reproducibility

Pins in `reproducibility.json`: extractor version, feature schema, model hashes, seeds,
manifests, capture hashes, model cards, environment versions.

## Threats to validity

See `threats_to_validity.md` (small lab, old services, single topology, python extractor,
limited families, run dependence, adaptation overfitting, unquantified Java/Python parity,
binary/family ground truth).

## Albanian methodology subsection

*Faza 17A është vetëm projektim dhe studim fizibiliteti; nuk trajnohet model dhe nuk
gjenerohet trafik. Modeli A (`xgb-baseline-cicids2017-v2`) mbetet përgjithmonë i ngrirë;
modeli i adaptuar do të jetë Modeli B (`deployment-adapted-v1`). Pyetja qendrore: a mund të
zvogëlohet një pjesë e hendekut të gjeneralizimit të vendosjes kur trajnimi dhe vendosja
ndajnë të njëjtin mjedis nxjerrjeje veçorish? Strategjia A (rinxjerrje e CICIDS2017 me
python cicflowmeter) është e parealizueshme tani sepse PCAP-të origjinale nuk janë lokale
(~50 GB) dhe transferimi i etiketave mbi flukse të ri-segmentuara është i pazgjidhur;
mbahet si punë e ardhshme. Strategjia B (adaptim në domenin laboratorik) është praktike dhe
rekomandohet: Modeli B trajnohet mbi flukse laboratorike të nxjerra me python cicflowmeter
0.5.0 dhe vlerësohet mbi ekzekutime laboratorike TË REJA të nxjerra në të njëjtën mënyrë,
kështu që trajnimi dhe vendosja ndajnë ekstraktuesin nga vetë ndërtimi. Objektivi primar
është binar (BENIGN kundrejt ATTACK), me atribuim familjeje si dytësor. Arkitektura e
rekomanduar është dy-fazëshe: një detektor binar i adaptuar (Faza 1) plus Modeli A i ngrirë
për atribuim (Faza 2), çka eliminon harresën katastrofike dhe ruan krahasueshmërinë. Ndarja
është vetëm në nivel ekzekutimi (asnjë ndarje e rastësishme fluksesh), me ≥3 ekzekutime
adaptimi dhe ≥3 vlerësimi për skenar, dhe krahasim i çiftëzuar Model A vs Model B mbi
pikërisht të njëjtat flukse të reja. Kufizim kryesor: Strategjia B ndreq njëkohësisht
konsistencën e ekstraktuesit dhe përputhjen e domenit, prandaj nuk e izolon dot efektin e
ekstraktuesit; pariteti empirik Java/Python mbi të njëjtin PCAP mbetet i pamatur.*

## Artifacts

`feasibility.json`, `strategy_comparison.csv`, `data_split_protocol.json`, `run_plan.json`,
`model_b_options.json`, `evaluation_protocol.json`, `leakage_guards.json`,
`calibration_ood.json`, `reproducibility.json`, `threats_to_validity.md`. No model, no
training, no traffic.
