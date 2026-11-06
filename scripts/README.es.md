# Carpeta `scripts`

Esta carpeta contiene **scripts auxiliares** del monorepo: automatizaciones de desarrollo, utilidades de mantenimiento, tareas repetitivas (setup, lint, migraciones, generación de datos, etc.) y tooling interno.

- **Propósito principal**: agrupar herramientas de soporte que no pertenecen a una app/agente/pipeline específico, pero facilitan el trabajo del equipo.
- **Recomendación**: documenta cada script (qué hace, parámetros, requisitos, ejemplos de uso) y procura que sean reproducibles (y seguros) en distintos entornos.

## Exportación nocturna de telemetría

`python scripts/nightly_export.py` exporta a `data/raw/telemetry_YYYY-MM-DD.csv` el día anterior en UTC y luego inicia el pipeline existente como un subproceso independiente. El CSV es un snapshot de respaldo/auditoría; el pipeline sigue leyendo `public.telemetry_events` desde PostgreSQL y recibe el lunes ISO de la semana de `TARGET_DATE`.

- Variables requeridas: `TELEMETRY_DATABASE_URL` (rol de solo lectura) y `TELEMETRY_DATABASE_READ_ONLY=true`. Para el estado de `public.job_runs`, se usa `JOB_RUNS_DATABASE_URL` o, como fallback, `DATABASE_URL`; ese rol necesita permisos de inserción y actualización en la tabla.
- `TARGET_DATE=YYYY-MM-DD` (formato estricto) cambia el día de destino para pruebas sin modificar código; también se admite `--target-date YYYY-MM-DD`, que tiene precedencia. Sin override se procesa el día anterior en UTC.
- El registro único por `(job_name, target_date)` en `job_runs` lleva los estados `pending → processing → completed|failed`. Cualquier fila `processing` de `nightly_export` impide otra ejecución, incluso para otra fecha. Si la fecha ya está `completed`, no se repiten ni la exportación ni el pipeline. La omisión se informa por salida estándar, sin modificar la fila activa o completada. Los fallos guardan el mensaje de excepción saneado.
- La migración `services/api/migrations/004_job_runs.sql` debe estar aplicada antes de programar el job. La decisión de implementación es usar `crontab` del sistema operativo: el script es un proceso Python independiente que lanza el ETL como subproceso; no se ejecuta dentro de FastAPI ni usa APScheduler, `@repeat_every` o hooks de lifespan. Esto aísla el trabajo del hilo y ciclo de vida de la API.
- Expresión recomendada: `0 2 * * *` (una ejecución diaria a las 02:00). Configure cron en UTC para que el horario sea estable; donde esté soportado, `CRON_TZ=UTC` define esa zona. Si el sistema no admite `CRON_TZ`, ajuste la zona horaria del host o convierta la hora local. `TARGET_DATE` no debe fijarse en la entrada diaria normal; úselo solo para ejecutar una fecha explícita en pruebas.
- Los eventos del job se registran por `logging`: INFO para inicio (`processing`), fin (`completed`) y omisión por duplicado/bloqueo (`skipped`); ERROR con traceback para excepciones (`failed`). Cada registro incluye timestamp UTC, `job=<nombre>` y `status=<estado>`. Redirija stdout/stderr a un archivo o al colector de logs del host; configure rotación fuera del script.

```cron
CRON_TZ=UTC
0 2 * * * cd /ruta/al/monorepo && /ruta/al/monorepo/.venv/bin/python scripts/nightly_export.py >> /var/log/nexova-nightly-export.log 2>&1
```

Para una ejecución manual de prueba, ejecute `TARGET_DATE=2026-11-05 /ruta/al/monorepo/.venv/bin/python scripts/nightly_export.py` (reemplace la fecha). La misma fecha no repetirá el trabajo si ya figura como completada.
