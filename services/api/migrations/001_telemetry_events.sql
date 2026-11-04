-- Telemetry is immutable: create the append-only table, indexes, and write guard.
CREATE TABLE IF NOT EXISTS public.telemetry_events (
    event_id varchar(36) PRIMARY KEY,
    event_type varchar(128) NOT NULL,
    timestamp timestamptz NOT NULL,
    service varchar(64) NOT NULL,
    tags jsonb NOT NULL,
    session_id varchar(36),
    user_id varchar(67),
    schema_version varchar(16) NOT NULL,
    request_id varchar(36) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_telemetry_events_timestamp
    ON public.telemetry_events USING btree (timestamp);
CREATE INDEX IF NOT EXISTS ix_telemetry_events_event_type
    ON public.telemetry_events USING btree (event_type);
CREATE INDEX IF NOT EXISTS ix_telemetry_events_tags_gin
    ON public.telemetry_events USING gin (tags);

-- Supabase grants broad defaults in public; revoke browser access explicitly.
REVOKE ALL ON TABLE public.telemetry_events FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON TABLE public.telemetry_events TO service_role;

CREATE OR REPLACE FUNCTION public.reject_telemetry_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'telemetry_events rows are immutable; % is not allowed', TG_OP
        USING ERRCODE = '55000';
END;
$$;

DROP TRIGGER IF EXISTS telemetry_events_immutable ON public.telemetry_events;
CREATE TRIGGER telemetry_events_immutable
    BEFORE UPDATE OR DELETE ON public.telemetry_events
    FOR EACH ROW EXECUTE FUNCTION public.reject_telemetry_event_mutation();
DROP TRIGGER IF EXISTS telemetry_events_no_truncate ON public.telemetry_events;
CREATE TRIGGER telemetry_events_no_truncate
    BEFORE TRUNCATE ON public.telemetry_events
    FOR EACH STATEMENT EXECUTE FUNCTION public.reject_telemetry_event_mutation();

ALTER TABLE public.telemetry_events ENABLE ROW LEVEL SECURITY;
