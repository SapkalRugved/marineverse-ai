CREATE TABLE ocean_conditions (
    ocean_id BIGSERIAL PRIMARY KEY,
    valid_time TIMESTAMPTZ,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    location GEOGRAPHY(POINT, 4326),
    depth_m REAL DEFAULT 0,

    current_u_mps REAL NULL,
    current_v_mps REAL NULL,
    current_speed_mps REAL NULL,
    current_direction_deg REAL NULL,

    sea_surface_temperature_c REAL NULL,

    wave_height_m REAL NULL,
    wave_direction_deg REAL NULL,
    wave_period_s REAL NULL,

    is_forecast BOOLEAN,
    source VARCHAR(50),
    source_dataset VARCHAR(150),
    ingested_at TIMESTAMPTZ
);