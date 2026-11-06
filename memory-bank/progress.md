## Instrumentación amplia de telemetría de frontend (2026-11-04)

- Creado `packages/shared/telemetry-service.ts`: cliente universal reutilizable en todas las apps (Website, Backoffice, Tracker) con validación estricta de eventos contra schema, cola en memoria, reintentos exponenciales, pseudonimización de userId con HMAC, y sendBeacon al cerrar sesión.
- Creado `packages/shared/telemetry-events.ts`: funciones helpers tipadas para todos los eventos del plan (inbound/outbound orders, stock threshold, cost variance, validation failures, auth, data loads, etc.), allowlists respetadas, sin PII directa.
- Implementados hooks React reutilizables en cada app (`lib/telemetry-hooks.tsx`): useTelemetryPageView (captura navegación), useGlobalErrorHandlers (window.onerror, unhandledrejection), TelemetryErrorBoundary (captura render errors con fingerprint SHA-256 sanitizado), useTelemetryDataLoad (cargas de datos).
- Actualizado layout raíz en Backoffice, Website y Tracker con ClientLayout wrapper que aplica Error Boundary global y hooks de telemetría; page views se capturan automáticamente al navegar.
- Creados proxies de telemetría en cada app (`app/api/telemetry/events/route.ts`) que reenvan eventos al backend FastAPI en desarrollo (127.0.0.1:8000) o variable de entorno `TELEMETRY_ENDPOINT` en producción.
- Actualizado `packages/shared/telemetry.ts` para exportar TELEMETRY_SCHEMA_VERSION; refactorizado TelemetryService desde Backoffice a una clase reutilizable con soporte para configuración custom (endpoint, batchSize, retryDelays, appVersion).
- Piso técnico transversal instrumentado: page views en secciones principales, latencias API (route_template, method, status, duration_ms), errores globales no capturados (error_boundary/window_error/unhandled_rejection), cargas de datos (section, outcome, duration_ms, reason_code).
- Todas las métricas obligatorias del contexto (CONTEXT-06) incluidas: inbound/outbound orders, stock thresholds, direct edit rejections, cost variance, validations, login/session, data loads.
- Validación: typecheck sin errores (Backoffice, Website); lint sin errores; build exitoso Backoffice y Website; Tracker build falla por error preexistente en services/api.ts (no relacionado a telemetría).
- Documentado en `docs/telemetry/TELEMETRY-FRONTEND.md`: arquitectura, cómo verificar en DevTools Network, ejemplos de eventos capturados, instrucciones para instrumentar nuevos eventos, validaciones locales aplicadas.
- Script demo creado: `scripts/telemetry-demo.sh` arranca Backend + Backoffice para verificar events en DevTools Network.
- Pendiente: persistencia de eventos en base de datos, reportes ejecutivos, alertas por umbrales, seeds de datos de prueba para validar flujos de inventario end-to-end.

## Persistencia de telemetría en Supabase (2026-11-04)

- Implementado `POST /telemetry/events` con validación individual de cada evento contra `docs/telemetry/event-schemas.json`, persistencia bulk, idempotencia por `eventId` y respuesta `received/stored/rejected`; `properties` se conserva en `tags` JSONB. Frontend intacto.
- Aplicada `services/api/migrations/001_telemetry_events.sql` a Supabase. Verificado: índice GIN de `tags` y B-tree de timestamp/event_type; índices compuestos preexistentes preservados; RLS activada; roles `anon` y `authenticated` sin grants, `service_role` limitado a SELECT/INSERT; triggers UPDATE/DELETE/TRUNCATE activos; tabla sigue con 0 filas.
- Probados los tres triggers de inmutabilidad mediante operaciones temporales con rollback; ninguna fila de prueba quedó persistida.
- Verificación local: suite backend 60 passed y 7 subtests, un warning preexistente de Starlette/httpx; `uv lock --check`, `compileall`, `git diff --check` y revisión del editor correctos.
- Ajuste posterior: `TelemetryEvent` se conserva idéntico al modelo Pydantic previo; la validación del JSON Schema canónico se ejecuta por evento en el handler. Añadida prueba HTTP que confirma respuesta 200 y ACK `{received, stored, rejected}` compatible con el TelemetryService.
- Verificación final: suite backend 61 passed y 7 subtests; un warning preexistente de Starlette/httpx; `compileall`, `git diff --check` y revisión del editor sin errores.
- Pendiente: desplegar backend actualizado. Corrección del handler/documentación/tests pendiente de commit.

## Captura de telemetria: TelemetryService de Backoffice (2026-11-03)

- Añadido `uis/backoffice/lib/telemetry.ts`: API unica `track()`, envelope automatico, allowlists y validaciones locales, cola en memoria (20 eventos/10 s), proxy same-origin, reintentos y `sendBeacon` al ocultar/cerrar.
- Backoffice captura login, secciones autorizadas, cargas de inventario/proveedores/incidencias/perfil, validaciones de orden y respuestas HTTP de clientes centrales. No se instrumentaron otras apps ni se incluyeron nombres, valores de formularios, tokens o cuerpos.
- `GET /auth/me` entrega `telemetry_user_id` HMAC con clave/env dedicados; sin pseudonimo los eventos que requieren identidad se omiten, nunca se usa el ID crudo.
- Validacion: typecheck, lint y 18 pruebas Backoffice; 19 pruebas auth extendidas; pruebas aisladas de stub y HMAC. `sendBeacon` es best-effort, no confirmacion de persistencia.
- Pendiente: los cinco obligatorios de inventario requieren metadatos/modelo o rutas que aun no existen (programa/categoria/coste/minimo/rechazo explicito). El stub no persiste y no aplica allowlists especificas. No se modifico el esquema de inventario ni se crearon seeds.

# Progreso del proyecto

## Orquestación de exportación nocturna (2026-11-06)

- Añadida la migración `services/api/migrations/004_job_runs.sql` para `public.job_runs`, con estados `pending`/`processing`/`completed`/`failed` y unicidad diaria por `(job_name, target_date)`, separada de `reporting.pipeline_runs`.
- Implementada `services/job_runs.py` para persistir la transición pending→processing y terminal, serializar adquisiciones mediante la fila diaria, omitir una ejecución ya activa/completada y recuperar como obsoleta una fila processing con más de 24 horas.
- Añadido `scripts/nightly_export.py`: resuelve `TARGET_DATE` o ayer UTC; exporta `public.telemetry_events` por rango UTC a CSV sin sobrescribir snapshots; luego invoca el CLI existente del pipeline en un subproceso para la semana ISO del día objetivo. El pipeline continúa leyendo PostgreSQL, no el CSV.
- La ejecución no se integra en FastAPI: queda para cron/scheduler externo. Documentados entorno, migración y ejemplo de cron en `scripts/README.es.md`; añadida la dependencia directa `python-dotenv`.
- Pruebas nuevas para calendario UTC, exportación idempotente, comando ETL, omisión por concurrencia, estado failed/completed y persistencia del ciclo; validación conjunta `uv run pytest services/tests/test_job_runs.py scripts/tests/test_nightly_export.py data/pipelines/tests -q`: 27 passed.
- Pendiente aplicar la migración en la base autorizada, conceder al rol dedicado de job permisos mínimos sobre `public.job_runs`, configurar cron y ejecutar una prueba de integración controlada. No se ejecutó la exportación contra telemetría real.

## Dashboard empresarial de reporting semanal (2026-11-05)

- Añadida la página protegida `/reporting` en Backoffice, dirigida a stakeholders de negocio: consume los resultados semanales reales mediante un proxy Next autenticado hacia `GET /reporting/weekly-office-program-performance` y muestra el rango lunes-domingo de `week_start`.
- Presenta los cuatro KPIs con sus nombres del briefing —Costo de material por oficina/programa, Kits entregados, Frecuencia de escasez y Frecuencia de variación de costo— en tabla por oficina/programa; el coste se formatea por fila en EUR o USD sin mezclar monedas.
- Incluye carga, error con reintento, actualización, periodo sin filas y fecha visible; se añadió acceso desde navegación y página inicial, estilos responsivos y clasificación de la vista en telemetría.
- Validación en `uis/backoffice`: `npm run typecheck`, `npm run lint`, Jest (3 suites, 18 tests) y `npm run build` correctos. El build registró `/reporting` y el proxy dinámico. No se llamó al API contra una base real ni se generaron datos de dashboard.
- Pendiente: validar visualmente con una sesión y un reporte semanal disponible en un entorno autorizado. No se creó commit.

### Validación integrada del reporting (2026-11-05)

- Ejecutado el ETL real para la semana iniciada el 2026-11-02: 2 eventos procesados y aceptados, 0 rechazados y 1 fila KPI publicada. La fila corresponde a Valencia / `onboarding-soporte` (20 EUR de material, 1 kit, 0 eventos de escasez y 0 variaciones de coste); se verificó la lectura desde el almacenamiento.
- Aplicadas por el desarrollador las políticas RLS de mínimo privilegio para el rol de escritura de reporting; verificación posterior confirmó las políticas de ambas tablas. Se añade la migración reproducible `data/pipelines/migrations/002_reporting_writer_rls_policies.sql`.
- Corregida la invocación de subflows Prefect: `return_state=True` se pasa al invocar el Flow, no a `with_options()`. Actualizadas las aserciones de regresión. Validación de pipeline anterior: 20 pruebas correctas.
- Diagnóstico del 500 de Reporting: la API activa conservaba la configuración de conexión anterior en memoria. Tras reiniciarla cargando el `.env` actualizado, el endpoint autenticado de FastAPI y el proxy del Backoffice respondieron HTTP 200 para la semana publicada.
- Estado: ETL y consulta de reporting verificados de extremo a extremo en el entorno local autorizado. Pendiente validar la visualización en navegador con la sesión del usuario y definir/configurar el deployment programado de Prefect; la ejecución del ETL no se automatiza desde el dashboard.

## Subflows ETL del pipeline de desempeño (2026-11-05)

- Refactorizado `weekly_office_program_performance` para invocar secuencialmente los subflows Prefect `extract_events_subflow(week_start) -> events`, `transform_business_kpis_subflow(events, week_start) -> aggregate` y `load_week_partition_subflow(aggregate, run_id) -> rows_written`. Los contratos son explícitos y las tasks originales siguen conservando retries, caché y lógica de auditoría/idempotencia.
- Extraído `evaluation_artifact_subflow(aggregate, rows_written, run_id) -> path` como paso opcional. El flow principal lo invoca con `return_state=True, raise_on_failure=False`; un fallo del artefacto se registra como warning y no altera una publicación correcta. La carga igualmente expone su estado al padre para persistir el estado `Failed` antes de relanzar fallos críticos.
- Añadida prueba de topología: valida que las cuatro etapas son flows Prefect, sus entradas declaradas y orden de llamada. README y diseño de pipeline actualizados.
- Validación: `uv run pytest data/pipelines/tests -q` (12 passed), CLI `--help`, `compileall`, `uv lock --check` y `git diff --check` correctos. No se ejecutó ETL ni se conectó a bases de datos.
- Pendiente: desplegar/ejecutar el flow compuesto contra Prefect y PostgreSQL en entorno autorizado; no se creó commit.


## API de reporting para el pipeline de desempeño (2026-11-05)

- Añadido `services/reporting/` como módulo separado de `services/telemetry/`, con router autenticado por la dependencia existente `get_current_user` y schemas Pydantic para auditoría, disparo manual y feed de KPIs. Registrado en `services/api/main.py`; se conserva el envelope de errores común.
- Implementados `GET /reporting/pipeline-runs/latest`, `POST /reporting/pipeline-runs` y `GET /reporting/weekly-office-program-performance`. El último run incluye `flow_run_id` (el pipeline usa el mismo identificador Prefect en `run_id`); el feed entrega `{week_start, entries}` con las dimensiones y métricas del briefing.
- Consultas SQL de reporting encapsuladas en `data/pipelines/reporting_store.py`; el disparo delegado a `data/pipelines/prefect_client.py` solicita el deployment configurado por `BUSINESS_PERFORMANCE_DEPLOYMENT` (por defecto `weekly-office-program-performance/weekly`) y no ejecuta ETL dentro de FastAPI. Prefect se declara también para la imagen/runtime de API.
- Pruebas autenticadas nuevas cubren 401 sin token, respuesta y 404 de auditoría, 202 y errores 422/503 al disparar, serialización/contenido del feed KPI y solicitud mockeada al deployment configurable. No se ejecutó un deployment real.
- Validación: suite conjunta API + pipeline, 86 pruebas y 7 subtests correctos; `compileall`, `uv lock --check` y `git diff --check` correctos. Persiste un warning no bloqueante preexistente de Starlette/httpx.
- Pendiente antes de desplegar: configurar `BUSINESS_PERFORMANCE_DEPLOYMENT` con un deployment Prefect realmente creado, y suministrar a la API acceso de solo lectura a reporting además de las credenciales/URL del servidor Prefect. No se verificó una llamada externa al deployment ni se ejecutó ETL.

## Fase 4: ejecución por CLI y frecuencia de reporting (2026-11-05)

- Confirmado el punto de entrada `if __name__ == "__main__": main()` en `data/pipelines/pipeline.py` y documentado el comando directo `uv run python data/pipelines/pipeline.py [YYYY-MM-DD]` en comentario y `data/pipelines/PIPELINE_DESIGN.md`.
- Documentada la frecuencia prevista: consolidación semanal cada lunes por la mañana UTC. La hora exacta queda por configurar en el deployment/scheduler de Prefect; el CLI manual no crea un calendario.
- Validación local: `uv run python data/pipelines/pipeline.py --help`, 11 pruebas, `compileall`, `uv lock --check` y `git diff --check` correctos.
- Pendiente verificar ejecución ETL completa contra Supabase: el `.env` actual solo expone por nombre `DATABASE_URL`, no `TELEMETRY_DATABASE_URL`, `REPORTING_DATABASE_URL` ni `TELEMETRY_DATABASE_READ_ONLY`. No se ejecutó una carga parcial ni se asumieron credenciales/roles; hacen falta variables de origen y destino con permisos adecuados.

## Fase 3: idempotencia y auditoría del pipeline Prefect

- La carga reconcilia la partición semanal dentro de una transacción protegida por lock: hace `UPSERT` usando la restricción única `(office, programme_id, week_start)` y elimina únicamente claves obsoletas. Las filas con métricas idénticas conservan su `id` y `computed_at`, por lo que reruns idénticos no cambian el resultado de destino.
- `reporting.pipeline_runs` registra inicio UTC, fin, cantidad procesada y estado final. En fallos críticos guarda tipo y detalle sanitizado (enmascara contraseñas PostgreSQL y limita el mensaje); la carga actualiza datos y auditoría de éxito en la misma transacción. Fallos del artefacto de evaluación, que es opcional, se registran en el log sin cambiar el éxito ETL.
- Añadidas pruebas para la sanitización del error y la estrategia de upsert/reconciliación. Validación focal: 11 pruebas correctas; también pasan `compileall`, `uv lock --check`, CLI `--help` y `git diff --check`.
- Pendiente: aplicar la migración y validar contra PostgreSQL en un entorno autorizado; no se conectó a una base ni se ejecutó la migración. Las pruebas de la estrategia SQL son unitarias/inspección de fuente, no una prueba de integración.

## Fase 2: resiliencia del pipeline Prefect (2026-11-05)

- Añadida política de reintentos documentada para cada task con acceso externo: inicio de auditoría (1 reintento/1 s), extracción (3 reintentos/1, 5 y 15 s), carga idempotente (3 reintentos/1, 5 y 15 s) y persistencia de fallo (2 reintentos/1 y 5 s). Los comentarios explican la tolerancia a fallos transitorios, seguridad de repetición y límites de espera.
- El flow captura explícitamente con `return_state=True` el estado de la carga, lee el error y lo vuelve a lanzar tras intentar marcar la corrida como `Failed`; evita perder la auditoría por propagación automática de Prefect.
- Documentada la caché de transformación: `task_input_hash` incluye la tanda completa de eventos y `week_start`, con TTL de una hora para reutilizar cálculos idénticos sin mantenerlos obsoletos demasiado tiempo.
- Añadida cobertura de metadatos de retries/cache y del re-lanzamiento de error desde un estado Prefect fallido. Validación focal: 9 pruebas de pipeline correctas.
- Pendiente: integración real con PostgreSQL y manejo de resultados en almacenamiento Prefect de producción; no se conectó a bases durante esta fase.

## Implementación Prefect del pipeline de desempeño de negocio (2026-11-05)

- Implementado `data/pipelines/pipeline.py` con el flow Prefect 3 `weekly_office_program_performance` y tasks independientes para resolver semana, crear registro de corrida, extraer eventos, transformar KPIs, publicar la partición y generar un artefacto opcional de evaluación. El identificador de auditoría enlaza al `flow_run_id`.
- La extracción usa exclusivamente `TELEMETRY_DATABASE_URL`, exige `TELEMETRY_DATABASE_READ_ONLY=true` y ejecuta un SELECT acotado por semana UTC y los cuatro tipos aprobados. La protección de solo lectura también requiere que el rol PostgreSQL esté configurado realmente sin permisos de escritura.
- `data/process/business_performance.py` valida cada evento independientemente, deduplica IDs, comprueba semana/dimensiones/moneda/costos y suma con `Decimal`; eventos inválidos se cuentan como rechazados sin impedir el resto. El material se calcula como `unit_cost × quantity`; entregas, faltantes y variaciones se cuentan por evento según el briefing.
- La task de transformación conserva resultados exitosos en caché por una hora; extracción y carga tienen reintentos limitados. La publicación reemplaza atómicamente la partición semanal bajo advisory lock y solo confirma la auditoría al completar la transacción. Fallos críticos intentan dejar estado `Failed`; la escritura del resumen en `data/eval/` es opcional y no bloquea el ETL.
- Añadidos migración de destino/auditoría en `data/pipelines/migrations/001_reporting_weekly_office_program_performance.sql`, fixture sintético `data/raw/business_performance_sample.json`, tests y guías operativas en inglés/español. `pyproject.toml` declara Prefect y el CLI `business-performance-pipeline`; `uv.lock` está actualizado.
- Validación: 8 pruebas de pipeline, 67 pruebas backend y 7 subtests correctos; `compileall`, `uv lock --check`, CLI `--help`, `git diff --check` y diagnósticos del editor sin errores. Backend mantiene un warning no bloqueante preexistente de deprecación Starlette/httpx.
- Pendiente antes de uso: aplicar la migración en una base de reporting; configurar URLs/roles separados con mínimo privilegio; ejecutar integración controlada para comprobar permisos y SQL contra PostgreSQL, comportamiento de reintentos/cache y carga transaccional. No se conectó ninguna base en esta fase. No se implementaron aquí los endpoints de reporting del diseño.
- Los cambios ajenos preexistentes en `uis/backoffice/next-env.d.ts` y `temp_pipeline_implem.md` permanecen fuera de alcance. No se creó commit.

## Diseño del pipeline de desempeño de negocio (2026-11-05)

- Creado `data/pipelines/PIPELINE_DESIGN.md` como diseño, sin código de orquestación. Define el Reporte Semanal de Desempeño por Oficina y Programa para Laura y Elena, los cuatro KPIs y sus eventos obligatorios, la granularidad ISO semanal UTC y el destino exacto `reporting.weekly_office_program_performance`.
- El diseño no usa etiquetas de fase. Especifica el flow Prefect `weekly_office_program_performance`, sus estados `Running`/`Completed`/`Failed`, tasks, Blocks de configuración y secretos, y la separación estricta entre el API HTTP y ETL.
- Define tres endpoints futuros en `services/reporting/` y su delegación: estado más reciente y feed de KPIs a `data/pipelines/reporting_store.py`, y disparo manual a `data/pipelines/prefect_client.py`. Ningún endpoint ejecuta ETL en FastAPI; `GET /telemetry/report` y `services/telemetry/analysis.py` quedan separados e intactos.
- Usa el vocabulario canónico Nexova (`office`: `valencia`/`miami`; `programme_id`: `ventas-b2b`, `liderazgo-basico`, `onboarding-soporte`; KPIs `total_material_cost`, `kits_delivered_count`, `shortage_events_count`, `cost_variance_events_count`; monedas `EUR`/`USD`).
- La publicación semanal es idempotente por `(office, programme_id, week_start)` y reemplaza la partición completa en una transacción atómica; documenta recuperación ante fallos, checkpoints, eventos tardíos, concurrencia y auditoría de cada corrida/partición con conteos, timestamps, estado, intento y error sanitizado.
- Confirmado en `docs/telemetry/event-schemas.json` que `inbound_order_created` ya incluye `unit_cost`; no se modificó el esquema ni el reporte técnico. La definición de kits entregados sigue el briefing (conteo de eventos outbound), con nota pendiente de validar si negocio quiere contar unidades (`quantity`).
- Validación documental: `git diff --check` y comprobaciones dirigidas de rutas, delegaciones, vocabulario, idempotencia, auditoría y límites ETL sin errores. No aplican lint ni pruebas de código porque solo se modificó diseño documental.
- Pendiente: revisión del diseño y, en una fase posterior, implementación del pipeline y los endpoints sin tocar `services/telemetry/analysis.py` ni `GET /telemetry/report`.

## Reporte operacional de telemetria (2026-11-04)

- Verificado y corregido el nombre del modulo a `services/telemetry/analysis.py` y el test a `test_analysis.py`; el endpoint `GET /telemetry/report` permanece en `services/api/routes/telemetry.py`.
- Añadido `GET /telemetry/report` con `start_date`/`end_date` ISO 8601 opcionales, normalizacion a UTC, periodo predeterminado de siete dias y validacion de rango no vacio.
- Implementado cache in-process con TTL de 60 segundos, clave por parametros de ventana normalizados (incluidos parametros omitidos) y respuestas copiadas al entrar/salir del cache.
- El endpoint delega el calculo en `services/telemetry/analysis.py`. `events_per_day` y `error_rate_by_type` cargan solo columnas necesarias con filtros SQL de timestamp `[inicio, fin)` y event_type para errores; calculan grupos diarios tras convertir timestamps a datetime UTC.
- El JSON contiene `period.from/to` y `metrics.events_per_day` / `metrics.error_rate_by_type`. La tasa tecnica clasifica HTTP 5xx, cargas frontend con outcome error y eventos frontend no manejados; no incluye metricas de negocio.
- Pruebas nuevas verifican limites temporales, resultado JSON, cache con fechas explicitas y predeterminadas, fechas invalidas/invertidas y tasas por catalogo. Suite backend completa: 67 tests y 7 subtests correctos; un warning preexistente de Starlette/httpx.
- Pendiente: commit de esta fase; cambios ajenos preexistentes permanecen fuera de alcance.

## Pipeline de analisis de telemetria operacional (2026-11-04)

- Creado `services/telemetry/analysis.py` con metricas Pandas independientes y sin mutacion del DataFrame: volumen de eventos por tipo/dia UTC, volumen de solicitudes API por ruta/metodo/dia, tasa de errores HTTP 5xx por ruta/dia, latencia API media/maxima por ruta/dia y errores de carga frontend por seccion/motivo/dia.
- Los eventos se filtran por `event_type`, sus `tags` se normalizan y los timestamps se convierten a datetime UTC antes de agrupar; las salidas son listas de diccionarios serializables. No se usan loops para calcular metricas ni dimensiones de negocio.
- Declarada Pandas en `pyproject.toml` y `services/api/requirements.txt`, con resolucion reflejada en `uv.lock`.
- Pruebas en `services/telemetry/tests/test_analysis.py`: seis casos correctos, incluidos limite de dia UTC, tasa 5xx, errores frontend, determinismo, no mutacion e input vacio.
- Pendiente: implementar carga acotada por rango/event_type desde SQL y `GET /telemetry/report` con cache; este avance solo cubre el pipeline solicitado en fase 1 y sus funciones consumen un DataFrame ya cargado.

## Captura de telemetria: TelemetryService de Backoffice (2026-11-03)

- Añadido `uis/backoffice/lib/telemetry.ts`: API unica `track()`, envelope automatico, allowlists y validaciones locales, cola en memoria (20 eventos/10 s), proxy same-origin, tres reintentos exponenciales y `sendBeacon` al ocultar/cerrar.
- Backoffice captura login, secciones autorizadas, cargas de inventario/proveedores/incidencias/perfil, validaciones de orden y respuestas HTTP de clientes centrales. No se instrumentaron otras apps ni se incluyeron nombres, valores de formularios, tokens o cuerpos.
- `GET /auth/me` entrega `telemetry_user_id` HMAC con clave/env dedicados; sin pseudonimo los eventos que requieren identidad se omiten, nunca se usa el ID crudo.
- Validacion: typecheck, lint, build y 18 pruebas Backoffice; 57 pruebas backend, prueba HTTP de login/HMAC y pruebas previas del stub/cola. `sendBeacon` es best-effort, no confirmacion de persistencia.
- Pendiente: los cinco obligatorios de inventario requieren metadatos/modelo o rutas que aun no existen (programa/categoria/coste/minimo/rechazo explicito). El stub no persiste y no aplica allowlists especificas. No se modifico el esquema de inventario ni se crearon seeds.

## Captura de telemetria: stub FastAPI (2026-11-03)

- Agregado `POST /telemetry/events` en router propio; acepta lotes de hasta 50 envelopes, registra cantidad y tipos sin payload/identificadores y devuelve `received`. Sin persistencia, redireccion ni dependencia de base de datos en el handler.
- Definidos `TelemetryEvent`, `TelemetryBatch` y `TelemetryReceipt` con Pydantic; envelope obligatorio, UUID v4, timestamp UTC real, version fija, pseudonimo/null y rechazo de extras. `TELEMETRY_ENDPOINT` se lee del entorno al importar el router, sin alterar la ruta fija.
- Validados lotes correctos/vacios, campos ausentes, IDs/fecha/version invalidos, logs sin payload e integracion en la app real bloqueando conexiones de DB. En la entrega inicial no se modificaron frontends; la fase posterior se registra arriba.
- Pendiente: validacion especifica de properties y reglas de negocio, mas persistencia de fase posterior. El stub es publico y solo para verificacion con datos de prueba.

## Estrategia de entrega de telemetria (2026-11-03)

- Documentada decision stream/batch para los 14 eventos diseñados, con ventanas justificadas por urgencia operativa, reglas de throttle/debounce, deduplicacion y riesgos/exclusiones.
- El contrato se renombro a `docs/telemetry/event-schemas.json`; plan y comando de validacion usan esa ruta canonica, sin cambios al contenido del esquema.
- Pendiente: implementar captura, transporte, ACK y persistencia. Las ventanas y limites son propuestas de diseño, no SLA verificados.

## Plan de telemetria: fase 2 (2026-11-03)

- Definido envelope obligatorio y exportado JSON Schema draft-07 version 1.0.0 en `docs/telemetry/event-schemas.json`: cinco eventos obligatorios y nueve oportunidades del catalogo en cinco categorias.
- Documentados tipos, propiedades requeridas/opcionales, allowlists cerradas, correlacion, pseudonimizacion y reglas semanticas fuera del esquema. El contexto se incorpora al repositorio por autorizacion del desarrollador.
- Validacion: metaschema, 14 ejemplos aceptados, 80 casos rechazados y cobertura documental correctos; comprobacion precommit de envelope, categorias, allowlists y date-time correcta.
- Pendiente: instrumentacion y almacenamiento, aprobacion de privacidad y resolucion de brechas de programa, categorias, umbral y costes. `event-schemas.json` contiene el contrato vigente; no se usa un archivo vacio alternativo.

## Plan de telemetria: fase 1 (2026-11-03)

- Catalogo documentado en `docs/telemetry/telemetry-plan.md`: cinco eventos obligatorios del contexto y 40 oportunidades adicionales con punto de captura, hipotesis y decision.
- Mapeados once puntos del flujo autenticado de inventario, incluidos validaciones, rechazos de stock directo, confirmacion de ordenes y cruce de umbral; identificadas brechas de programa, categorias, minimo configurable y coste historico.
- Revisadas oportunidades de autenticacion, rendimiento, errores, navegacion, proveedores, incidencias y cuenta; definidas precauciones de privacidad, deduplicacion y clasificacion de abandono.
- Validacion documental: nombres obligatorios contrastados con el contexto, 45 eventos unicos y justificaciones completas. No se implemento captura ni se ejecutaron seeds; esquemas y contrato de eventos quedan pendientes.

## Medición de caching y optimización frontend (2026-11-02)

- PostgreSQL 16 de prueba inicializado bajo el usuario `codespace` en el puerto 5433; FastAPI de prueba usó el puerto 8001 y `nexova_test`. Supabase no recibió escrituras.
- Seed de rendimiento ejecutado: 1.000 activos, 3.000 entradas y 2.000 salidas. En 20 solicitudes a `GET /inventory/products`, la mediana sin datos fue 2.8 ms y, tras el seed, 992.8 ms; resultados y condiciones están en `CACHING_REPORT.md`.
- Backoffice: los diálogos de alta de proveedor y edición de tarifa se cargan bajo demanda con `next/dynamic`; el resumen de inventario memoiza total y recuento bajo con dependencia `[assets]`.
- Validación de Backoffice: lint, typecheck, 3 suites Jest (18 pruebas) y las rutas `/suppliers` e `/inventory/products` respondieron correctamente.
- Backend: analizados los 31 endpoints FastAPI. Caché in-process para `GET /api/incidents`, `/api/incidents/summary` (TTL 30 s, claves por usuario/filtros) y `GET /inventory/products` (TTL 5 s); las escrituras relevantes invalidan cada vista y la consulta individual de stock permanece fresca.
- Medición de caché: 1.000 filas sintéticas en memoria dieron listado de incidencias 129.8 ms frío / 19.1 ms mediana caliente y resumen 5.7 / 4.1 ms. Con el inventario PostgreSQL seeded (1.000 activos, 3.000 entradas, 2.000 salidas), productos dio 1,186.1 ms frío / 8.5 ms mediana caliente. Son pruebas locales; frecuencias de producción siguen estimadas.
- Validación backend: 57 pruebas, smoke HTTP autenticado de incidencias, invalidación de producto/entrada/salida en SQLite, compilación y `git diff --check` correctos. No se midió aún el tamaño de chunks ni LCP/INP después de lazy loading. `caching_context.md` permanece sin incluir en cambios versionados.

## Auditoría de rendimiento frontend (2026-10-30)

- Realizada auditoría Lighthouse before/after de cuatro vistas desktop y mobile de Website y Backoffice, con capturas organizadas en `audit/before/` y `audit/after/`; resultados y comparación documentados en `AUDIT.md` y `REPORT.md`.
- Extraído `uis/backoffice/hooks/useInventoryAssets.ts` para compartir carga, validación runtime, errores y reintento de activos entre productos, entradas y salidas de inventario.
- Extraído `uis/website/components/SiteHeader.tsx` y reutilizado en las páginas de portada y talento.
- Las métricas after muestran reducción de TBT móvil en tres vistas (−100, −60 y −120 ms) y CLS móvil de 0 en las cuatro. TBT se interpreta como métrica de laboratorio, no como Core Web Vital.
- Validación de Backoffice: `npm run lint`, `npm run typecheck` y Jest correctos (3 suites, 18 pruebas). Validación de Website: `npm run lint` y `npm run build` correctos; Next informa un warning no bloqueante por múltiples lockfiles.
- Revisión de formato: `git diff --check` y `git diff --cached --check` correctos. Los cambios están organizados para commits separados de Backoffice, Website y, finalmente, capturas after más entregables; los commits se ejecutarán tras confirmación explícita de sus mensajes.

## Dockerizacion del monorepo (2026-10-29)

- Aniadidos Dockerfile y .dockerignore en `uis/` y `services/`, y `docker-compose.yml` en la raiz. La API usa un volumen persistente para TinyDB y requiere `DATABASE_URL` por entorno para PostgreSQL.
- La imagen Node Alpine instala y compila Website y Backoffice por separado. `uis/start.sh` arranca Website en 3000 y Backoffice en 3001, y termina ambos procesos al detener el contenedor o finalizar uno de ellos. Compose publica ambos puertos y conecta los proxies con la API en 8000.
- Validacion previa al commit: lint de Website y Backoffice correctos; 3 suites y 18 pruebas de Backoffice correctas; sintaxis Bash y `docker compose config --quiet` correctas. Website no declara script de pruebas.
- La imagen API se construyo correctamente. Los builds Next de ambas interfaces pasaron, pero la exportacion de su ultima imagen se cancelo; pendiente completar la imagen y comprobar el arranque HTTP de ambos servidores. No se verifico conexion con PostgreSQL ni se usaron credenciales reales.
- Actualizacion 2026-10-30: API con Python oficial, instalacion mediante uv y Uvicorn con `--reload`; incorporado `packages/shared` al contexto de build para resolver la importacion del parser CSV. Compose define dos servicios con bind mounts, volumenes independientes de dependencias y cache Next, y red con nombre configurable. El script de interfaces admite modo y puertos por entorno; Compose conserva modo desarrollo, no una configuracion endurecida de produccion.
- Verificacion actual: lint de ambas interfaces, 6 pruebas de sesion compartida, sintaxis Bash, Compose con entorno de ejemplo y build/importaciones de la imagen API correctos. Pendiente comprobar arranque integral y revisar la plantilla `.env.example`, protegida por Copilot; `.env` permanece ignorado por Git y sin cambios del agente.

## Unificación de Application en Backoffice (2026-10-29)

- Migradas las rutas de proveedores, login, registro, recuperación/restablecimiento de contraseña, perfil y cambio de contraseña a `uis/backoffice`; retirado del repositorio el frontend independiente `uis/application`.
- Backoffice conserva el JWT `nexova_access_token` y la sesión compartida; agregados proxies same-origin para registro, contraseña, perfil y proveedores, con autorización bearer en las rutas protegidas.
- La navegación incluye Proveedores y Mi cuenta. La página inicial enlaza proveedores, inventario, incidencias y validación técnica.
- Migradas a Backoffice las tres suites de autenticación/cuenta: 18 pruebas correctas. `npm run typecheck`, `npm run lint` y `npm run build` correctos; rutas principales responden 200 y los endpoints de sesión/proveedores sin token responden 401.
- Login probado manualmente con una cuenta válida: autenticación correcta. Pendiente comprobar visualmente el flujo y probar registro/recuperación; no se leyeron credenciales locales.

## Gestor centralizado de incidencias

- Definidos modelos Pydantic y enums de incidencia, con validacion de campos, estado y timestamps UTC de sistema.
- Centralizados parser y validador de CSV; implementado `scripts/seed_incidents.py` con transformaciones del legado, reporte de filas invalidas e idempotencia por ticket o fallback titulo/fecha. Verificado con 96 altas, 4 filas invalidas y 0 altas en la segunda ejecucion; conteos de estados y categorias coinciden con el contexto.
- Implementados endpoints autenticados para alta, listado con filtros, detalle, cambio de estado y resumen por estado/categoria/origen/sucursal. Se validan transiciones y estados finales; listas y resumen funcionan con la base vacia.
- Errores de validacion de incidencias se presentan como HTTP 400 con campos; se preserva HTTP 422 en endpoints existentes. Excepciones inesperadas devuelven un mensaje 500 generico.
- Documentados API y seed en `services/api/README.md`. Verificacion: pruebas aisladas de endpoints con TinyDB en memoria, `compileall`, `git diff --check` y 12 pruebas de restablecimiento de contrasena correctas.
- Backoffice: agregado menu global y paginas `/incidents` y `/incidents/new`. El formulario mantiene sede requerida visible, muestra todas las sedes del contexto, enfatiza sede para origen sucursal, presenta errores por campo y confirma/limpia tras el alta.
- El panel lista incidencias con filtros por estado, origen y sede, estados de carga/error/reintento y vacios diferenciados; los cambios de estado son optimistas y revierten ante fallo. El resumen por estado, categoria, origen y sede tiene carga, reintento y ciclo de actualizacion independiente, y conserva las metricas visibles durante recargas o errores.
- Agregados proxies Next autenticados `/api/incidents` (incluyendo resumen, detalle y cambio de estado), con destino configurable mediante `SUPPLIERS_API_URL`. Los errores tecnicos no se exponen como detalles internos al usuario.
- Validacion frontend en `uis/backoffice`: `npm run lint`, `npx tsc --noEmit`, `npm run build` y `git diff --check` correctos. El build reconoce paginas de incidencias y sus cuatro rutas proxy. No hay suite automatizada de UI ni validacion visual en navegador.

## Auditoría y mejoras de gestión de errores (2026-10-08)

- Creado `docs/auditoria-gestion-errores.md` con hallazgos priorizados para frontend, API y scripts; el alcance es estático y el documento conserva recomendaciones pendientes para legacy JS y el seeder.
- En `uis/application` y `uis/backoffice`, los clientes HTTP convierten errores de transporte, parseo y respuesta en mensajes controlados; se validan respuestas antes de renderizar datos de proveedores, perfil e incidencias.
- Los formularios limpian estado `busy` mediante `finally`; cargas de incidencias también limpian `loading` en `finally`. Los errores de cambio de estado del panel ofrecen reintento, y los fallbacks evitan fallos de render con datos opcionales.
- Verificación: lint, typecheck y build correctos en Application y Backoffice; `git diff --check` correcto. Website no tiene dependencias instaladas en el workspace y no fue modificado; las apps no ofrecen suite automatizada de UI.

## Gestión de errores del backend (2026-10-08)

- Los handlers FastAPI devuelven códigos estables (`code`) y `status_code` junto a `detail` compatible; las validaciones sanitizan el nombre de campo y mensajes, y los fallos no manejados responden 500 genérico mientras el log registra solo el tipo de excepción.
- El endpoint de análisis CSV cierra siempre el archivo cargado, convierte fallos de lectura en 500 controlado y mantiene validaciones 400/415/422.
- El único cliente externo de la API, Resend, limita los `try/except` a parseo de URL, construcción de request y transporte; controla errores HTTP, URL y timeout sin registrar token, destinatario, URL ni cuerpo.
- Verificación backend: 16 pruebas pasan, incluyendo respuestas estructuradas 400/404/422/500, fallos de transporte y ausencia de secretos en logs; `compileall` y `git diff --check` correctos.
- Scripts Python: lectores/parseo CSV conservan errores de dominio sanitizados; errores de escritura y procesamiento imprimen mensajes controlados a stderr y terminan con código no cero. Importaciones parciales del seeder de incidencias también devuelven `1`; errores de mapeo ya no incluyen valores de filas.
- Revisados los `print` del alcance: el análisis solo emite agregados, el seeder muestra códigos por fila, y `pandas_clean.py` reporta metadatos sin imprimir nombres de columnas ni filas. No se encontraron llamadas `console.error` en `uis/`.
- Verificación de scripts: `py_compile` pasa; suite backend 16/16; fallos simulados de ambos seeders devuelven código 1; CSV inexistente en `scripts/analyze.py` devuelve código 2. No se ejecutaron seeds contra la base de datos real.

## Estado actual (resumen ejecutivo)

El desarrollo del Talent Pipeline Tracker se encuentra en una fase avanzada y ya cubre el flujo operativo principal de gestion de candidaturas en Nexova.

- La base documental del proyecto esta definida y alineada con el contexto de negocio.
- El equipo cuenta con una experiencia funcional completa para gestionar candidaturas: visualizacion, seguimiento y actualizacion del proceso.
- Ya estan habilitadas las operaciones clave del ciclo diario: alta de candidaturas, actualizacion de estado y etapa, y gestion de notas internas.
- La solucion prioriza continuidad operativa: el trabajo se realiza sin recargas completas y con retroalimentacion visible en cada accion.

En terminos de impacto, el proyecto ya reduce friccion en la operacion de seleccion y mejora la visibilidad del pipeline para el equipo.

## Hito 09: modelo de proveedores

- Implementados SupplierCreate (entrada sin updated_at) y Supplier (respuesta con timestamp UTC generado por el sistema) en services/api/models.py.
- Validados campos requeridos, estados active/suspended, categorias permitidas, tarifa positiva finita, moneda por pais y fecha opcional de renovacion.
- Pydantic 2 y TinyDB 4 declarados como dependencias directas de la API.
- Seeder implementado con los 15 proveedores exactos del contexto; valida con Pydantic y evita duplicados por nombre y pais sin sobrescribir registros existentes.
- Comando `uv run seed` configurado mediante pyproject.toml. Almacenamiento por defecto en data/suppliers.json, configurable con SUPPLIERS_DB_PATH.
- Verificacion previa: 11 pruebas correctas; archivos de pruebas retirados despues por peticion del desarrollador. Comando real ejecutado dos veces en una base temporal: 15 insertados y luego 0.
- Implementados los seis endpoints /suppliers: alta (201), listado con filtros country/category, detalle, cambio de tarifa, cambio de estado y borrado fisico (204), con 404 para IDs inexistentes y 422 para entradas invalidas.
- SupplierResponse expone el doc_id de TinyDB como id; entradas separadas SupplierRateUpdate y SupplierStatusUpdate rechazan campos del sistema. Cada cambio real de tarifa registra updated_at UTC; el cambio de estado no altera esa fecha.
- Router registrado antes del frontend estatico. Acceso TinyDB serializado dentro de un proceso; ejecutar con un solo worker y sin seeder concurrente.
- Verificacion de endpoints: 51 comprobaciones HTTP correctas con TestClient y una base temporal, sin crear archivos de pruebas. Sin errores del editor ni de git diff --check.
- Frontend Next y React creado en uis/application con autorizacion para su configuracion independiente. Directorio /suppliers accesible desde el menu y apertura directa desde /.
- Implementados listado responsive, busqueda y filtros locales, formulario de alta, errores de API, edicion de tarifa inmediata, controles de activacion/suspension y estados diferenciados. Renovaciones proximas a 60 dias destacadas y totales separados por moneda.
- Proxy Next /api/suppliers hacia FastAPI, configurable con SUPPLIERS_API_URL (por defecto http://127.0.0.1:8000).
- Verificacion frontend: typecheck, lint y build correctos; flujos HTTP comprobados mediante proxy sobre una base temporal sin tocar datos reales ni crear archivos de pruebas.
- Pendiente: revision visual/interactiva en navegador de escritorio y movil. Chromium bloqueado por bibliotecas graficas ausentes; alternativa DOM interrumpida sin resultado. Cinco avisos altos de auditoria quedan en dependencias de ESLint (braces sin version corregida publicada); Next actualizado a 16.3.8.

## Autenticacion y cuenta: frontend (2026-10-07)

- Implementado /login con email y password, POST /auth/login mediante proxy Next, JWT en localStorage bajo nexova_access_token y redireccion a /suppliers.
- El directorio adjunta Authorization: Bearer en sus solicitudes; sin token o con respuesta 401 vuelve a /login y elimina el token rechazado.
- Implementado /register con nombre, telefono y direccion opcionales, POST /users seguido de login automatico. Errores 422 por campo y correo duplicado (409); mensaje diferenciado si se crea la cuenta pero falla el login.
- Implementado /account/profile: carga email y perfil con GET /auth/me, email de solo lectura y actualizacion de nombre, telefono y direccion con PUT /profiles/me autenticado. Campos vacios enviados como null, confirmacion de guardado, reintento de carga y enlace Mi cuenta.
- Verificacion actual: lint y typecheck correctos; comprobaciones en memoria de registro, login, almacenamiento JWT y errores 422/409/401 correctas. Servicio de cuenta previamente comprobado en memoria para GET, PUT, bearer token, null y sesion ausente/caducada.
- Rutas /login, /register y /account/profile comprobadas con HTTP 200; proxies comprobados con respuestas reales 422 y 401 de FastAPI, sin crear cuentas de prueba.
- El paquete frontend no dispone de script de pruebas automatizadas. Pendiente: validacion visual y flujos completos de registro, login y guardado de perfil en navegador con una cuenta valida.
- Commits funcionales creados con confirmacion del desarrollador: 62f1eba (login y proteccion del directorio), dbcb943 (registro) y a077972 (perfil de cuenta). Cada snapshot del indice paso TypeScript y ESLint de forma independiente; documentacion de progreso separada en el cuarto commit.

## Restablecimiento de contrasena (2026-10-07)

- Backend: POST /auth/forgot-password responde de forma generica y crea JWT de un solo uso con expiracion de 30 minutos; solo se persiste el digest. POST /auth/reset-password verifica firma, uso, expiracion y vinculo al hash anterior. POST /auth/change-password requiere sesion bearer y contrasena actual valida.
- Email transaccional con Resend por HTTPS; RESEND_API_KEY, RESEND_FROM_EMAIL y PASSWORD_RESET_URL se leen solo del entorno. El email incluye HTML responsive, texto plano y enlace alternativo; fallos de envio se registran sin secretos ni tokens.
- Frontend: paginas /forgot-password y /reset-password, cambio autenticado en /account/change-password, validacion de confirmacion, mensajes claros, link desde login y aviso posterior al reset. Las rutas publicas se excluyen del guard.
- El estado exitoso del boton de solicitud no muestra el efecto de espera aunque el boton permanece deshabilitado para evitar duplicados.
- Verificacion: 12 pruebas backend pasan; typecheck y lint de application pasan. Pruebas backend simulan Resend; no se verifico entrega real del proveedor ni se enviaron correos.
- Pendiente crear commits separados de backend/tests, frontend y documentacion. Los mensajes se deben confirmar antes de crear los commits.

## Pruebas de autenticación FastAPI (2026-10-09)

- Pruebas ubicadas bajo `services/api/tests/`, raíz del proyecto FastAPI, con un módulo por endpoint de autenticación: registro, login, consulta de sesión (`/auth/me`), solicitud de restablecimiento, restablecimiento y cambio de contraseña. Se conservaron pruebas ampliadas y la suite unittest de restablecimiento.
- Cada endpoint cuenta con camino feliz, caso límite y fallo, usando TestClient, TinyDB en memoria y email simulado.
- El `pyproject.toml` del monorepo conserva únicamente pytest y pytest-cov en el grupo dev; las dependencias FastAPI se instalan desde `services/api/requirements.txt`. Las opciones de coverage se pasan explícitamente al comando.
- Verificación tras el traslado, desde la raíz del monorepo: 57 tests correctos y 7 subtests; cobertura combinada **93%** (auth routes 96%, security 90%, password service 93%), superior al mínimo 70%, usando `uv run --with-requirements services/api/requirements.txt pytest services/api/tests --cov=services.api.routes.auth --cov=services.api.security --cov=services.api.services.passwords`.
- La suite TypeScript de `uis/application` también quedó implementada y validada; sus resultados se registran a continuación.

## Pruebas automatizadas del frontend (2026-10-09)

- Configurados Jest 30, ts-jest y jsdom en `uis/application`, con scripts `test` y `test:coverage` y sus dependencias de desarrollo.
- Añadidas suites de autenticación y cuenta: 11 pruebas en 2 suites.
- Verificación desde `uis/application`: pruebas Jest correctas, cobertura de líneas 87.6% y `npm run typecheck` correcto. `npm run lint` terminó con 0 errores y 1 warning en JavaScript generado por el informe de cobertura.
- Los tests usan mocks y no llaman una API real ni envían correos. Los artefactos de cobertura se retiraron del árbol de trabajo.

## Documentación de pruebas (2026-10-09)

- Añadido `TESTING.md` con alcance, casos, comandos y resultados de las suites FastAPI y TypeScript.
- Pendiente: crear commits separados para pruebas/configuración FastAPI, pruebas/configuración Jest y documentación, con mensajes en español aprobados por el desarrollador.

## Cobertura de utilidades TypeScript de autenticación (2026-10-09)

- Ampliadas las suites Jest para probar las utilidades compartidas de sesión (`packages/shared/auth/session.ts`): inicio de sesión con almacenamiento de token, lectura/limpieza y validación de sesión; todos los flujos principales tienen camino feliz y fallo.
- Añadidos casos para almacenamiento bloqueado, tokens ausentes/revocados, respuesta malformada, errores de API/red y aborto de petición. La suite total queda en 18 pruebas.
- Corregida la configuración Jest para usar el root del monorepo e instrumentar el paquete compartido; ESLint ignora `coverage/` generado.
- Validación: `npm run test:coverage` (3 suites, 18 tests; 91.77% líneas globales, 100% líneas en `session.ts`), `npm run typecheck` y `npm run lint` correctos. No se detectaron bugs de implementación, por lo que no fue necesario modificar las utilidades productivas.

## Proteccion de rutas internas (2026-10-07)

- Aniadido SessionGuard cliente compartido: valida el JWT de localStorage consultando /api/auth/me, bloquea la vista durante la comprobacion y redirige a /login si falta o no es valido. Revalida al cambiar ruta, recuperar foco, recibir cambios de almacenamiento y cada minuto; muestra reintento ante errores de conexion.
- Integrado en los layouts de uis/application, uis/backoffice y apps/talent-pipeline-tracker. Las rutas publicas /login y /register de application quedan excluidas; el website publico no tiene cambios.
- Aniadidos login y proxies /api/auth/me y /api/auth/login en backoffice y tracker, usando la API FastAPI y el almacenamiento JWT compartidos. Eliminada la proteccion duplicada del listado de proveedores, ahora cubierta por el guard del layout.
- Validacion: lint y typecheck correctos en application y backoffice. En tracker los archivos modificados pasan ESLint; lint completo conserva cuatro errores preexistentes en app/candidates/[id]/page.tsx y hooks/useCandidatesList.ts, y typecheck completo un error preexistente en services/api.ts:76 (GetRecordsParams no asignable al tipo query). No se modificaron esos archivos.
- Endpoints locales de login con credenciales invalidas y de sesion sin token devuelven 401 en backoffice (3001) y tracker (3002). Sin pruebas visuales con Chromium porque falta libatk-1.0.so.0 en el contenedor.
- Commits creados con confirmacion del desarrollador: 1dac059 (utilidades compartidas), 0f7d709 (application), e0d1a35 (backoffice) y 54ab31b (tracker). La documentacion de progreso se registra en un commit separado.

## Proximos pasos del tracker

1. Cerrar ajustes de presentacion y coherencia de marca para la entrega del hito.
2. Ejecutar validacion funcional integral del flujo completo de candidaturas.
3. Reforzar calidad en validaciones y manejo de errores para reducir riesgo operativo.
4. Completar checklist de entrega y criterios de despliegue.
5. Preparar el proyecto para la siguiente iteracion de mejora y escalado.

## Cliente API de inventario en Backoffice (2026-10-27)

- Aniadido `uis/backoffice/lib/inventory.ts` con tipos y funciones centralizadas para los seis endpoints de inventario; las operaciones protegidas adjuntan el token `nexova_access_token` y exponen mensajes de error del backend.
- Aniadido proxy same-origin de Next en `/api/inventory/[...path]`, que reenvia la autorizacion al backend configurado por `NEXT_PUBLIC_INVENTORY_API_URL`.
- Aniadida la regla `*.tsbuildinfo` a `.gitignore` para excluir la cache incremental de TypeScript.
- Validacion: `npx tsc --noEmit` y ESLint enfocado en los tres archivos nuevos pasan. No se modificaron componentes; los consumidores deben usar el modulo central.

## Flujos de órdenes de inventario en Backoffice (2026-10-28)

- `/inventory/products` muestra listado responsive, busqueda, SKU, categoria, oficina y stock calculado; indicadores: saludable desde 5 unidades, bajo de 1 a 4 y agotado en 0.
- Las acciones de entrada y salida aparecen una sola vez en la cabecera cuando hay productos cargados. Formularios dedicados `/inventory/orders/inbound` y `/inventory/orders/outbound` permiten elegir producto por nombre.
- La salida consulta stock actualizado al cambiar de producto, advierte si la cantidad lo supera y muestra el HTTP 400 de stock insuficiente junto al campo. La entrada muestra exito y errores inline; ambas operaciones usan el cliente central autenticado.
- Aniadido `/inventory/orders` como historial de solo lectura con producto, cantidad, tipo, fecha y `user_uuid`; distingue visualmente entradas y salidas y enlaza desde la pagina de productos. Queda cubierto por el `SessionGuard` global.
- La navegación ya no duplica «Registrar incidencia»; esa acción permanece en la página de incidencias. El proxy de inventario no reenvia AbortSignal para evitar cancelar la petición upstream en Next.
- Validacion: `npm run lint`, `npx tsc --noEmit` y `npm run build` correctos para los flujos de ordenes; al aniadir historial, typecheck y ESLint enfocado pasan, la ruta responde HTTP 200 y la API de ordenes sin autenticacion responde 401. Backoffice no dispone de pruebas automatizadas.

## Auditoría e implementación de serialización FastAPI (2026-10-31)

- `docs/serialization-audit.md` inventaría 35 rutas (22 serializadas, 1 parcialmente serializada y 12 sin serializar en la clasificación inicial) y distingue esos hallazgos históricos del resultado de fase 2.
- Añadidos esquemas de respuesta para mensajes de autenticación, registro genérico, perfil, resumen/análisis de incidencias y movimientos de inventario. Los endpoints de 204 y descarga declaran `response_model=None`; las rutas HTML/OpenAPI generadas se documentan como auxiliares automáticas.
- Las respuestas de registro y recuperación/cambio de contraseña no exponen email ni secretos. `/auth/me` conserva el email del usuario autenticado y limita perfil a nombre, teléfono y dirección.
- Las respuestas de inventario separan los modelos de entrada y salida. El historial usa proyecciones planas con nombre/SKU del activo, proveedor o destinatario/tipo de movimiento; omite claves foráneas e identificador interno del usuario. Backoffice se alineó con ese contrato.
- Verificación: backend `57 passed`, 7 subtests y 1 warning no bloqueante de deprecación Starlette; Backoffice `npm run lint`, `npm run typecheck` y `npm test` correctos (3 suites, 18 pruebas); `git diff --check` correcto y recuento de auditoría comprobado.
- Pendiente: crear commits separados para implementación (backend, tests y consumidor Backoffice) y documentación (auditoría y este progreso), previa confirmación explícita de los mensajes.