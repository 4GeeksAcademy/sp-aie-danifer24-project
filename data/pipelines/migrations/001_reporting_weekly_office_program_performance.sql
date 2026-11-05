CREATE SCHEMA IF NOT EXISTS reporting;

CREATE TABLE IF NOT EXISTS reporting.weekly_office_program_performance (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    office text NOT NULL CHECK (office IN ('valencia', 'miami')),
    programme_id text NOT NULL,
    week_start date NOT NULL,
    total_material_cost numeric NOT NULL DEFAULT 0,
    kits_delivered_count integer NOT NULL DEFAULT 0,
    shortage_events_count integer NOT NULL DEFAULT 0,
    cost_variance_events_count integer NOT NULL DEFAULT 0,
    currency text NOT NULL CHECK (currency IN ('EUR', 'USD')),
    computed_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_weekly_office_program_performance
        UNIQUE (office, programme_id, week_start),
    CONSTRAINT ck_weekly_office_program_performance_currency
        CHECK ((office = 'valencia' AND currency = 'EUR') OR (office = 'miami' AND currency = 'USD'))
);

CREATE TABLE IF NOT EXISTS reporting.pipeline_runs (
    run_id text PRIMARY KEY,
    flow_name text NOT NULL,
    status text NOT NULL CHECK (status IN ('Running', 'Completed', 'Failed')),
    week_start date NOT NULL,
    started_at timestamptz NOT NULL,
    ended_at timestamptz,
    processed_records integer NOT NULL DEFAULT 0,
    accepted_records integer NOT NULL DEFAULT 0,
    rejected_records integer NOT NULL DEFAULT 0,
    rows_written integer NOT NULL DEFAULT 0,
    error_code text,
    error_message text
);
