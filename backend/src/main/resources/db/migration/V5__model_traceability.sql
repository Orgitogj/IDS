ALTER TABLE ml_models
    ADD COLUMN version         VARCHAR(50) NOT NULL DEFAULT '1.0',
    ADD COLUMN feature_version VARCHAR(50);

ALTER TABLE network_flows
    ADD COLUMN model_id         UUID REFERENCES ml_models (id),
    ADD COLUMN model_name       VARCHAR(150),
    ADD COLUMN model_version    VARCHAR(50),
    ADD COLUMN feature_version  VARCHAR(50),
    ADD COLUMN detection_method VARCHAR(30),
    ADD COLUMN anomaly_score    DOUBLE PRECISION;

CREATE INDEX idx_network_flows_created_at ON network_flows (created_at DESC);
CREATE INDEX idx_network_flows_model_id ON network_flows (model_id);
