CREATE TABLE vessels (
    vessel_id BIGSERIAL PRIMARY KEY,
    mmsi BIGINT UNIQUE,
    imo BIGINT NULL,
    name VARCHAR(200) NULL,
    ship_type VARCHAR(100) NULL,
    length_m REAL NULL,
    width_m REAL NULL,
    source VARCHAR(50),
    updated_at TIMESTAMPTZ
);