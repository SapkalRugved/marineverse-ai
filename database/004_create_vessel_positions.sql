CREATE TABLE vessel_positions (
    position_id BIGSERIAL PRIMARY KEY,
    vessel_id BIGINT,
    observed_at TIMESTAMPTZ,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    location GEOGRAPHY(POINT, 4326),
    speed_mps REAL NULL,
    course_deg REAL NULL,
    heading_deg REAL NULL,
    navigation_status VARCHAR(50) NULL,
    source VARCHAR(50),
    ingested_at TIMESTAMPTZ,

    CONSTRAINT fk_vessel_positions_vessel
        FOREIGN KEY (vessel_id)
        REFERENCES vessels(vessel_id)
);

CREATE INDEX idx_vessel_positions_location_gist
    ON vessel_positions
    USING GIST (location);

CREATE INDEX idx_vessel_positions_vessel_observed_at
    ON vessel_positions (vessel_id, observed_at);

CREATE INDEX idx_vessel_positions_observed_at
    ON vessel_positions (observed_at);