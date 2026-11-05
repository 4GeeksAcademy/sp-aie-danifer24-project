# Pipeline semanal de desempeño de negocio Nexova

`pipeline.py` es el punto de entrada Prefect 3 del flow `weekly_office_program_performance`. Contiene tasks independientes para resolver la semana, registrar la corrida, extraer eventos, transformar KPIs, publicar la partición y crear un resumen opcional de evaluación.

## Ejecución local

Primero aplica `migrations/001_reporting_weekly_office_program_performance.sql` a PostgreSQL. Configura credenciales separadas:

- `TELEMETRY_DATABASE_URL`: rol PostgreSQL de solo lectura para `public.telemetry_events`.
- `TELEMETRY_DATABASE_READ_ONLY=true`: confirmación explícita de que el rol de origen es de solo lectura.
- `REPORTING_DATABASE_URL`: credenciales PostgreSQL con escritura en el esquema `reporting`.

Ejecuta:

```bash
uv run python -m data.pipelines.pipeline [YYYY-MM-DD]
# o, con el proyecto instalado:
uv run business-performance-pipeline [YYYY-MM-DD]
```

La fecha opcional debe ser lunes ISO. Sin fecha, se usa la última semana UTC completada. El artefacto de evaluación se guarda en `data/eval/` y no es crítico.

Cada registro de auditoría se vincula al ID de la corrida Prefect. La extracción consulta solo los cuatro tipos de evento aprobados. La transformación usa el catálogo Nexova y moneda local de cada oficina; la carga reemplaza transaccionalmente la partición semanal. La fuente de telemetría nunca se modifica. La task de transformación cachea resultados una hora; extracción y carga tienen reintentos Prefect.

Los datos sintéticos están en `data/raw/business_performance_sample.json`; las pruebas de transformación, en `data/pipelines/tests/`.
