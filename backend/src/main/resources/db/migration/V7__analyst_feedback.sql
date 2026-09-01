CREATE TABLE analyst_feedback (
    id                      UUID PRIMARY KEY,
    alarm_id                UUID NOT NULL REFERENCES alarms (id),
    network_flow_id         UUID NOT NULL REFERENCES network_flows (id),
    incident_id             UUID REFERENCES incidents (id),
    original_prediction     VARCHAR(20) NOT NULL,
    original_attack_type    VARCHAR(100),
    original_confidence     DOUBLE PRECISION,
    original_anomaly_score  DOUBLE PRECISION,
    detection_method        VARCHAR(30),
    analyst_verdict         VARCHAR(20) NOT NULL,
    analyst_attack_type     VARCHAR(100),
    analyst_username        VARCHAR(100) NOT NULL,
    notes                   TEXT,
    model_id                UUID REFERENCES ml_models (id),
    model_name              VARCHAR(150),
    model_version           VARCHAR(50),
    feature_version         VARCHAR(50),
    feature_vector          JSONB NOT NULL,
    ground_truth_label      VARCHAR(100),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE network_flows
    ADD COLUMN ground_truth_attack_type VARCHAR(100);

CREATE INDEX idx_network_flows_known_label ON network_flows (label)
    WHERE label <> 'UNKNOWN';

CREATE INDEX idx_analyst_feedback_alarm_id ON analyst_feedback (alarm_id);
CREATE INDEX idx_analyst_feedback_verdict ON analyst_feedback (analyst_verdict);
CREATE INDEX idx_analyst_feedback_model_id ON analyst_feedback (model_id);
CREATE INDEX idx_analyst_feedback_created_at ON analyst_feedback (created_at DESC);
