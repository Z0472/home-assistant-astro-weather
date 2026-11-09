CREATE TABLE IF NOT EXISTS astro_forecast_snapshots (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    location_key text NOT NULL,
    generated_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    backend_version text NOT NULL,
    weather jsonb NOT NULL,
    decision jsonb NOT NULL,
    moon jsonb NOT NULL,
    UNIQUE (location_key, generated_at)
);
CREATE INDEX IF NOT EXISTS astro_forecast_location_id
    ON astro_forecast_snapshots (location_key, id DESC);
