CREATE TABLE drift_reports (
    id                     UUID PRIMARY KEY,
    status                 VARCHAR(20) NOT NULL,
    feature_version        VARCHAR(50),
    observed_flows         BIGINT NOT NULL,
    accepted_flows         BIGINT NOT NULL,
    rejected_flows         BIGINT NOT NULL,
    sample_size            INTEGER NOT NULL,
    invalid_rate           DOUBLE PRECISION NOT NULL,
    drifted_feature_count  INTEGER NOT NULL,
    drifted_fraction       DOUBLE PRECISION NOT NULL,
    calibration_window     INTEGER,
    reasons                JSONB NOT NULL DEFAULT '[]'::jsonb,
    drifted_features       JSONB NOT NULL DEFAULT '[]'::jsonb,
    details                JSONB NOT NULL DEFAULT '{}'::jsonb,
    generated_at           TIMESTAMPTZ NOT NULL,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_drift_reports_created_at ON drift_reports (created_at DESC);
CREATE INDEX idx_drift_reports_status ON drift_reports (status);
