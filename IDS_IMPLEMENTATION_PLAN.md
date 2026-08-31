# IDS_IMPLEMENTATION_PLAN.md

Companion to `IDS_ARCHITECTURE_AUDIT.md`. Every item traces back to a limitation
(`L1`–`L17`) recorded there.

**Priorities**

| | Meaning |
|---|---|
| **P0 — Critical** | The system is not technically defensible without it. Implement first, in order. |
| **P1 — High** | Required for the thesis claims (hybrid detection, correlation, feedback, drift). |
| **P2 — Medium** | Rigour, reproducibility, coverage, dashboard surface. |
| **P3 — Optional** | Packaging and polish. |

**Ground rules carried into every package** — reuse existing layers, no rewrite; no new
dependency without a stated reason; the dataset-replay path must keep working after each
package; each package ends with a green test run.

---

## P0 — Critical  — **COMPLETE (2026-08-30)**

All four packages are implemented and verified. Cross-stack state at completion:
**177 tests passing** (144 Python + 33 Java), replay dry-run unchanged at 100 flows /
30 attacks / 0 errors, Angular `tsc --noEmit` clean, backend `mvn -o test` green against
the migrated database. The next package is **P1-1**.

### P0-1 · Measure what CICFlowMeter actually produces  *(L2, L3 — Phase 1)* — **DONE**

> **Status 2026-08-30:** tooling built, verified and committed. The compatibility matrix is
> generated and complete on the training side; the 70 non-constant features are marked
> `PENDING_CAPTURE` until the CICFlowMeter CSV arrives, at which point re-running the probe
> fills them in with no code change. Delivered:
>
> * `ml-service/training/build_feature_reference.py` → `reports/training_feature_reference.json`
>   (78 features × 101-point quantile grid, dataset sha256, label distribution, all 5 feature sets)
> * `ml-service/app/replay/feature_mapping.py` — the name map, extracted from `live_agent.py`
>   so the agent and the probe cannot drift apart (pure refactor, agent behaviour unchanged;
>   standalone import on the capture host still works)
> * `ml-service/app/replay/feature_derivation.py` — 15 derivation rules
> * `ml-service/training/verify_derivations.py` → `reports/derivation_verification.json`
>   (regression gate: exits non-zero if a rule degrades)
> * `ml-service/app/replay/feature_probe.py` → `reports/live_feature_profile.json` + `FEATURE_COMPATIBILITY.md`
>
> **Findings.** 8 features are constant zero across all 2,827,876 rows → zero-fill is exact,
> none of them in the top-50 set. **15 further features are reconstructable from other
> columns** with rates verified against 100 k real rows (9 of the 15 are in the top-50 set;
> 10 rules are exact on 100 % of rows). `Average Packet Size` is **not** derivable — its
> implied denominator is fractional against the packet counts (40.9 % agreement), so it is
> documented as a limitation rather than approximated. Net effect: of the 50 active
> features, a capture would have to lose a feature that is neither constant-zero nor
> derivable before the live path is genuinely blocked.

#### Original scope (for reference)


Everything else in Phase 1 is guesswork until this exists. The audit established that the
name map in `live_agent.py` is *complete* (78/78) — so the real question is what the
deployed CICFlowMeter emits, in what units, and how often values are absent, empty,
non-numeric or infinite.

**Deliverables**

* `ml-service/app/replay/feature_probe.py` — offline tool. Input: a CSV produced by the
  capture host's CICFlowMeter. Output: `reports/live_feature_profile.json` +
  a printed compatibility matrix with one row per training feature:

  ```
  Feature                 Training  Live  Mapping  Live-null%  Live-inf%  Verdict
  ----------------------------------------------------------------------------------
  Flow Duration           YES       YES   exact    0.0         0.0        OK
  Bwd Avg Bulk Rate       YES       YES   exact    0.0         0.0        CONST-ZERO-OK
  Init_Win_bytes_backward YES       NO    —        100.0       —          MISSING
  ```

* `ml-service/reports/training_feature_reference.json` — per-feature reference statistics
  computed from `cicids2017_cleaned.parquet` (n, mean, std, min, p1, p25, p50, p75, p99,
  max, zero-fraction, nunique). Generated once, committed. This artifact is reused
  verbatim by P1-4 (drift) and P0-2 (range validation), so it is built here, not later.

* `FEATURE_COMPATIBILITY.md` — the filled-in matrix plus, for each feature that turns out
  to be absent or semantically different, the four-way verdict the brief asks for:
  *available under another name* / *derivable from other CICFlowMeter fields* /
  *zero is mathematically valid* / *cannot be obtained → documented limitation*.

**Already decided by evidence, before the probe runs**

* The 8 features constant-zero across all 2.83 M training rows
  (`Bwd PSH Flags`, `Bwd URG Flags`, and the 6 bulk features) → **zero-fill is exact**,
  and none of them is in the top-50 live feature set. These are whitelisted as
  `CONST_ZERO_OK` and produce an *info*, never a warning.
* Everything else → zero-fill is a **decision that must be recorded**, never a silent default.

**Requires from you:** one CSV from a real CICFlowMeter capture run on the Linux host
(any traffic, a few hundred flows is enough). Without it the matrix ships with the
70 remaining features marked `UNVERIFIED` and honestly labelled as such.

**Explicitly not done here:** no retraining. If the probe shows a feature is genuinely
unobtainable, the answer is a documented limitation plus (if it is in the top-50 set) a
recommendation to move the live path to a feature set that is fully observable — a
proposal to you, not an autonomous retrain.

---

### P0-2 · Feature validation layer  *(L2, L3 — Phase 2)* — **DONE**

> **Status 2026-08-30:** built, wired into every inference entry point, and verified.
> `ml-service/app/ml/feature_validation.py` is the single validator; nothing reaches a
> model without passing through it. All three silent zero-fill sites are gone
> (`inference.py:46`, `live_agent.py:133`, `live_agent.py:135`).
>
> **Resolution order for a feature that is absent or unusable:** use the sensor value →
> else reconstruct it with a P0-1 verified derivation rule → else zero-fill *only* if the
> feature is one of the 8 proven constant-zero → else reject the flow. Every step is
> recorded in the result; none of them is silent.
>
> **Behaviour changes.** `/api/predict` and `/api/explain` now return **422** with the
> structured validation object instead of a confident prediction on garbage input —
> `/api/explain` rejects *before* calling any LLM, so bad input no longer costs money.
> `PredictionRequest.feature_vector` was loosened from `dict[str, float]` to
> `dict[str, Any]` so malformed values produce our structured error rather than a generic
> Pydantic one. The live agent skips rejected flows and prints a rejection rate on exit.
> Present-but-`null` is reported as `invalid/null`, distinct from an absent key, because
> P1-4 needs to tell a broken sensor field from a missing column.
>
> **Verified.** Replay dry-run unchanged before and after (100 flows, 30 attacks, 0 errors,
> three consecutive runs). Validator exercised across all branches: clean vector, dropped
> derivable feature, dropped non-derivable feature, NaN, ±inf (both recoverable and not),
> non-numeric, null, empty vector, out-of-range. Live-agent path run end to end against a
> 200-flow synthetic capture: 192 accepted, 8 rejected (5 × unrecoverable `inf`,
> 3 × empty non-derivable), and **3 flows rescued by derivation** that the old code would
> have silently zero-filled. Capture-host standalone layout re-verified with the four
> files copied flat.

#### Original scope (for reference)


A single validator shared by *every* inference entry point. Nothing may reach a model
without passing through it.

```
raw mapping → FeatureValidator.validate() → ordered vector → model
                        │
                        └── FeatureValidationResult (structured, never silent)
```

**New:** `ml-service/app/ml/feature_validation.py`

```python
{
  "valid": false,
  "feature_version": "cicids2017-78-v1",
  "missing_features": ["Init_Win_bytes_backward"],
  "zero_filled_features": ["Bwd Avg Bulk Rate"],     # CONST_ZERO_OK, informational
  "invalid_features": [{"feature": "Flow Bytes/s", "reason": "inf"}],
  "out_of_range_features": [{"feature": "Flow Duration", "value": 9.9e12, "p99": 1.2e8}],
  "warnings": ["Feature cannot be generated from CICFlowMeter: Init_Win_bytes_backward"]
}
```

Checks, in order: expected names present · unexpected names · numeric type ·
`None`/empty → *not* 0.0 · `NaN` · `±inf` (reject — training contained none, verified) ·
range vs. the p1/p99 reference from P0-1 (warn, never reject) · final ordering to
`feature_names_in_`.

**Policy — decided 2026-08-30: the live path rejects.** A rejected flow raises no alarm,
increments a per-reason counter, and that counter is consumed by P1-4 as a health/drift
signal, so a silently degrading sensor becomes visible instead of producing zero-filled
predictions.

| Condition | Live path | Replay path |
|---|---|---|
| `CONST_ZERO_OK` feature absent | zero-fill + info | n/a (all 78 present) |
| Any other feature absent | **reject**, `422`, no alarm | reject |
| NaN / ±inf | **reject** | reject |
| Out of p1–p99 range | accept + warn, warning rides along on the detection | accept + warn |

**Touches:** `inference.py` (replace `feature_vector.get(col, 0.0)` on line 46),
`live_agent.py` (replace both zero-fill branches), `predict.py` (return `422` +
the validation object on failure). `cicids_replay.py` needs no change — it supplies all
78 features from the parquet, so it passes validation unchanged. **A regression test
asserting exactly that is part of this package.**

---

### P0-3 · Model identity, versioning and traceability  *(L1 — Phases 3 & 5)* — **DONE**

> **Status 2026-08-30:** implemented and verified end to end against a live
> Postgres + Spring Boot + ML-service stack. `V5__model_traceability.sql` applied cleanly
> to the existing dev database (Flyway v4 → v5, 1 migration, 107 ms), and
> `xgb-smote-top50features-v1` is now the active model.
>
> **Delivered.** Backend: `V5` migration, `DetectionMethod` enum, `version`/`featureVersion`
> on `MLModel`, six traceability columns on `NetworkFlow`, `GET /api/models/active`,
> ingest DTO/response carrying model identity, and an unknown-`modelId` guard that returns
> 400 instead of a FK 500. ML service: `app/ml/model_registry.py` (Spring-backed, **no DB
> access**), `inference.py` rebuilt around a `LoadedModel` cache (max 4, active pinned),
> `GET /api/models/active` + `POST /api/models/reload`, and `model_id` targeting on
> `/api/predict` and `/api/explain`. The replay and the live agent both stamp every
> detection with the model that produced it; the agent additionally compares its local
> artifact against the registry's active model and **warns loudly on mismatch** — the exact
> L1 defect.
>
> **Verified.** Role matrix: SERVICE gets 200 on `/api/models/active` and `/api/models/{id}`,
> 403 on the model list and on activate; anonymous 403. A 20-flow live replay wrote 20 fully
> traceable rows (`model_name`, `model_version`, `feature_version=cicids2017-top50-v1`,
> `detection_method=SUPERVISED_ML`, FK resolving) while all **132 pre-existing rows kept
> NULL model columns** — history untouched, as decided. `model_id` targeting proven to load
> genuinely different artifacts: the same feature vector returns SHAP top feature
> `min_seg_size_forward` under the 50- and 78-feature models but `Bwd Packets/s` under the
> 10-feature model. Unknown `model_id` → 404. Registry unreachable → falls back to
> `settings.fallback_model_file`, marks `registry_source=fallback` with a null `model_id`,
> and keeps predicting. Replay dry-run unchanged (100 flows, 30 attacks, 0 errors). Angular
> `tsc --noEmit` clean; backend compiles.
>
> **Deferred deliberately.** `predictionConfidence` stays `@NotNull` — nothing emits a
> null-confidence detection until the anomaly path lands, so P1-1 relaxes it together with
> the producer rather than adding an unused nullable path now. `ml_models.feature_version`
> is left NULL for pre-existing rows; the ML service resolves it from the artifact's own
> `feature_names_in_` against the training reference, which is ground truth rather than a
> guess from the free-text `feature_set` column.

#### Original scope (for reference)


Kill the hardcoded artifact and make every prediction attributable.

**Configuration flow (no DB access from the ML service)**

```
Spring  GET /api/models/active   ──►  ml-service  ──►  loads that artifact
        (ml_models.active = true)     caches it       reports its identity back
```

The ML service asks Spring at startup and on an explicit `POST /api/models/reload`
(ADMIN-triggered through Spring). It never opens a JDBC connection. If Spring is
unreachable at startup it falls back to `settings.default_model_name` and says so loudly
in `/health`.

**New backend endpoint:** `GET /api/models/active` (ANALYST, ADMIN, SERVICE).

**Schema — `V5__model_traceability.sql`**

```sql
ALTER TABLE ml_models
  ADD COLUMN version         VARCHAR(50)  NOT NULL DEFAULT '1.0',
  ADD COLUMN feature_version VARCHAR(50);

ALTER TABLE network_flows
  ADD COLUMN model_id         UUID REFERENCES ml_models(id),
  ADD COLUMN model_name       VARCHAR(150),
  ADD COLUMN model_version    VARCHAR(50),
  ADD COLUMN feature_version  VARCHAR(50),
  ADD COLUMN detection_method VARCHAR(30),
  ADD COLUMN anomaly_score    DOUBLE PRECISION;

CREATE INDEX idx_network_flows_created_at ON network_flows (created_at DESC);
```

`detection_method` and `anomaly_score` are added here (nullable) so P1-1 does not need a
second migration; they stay `SUPERVISED_ML` / `NULL` until then.

**Detection payload — the contract from Phase 5**

```json
{
  "prediction": "PortScan",
  "confidence": 0.96,
  "detectionMethod": "SUPERVISED_ML",
  "anomalyScore": null,
  "modelId": "xgb-smote-top50features-v1",
  "modelVersion": "1.0",
  "featureVersion": "cicids2017-top50-v1"
}
```

`confidence` is documented — in the API, in the DTO and in the dashboard tooltip — as
*"model class posterior, not a probability that this traffic is malicious"*. The severity
mapping keeps using it (unchanged behaviour) but stops being labelled "confidence" in the
analyst-facing UI.

**Also fixes L1's worst symptom:** the dashboard's SHAP call will resolve the same model
that produced the alarm, because `/api/predict` will accept the flow's `modelName` and
`inference.py` will keep a small LRU of loaded artifacts.

**History is left untouched** (decided). Existing `network_flows` rows keep `NULL` model
columns — no backfill, no inferred attribution. The dashboard renders those as
*"model not recorded"*, so pre-P0-3 detections are visibly distinguishable from traceable
ones instead of being retro-labelled with a model that may not have produced them.

**Decided:** the active model is **`xgb-smote-top50features-v1`** (`feature_version`
`cicids2017-top50-v1`). `xgb-smote-cicids2017-v1` stays registered as an inactive
78-feature baseline for the thesis comparison but is no longer loaded at runtime. This
also collapses the two inference paths onto one artifact, which is the direct fix for L1.

---

### P0-4 · Tests for everything P0 introduces  *(L16 — Phase 15, first slice)* — **DONE**

> **Status 2026-08-30:** **177 tests, all passing** — 144 Python (pytest, 25 s) and
> 33 Java (Maven Surefire). Up from 2 trivial tests before P0.
>
> **Python** (`ml-service/tests/`, driven by `pytest.ini` with `artifacts`/`dataset`
> markers so the suite degrades to skips rather than errors when the model artifacts or
> the 363 MB parquet are absent):
> `test_feature_mapping.py` (16) · `test_feature_derivation.py` (29) ·
> `test_feature_validation.py` (41) · `test_model_registry.py` (12) ·
> `test_inference.py` (20) · `test_predict_api.py` (18) · `test_replay_regression.py` (8).
>
> **Java** (`backend/src/test/java/`): `JwtServiceTest` (7 — round trip, expiry,
> wrong-key forgery, tampering, garbage) · `AlarmIngestControllerTest` (10 — the full role
> matrix plus malformed body, unknown enum, unknown model, and a legacy payload with no
> model identity) · `MLModelControllerTest` (15 — who may read the active model, resolve
> one by id, list, activate, and register). Both use `@WebMvcTest` + `@Import(SecurityConfig…)`
> so the real filter chain and `@PreAuthorize` rules are exercised, not mocked away.
> The pre-existing `IdsmlApplicationTests.contextLoads()` still passes against the migrated
> database, which is what confirms the V5 schema and the JPA entities agree under
> `ddl-auto: validate`.
>
> **Two real defects in P0-3 were found and fixed by these tests:**
> 1. `_evict_if_needed()` abandoned eviction entirely whenever the oldest cache entry was
>    the active model, so the model cache grew without bound. It now skips the active key
>    and keeps evicting.
> 2. `fetch_active_identity()` parsed the registry response *outside* its `try`, so a
>    malformed `/api/models/active` body raised `KeyError` out of startup instead of
>    falling back. The parse moved inside, and `TypeError` joined the caught set.
>
> **Note on Maven:** running tests needed `surefire-junit-platform`, which had never been
> downloaded into `~/.m2` — the suite had never been run through Maven. It is cached now,
> so `mvn -o test` works offline going forward.

#### Original scope (for reference)


`ml-service/tests/` (pytest, already a declared dependency):
`test_feature_mapping.py`, `test_feature_validation.py`, `test_inference.py`,
`test_model_registry_client.py`, plus `test_replay_regression.py` asserting the parquet
path still produces a valid 78-feature vector and an unchanged prediction for a fixed
sample.

`backend/src/test/java/...`: `AlarmIngestControllerTest` (role matrix: SERVICE 201,
ANALYST 403, anonymous 401, malformed body 400) and `JwtServiceTest`. `@WebMvcTest` +
`@MockBean` — no new dependency, `spring-boot-starter-test` is already present.

---

## P1 — High

### P1-1 · Hybrid detection: XGBoost + Isolation Forest  *(L9 — Phase 4)* — **DONE**

> **Status 2026-08-31:** evaluated first, then wired. Full write-up in **`EVALUATION.md`**;
> raw results in `reports/isolation_forest_evaluation.json` and
> `reports/leave_one_family_out.json`.
>
> **Step 1 — the leak, quantified.** The registered v1 detector used
> `contamination = 0.19681`, the *test-set* attack rate. Reproduced exactly (recall 0.4665,
> precision 0.3670 — matching the notebook to four decimals) and shown to flag **19.7 % of
> all benign traffic**. Replaced with a leak-free protocol: fit on BENIGN training rows
> only (1,453,644), threshold from a held-out BENIGN calibration split (363,411). No attack
> row and no test row touches the model or the threshold.
>
> **Step 2 — leave-one-family-out.** XGBoost retrained from scratch 11 times, once per
> family, with that family entirely removed. The result is decisive and **narrow**: the
> detector recovers 32.4 % of unseen DoS Hulk at a 1 % benign flag rate (52.7 % at 2 %) and
> **0.0 % of unseen PortScan, FTP-Patator and SSH-Patator** — families the supervised model
> calls BENIGN 99–100 % of the time when unseen. `EVALUATION.md` therefore states the claim
> as *unknown/anomalous traffic detection with coverage demonstrated only for DoS-class
> flows*, and explicitly refuses the "zero-day" framing.
>
> **Step 3 — decision engine.** `app/ml/detection_engine.py`: a named attack stays
> `KNOWN_ATTACK/SUPERVISED_ML`; supervised-BENIGN + anomalous becomes
> `SUSPICIOUS/ANOMALY_DETECTION` with `prediction=UNKNOWN` and `confidence=null`. The
> anomaly branch can only *add* a suspicion — it can never override, downgrade or relabel a
> supervised verdict, and an unavailable detector never blocks a detection. The plan's
> "XGBoost low-margin" rule was **deliberately omitted**: no margin threshold was measured,
> and inventing one would violate the project's own rule against arbitrary thresholds.
>
> **Steady-state cost, measured.** Over 4,000 real flows with all families known: 36
> SUSPICIOUS flags, observed rate 0.90 % against a 1.00 % target — and **all 36 were
> benign**. With every family known the anomaly branch adds no detections and costs ~1 %
> false positives. This is stated plainly in `EVALUATION.md`, and it is the concrete reason
> **P1-2 correlation is a prerequisite** for running it on a real network.
>
> **Delivered.** `training/evaluate_isolation_forest.py`, `training/leave_one_family_out.py`,
> `training/build_anomaly_detector.py` → `models/isolation_forest_benign_v2.joblib` +
> calibration JSON (v1 kept intact for reproducibility); `app/ml/anomaly.py` (calibrated
> percentile scoring, graceful unavailability); `app/ml/detection_engine.py`;
> wiring through `inference.py`, the API schema, replay and the live agent; `EVALUATION.md`.
> Backend: `predictionConfidence` relaxed to nullable with a service rule that a detection
> must carry *either* a confidence *or* an anomaly score; `UNKNOWN` flows now raise alarms
> at a fixed MEDIUM severity (the confidence-based ladder is meaningless for an anomaly
> score that is ~0.99 by construction at the threshold). LLM prompt bumped to `v2` with a
> dedicated SUSPICIOUS template that forbids naming an attack type.
> `isolation-forest-benign-v2` registered in the model registry.
>
> **A real bug this surfaced.** After P0-3 the replay built only the *active model's* 50
> features, so the 78-feature anomaly detector reported "unavailable" for every flow and
> silently contributed nothing. Fixed by building the union of both detectors' feature
> sets, and locked with a regression test.
>
> **Verified end to end** against live Postgres + Spring + ML service: a 1,500-flow replay
> produced 155 known attacks and 11 SUSPICIOUS flows, each stored with
> `detection_method=ANOMALY_DETECTION`, `anomaly_score` 0.990–0.996, null confidence, and a
> MEDIUM alarm. 179 Python + 35 Java tests pass; Angular `tsc` clean.

#### Original scope (for reference)


**Step 1 — evaluate before wiring.** `training/evaluate_isolation_forest.py` computes,
on the existing test split: score distribution for BENIGN vs each attack family, ROC/PR,
and the score threshold at target BENIGN false-positive rates (0.1 %, 0.5 %, 1 %, 5 %).
The threshold is **read off that curve**, not invented. The `contamination=0.19681`
test-set leak (audit §4.5) is corrected by refitting with `contamination='auto'` and
selecting the operating point on a validation split carved out of *training* data only.

**Step 2 — leave-one-family-out.** Retrain the IF with one attack family excluded and
measure detection of the held-out family. This is the only evidence that justifies
language about unseen attacks. Results go into `EVALUATION.md` **whatever they show.**

**Step 3 — decision engine** (`ml-service/app/ml/detection_engine.py`):

```
XGBoost says BENIGN  +  IF score below threshold   →  BENIGN
XGBoost says <attack>                              →  KNOWN_ATTACK   (SUPERVISED_ML)
XGBoost says BENIGN  +  IF score above threshold   →  SUSPICIOUS     (ANOMALY_DETECTION)
XGBoost low-margin   +  IF score above threshold   →  SUSPICIOUS, note the disagreement
```

XGBoost keeps precedence for known families; the IF only *adds* a SUSPICIOUS class where
the supervised model saw nothing. `FlowLabel` already has an `UNKNOWN` member — it is
reused rather than adding an enum value.

**Terminology, enforced in code comments, API docs and UI strings:**
*unknown/anomalous traffic detection*. The phrase "zero-day" is not used unless Step 2
produces evidence, and then only with the measured numbers attached.

---

### P1-2 · Alert correlation and incidents  *(L6 — Phase 6)* — **DONE**

> **Status 2026-08-31:** window derived from data, then implemented.
> `training/analyze_correlation_windows.py` → `reports/correlation_windows.json`.
>
> **The window is measured, not chosen.** Inter-arrival gaps between consecutive flows of
> the same attack family from the same source, taken from the original CICIDS2017 capture
> timestamps. **Bot is the discriminating family** — it beacons at exactly 120 s, so only
> 67 % of its gaps fall inside 30 s and 89 % inside 60 s, but **100 % inside 120 s**. Every
> other family is ≥99.96 % at 120 s, and 300 s buys essentially nothing more. **120 seconds**
> is therefore the smallest window that does not fragment a botnet, and it is configurable
> via `ids.correlation.window-seconds`.
>
> **Delivered.** `V6__incidents.sql` (incidents table + `alarms.incident_id`);
> `Incident` entity with capped destination tracking (100, with a `destinationsTruncated`
> flag and an exact count query behind it); `IncidentService.correlate()` running inside the
> ingest transaction and serialised per correlation key with a Postgres advisory lock;
> `IncidentRepository`; `IncidentController` with `GET /api/incidents`, `/{id}`,
> `/{id}/alarms`, `PATCH /{id}/status`. Severity escalates to the max alarm severity and
> never downgrades. A second WebSocket topic `/topic/incidents` carries one frame per
> incident state change while `/topic/alarms` keeps its per-alarm frames, so the existing
> dashboard is untouched. The old read-time query is preserved at
> `GET /api/alarms/incidents` (its DTO renamed `AlarmGroupResponse` to stop it competing
> with the real incident) — verified still returning 200.
>
> **Measured result.** A 2,000-flow attack-heavy replay with real 2017 timestamps produced
> **1,802 alarms → 30 incidents (60:1)**. The largest is a single DoS Hulk incident holding
> **525 alarms across 23 minutes** of capture time. That is the plan's stated goal met.
>
> **A design flaw the tests caught.** `findMostRecentOpen` was a repository *default method*,
> so Mockito stubbed it away rather than executing it — hiding the selection logic and
> silently defeating every correlation test. The selection moved into the service where it
> belongs and is now directly tested.
>
> **Verified:** 50 Java tests (15 new `IncidentServiceTest`), Angular `tsc` clean, and the
> API exercised live — 525 alarms retrieved for one incident, status transition applied,
> SERVICE and anonymous both 403.

#### Original scope (for reference)


Promote the read-time `findIncidents` query into a real persisted entity. Alarms are
**not** removed — an incident groups them.

`V6__incidents.sql`: `incidents(id, correlation_key, attack_type, source_ips[],
destination_ips[], first_seen, last_seen, flow_count, alarm_count, severity, status,
detection_method, created_at, updated_at)` + `alarms.incident_id UUID REFERENCES incidents(id)`.

Correlation key and window are **derived from the data, not invented**: a short study
script measures the real inter-alarm interval distribution per `(source_ip, attack_type)`
in the existing `alarms` table and in a PortScan replay, and the window is set from that
distribution (documented in the file). Starting hypothesis to be confirmed or rejected:
key = `(source_ip, attack_type)`, window = idle-gap based, i.e. an incident stays open
while alarms keep arriving within *W*, then closes.

`IncidentService.correlate(alarm)` runs inside the existing ingest transaction: find or
open the incident, bump counters, escalate severity, and emit **one** WebSocket frame per
incident *state change* instead of one per flow. Per-alarm frames stay available on a
second topic so the existing live feed is not broken.

`GET /api/incidents`, `/api/incidents/{id}`, `/api/incidents/{id}/alarms`,
`PATCH /api/incidents/{id}/status`. `GET /api/alarms/incidents` is kept as a deprecated
alias so the current dashboard keeps working while the UI moves over.

---

### P1-3 · False-positive feedback dataset  *(L4, L5 — Phase 7)* — **DONE**

> **Status 2026-08-31:** implemented and verified end to end.
>
> **L4 closed — ground truth is finally stored.** `NetworkFlowIngestRequest` gained
> `groundTruthLabel` and `groundTruthAttackType`, `network_flows.label` is set from the
> request instead of being hardcoded `UNKNOWN`, and the replay now sends the real CICIDS2017
> label. A 400-flow replay immediately produced a usable online confusion matrix straight
> from the database: 200 attacks all predicted `ATTACK`, 196 benign predicted `BENIGN`, and
> the 4 anomaly false positives visible as `BENIGN → UNKNOWN`.
>
> **L5 closed — `FALSE_POSITIVE` is no longer a dead end.** `V7__analyst_feedback.sql`
> adds `analyst_feedback`, written whenever an alarm moves to `FALSE_POSITIVE` or
> `CONFIRMED`. Each record snapshots the original prediction, confidence, anomaly score,
> detection method, the **full 78-feature vector**, the model id/name/version/feature
> version, the incident, the analyst username, and the ground-truth label — so it survives
> any later model change. Recording is idempotent per (alarm, verdict), verified live.
>
> **Delivered.** `AnalystFeedback` entity + repository + service; `AnalystFeedbackController`
> with `GET /api/feedback` (paged), `/stats` (verdict counts, FP rate, per-model breakdown)
> and `/export` returning JSONL for the training experiment. `AlarmController.updateStatus`
> now passes the authenticated analyst through so the verdict is attributable.
> Frontend feedback model + service added (no UI; that is P2-5).
>
> **Nothing retrains automatically.** The export endpoint is the only automated step; the
> path stays `feedback → dataset → experiment → evaluation → human approval → registry`.
>
> **Verified live:** 6 alarms triaged → 6 feedback records; `/stats` reported FP rate 0.5
> with a per-model breakdown; export returned 6 JSONL lines each carrying a 78-feature
> snapshot; re-applying the same verdict left the count at 6. Export authorisation is
> ADMIN-only (SERVICE 403, anonymous 403). 66 Java tests (16 new `AnalystFeedbackServiceTest`),
> 179 Python tests, Angular `tsc` clean, replay dry-run unchanged.

#### Original scope (for reference)


`V7__feedback.sql`: `analyst_feedback(id, alarm_id, network_flow_id, original_prediction,
original_confidence, analyst_classification, analyst_attack_type, model_id, model_name,
model_version, feature_version, feature_vector JSONB, analyst_user_id, notes, created_at)`.

Written whenever an alarm moves to `FALSE_POSITIVE` or `CONFIRMED`. The feature vector is
snapshotted at feedback time so the record survives model changes.

`GET /api/feedback/export?format=jsonl` (ADMIN) produces the training-experiment dataset.

**Nothing retrains automatically.** The documented path stays
`feedback → dataset → experiment → evaluation → human approval → registry → activation`,
and the only automated step is the first arrow.

Also lands here, because it is the same root cause (L4): `NetworkFlowIngestRequest` gains
an optional `groundTruthLabel`, and `cicids_replay.py` sends the real CICIDS2017 label so
`network_flows.label` finally means something and online precision/recall becomes computable.

---

### P1-4 · Drift monitoring  *(L14 — Phase 8)* — **DONE**

> **Status 2026-08-31:** thresholds calibrated from the data, then implemented.
> `training/calibrate_drift_thresholds.py` → `reports/drift_thresholds.json`.
>
> **The textbook threshold would have made the monitor useless.** Bootstrap (200 draws at
> each of four window sizes) shows the real no-drift KS ceiling is **≈0.32**, while the
> asymptotic Kolmogorov–Smirnov value `1.358/√n` gives **0.03–0.10** — a 7–10× gap. The
> cause is that CICIDS2017 features are heavily tied and zero-inflated, which violates the
> continuity assumption the formula rests on. Using the formula would have flagged nearly
> every feature as drifted permanently. This is exactly why the plan required calibration
> rather than a literature constant, and the comparison is kept in the artifact and asserted
> by a test.
>
> **Status rules.** A feature counts as drifted when its KS exceeds **its own p95 under the
> null** at the nearest calibrated window. The NORMAL→WARNING boundary on the drifted
> fraction is the **calibrated null p99** (7.7–11.5 % depending on window; mean under the
> null is 1.0 %); CRITICAL is a stated policy limit of 20 %, comfortably clear of the null.
> Invalid-vector rate adds WARNING above 1 % and CRITICAL above 5 %, and any required
> feature missing in more than 1 % of flows is CRITICAL on its own.
>
> **No new dependency.** The KS statistic is computed with numpy against the reference
> quantile grid from P0-1, so the planned `scipy` dependency was not needed.
>
> **Delivered.** `app/ml/drift.py` (`DriftMonitor` with a bounded window, per-feature
> missing/invalid/derived/zero-filled/out-of-range rates, KS, and status); wiring into
> `predict()` so **rejected vectors are counted too** — the P0-2 rejection rate is now a
> first-class drift signal, as promised; auto-publish every N flows plus
> `GET /api/drift/report` and `POST /api/drift/publish` on the ML service;
> `V8__drift_reports.sql`, `DriftReport` entity/repository/service and
> `POST /api/drift/reports` (SERVICE/ADMIN), `GET /api/drift/status`, `GET /api/drift/history`
> (ANALYST/ADMIN); frontend drift model + service (no UI; that is P2-5).
>
> **Verified by injecting drift**, not just by inspection: baseline traffic → NORMAL with
> 0 drifted features; 12 features scaled ×50 → **CRITICAL, and exactly those 12 flagged**
> with no false positives; 3 % unparseable → WARNING; 8 % → CRITICAL; a feature dropped
> entirely → CRITICAL citing both the invalid rate and the missing feature. A live
> 600-flow replay auto-published a NORMAL report to Spring
> (`feature_version=cicids2017-top50-v1`, calibration window 500).
>
> **202 Python + 77 Java tests** (23 new `test_drift.py`, 11 new `DriftReportControllerTest`),
> Angular `tsc` clean, replay dry-run unchanged.

#### Original scope (for reference)


Reference = `reports/training_feature_reference.json` from P0-1. Production window =
the last *N* ingested flows.

Per feature: missing rate, zero-fill rate, invalid rate (NaN/inf/reject), mean, std,
p25/p50/p75, and a **two-sample Kolmogorov–Smirnov statistic** against the reference
quantiles (`scipy.stats` — the only new dependency in this package, justified by not
hand-rolling a KS test; `scipy` is already an indirect dependency of scikit-learn, so it
adds nothing to the install).

Status thresholds derived from a bootstrap over the training set itself (what KS value do
two random training samples produce?) rather than picked by hand:

```
NORMAL   — KS below the 95th percentile of the null distribution, invalid rate < 1 %
WARNING  — KS above it on ≤ 20 % of features, or invalid rate 1–5 %
CRITICAL — KS above it on > 20 % of features, or invalid rate > 5 %, or any
           required feature missing in > 1 % of flows
```

`V8__drift.sql` → `drift_reports`. `GET /api/drift/status`, `GET /api/drift/history`.
Computed by the ml-service on a schedule and POSTed to Spring (same service-account
pattern as explanations).

---

### P1-5 · Security fixes that should not wait  *(L10, L11, L13 — Phase 17, first slice)*

* **ml-service authentication.** `/api/predict` and `/api/explain` require the same JWT
  the rest of the system uses (verify the HS signature with a shared secret, check the
  role claim). `/health` stays open. Removes the anonymous-LLM-spend hole.
* **Registration closed** (decided). `POST /api/auth/register` is removed from the
  `permitAll` matchers and replaced by `POST /api/users` (ADMIN only) creating an
  ANALYST/ADMIN/SERVICE account. `AuthService.register` is retained and reused so the
  BCrypt + duplicate-username handling is not rewritten; the Angular `/register` route is
  removed and the login page loses its sign-up link. The three roles are unchanged.
* `GlobalExceptionHandler`: add `DataIntegrityViolationException` → 409,
  `AccessDeniedException` → 403, `AuthenticationException` → 401, and a catch-all that
  logs the stack trace but returns a generic message.
* Basic rate limiting on `/api/auth/login` and `/api/auth/register` (Spring's own
  `Bucket4j`-free approach: a small in-memory filter — no new dependency).

---

## P2 — Medium

### P2-1 · Reproducible training pipeline  *(L7 — Phase 10)*

```
ml-service/training/
    data.py          load + clean (reuses app/ml/data_loading.py, no duplication)
    preprocessing.py THE missing balancing step, reconstructed and versioned
    split.py         random split (reproduce current numbers) AND a temporal split
    train.py         XGB / RF / MLP / IsolationForest from one config
    evaluate.py      full metric suite, confusion matrix, per-class table
    register.py      artifact + metadata → POST /api/models
    configs/*.yaml   one file per experiment
```

`preprocessing.py` reconstructs `undersample_benign_200k_oversample_rare_2k` from the
registered metadata, and the reconstruction is **validated by re-running the pipeline and
comparing metrics against the notebook's recorded numbers**. If they do not match, the
discrepancy is reported rather than papered over. The 8.9 GB `session_checkpoint.pkl` is
a fallback source of truth for what the original arrays looked like.

`notebooks/eda_step1_read.py.ipynb` is **kept untouched** as the research record.

### P2-2 · Evaluation rigour  *(L7, L8 — Phase 9)*

Adds to `evaluate.py`: per-class precision/recall/F1 **with support counts printed
next to every number**, confusion matrix (saved as CSV + PNG), macro/weighted F1,
overall and per-class FPR/FNR, and a **temporal-split run reported alongside the random
split** so the optimism of the current numbers is quantified rather than argued about.

`EVALUATION.md` states plainly that Heartbleed (≈2 test rows), SQL Injection (≈4) and
Infiltration (≈7) cannot support a performance claim, and reports them as
"insufficient support" rather than as a score.

### P2-3 · Experiment tracking decision  *(L15 — Phase 11)*

The brief allows either. Recommendation: **integrate MLflow** — it is already installed,
`training/` gives it something real to log, and "every trained model has metadata" is a
thesis requirement. Scope: local file-backed tracking URI, one run per `train.py`
invocation, logging params/metrics/artifact path/dataset hash, and the run id written
into `ml_models.hyperparameters` metadata.

**Optuna is removed** unless a tuning experiment is actually planned — there is no
justification for keeping an unused dependency. Also in this package: add `pyarrow` and
`shap` to `requirements.txt` (both genuinely used), drop `lightgbm`.

### P2-4 · Backend model completeness  *(Phase 12)*

Entities/DTOs/endpoints for `Incident`, `Feedback`, `DriftReport` (delivered by P1-2/3/4);
`@PreAuthorize` role matrix reviewed as a single table and made the single source of truth
(the duplicated `SecurityConfig` URL matchers reduced to defence-in-depth); pagination and
validation applied consistently. Existing JWT and the ADMIN/ANALYST/SERVICE roles are
preserved exactly.

### P2-5 · Dashboard  *(Phase 13)*

The existing SOC design is preserved; new information is added, nothing is redesigned.

* **Overview** — add: active incidents, anomalous-traffic count, drift status chip.
  (Total flows, total alarms, critical, FP rate already exist.)
* **Detection breakdown** — Known attack / Unknown-anomalous / Benign.
* **Incidents view** — incident → related alarms → related flows → detection info →
  SHAP → LLM explanation.
* **Model info on every detection** — model, version, detection method, feature version,
  confidence, anomaly score.
* **Wording** — "confidence" relabelled for non-technical readers; `UNKNOWN` shown as
  *"anomalous — no known CICIDS2017 attack class"*, never as a named attack.
* Housekeeping: `environment.ts` for the two base URLs (currently hardcoded in 9 files);
  the hardcoded lab IPs in `topology.component.ts` become inputs.

### P2-6 · LLM explanation for `UNKNOWN`  *(Phase 14)*

The existing SHAP→LLM architecture is kept. Changes: a second prompt template for the
anomaly case that states the system found anomalous behaviour it **cannot** attribute to a
known CICIDS2017 class; an explicit instruction not to name an attack type not present in
the supplied evidence; `PROMPT_VERSION` bumped to `v2` (the DB already versions prompts,
so `v1` explanations remain comparable). The LLM still never decides anything.

### P2-7 · Test coverage breadth  *(L16 — Phase 15, remainder)*

Python: preprocessing, model loading, anomaly detection, invalid inputs.
Spring: auth, authorization matrix, alarm creation, incident correlation, status
transitions, model APIs, validation, error handling.
Angular (Vitest — already installed): auth service, alarm feed, WebSocket updates,
filtering, alarm/incident detail, model info.
One end-to-end test: fixture flow → ml-service inference → Spring ingest → DB assertion →
WebSocket frame assertion.

---

## P3 — Optional

### P3-1 · Containerisation  *(L17 — Phase 16)*

Dockerfiles for backend (multi-stage Maven→JRE), frontend (build→nginx), ml-service
(slim Python + the `models/` volume). A **development** `docker-compose.yml` at the repo
root wiring all four services. No production assumptions, no secrets in images —
everything through env vars with `.env.example` files.

### P3-2 · README  *(L17)*

Architecture, prerequisites, setup, environment variables, database setup, ML setup,
running dataset replay, running live capture, API reference, dashboard, testing.

### P3-3 · Remaining security audit  *(Phase 17, remainder)*

Angular token storage review, XSS surface, route guards vs. server checks, tightening
`setAllowedOriginPatterns("*")` on the STOMP endpoint, dependency vulnerability scan,
removal of the committed default credentials in `application.yml` in favour of
fail-fast-if-unset.

---

## Suggested execution order

```
P0-1 ─► P0-2 ─► P0-3 ─► P0-4        (Phase 1,2,3,5 + first tests)   ← implement after approval
          │        │
          │        └─► P1-1 (needs model identity)  ─┐
          └──────────► P1-4 (needs the reference)    ├─► P2-*
                       P1-2, P1-3, P1-5 (independent)┘
```

P0-1 gates P0-2 (the validator needs the reference statistics) and P1-4. P0-3 gates P1-1.
P1-2, P1-3 and P1-5 have no dependency on each other and can be done in any order.

---

## Decisions taken (2026-08-30)

1. **Active model → `xgb-smote-top50features-v1`.** Both inference paths converge on the
   50-feature model. Fewer live-mapping assumptions, smaller drift surface; the RQ3
   accuracy cost is small. Affects P0-3, and means the 78-feature model becomes a
   registered-but-inactive baseline rather than a runtime artifact.
2. **A CICFlowMeter capture CSV will be supplied.** P0-1 is therefore built to consume a
   real capture and the compatibility matrix ships with **measured** values for all 78
   features, not 70 `UNVERIFIED` rows.
3. **Public registration is closed.** `POST /api/auth/register` becomes ADMIN-only user
   creation. Affects P1-5; the login flow and the three existing roles are unchanged.
4. **Live-path validator rejects.** A flow with a missing required feature, `NaN` or
   `±inf` raises **no alarm**; it is counted, and the rejection rate becomes a
   first-class health/drift metric consumed by P1-4. The 8 provably constant-zero
   features remain a whitelisted zero-fill emitting an *info*, not a rejection — they are
   not in the top-50 set, so on the live path this branch is inert.

### Still open

* **Optuna** — remove the unused dependency, or is a hyperparameter-tuning experiment
  planned for the thesis? (P2-3; not blocking P0.)
