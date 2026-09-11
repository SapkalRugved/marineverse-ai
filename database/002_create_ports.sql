CREATE TABLE ports (
    port_id BIGSERIAL PRIMARY KEY,
    source_id TEXT,
    name VARCHAR(200),
    country VARCHAR(100) NULL,
    port_type VARCHAR(50) NULL,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    location GEOGRAPHY(POINT, 4326),
    source VARCHAR(50),
    updated_at TIMESTAMPTZ,

    CONSTRAINT uq_ports_source_source_id
        UNIQUE (source, source_id)
);

CREATE INDEX idx_ports_location_gist
    ON ports
    USING GIST (location);

CREATE INDEX idx_ports_name
    ON ports (name);