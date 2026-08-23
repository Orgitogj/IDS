ALTER TABLE explanations DROP CONSTRAINT IF EXISTS explanations_alarm_id_key;

CREATE UNIQUE INDEX IF NOT EXISTS ux_explanations_alarm_model_prompt
    ON explanations (alarm_id, llm_model, llm_prompt_version);

CREATE INDEX IF NOT EXISTS ix_explanations_alarm_id
    ON explanations (alarm_id);

ALTER TABLE explanations
    ADD COLUMN IF NOT EXISTS rating                VARCHAR(20),
    ADD COLUMN IF NOT EXISTS rated_at              TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS generation_latency_ms DOUBLE PRECISION;
