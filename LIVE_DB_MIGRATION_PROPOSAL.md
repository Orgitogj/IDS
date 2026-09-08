# Proposed PostgreSQL migration — laboratory experiment traceability

**Status: PROPOSAL ONLY. NOT APPLIED. NOT PLACED IN `db/migration`.**

This file deliberately lives outside `backend/src/main/resources/db/migration/` so Flyway
cannot pick it up. Nothing in it runs until it is explicitly approved and moved.

## 1. Is a migration required for Phase 16 metrics?

**No.** The laboratory experiment ledger is file-based, in `reports/live_evaluation/`,
exactly like `artifact_evaluation`, `temporal_evaluation` and `lofo_evaluation`. Every
Phase 16 metric is computed from `runs/<run-id>/predictions.csv` plus `state.json`. The
thesis result does not depend on PostgreSQL at all.

A migration is only needed if laboratory flows should **also** be queryable in the
operational database with their experiment identity attached.

## 2. What the existing schema already carries

`network_flows` needs no change to support the following, and the ingest contract already
accepts all of them:

| Requirement | Existing column | Existing DTO field |
|---|---|---|
| dataset source | `dataset_source` (enum, has `LAB_LIVE`) | `datasetSource` |
| expected binary label | `label` (`FlowLabel`) | `groundTruthLabel` |
| expected attack family | `ground_truth_attack_type` | `groundTruthAttackType` |
| capture timestamp | `flow_timestamp` | `flowTimestamp` |
| ingested at | `created_at` | returned as `createdAt` |
| model identity | `model_name`, `model_version`, `feature_version` | same |

The current gap is entirely on the producer side: `live_agent.py` never sends the ground
truth fields and overwrites `flowTimestamp` with `now()`. Both are fixed in the ML service
without touching the database.

## 3. What is genuinely missing

| Field | Purpose |
|---|---|
| `experiment_id` | which laboratory experiment produced the flow |
| `run_id` | which controlled execution produced the flow |
| `scenario_id` | intended traffic scenario |
| `validation_status` | machine-readable pipeline/data integrity outcome |
| `validation_errors` | short, bounded error summary (never a stack trace) |
| `capture_timestamp_source` | exact capture time vs named approximation |

## 4. Proposed DDL

```sql
-- V10__live_experiment_traceability.sql
ALTER TABLE network_flows
    ADD COLUMN experiment_id VARCHAR(64),
    ADD COLUMN run_id VARCHAR(64),
    ADD COLUMN scenario_id VARCHAR(64),
    ADD COLUMN validation_status VARCHAR(32),
    ADD COLUMN validation_errors VARCHAR(1000),
    ADD COLUMN capture_timestamp_source VARCHAR(48);

CREATE INDEX idx_network_flows_run_id ON network_flows (run_id);
CREATE INDEX idx_network_flows_experiment_id ON network_flows (experiment_id);

COMMENT ON COLUMN network_flows.validation_status IS
    'Pipeline and data integrity only. A misclassified flow is still VALID.';
COMMENT ON COLUMN network_flows.capture_timestamp_source IS
    'cicflowmeter_flow_timestamp when exact; approximate_agent_read_time otherwise.';
```

All six columns are nullable with no default, so every existing row stays valid and the
migration takes no table rewrite beyond adding the columns.

`validation_errors` is capped at 1000 characters. Stack traces are never persisted; the
producer truncates each entry and keeps at most ten.

## 5. Affected artefacts

| Layer | File | Change |
|---|---|---|
| entity | `entity/NetworkFlow.java` | six `@Column` fields |
| DTO in | `dto/NetworkFlowIngestRequest.java` | six optional record components |
| DTO out | `dto/NetworkFlowResponse.java` | six components, plus the constructor call in `NetworkFlowService.toResponse` |
| service | `service/NetworkFlowService.java` | six builder lines in `processFlowResult` |
| endpoint | `POST /api/alarms/ingest` | no signature change; new fields optional |
| query | `NetworkFlowRepository` | optional `findByRunId` for operational lookup |
| producer | `app/services/spring_client.py` | six optional keyword arguments |
| frontend | `network-flow.model.ts` | optional fields only if the UI should surface them |

## 6. Backward compatibility

* **Existing callers are unaffected.** Every new field is optional; the replay path and any
  current live agent keep working unchanged.
* **Existing rows are unaffected.** All columns are nullable; no backfill is required.
* `spring.jpa.hibernate.ddl-auto` is `validate`, so the entity and the migration must land
  **together**. Deploying the entity change without the migration fails application
  startup. This is the main deployment risk and the reason the two must be one commit.
* Migration ordering: the next free version is **V10**; `V1`–`V9` are already applied.
  Flyway will refuse a checksum change to any existing file, so nothing below V10 may be
  edited.
* No enum values change, so no existing `DatasetSource` or `FlowLabel` data is touched.

## 7. Rollback

* **Forward-only rollback** (preferred, Flyway convention): add `V11__revert_live_traceability.sql`
  dropping the two indexes and the six columns. Data in those columns is lost, which is
  acceptable because the file-based ledger in `reports/live_evaluation/` remains the source
  of truth for every thesis metric.
* **Code rollback alone is unsafe**: reverting the entity while V10 stays applied is fine
  (`ddl-auto: validate` tolerates extra columns), but reverting the migration while the
  entity still declares the fields breaks startup. Roll back code first, schema second.
* A dump of `network_flows` before applying V10 is cheap insurance and is recommended.

## 8. Recommendation

Do **not** apply this for Phase 16. Run the laboratory experiment on the file-based ledger
first. Apply V10 later only if operational querying of laboratory flows turns out to be
wanted for the dashboard, at which point it is an isolated, low-risk, additive change.

Awaiting explicit approval. No migration has been written to `db/migration`, no schema has
been altered, and no experimental flow has been written to PostgreSQL.
