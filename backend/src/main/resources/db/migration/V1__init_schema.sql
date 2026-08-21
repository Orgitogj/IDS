CREATE TABLE network_flows (
    id                      UUID PRIMARY KEY,
    dataset_source          VARCHAR(50) NOT NULL,
    source_ip               VARCHAR(45),
    destination_ip          VARCHAR(45),
    source_port             INTEGER,
    destination_port        INTEGER,
    protocol                VARCHAR(20),
    feature_vector          JSONB NOT NULL,
    label                   VARCHAR(20) NOT NULL,
    attack_type             VARCHAR(100),
    predicted_label         VARCHAR(20),
    prediction_confidence   DOUBLE PRECISION,
    flow_timestamp          TIMESTAMPTZ NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_network_flows_dataset_source ON network_flows (dataset_source);
CREATE INDEX idx_network_flows_label ON network_flows (label);
CREATE INDEX idx_network_flows_source_ip ON network_flows (source_ip);
CREATE INDEX idx_network_flows_destination_ip ON network_flows (destination_ip);

CREATE TABLE alarms (
    id                  UUID PRIMARY KEY,
    network_flow_id     UUID NOT NULL UNIQUE REFERENCES network_flows (id),
    severity            VARCHAR(20) NOT NULL,
    status              VARCHAR(20) NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    acknowledged_at     TIMESTAMPTZ,
    resolved_at          TIMESTAMPTZ
);

CREATE INDEX idx_alarms_status ON alarms (status);

CREATE TABLE explanations (
    id                    UUID PRIMARY KEY,
    alarm_id              UUID NOT NULL UNIQUE REFERENCES alarms (id),
    explanation_text      TEXT NOT NULL,
    llm_model             VARCHAR(100) NOT NULL,
    llm_prompt_version    VARCHAR(50) NOT NULL,
    generated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ml_models (
    id                    UUID PRIMARY KEY,
    algorithm             VARCHAR(50) NOT NULL,
    name                  VARCHAR(150) NOT NULL UNIQUE,
    trained_on_dataset    VARCHAR(50) NOT NULL,
    artifact_path         VARCHAR(500) NOT NULL,
    hyperparameters       TEXT,
    feature_set           TEXT,
    active                BOOLEAN NOT NULL DEFAULT false,
    trained_at            TIMESTAMPTZ NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE experiment_results (
    id                    UUID PRIMARY KEY,
    ml_model_id           UUID NOT NULL REFERENCES ml_models (id),
    tested_on_dataset     VARCHAR(50) NOT NULL,
    feature_set_used      TEXT,
    accuracy              DOUBLE PRECISION NOT NULL,
    precision_score       DOUBLE PRECISION NOT NULL,
    recall                DOUBLE PRECISION NOT NULL,
    f1_score              DOUBLE PRECISION NOT NULL,
    avg_latency_ms        DOUBLE PRECISION,
    sample_size           BIGINT,
    notes                 TEXT,
    ran_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_experiment_results_ml_model_id ON experiment_results (ml_model_id);
