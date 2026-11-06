# `scripts` folder

This folder contains **helper scripts** for the monorepo: development automation, maintenance utilities, repetitive tasks (setup, lint, migrations, data generation, etc.), and internal tooling.

- **Main purpose**: group support tools that do not belong to a specific app, agent, or pipeline but make the team’s work easier.
- **Recommendation**: document each script (what it does, parameters, requirements, usage examples) and keep them reproducible (and safe) across environments.

> _Spanish version: [README.es.md](./README.es.md)._

## Nightly telemetry export

Run `python scripts/nightly_export.py` to export the previous UTC day to
`data/raw/telemetry_YYYY-MM-DD.csv` and launch the existing ETL as a separate
subprocess. The CSV is a backup/audit snapshot; the ETL continues to read
`public.telemetry_events` from PostgreSQL and receives the ISO Monday of the
week containing the target date.

- Required source settings: `TELEMETRY_DATABASE_URL` (read-only role) and
	`TELEMETRY_DATABASE_READ_ONLY=true`. Job state uses `JOB_RUNS_DATABASE_URL`,
	falling back to `DATABASE_URL`; that role needs insert/update access to
	`public.job_runs`.
- `TARGET_DATE=YYYY-MM-DD` (strict format) overrides the target date for tests
	without code changes; `--target-date YYYY-MM-DD` is also supported and takes
	precedence. Without an override, the previous UTC day is selected.
- Apply `services/api/migrations/004_job_runs.sql` before scheduling. The
	implementation deliberately uses the OS `crontab`: this script is a standalone
	process and launches ETL as a subprocess. It does not run inside FastAPI and
	does not use APScheduler, `@repeat_every`, or API lifespan hooks, isolating the
	workload from the API's main thread and HTTP lifecycle.
- Recommended expression: `0 2 * * *` (daily at 02:00). Configure cron in UTC
	for a stable schedule; use `CRON_TZ=UTC` where supported, or configure the host
	timezone/convert the local time. Do not set `TARGET_DATE` for the ordinary
	daily cron entry; use it for explicit-date testing only.
- Logs use INFO for start (`processing`), finish (`completed`), and duplicate or
	lock omission (`skipped`); exceptions are ERROR with traceback (`failed`).
	Every record includes a UTC timestamp, `job=<name>`, and `status=<result>`.
	Redirect output to a host log collector/file and configure rotation outside
	the script.

Example crontab entry:

```cron
CRON_TZ=UTC
0 2 * * * cd /path/to/monorepo && /path/to/monorepo/.venv/bin/python scripts/nightly_export.py >> /var/log/nexova-nightly-export.log 2>&1
```

For a manual test, run `TARGET_DATE=2026-11-05 /path/to/monorepo/.venv/bin/python
scripts/nightly_export.py` (replace with the desired date). A target already
recorded as completed will be skipped.
