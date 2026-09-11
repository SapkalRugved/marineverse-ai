CREATE TABLE ingestion_runs (
    run_id BIGSERIAL PRIMARY KEY,
    pipeline VARCHAR(100),
    source VARCHAR(100),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ NULL,
    status VARCHAR(20),
    records_read INTEGER,
    records_written INTEGER,
    error_message TEXT NULL
);
