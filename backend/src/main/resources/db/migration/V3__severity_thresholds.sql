CREATE TABLE severity_thresholds (
    id           UUID PRIMARY KEY,
    critical_min DOUBLE PRECISION NOT NULL,
    high_min     DOUBLE PRECISION NOT NULL,
    medium_min   DOUBLE PRECISION NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO severity_thresholds (id, critical_min, high_min, medium_min)
VALUES ('00000000-0000-0000-0000-000000000001', 0.95, 0.85, 0.70);
