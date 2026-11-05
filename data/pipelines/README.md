# Weekly Nexova business performance pipeline

`pipeline.py` is the Prefect 3 entry point for the `weekly_office_program_performance` flow. It has independent tasks for resolving the week, creating a run record, extracting source events, transforming KPI rows, loading the target partition, and writing an optional evaluation summary.

## Run locally

Apply `migrations/001_reporting_weekly_office_program_performance.sql` to the target PostgreSQL database first. Configure separate credentials:

- `TELEMETRY_DATABASE_URL`: read-only PostgreSQL role for `public.telemetry_events`.
- `TELEMETRY_DATABASE_READ_ONLY=true`: required explicit confirmation of the source role's permissions.
- `REPORTING_DATABASE_URL`: PostgreSQL credentials with write access to the `reporting` schema.

Then run either:

```bash
uv run python -m data.pipelines.pipeline [YYYY-MM-DD]
# or, after installing the project:
uv run business-performance-pipeline [YYYY-MM-DD]
```

The optional date must be an ISO-week Monday. Without a date, the most recently completed UTC week is selected. The evaluation artifact is written under `data/eval/` and is non-critical.

Each audit run is linked to its Prefect flow-run ID. The flow queries only the four approved event types, aggregates the configured Nexova programme catalog and local office currencies, and transactionally replaces the selected reporting week. The source telemetry table is never mutated. The transformation task caches successful results for one hour; extraction and loading use Prefect retries.

Synthetic test data lives in `data/raw/business_performance_sample.json`; transformation tests are under `data/pipelines/tests/`.
