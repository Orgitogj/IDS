# IDS_ARCHITECTURE_AUDIT.md

**Repository:** `C:\IDS` — branch `main` @ `82a4475e`
**Audit date:** 2026-08-30
**Scope:** Phase 0 — read-only audit. No application behaviour was modified.

Every claim below was verified against source code or against the dataset/model artifacts
themselves. Where a claim could **not** be verified in this environment (e.g. the runtime
behaviour of CICFlowMeter on the Linux capture host), it is explicitly marked
**[UNVERIFIED]** rather than assumed.

---

## 1. Current architecture

Three independently started processes plus one container:

| Component | Tech | Location | Port | How it is started |
|---|---|---|---|---|
| Backend | Spring Boot 3.3.4, Java 17 | `backend/` | 8080 | manual (`mvn spring-boot:run` / IDE) |
| Frontend | Angular 22 (zoneless, standalone, Tailwind 4) | `frontend/` | 4200 | manual (`ng serve`) |
| ML service | FastAPI + XGBoost | `ml-service/` | 8000 | manual (`uvicorn app.main:app`) |
| Database | PostgreSQL 16-alpine | `backend/docker-compose.yml` | 5433→5432 | Docker Compose |

There is **no** Dockerfile for backend, frontend or ml-service, and no root-level
compose file. The only container is Postgres.

Additional off-repo component: the **live capture agent**
(`ml-service/app/replay/live_agent.py`) is designed to run on a *separate Linux host*
(it shells out to `sudo /usr/local/bin/cicflowmeter`) and talks to the backend over the
network (default `--backend http://192.168.100.3:8080`). The artifacts it needs are
duplicated into `app/replay/` for copying to that host:

```
app/replay/xgb_smote_top50features_v1.joblib   (md5 identical to models/ copy)
app/replay/label_encoder_cicids2017.joblib     (md5 identical to models/ copy)
app/replay/feature_columns.json                (byte-identical to models/ copy)
```

### Component diagram (as actually built)

```
                                  ┌──────────────────────────────┐
   Angular 22 SPA  :4200 ─────────┤ REST + JWT  →  Spring :8080  │
        │  │                      │ STOMP/SockJS /ws  (JWT on    │
        │  │                      │        CONNECT frame)        │
        │  └── direct HTTP ──┐    └──────────────┬───────────────┘
        │   (SHAP + explain) │                   │ JPA / Flyway
        │                    ▼                   ▼
        │            FastAPI ml-service   PostgreSQL 16 :5433
        │                :8000  (NO AUTH)
        │                    │
        │                    ├─ XGBoost (78-feature model, hardcoded)
        │                    ├─ TreeSHAP via xgboost pred_contribs
        │                    └─ Claude  → explanation text
        │                             │
        └─────────────────────────────┘  (explanation POSTed back to Spring
                                          by ml-service as user `ml-service`)

   Linux capture host (separate machine)
        cicflowmeter -i <iface> -c live_flows.csv
              │  (CSV polled every 5 s)
              ▼
        live_agent.py  ── loads its OWN copy of xgb_smote_top50features_v1
              │           (does NOT call the ml-service at all)
              └──── POST /api/alarms/ingest ──► Spring :8080
```

**Architectural note that matters:** there are **two independent inference paths**
using **two different models**. See §4.3.

---

## 2. Actual data flow

### 2.1 Live capture path (`live_agent.py`)

```
packets → cicflowmeter → live_flows.csv (appended)
   → csv.DictReader, poll every --poll-interval (default 5.0 s), slice [seen_rows:]
   → map_row_to_feature_vector()            live_agent.py:120-142
        · CICFLOWMETER_TO_CICIDS2017 rename (78 entries)
        · float() cast; on ValueError/TypeError → 0.0  (live_agent.py:132-133)
        · key not present               → 0.0  (live_agent.py:135-136)
        · prints a stderr warning listing missing names
   → predict_flow()                          live_agent.py:145-152
        · np.array([[...]]) in feature_columns order (from model.feature_names_in_)
        · model.predict / predict_proba
   → ingest_flow()                           live_agent.py:165-190
        · predictedLabel = "BENIGN" if label=="BENIGN" else "ATTACK"
        · attackType    = raw class name
        · flowTimestamp = datetime.now(UTC)  ← capture time is discarded
        · datasetSource NOT sent → backend defaults to LAB_LIVE
   → POST /api/alarms/ingest (Bearer JWT from /api/auth/login as ml-service)
```

Login happens **once at startup**; there is no refresh, so the agent dies functionally
after JWT expiry (480 min) — it will log ingest errors forever without re-authenticating.

### 2.2 Dataset replay path (`cicids_replay.py`)

```
datasets/cicids2017_cleaned.parquet  (2,827,876 rows)
   → _select_indices(): stratified random sample, attack_ratio default 0.3, seed 42
   → _collect_rows(): iter_batches(50_000), pulls the chosen row indices
   → _build_payload():
        · feature_vector = {col: float(row[col]) for col in _feature_columns}  (all 78)
        · calls app.ml.inference.predict(...)  ← in-process, 78-feature model
        · predicted_label = "ATTACK"/"BENIGN", attack_type = model's class name
        · dataset_source = "CICIDS2017_REPLAY"
   → spring_client.ingest_flow() → POST /api/alarms/ingest, rate-limited (default 10/s)
```

The replay reads `row["Label"]` only to *choose* rows; the **ground-truth label is never
sent to the backend**. `NetworkFlow.label` is hardcoded to `UNKNOWN`
(`NetworkFlowService.java:60`), so the database never holds a ground truth for any flow.

### 2.3 Backend ingest → alarm → WebSocket

```
POST /api/alarms/ingest  (ROLE_SERVICE or ROLE_ADMIN)
   → NetworkFlowService.processFlowResult()
        · save NetworkFlow (feature_vector as jsonb, label=UNKNOWN)
        · if predictedLabel == ATTACK:
              severity = SeverityThresholdsService.resolveSeverity(confidence)
                         CRITICAL ≥0.95, HIGH ≥0.85, MEDIUM ≥0.70, else LOW
              save Alarm(status=NEW)
              messagingTemplate.convertAndSend("/topic/alarms", alarmResponse)
   → 201 with NetworkFlowResponse
```

**One flow ⇒ at most one alarm.** No dedup, no correlation, no incident entity.

### 2.4 Dashboard explanation path

```
Analyst clicks an alarm (alarms.component.ts:229)
   → GET /api/flows/{networkFlowId}          (Spring)
   → POST http://localhost:8000/api/predict  (ml-service, DIFFERENT model — see §4.3)
        → SHAP top-5 rendered as a bar chart
   → "Generate explanation" → POST :8000/api/explain
        → ml-service re-predicts, calls Claude,
          POSTs the text back to Spring as ml-service, then the UI re-GETs it.
```

---

## 3. Important files

| Path | Role |
|---|---|
| `ml-service/app/ml/inference.py` | Model load + predict + TreeSHAP. **Hardcodes `xgb_smote_cicids2017_v1.joblib`** (line 22) and silently zero-fills missing features (line 46). |
| `ml-service/app/replay/live_agent.py` | Standalone live agent. Owns the CICFlowMeter→CICIDS2017 name map (lines 11-88) and its own zero-fill (lines 130-142). |
| `ml-service/app/replay/cicids_replay.py` | Dataset replay driver. |
| `ml-service/app/api/predict.py` | `/api/predict`, `/api/explain`. **No authentication.** |
| `ml-service/app/services/llm_explainer.py` | Prompt construction + Claude calls. Prompt is in Albanian, version `v1`. |
| `ml-service/app/services/spring_client.py` | JWT login + retry-once wrapper for all Spring calls. |
| `ml-service/models/feature_columns.json` | The 78 training feature names, in training order. |
| `backend/.../service/NetworkFlowService.java` | Ingest → flow → alarm → WebSocket. |
| `backend/.../repository/AlarmRepository.java` | Contains the only "incident" logic: a read-time `GROUP BY source_ip, attack_type` native query. |
| `backend/.../config/SecurityConfig.java` | JWT filter chain + URL rules. |
| `backend/src/main/resources/db/migration/V1..V4` | Full schema. |
| `frontend/src/app/features/alarms/alarms.component.ts` | Alarm feed, SHAP chart, LLM explanation UI, status transitions. |
| `ml-service/notebooks/eda_step1_read.py.ipynb` | 93 cells; the entire training history. |

---

## 4. Current ML pipeline

### 4.1 Data

* Source: `datasets/TrafficLabelling/*.csv` (8 files, latin-1). `MachineLearningCVE/` is a
  second unused copy of the same data without identifier columns.
* Cleaning (`app/ml/data_loading.py`): strip column names, drop duplicate
  `Fwd Header Length.1`, replace ±inf with NaN, `dropna(subset=["Flow Bytes/s","Flow Packets/s"])`.
* Cached as `datasets/cicids2017_cleaned.parquet` — **2,827,876 rows**, verified.

Verified label distribution of the cleaned parquet:

| Class | Rows | Share |
|---|---:|---:|
| BENIGN | 2,271,320 | 80.32 % |
| DoS Hulk | 230,124 | 8.14 % |
| PortScan | 158,804 | 5.62 % |
| DDoS | 128,025 | 4.53 % |
| DoS GoldenEye | 10,293 | 0.36 % |
| FTP-Patator | 7,935 | 0.28 % |
| SSH-Patator | 5,897 | 0.21 % |
| DoS slowloris | 5,796 | 0.20 % |
| DoS Slowhttptest | 5,499 | 0.19 % |
| Bot | 1,956 | 0.069 % |
| Web Attack – Brute Force | 1,507 | 0.053 % |
| Web Attack – XSS | 652 | 0.023 % |
| Infiltration | **36** | 0.0013 % |
| Web Attack – Sql Injection | **21** | 0.00074 % |
| Heartbleed | **11** | 0.00039 % |

With an 80/20 stratified split this leaves roughly **7 Infiltration, 4 SQL Injection and
2 Heartbleed rows in the test set**. Any per-class metric reported for those three
classes is statistically meaningless. (Class names contain the raw byte `\x96` — an
en-dash mis-decoded as latin-1; `cicids_replay._clean_label` patches it at replay time,
but the label encoder and the DB keep the broken form.)

### 4.2 Features

* 78 numeric columns = all parquet columns minus
  `['Flow ID','Source IP','Source Port','Destination IP','Timestamp','Label','source_file']`
  (notebook cell 12).
* `models/feature_columns.json` and `app/replay/feature_columns.json` are identical (78 names, verified).

**Empirically verified over all 2.83 M rows** — 8 of the 78 features are *constant zero
in the entire dataset*:

```
Bwd PSH Flags          Bwd URG Flags
Fwd Avg Bytes/Bulk     Fwd Avg Packets/Bulk    Fwd Avg Bulk Rate
Bwd Avg Bytes/Bulk     Bwd Avg Packets/Bulk    Bwd Avg Bulk Rate
```

A further 4 are ≥99.97 % zero: `Fwd URG Flags`, `RST Flag Count`, `CWE Flag Count`,
`ECE Flag Count`. This is directly relevant to the zero-fill question (§8).

Known CICIDS2017 data-quality artifacts confirmed in this copy: `Fwd Header Length`
ranges down to **−3.22 × 10¹⁰**, `min_seg_size_forward` down to **−5.37 × 10⁸`,
`Flow Duration` down to **−13**, `Flow Bytes/s` down to **−2.61 × 10⁸**. Negative values
are present in the *training* data and the model has learned around them.

### 4.3 Models on disk vs. models in use

| Artifact | n_features | Registered in DB | Used at runtime? |
|---|---:|---|---|
| `rf_baseline_cicids2017_v1.joblib` (155 MB) | 78 | yes | no |
| `rf_smote_cicids2017_v1.joblib` (90 MB) | 78 | yes | no |
| `xgb_baseline_cicids2017_v1.joblib` | 78 | yes | no |
| **`xgb_smote_cicids2017_v1.joblib`** | 78 | yes, `active=true` | **yes — hardcoded in `inference.py:22`** (ml-service + replay + dashboard SHAP) |
| `xgb_smote_top10/20/30/50/78features_v1.joblib` | 10/20/30/50/78 | yes | **`top50` only — hardcoded default in `live_agent.py:197`** |
| `isolation_forest_cicids2017_v1.joblib` | 78 | yes | **never loaded by any running code** |
| `mlp_smote_cicids2017_v1.joblib` + `scaler_cicids2017.joblib` | 78 | yes | no |

All XGBoost artifacts carry `feature_names_in_` and 15 classes; the label encoder has 15
classes. The Isolation Forest was fit on BENIGN-only training rows with
`contamination = 0.19681` (the *test-set* attack rate — a leak of test information into a
hyperparameter), `offset_ = −0.40489`.

**Finding (critical):** the live agent classifies with the **50-feature** model, but when
the analyst opens that alarm in the dashboard, the SHAP explanation is computed by the
ml-service using the **78-feature** model. The explanation therefore does not necessarily
explain the decision that raised the alarm, and can even disagree with it.

### 4.4 Training procedure (from the notebook)

* Split: `train_test_split(test_size=0.2, random_state=42, stratify=y)` — a **random**
  split of a time-ordered capture. Flows from the same attack burst land on both sides,
  which inflates all reported scores.
* Balancing: `X_train_balanced` — described in registered metadata as
  `"undersample_benign_200k_oversample_rare_2k"`. **The cell that actually builds
  `X_train_balanced` is not in the notebook** (searched all 93 cells; only *uses* of the
  variable survive). It was lost to cell re-execution and lives only inside the 8.9 GB
  `notebooks/session_checkpoint.pkl` dill dump. This is the single biggest
  reproducibility hole.
* Feature-selection experiment (RQ3): ranks features by `xgb_smote.feature_importances_`,
  retrains on the top-{10,20,30,50,78}. Verified: the top-50 set contains **none** of the
  8 constant-zero features.
* SHAP at training time used the `shap` package; **`shap` is not in `requirements.txt`
  and is not installed** — runtime SHAP uses `xgboost` `pred_contribs` instead, which is
  correct and dependency-free.
* Evaluation reported: accuracy, macro precision/recall/F1, `classification_report`,
  latency. No confusion matrix persisted, no FPR/FNR, no per-class table stored anywhere
  outside notebook output.

### 4.5 Isolation Forest, as evaluated in the notebook

Binary BENIGN-vs-attack on the test set: accuracy 0.7366, precision 0.3670,
recall 0.4665, F1 0.4108. As a stand-alone detector it is poor. It has **never been
evaluated on held-out attack families it did not see**, so there is at present *no
evidence* it detects unknown attacks. Calling it "zero-day detection" is not supportable
from what exists today.

---

## 5. Current database structure

Flyway V1–V4, `ddl-auto: validate`.

```
network_flows(id, dataset_source, source_ip, destination_ip, source_port,
              destination_port, protocol, feature_vector JSONB, label,
              attack_type, predicted_label, prediction_confidence,
              flow_timestamp, created_at)
    idx: dataset_source, label, source_ip, destination_ip

alarms(id, network_flow_id UNIQUE→network_flows, severity, status,
       created_at, acknowledged_at, resolved_at)
    idx: status

explanations(id, alarm_id→alarms, explanation_text, llm_model,
             llm_prompt_version, generated_at, rating, rated_at,
             generation_latency_ms)
    unique: (alarm_id, llm_model, llm_prompt_version)

ml_models(id, algorithm, name UNIQUE, trained_on_dataset, artifact_path,
          hyperparameters TEXT, feature_set TEXT, active BOOL, trained_at, created_at)

experiment_results(id, ml_model_id→ml_models, tested_on_dataset, feature_set_used,
                   accuracy, precision_score, recall, f1_score, avg_latency_ms,
                   sample_size, notes, ran_at)

severity_thresholds(id singleton, critical_min, high_min, medium_min, updated_at)

users(id, username UNIQUE, password_hash, role, enabled, created_at)
```

Gaps: no `incidents` table; no link from a flow/alarm to the **model that produced it**;
no `feedback` table; no drift/monitoring table; no version/`feature_version` column on
`ml_models`; `network_flows.label` is written but always `UNKNOWN`; no index on
`network_flows.created_at` or `flow_timestamp` even though every listing sorts by
`created_at DESC`.

---

## 6. Current API structure

### Spring Boot (`:8080`)

| Method | Path | Auth |
|---|---|---|
| POST | `/api/auth/login` | public |
| POST | `/api/auth/register` | **public — self-service ANALYST signup** |
| GET | `/api/auth/me` | authenticated |
| POST | `/api/alarms/ingest` | SERVICE, ADMIN |
| GET | `/api/alarms` (page/size/severity/status/search) | ANALYST, ADMIN |
| GET | `/api/alarms/stats` | ANALYST, ADMIN |
| GET | `/api/alarms/incidents?limit` | ANALYST, ADMIN |
| GET | `/api/alarms/{id}` | ANALYST, ADMIN |
| PATCH | `/api/alarms/{id}/status` | ANALYST, ADMIN |
| POST | `/api/alarms/{alarmId}/explanations` | SERVICE, ADMIN |
| GET | `/api/alarms/{alarmId}/explanations` | ANALYST, ADMIN |
| PATCH | `/api/alarms/{alarmId}/explanations/{id}/rating` | ANALYST, ADMIN |
| GET | `/api/flows`, `/api/flows/stats`, `/api/flows/{id}` | ANALYST, ADMIN |
| GET | `/api/models`, `/api/models/{id}` | ANALYST, ADMIN |
| POST | `/api/models` | SERVICE, ADMIN |
| PATCH | `/api/models/{id}/activate` | ADMIN |
| GET | `/api/experiments`, `/api/experiments/{id}` | ANALYST, ADMIN |
| POST | `/api/experiments` | SERVICE, ADMIN |
| GET | `/api/settings/thresholds` | ANALYST, ADMIN |
| PUT | `/api/settings/thresholds` | ADMIN |
| STOMP | `/ws` (SockJS), topic `/topic/alarms` | HTTP `permitAll`; JWT enforced on STOMP CONNECT |

Authorisation is declared **twice** — in `SecurityConfig` URL matchers *and* in
`@PreAuthorize` on the controllers. They currently agree, but it is duplicated state.

### FastAPI (`:8000`)

| Method | Path | Auth |
|---|---|---|
| GET | `/health` | **none** |
| POST | `/api/predict` | **none** |
| POST | `/api/explain` | **none** — triggers paid Claude calls |

---

## 7. Current Angular architecture

Angular 22, standalone components, **zoneless** change detection, signals throughout,
Tailwind 4 via PostCSS, `ng2-charts`/Chart.js, `@stomp/stompjs` + `sockjs-client`.

```
app.routes.ts
  /login, /register                    (public)
  / → ShellComponent [authGuard]
       /overview     KPI cards, alarm timeline, severity doughnut,
                     attack-type bar, top-5 models by F1, recent alarms,
                     live WS increments
       /topology     hardcoded attacker 192.168.50.10 → victim 192.168.50.20 animation
       /alarms       paged feed + filters + incident panel + alarm detail
                     (SHAP chart + LLM explanations + ratings + status buttons)
       /flows        paged flow table
       /experiments  experiment result table
       /models       model registry list; ADMIN can activate
       /settings     [adminGuard] severity thresholds
```

`core/` holds 8 services, 2 guards, 1 interceptor, 11 models. JWT is kept in
`localStorage`; the role is read by **client-side base64-decoding the JWT payload**
(`auth.service.ts:decodeRole`) with no signature check — fine for UI-only decisions,
since the server re-checks, but worth stating.

The auth interceptor attaches the Bearer token to *every* non-public request, including
the cross-origin calls to `http://localhost:8000` (the ml-service ignores it).

All backend URLs are hardcoded as `http://localhost:8080` / `:8000` string constants in
each service. There is no `environment.ts`.

Tests: `app.spec.ts` only (the CLI stub). Vitest and jsdom are installed as devDeps.

---

## 8. Existing detection mechanisms

1. **Supervised multiclass XGBoost.** The only mechanism that produces a detection today.
   15 classes; anything not `BENIGN` becomes `predictedLabel=ATTACK` + `attackType=<class>`.
2. **Severity mapping** from the XGBoost softmax probability via configurable thresholds
   (0.95/0.85/0.70). This treats a class posterior as a security-risk score.
3. **Read-time "incidents"** — `AlarmRepository.findIncidents`, a
   `GROUP BY f.source_ip, f.attack_type` over all alarms ever, with count, min-severity-rank,
   first/last seen. Not persisted, no time window, no destination, no status, no dedup;
   the alarms themselves are still 1-per-flow.
4. **SHAP** (TreeSHAP via `pred_contribs`) — explanation only, top 5 features.
5. **LLM narrative** (Claude `claude-sonnet-5`)
   — explanation only. It receives label, confidence and the SHAP top-5, and is instructed
   to explain, not to decide. That boundary is currently respected in code.
6. **Isolation Forest** — trained and registered, **not wired into anything**.

---

## 9. Existing limitations

Ordered by how much they threaten the technical defensibility of the system.

### L1 — Two inference paths, two models, no traceability *(critical)*
`live_agent.py` predicts with `xgb_smote_top50features_v1`; `inference.py` predicts with
`xgb_smote_cicids2017_v1`. Neither consults `ml_models.active`. A stored alarm records
**no model id, version, or feature set**, so no prediction in the database can be
attributed to the artifact that produced it, and the SHAP shown to the analyst may come
from a different model than the one that fired.

### L2 — Silent zero-fill and silent type coercion *(critical)*
Three separate places substitute `0.0` with no structured signal:
`live_agent.py:133` (unparseable value), `live_agent.py:135` (absent key),
`inference.py:46` (absent key in any `/api/predict` request). The live agent at least
prints to stderr; the ml-service is completely silent. A request that supplies **zero**
of the 78 features still returns a confident prediction.

What is *actually* known about the missing-feature problem:

* The name map in `live_agent.py` has **78 entries covering all 78 training features**
  (verified programmatically — 0 uncovered, 0 spurious). So the map is not *structurally*
  incomplete.
* For 8 features (`Bwd PSH Flags`, `Bwd URG Flags`, the 6 bulk features) zero-fill is
  **mathematically exact** — they are constant zero across all 2.83 M training rows, so
  the model can encode no information from them. **None of these 8 is in the top-50
  live feature set anyway.**
* Whether the *installed* CICFlowMeter build emits the remaining 70 keys under exactly
  these names, in these units, with these semantics, is **[UNVERIFIED]** — CICFlowMeter is
  not installed in this repo or in either venv, and the capture host is a separate
  machine. This must be measured on that host before any further change; §Phase 1 of the
  plan is written around producing that measurement rather than guessing.
* Independent of names, CICIDS2017 was generated by the **Java** CICFlowMeter v3/v4;
  the `snake_case` key style in the map is that of the **Python** re-implementation. Unit
  and semantic differences between the two (µs vs ms durations, header-length accounting,
  flag-count vs flag-present) are a documented class of problem and are the more likely
  source of distribution shift than missing columns.

### L3 — Infinity is not handled on the live path *(high)*
Training explicitly **dropped** every row where `Flow Bytes/s` or `Flow Packets/s` was
±inf (`data_loading.py:26-27`), and the cleaned parquet contains no infinities (verified).
`float("inf")` parses fine in `live_agent.map_row_to_feature_vector`, so a zero-duration
live flow feeds an infinity into a model that never saw one. Nothing rejects or flags it.

### L4 — No ground truth is ever stored *(high)*
`NetworkFlow.label` is hardcoded `UNKNOWN` (`NetworkFlowService.java:60`), and the replay
drops the CICIDS2017 label it already has in hand. The system therefore cannot compute a
single online accuracy/FPR figure, and analyst `FALSE_POSITIVE` verdicts have nothing to
be joined against.

### L5 — `FALSE_POSITIVE` is a dead end *(high)*
The status exists and the UI sets it, but nothing reads it except the overview's
"FP rate" tile. No feedback record, no features snapshot, no model attribution, no export.

### L6 — 1 flow = 1 alarm *(high)*
A PortScan replay of 500 flows produces 500 alarms and 500 WebSocket frames. The
`findIncidents` query is a reporting view bolted on top, not a correlation layer, and it
aggregates over all time with no window.

### L7 — Random split on time-ordered capture + unreproducible balancing *(high)*
See §4.4. Reported metrics are optimistic by an unknown margin, and the balancing step
cannot be re-run from the repository.

### L8 — Minority classes are unreportable *(high)*
Heartbleed (11 rows), SQL Injection (21), Infiltration (36) — see §4.1. Whatever
`classification_report` printed for these classes is noise. Bot (1,956) is small but
usable.

### L9 — Isolation Forest unused, and its one hyperparameter leaks the test set *(medium)*
`contamination` was set to the test-set attack rate (0.19681). Any evaluation of it at
that setting is contaminated.

### L10 — ml-service is unauthenticated *(medium/security)*
`/api/predict` and `/api/explain` accept anonymous requests. `/api/explain` spends money
(Claude) and writes to the database through the `ml-service` service account. CORS
is limited to `localhost:4200`, but CORS does not stop a non-browser client.

### L11 — Public self-service registration *(medium/security)*
`POST /api/auth/register` is `permitAll` and mints an `ANALYST`, who can read every alarm,
flow, feature vector and model in the system. There is no rate limiting and no password
policy (only whatever `RegisterRequest` bean validation declares).

### L12 — Committed default secrets *(medium/security)*
`application.yml` ships fallback values for `IDS_JWT_SECRET`, `admin/admin123` and
`ml-service/ml-service-secret`. `ml-service/.env` (correctly gitignored, verified not
tracked) holds a real Anthropic key. Nothing is currently leaked to git, but the
defaults will silently be used if the env vars are unset.

### L13 — Error handling gaps *(medium)*
`GlobalExceptionHandler` covers 3 custom exceptions + bean validation. A duplicate model
name (`ml_models.name` is UNIQUE — and the notebook re-registers the same names in cells
79–86) raises `DataIntegrityViolationException` → unhandled 500 with a stack trace.
No handler for `AccessDeniedException`, `AuthenticationException` or generic `Exception`.

### L14 — No drift or data-quality monitoring *(medium)*
Nothing measures the live feature distribution against the training reference, even
though L2/L3 guarantee there is a shift.

### L15 — Dependency hygiene *(low)*
`mlflow==2.16.2` and `optuna==4.0.0` are installed and imported nowhere (only
`settings.mlflow_tracking_uri` exists, unused). `lightgbm` unused. `shap` used in the
notebook but absent from `requirements.txt`. `pyarrow` is required by
`cicids_replay.py` but **not declared** in `requirements.txt`.

### L16 — Testing is effectively absent *(medium)*
Backend: one `contextLoads()`. Frontend: the CLI-generated `app.spec.ts`. ML service:
none at all, and no `tests/` directory.

### L17 — Operational packaging *(low)*
No Dockerfiles, no root compose, no README, no `environment.ts`, hardcoded URLs in nine
Angular services, hardcoded lab IPs in `topology.component.ts`, `live_agent.py` defaulting
to `http://192.168.100.3:8080`, and an 8.9 GB `session_checkpoint.pkl` sitting in
`notebooks/` (gitignored).

---

## 10. Feature compatibility matrix (Phase 1 groundwork)

The full 78-row matrix is mechanically derivable and is produced by the Phase 1 tooling in
the plan; what can be stated **today, verified**:

| Group | Count | Training | Mapped name exists | Zero-fill verdict |
|---|---:|---|---|---|
| Constant-zero in all 2.83 M rows (`Bwd PSH Flags`, `Bwd URG Flags`, 6 × bulk) | 8 | yes | yes | **Zero is exact.** Not in the top-50 live set. |
| ≥99.97 % zero (`Fwd URG Flags`, `RST/CWE/ECE Flag Count`) | 4 | yes | yes | Zero is a near-exact prior, but is a *decision*, not a fact — must be logged. |
| Remaining features | 66 | yes | yes (name map complete) | **[UNVERIFIED]** — depends on the capture host's CICFlowMeter build. Must be measured. |
| Features in the live top-50 model | 50 | yes | all 50 mapped | none of the 8 constant-zero features |

The honest conclusion for Phase 1 is: **the reported "missing features filled with 0"
problem is not a missing-name problem** — the name map is complete. The real exposures are
(a) whatever the deployed CICFlowMeter actually emits and under what units, (b) infinities
and unparseable values being coerced to 0.0, and (c) the total absence of any signal when
either happens. Fixing (b) and (c) is possible today and is unconditionally correct;
fixing (a) requires one measurement run on the capture host.

---

## 11. What is genuinely good and should not be touched

* Clean layered Spring Boot (controller → service → repository → entity), records for
  DTOs, Flyway with `ddl-auto: validate`.
* JWT + STOMP CONNECT authentication, method-level `@PreAuthorize`, BCrypt.
* Signals-based zoneless Angular with a coherent SOC visual language.
* TreeSHAP via `pred_contribs` — correct, fast, no extra dependency.
* The LLM is confined to explanation and is never consulted for the verdict.
* `spring_client._request` — token cache with a single forced-refresh retry.
* The replay driver's rate limiting, dry-run mode, and consecutive-error circuit breaker.
