CREATE TABLE weather_conditions (
    weather_id BIGSERIAL PRIMARY KEY,
    valid_time TIMESTAMPTZ,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    location GEOGRAPHY(POINT, 4326),
    air_temperature_c REAL NULL,
    pressure_hpa REAL NULL,
    precipitation_mm REAL NULL,
    wind_speed_mps REAL NULL,
    wind_direction_deg REAL NULL,
    wind_gust_mps REAL NULL,
    is_forecast BOOLEAN,
    source VARCHAR(50),
    source_dataset VARCHAR(100),
    ingested_at TIMESTAMPTZ
);