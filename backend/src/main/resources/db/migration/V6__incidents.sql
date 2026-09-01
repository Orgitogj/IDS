CREATE TABLE incidents (
    id                    UUID PRIMARY KEY,
    correlation_key       VARCHAR(300) NOT NULL,
    source_ip             VARCHAR(45),
    attack_type           VARCHAR(100),
    detection_method      VARCHAR(30),
    destination_ips       JSONB NOT NULL DEFAULT '[]'::jsonb,
    destinations_truncated BOOLEAN NOT NULL DEFAULT false,
    first_seen            TIMESTAMPTZ NOT NULL,
    last_seen             TIMESTAMPTZ NOT NULL,
    flow_count            BIGINT NOT NULL DEFAULT 0,
    alarm_count           BIGINT NOT NULL DEFAULT 0,
    severity              VARCHAR(20) NOT NULL,
    status                VARCHAR(20) NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_incidents_correlation_key ON incidents (correlation_key);
CREATE INDEX idx_incidents_status ON incidents (status);
CREATE INDEX idx_incidents_last_seen ON incidents (last_seen DESC);

ALTER TABLE alarms
    ADD COLUMN incident_id UUID REFERENCES incidents (id);

CREATE INDEX idx_alarms_incident_id ON alarms (incident_id);
