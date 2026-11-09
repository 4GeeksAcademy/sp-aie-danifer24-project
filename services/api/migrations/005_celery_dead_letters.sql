-- Terminal Celery failures after exhausting automatic retries.
-- Kept separate from public.job_runs and reporting.pipeline_runs: this table
-- records broker task delivery/retry diagnostics, not ETL/business run state.
CREATE TABLE IF NOT EXISTS public.celery_dead_letters (
    task_id text PRIMARY KEY,
    attempt integer NOT NULL CHECK (attempt > 0),
    error_message text NOT NULL,
    failed_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_celery_dead_letters_failed_at
    ON public.celery_dead_letters (failed_at DESC);
