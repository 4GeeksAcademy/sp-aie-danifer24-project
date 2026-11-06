# Diseño: Pipeline de Desempeño de Negocio Nexova

**Estado:** diseño (sin código de orquestación)  
**Fuente primaria:** `telemetry_events` (solo lectura)  
**Destino del reporte:** `reporting.weekly_office_program_performance`  
**Orquestación propuesta:** Prefect

## Estado actual y brecha

### Estado actual

Nexova instrumenta operaciones del sistema de inventario de material de formación, certificación e incorporación. La captura compartida de telemetría genera eventos con un envelope que incluye `eventId`, `timestamp`, `event_type` y `requestId`; `properties` contiene los atributos permitidos del evento. La ingesta FastAPI es `POST /telemetry/events` y persiste las propiedades en `telemetry_events.tags`, junto con el tipo, timestamp y metadatos del envelope. La tabla es append-only en PostgreSQL/Supabase. La clave primaria `event_id` y el `ON CONFLICT DO NOTHING` de la ingesta evitan insertar de nuevo el mismo `eventId`.

El contrato obligatorio de inventario incluye `inbound_order_created`, `outbound_order_created`, `stock_threshold_triggered`, `direct_stock_edit_rejected` y `kit_cost_variance_detected`. Para el pipeline de esta fase se usarán solamente los cuatro eventos que el briefing de data pipelines asigna a sus KPIs: `inbound_order_created`, `outbound_order_created`, `stock_threshold_triggered` y `kit_cost_variance_detected`. El campo aditivo `unit_cost` ya existe en el esquema de `inbound_order_created`; no hace falta modificar el contrato para este diseño. Los eventos también incluyen oficina, `programme_id`, moneda y los atributos operativos requeridos por su contrato.

El reporte técnico existente está separado: `services/telemetry/analysis.py` contiene funciones de análisis técnico y `GET /telemetry/report` vive en `services/api/routes/telemetry.py`. El endpoint devuelve volumen diario de eventos y tasa de error por tipo para un rango temporal, con normalización UTC y caché TTL. El módulo de análisis también contiene métricas técnicas de volumen de solicitudes, errores HTTP 5xx, latencia media/máxima y errores de carga frontend. Esas métricas son para ingeniería y observabilidad del sistema; esta propuesta no cambia ese módulo ni endpoint.

### Brecha de negocio

El reporte técnico no responde cuánto invierte cada oficina y programa en material durante una semana, cuántos kits entrega, cuántas veces cae el stock por debajo del mínimo ni cuántas anomalías de costo detecta. Tampoco presenta un consolidado legible para liderazgo. La pregunta no resuelta es: **¿cómo se comparan Valencia y Miami, por programa y semana, en costo de material, entregas y eventos de escasez o variación de costo?** Para responderla se necesita una transformación de negocio, una tabla de reporting propia y endpoints separados del reporte técnico.

## Propósito, audiencia y alcance

**Propósito:** producir cada lunes por la mañana el **Reporte Semanal de Desempeño por Oficina y Programa** para Laura (CEO) y Elena (Gerente de L&D), calculando costo de material, kits entregados, frecuencia de escasez y frecuencia de variación de costo a partir de las métricas obligatorias `inbound_order_created`, `outbound_order_created`, `stock_threshold_triggered` y `kit_cost_variance_detected` almacenadas en `telemetry_events`.

El reporte es un consolidado de negocio que los stakeholders pueden consultar sin depender de un informe manual. No expone eventos crudos ni está dirigido a depurar servicios.

El pipeline produce exactamente estos cuatro KPIs del briefing:

| KPI | Métrica de salida | Eventos fuente y regla |
| --- | --- | --- |
| Costo de material por oficina/programa | `total_material_cost` | Suma de `unit_cost × quantity` de `inbound_order_created`, en la moneda local y sin conversión. |
| Kits entregados | `kits_delivered_count` | Conteo de eventos confirmados `outbound_order_created` en la semana, según la agregación especificada en el briefing. |
| Frecuencia de escasez | `shortage_events_count` | Conteo de `stock_threshold_triggered`. |
| Frecuencia de variación de costo | `cost_variance_events_count` | Conteo de `kit_cost_variance_detected`. |

**Nota de definición para validar antes de implementación:** el contrato de salida y el briefing llaman a este KPI “kits entregados”, pero especifican contar eventos `outbound_order_created`; el evento también tiene `quantity`. La v1 seguirá el conteo de eventos establecido por el briefing, que representa órdenes/entregas confirmadas. Si negocio quiere contar unidades físicas cuando una orden lleva más de un kit, debe aprobarse explícitamente cambiar la regla a suma de `quantity` antes de implementar; no se mezclarán ambas definiciones.

### Formato y frecuencia de extracción

La única fuente v1 es `telemetry_events`, consultada en modo solo lectura desde PostgreSQL. Cada fila contiene columnas relacionales `event_id`, `event_type`, `timestamp`, `request_id` y `tags` JSONB; `tags` conserva el objeto `properties` del evento, incluidos `office`, `programme_id`, `currency`, `quantity` y, para entradas, `unit_cost`. La extracción devuelve registros estructurados (filas SQL con los campos requeridos y propiedades normalizadas), no archivos ni eventos tomados de `GET /telemetry/report`. Se filtran los cuatro tipos acordados por el intervalo UTC de la semana y se valida el contrato antes de agregar.

La fuente se actualiza conforme a la cadencia de captura definida por el briefing de telemetría: `inbound_order_created` y `outbound_order_created` por lotes cada 15 minutos; `stock_threshold_triggered` en stream con objetivo de hasta 60 segundos; y `kit_cost_variance_detected` por lotes cada hora. El pipeline de negocio consolida semanalmente, el lunes por la mañana (UTC). La hora exacta de despliegue debe configurarse en el scheduler/deployment de Prefect; este diseño no fija una hora como SLA. Una reejecución manual o reconciliación puede volver a leer una semana anterior para incorporar eventos tardíos; no se asume que la captura y el reporte semanal tengan la misma frecuencia.

### Ejecución operativa y CLI

`data/pipelines/pipeline.py` puede ejecutarse directamente desde la raíz del repositorio, con las variables de entorno `TELEMETRY_DATABASE_URL`, `TELEMETRY_DATABASE_READ_ONLY=true` y `REPORTING_DATABASE_URL` configuradas:

```bash
uv run python data/pipelines/pipeline.py [YYYY-MM-DD]
```

La fecha opcional debe ser el lunes de la semana ISO que se recalculará. Si se omite, el flow procesa la última semana UTC completada. Esta invocación ejecuta el flow completo; `--help` muestra la interfaz sin conectar a las bases de datos. Para automatización recurrente, el deployment de Prefect debe programarse semanalmente cada lunes por la mañana UTC; una ejecución CLI no instala ni activa por sí sola ese calendario.

### Flujo de datos

```text
+--------------------------- EXTRACCIÓN ----------------------------+
| Prefect: resolver semana ISO UTC                                  |
| SELECT de telemetry_events (solo lectura; 4 event_type; [inicio, fin)) |
| Capturar eventId/requestId, timestamp, tags y conteos por tipo    |
+------------------------------+----------------------------------+
                               |
                               v
+------------------------- TRANSFORMACIÓN --------------------------+
| Validar contrato/dimensiones y clasificar datos no válidos        |
| Deduplicación defensiva por eventId; agrupar por oficina/programa |
| Calcular los cuatro KPIs; fijar moneda local sin conversión       |
+------------------------------+----------------------------------+
                               |
                               v
+------------------------------ CARGA ------------------------------+
| Upsert transaccional en reporting.weekly_office_program_performance |
| Clave única (office, programme_id, week_start); registrar run/checkpoint |
| Publicar solo tras commit y exponer vía services/reporting/       |
+-------------------------------------------------------------------+
```

### Fuentes mutables y estrategia contra duplicados

La fuente seleccionada para v1 no actualiza filas: `telemetry_events` es append-only y la ingesta usa `event_id` como clave primaria más `ON CONFLICT DO NOTHING`. Por ello, el pipeline no necesita capturar cambios de una tabla de dominio mutable ni deduplicar por timestamp. La clave concreta de deduplicación de la acción es `eventId`/`event_id`, aplicada primero en la ingesta; `requestId` solo correlaciona. La transformación mantiene una salvaguarda determinista por `eventId` y reporta cualquier repetición inesperada, sin contarla dos veces.

Si una versión futura requiere leer una tabla de dominio que actualiza registros, esa fuente queda fuera de v1. Su integración deberá usar CDC o un `updated_at`/versión monotónica como watermark, seleccionar una sola versión vigente por clave de entidad y ventana, y aplicar `MERGE`/upsert determinista; no se tratarán cada snapshot como una acción nueva. La publicación de este pipeline seguirá reemplazando idempotentemente las filas de la partición semanal mediante la clave `(office, programme_id, week_start)`, de modo que relecturas y reintentos no inflen agregados.

### Grano, calendario y dimensiones

Una fila por `(office, programme_id, week_start)`, donde `week_start` es el lunes de la semana ISO en UTC. La extracción usa el intervalo temporal semiabierto `[week_start 00:00 UTC, next_week_start 00:00 UTC)`, aplicado al `timestamp` del evento (no al momento de recepción). Dimensiones permitidas: `office` (`valencia`/`miami`), `programme_id`, `week_start` y `currency`. Valencia se expresa en EUR y Miami en USD; no se suman ni convierten monedas. Los valores ausentes o no válidos de dimensiones/costo se contabilizan como rechazados de calidad y no se sustituyen por valores inventados.

La tabla de destino será exactamente `reporting.weekly_office_program_performance`, con el DDL y la restricción `unique (office, programme_id, week_start)` definidos en la sección “Tabla de destino” del briefing. El diseño no propone escribir los agregados en `telemetry_events`. Se podrán crear tablas auxiliares de auditoría bajo `reporting` para corridas/checkpoints, sin cambiar el nombre ni el propósito de la tabla de métricas.

### Prefect: composición de flow y subflows

El flow principal `weekly_office_program_performance` inicia y audita la corrida, y compone tres subflows secuenciales con contratos explícitos: `extract_events_subflow(week_start) -> events`, `transform_business_kpis_subflow(events, week_start) -> aggregate` y `load_week_partition_subflow(aggregate, run_id) -> rows_written`. Cada uno encapsula la task de su etapa y conserva su configuración de retries/cache. Tras la carga, `evaluation_artifact_subflow(aggregate, rows_written, run_id) -> path` produce el resumen local opcional; el padre lo invoca con `return_state=True` y aísla su fallo para no invalidar una publicación correcta. La carga también retorna su estado al padre para marcar la auditoría como fallida antes de relanzar errores críticos.

### Prefect: composición de flow y tasks

Un deployment semanal de Prefect ejecutará el flow `weekly_office_program_performance`. Se programará para comenzar el lunes antes del horario de consulta acordado, con margen para reintentos; la zona del cron se fijará explícitamente y la ventana de datos siempre será UTC. Un endpoint manual futuro iniciará el mismo deployment con `week_start` opcional; no implementará una segunda lógica de cálculo.

Tasks propuestas, cada una con límites de reintento y logs estructurados:

1. `resolve_week`: valida/resuelve `week_start` (lunes UTC), fija el intervalo y un `run_id`; el default es la semana ISO calculada más reciente que esté completa.
2. `extract_events`: consulta en solo lectura las columnas necesarias de `telemetry_events`, limitadas por timestamp y a los cuatro tipos aprobados. Registra el total por tipo y el watermark/intervalo observado.
3. `validate_source`: valida oficina, programa, moneda, cantidades, costos, tipos de evento y `eventId`; cuenta y clasifica registros no utilizables sin registrar payloads sensibles.
4. `aggregate_business_kpis`: agrega con aritmética decimal para importes, dimensiones y ventana definidas; no genera cifras derivadas de eventos técnicos ajenos al entregable.
5. `load_week_partition`: hace upsert en la tabla de destino por clave única, con transacción y lock por semana. Reemplaza el resultado completo de la partición, no incrementa los totales existentes.
6. `publish_and_audit`: registra conteos, resultado, `computed_at`, ventana y estado final; marca la partición como publicada solo después de confirmar la carga.

El flow principal de Prefect es `weekly_office_program_performance`; sus tasks y
sus ejecuciones individuales quedan asociadas al `flow_run_id`, `task_run_id`,
deployment y al `run_id` de dominio. En el ciclo normal, la corrida pasa a
`Running` al comenzar, a `Completed` solo tras publicar y auditar la partición
después del commit, o a `Failed` ante un error no recuperable o agotamiento de
reintentos. Un fallo transitorio puede reintentar la task con backoff exponencial
y jitter; el intento fallido queda registrado y no se presenta como una corrida
completada. Errores de contrato o de calidad que superen umbrales acordados
fallan explícitamente y generan alerta, no se ocultan como éxito parcial.

La configuración se inyecta mediante Prefect Blocks, sin secretos en código,
parámetros visibles ni logs. Se proponen un block de conexión/credenciales
PostgreSQL-Supabase de solo lectura para consultar `telemetry_events`, otro
block de conexión de escritura restringida al esquema `reporting`, y blocks de
configuración para deployment (zona horaria, calendario, límites/reintentos) y
notificaciones/alertas. Según la instalación, pueden materializarse como
`SqlAlchemyConnector`/`DatabaseCredentials` y `Secret` blocks, o blocks propios
que encapsulen esas conexiones. Los secretos se rotan fuera del flow y los logs
solo indican el nombre lógico del block, nunca su valor.

### Integración con la aplicación: API de reporting

La aplicación expondrá un router nuevo en `services/reporting/` (por ejemplo,
`router.py`, `schemas.py` y un adaptador HTTP fino). No se añadirán estas rutas a
`services/telemetry/` ni se cambiará `GET /telemetry/report`. El módulo
`services/` se limita a validar parámetros HTTP, aplicar autenticación y
autorización, delegar en las funciones indicadas abajo y serializar respuestas;
no contiene extracción, transformación, agregación ni carga (ETL).

El vocabulario de payload sigue el contrato Nexova: `office` es `valencia` o
`miami`; `programme_id` usa el catálogo de inventario (`ventas-b2b`,
`liderazgo-basico`, `onboarding-soporte`); `week_start` es el lunes de la semana
ISO en UTC; las monedas son `EUR` para Valencia y `USD` para Miami. Se mantiene
el nombre exacto `programme_id` (no `program_id`). El feed conserva las métricas
`total_material_cost`, `kits_delivered_count`, `shortage_events_count`,
`cost_variance_events_count` y `currency` de
`reporting.weekly_office_program_performance`.

#### Consulta del estado de la última corrida

- **Ruta:** `GET /reporting/pipeline-runs/latest`
- **Uso:** estado y resultado de la corrida más reciente para operaciones y la
  aplicación.
- **Delegación:** el handler llama a
  `data/pipelines/reporting_store.py:get_latest_pipeline_run()`. Esta función
  solo lee el registro más reciente de `reporting.pipeline_runs`; no inicia ni
  ejecuta el flow.
- **Respuesta 200 (contrato ilustrativo):**

```json
{
  "run_id": "<id-de-corrida-de-negocio>",
  "flow_name": "weekly_office_program_performance",
  "flow_run_id": "<id-de-prefect>",
  "status": "Completed",
  "trigger_type": "scheduled",
  "week_start": "2026-11-02",
  "started_at": "2026-11-09T07:00:00Z",
  "ended_at": "2026-11-09T07:00:12Z",
  "processed_records": 42,
  "accepted_records": 42,
  "rejected_records": 0,
  "rows_written": 6,
  "error_code": null,
  "error_message": null
}
```

`status` usa `Running`, `Completed` o `Failed`; cualquier error se devuelve
sanitizado. `404` indica que todavía no hay corridas. El endpoint no lee eventos
fuente ni calcula KPIs.

#### Disparo manual de una corrida

- **Ruta:** `POST /reporting/pipeline-runs`
- **Uso:** solicitud autenticada y autorizada de recálculo. El cuerpo es
  opcional; para reconciliar una semana concreta:

```json
{ "week_start": "2026-11-02" }
```

- **Delegación:** el handler llama a
  `data/pipelines/prefect_client.py:start_weekly_office_program_performance(week_start)`.
  Esta función solicita una ejecución del deployment Prefect del flow
  `weekly_office_program_performance`; no ejecuta ETL dentro de FastAPI. Sin
  `week_start`, el flow resuelve la semana completa más reciente; si se indica,
  debe ser lunes UTC. El flow crea y actualiza la corrida en
  `reporting.pipeline_runs` y reporta su resultado a Prefect.
- **Respuesta:** `202 Accepted` con `run_id`, `flow_run_id`, `status: Running` y
  `week_start`. Una fecha que no sea lunes responde `422`; si el deployment no
  está disponible, se devuelve un error de servicio sin ejecutar ETL en el API.

#### Feed semanal de KPIs para el dashboard

- **Ruta:** `GET /reporting/weekly-office-program-performance?week_start=YYYY-MM-DD`
- **Uso:** feed de solo lectura para el dashboard futuro. Si se omite
  `week_start`, devuelve la semana publicada más reciente; un valor explícito
  debe ser lunes ISO UTC.
- **Delegación:** el handler llama a
  `data/pipelines/reporting_store.py:get_weekly_office_program_performance(week_start)`.
  Esta función consulta exclusivamente filas publicadas de
  `reporting.weekly_office_program_performance`; no lanza el flow ni recalcula
  KPIs en `services/`.
- **Respuesta 200 (contrato ilustrativo, usando un ID real del catálogo Nexova):**

```json
{
  "week_start": "2026-11-02",
  "entries": [
    {
      "office": "valencia",
      "programme_id": "ventas-b2b",
      "total_material_cost": 1240.50,
      "kits_delivered_count": 18,
      "shortage_events_count": 1,
      "cost_variance_events_count": 0,
      "currency": "EUR"
    }
  ]
}
```

Si no hay publicación para la semana solicitada, se recomienda responder `200`
con `entries: []`. Los endpoints consultan o disparan trabajo del esquema
`reporting`; solo el flow Prefect lee `telemetry_events` en modo lectura. Ninguno consulta ni altera `GET /telemetry/report`, `services/telemetry/analysis.py` ni
su contrato técnico.

Estos endpoints y adaptadores son diseño, no implementación. Las funciones bajo
`data/pipelines/` son interfaces propuestas; las consultas de reporting son de
solo lectura y el único punto de ejecución ETL es el flow
`weekly_office_program_performance`.

## Idempotencia y resiliencia

### Duplicados en el origen

`eventId` identifica un evento lógico y debe conservarse entre reintentos del cliente. La deduplicación primaria ocurre en la capa de ingesta: `telemetry_events.event_id` es clave primaria y el insert ignora el conflicto. Así, si se reenvía una acción con el mismo `eventId` aunque cambie el timestamp de recepción, queda una sola fila. El `requestId` correlaciona una petición/operación con eventos relacionados; no es la clave de deduplicación. El pipeline trabaja sobre la tabla ya deduplicada y no vuelve a contar un `eventId` repetido si una futura extracción une fuentes auxiliares.

Como defensa adicional, las tareas de validación pueden registrar IDs vistos/repetidos dentro de una ventana y fallar o excluir duplicados de una extracción anómala, pero la autoridad de deduplicación está en la ingesta. No se usa timestamp, usuario ni `requestId` para deduplicar acciones distintas.

### Reintento tras una carga parcial

La unidad reintentable/publicable es la partición semanal `(week_start)`, y cada
fila de la salida tiene la clave idempotente `(office, programme_id, week_start
)`. El flow recalcula el conjunto semanal completo desde la fuente; nunca suma
el nuevo resultado encima del valor de reporting ya cargado. La carga se prepara
y valida antes de publicar, y luego reemplaza/upsertea el conjunto de la semana
dentro de una única transacción. El commit de los datos, `computed_at` y el
marcador de publicación debe ser atómico: ante cualquier error antes del commit,
la transacción se revierte y los lectores siguen viendo íntegra la publicación
anterior. Si el proceso pierde confirmación después del commit, al reintentar
vuelve a calcular la misma partición y escribe los mismos valores bajo la clave
única `(office, programme_id, week_start)`; no crea filas duplicadas ni infla
contadores, y una semana que ahora no tenga filas elimina de forma transaccional
las filas obsoletas de esa partición. La corrida fallida se conserva y la nueva
corrida registra el intento de recuperación. No se considera segura una carga
que confirme filas individuales parcialmente: se requiere staging validado y
swap/merge transaccional cuando la tabla o volumen impida una única escritura.

Los checkpoints persisten `run_id`, `week_start`, etapa alcanzada (`resolved`, `extracted`, `transformed`, `loaded`, `published`), conteos y timestamps. Solo se reanuda directamente desde una etapa si el artefacto intermedio está persistido y validado; si no, se vuelve a extraer y recalcular la partición completa, que es la recuperación segura por defecto.

### Eventos tardíos e invalidación

Los eventos tardíos se asignan a la semana de su `timestamp` de negocio. Una tarea de reconciliación identifica las semanas afectadas desde el watermark/ventana de llegada, invalida lógicamente la publicación previa y relanza el flow para cada semana. El nuevo resultado se recalcula desde todos los eventos de esa partición y se hace upsert: no se incrementan contadores sobre la cifra anterior. La corrida nueva registra `late_data_recompute`, semana y conteos; la fila publicada conserva `computed_at` actualizado y el historial de corridas mantiene la evidencia de qué publicación se sustituyó.

La ventana de búsqueda de tardíos y política de retención del historial deben configurarse con el SLA de captura; inicialmente se recomienda reexaminar semanas recientes en cada corrida y permitir una reejecución manual de cualquier semana histórica.

## Observabilidad y auditoría

### Corridas, heartbeats y silencio

Bajo `reporting` se propone una tabla genérica `pipeline_runs` para registrar
el estado y los metadatos de las corridas, además de `pipeline_run_partitions`
para las semanas procesadas. Cada
registro de ejecución incluye como mínimo:

- `run_id`, nombre/versión del flow e IDs Prefect: enlazan el registro de negocio
  con el flow, deployment, tasks y logs técnicos.
- `started_at` y `ended_at` (UTC): delimitan la ejecución y permiten medir
  duración, detectar timeouts y demostrar cuándo se procesó el reporte.
- `processed_records` (total leído) y conteos por `event_type`, junto con
  `accepted_records`, `rejected_records`, filas agregadas y filas cargadas:
  reconcilian entrada, decisiones de calidad y salida para auditar que no haya
  pérdida o doble conteo silencioso.
- `status` (`Running`, `Completed` o `Failed`), `stage`/checkpoint e `attempt`:
  identifican el resultado y último punto confirmado, distinguiendo una corrida
  aún activa de una terminada y haciendo trazables los reintentos.
- `week_start`, tipo de corrida (`scheduled`/`manual`/`recovery`), ventana y
  watermark: documentan qué periodo y hasta qué punto de la fuente se incluyeron.
- `error_code` y `error_message` sanitizados cuando aplique, más `computed_at`
  publicado: permiten diagnosticar fallos sin exponer secretos/PII y probar qué
  versión de datos quedó disponible para consulta.

El inicio de la corrida crea el registro con estado `Running` y `started_at`; al
terminar se fija `ended_at` y se actualiza a `Completed` únicamente después del
commit, o a `Failed` al agotar la recuperación, guardando el error sanitizado.
Los cambios de estado se conservan en el historial de intentos, no se reemplaza
un fallo previo al crear una nueva corrida. En `pipeline_run_partitions` se
conservan semana, conteos y resumen de IDs fuente/eventos por tipo para lineage,
sin copiar payloads personales.

Cada inicio y fin emite heartbeat. Un flow exitoso con cero eventos es un resultado distinto de un flow ausente/fallido: la salida cero solo se comunica si la consulta a fuente terminó correctamente, la ventana y permisos fueron verificados y los controles de calidad pasaron. Alertas operativas: ninguna corrida exitosa antes del límite de lunes, heartbeat/flow ausente, fuente inaccesible, retraso de watermark, tasa anormal de rechazados, partición vacía inesperada o fallo de publicación. Los umbrales de silencio por oficina se fijan con negocio/operaciones para no interpretar el cierre de una oficina como pérdida de datos.

### Trazabilidad evento → reporte

El `run_id` enlaza tasks, `pipeline_runs`, particiones y logs. En extracción se preservan `eventId`, `requestId`, `event_type` y `timestamp` como contexto de lineage; `eventId` permite localizar el registro fuente y `requestId` ayuda a correlacionar la operación de origen. Los logs y APIs de negocio solo exponen agregados y metadatos sanitizados, nunca payloads completos, usuarios o PII. La auditoría debe permitir reconstruir intervalo, número de eventos leídos por tipo, transformaciones/versionado y filas de salida publicadas, además de diferenciar un pico real de la relectura de una ventana duplicada.

### Crecimiento frente a pérdida de captura

Además de comparar KPIs semana contra semana, el monitor compara eventos por tipo/oficina con corridas, oficinas/sesiones que reportaron cuando esa señal esté disponible, rechazos, duplicados y salud de `POST /telemetry/events`. Un cambio en volumen se marca como “dato posiblemente incompleto” si hay retraso/ausencia de heartbeat, fallos HTTP, huecos de ingestión o cambio en la tasa de rechazo. No se infiere crecimiento del negocio exclusivamente a partir de un aumento de telemetría.

## Recuperabilidad, transporte y concurrencia

### Caída de base de datos y checkpoints

Ante caída de PostgreSQL, la task falla con estado Prefect `Failed`, aplica reintentos acotados y deja el checkpoint de última fase confirmada. Una falla durante extracción o transformación retoma esa task si sus artefactos fueron guardados de forma durable; si no, vuelve a ejecutar desde extracción. Una falla durante carga revierte la transacción cuando sea posible y repite la partición semanal completa mediante upsert. `published` solo se marca después del commit de todas las filas del periodo; el endpoint de reporte consulta exclusivamente publicaciones completas.

### Buffer del frontend y límites de garantía

La instrumentación actual describe cola en memoria y reintentos, no un outbox durable offline. El diseño no asume que el navegador sea almacenamiento confiable: ante una desconexión larga, un buffer persistente de cliente con límite de tamaño/edad puede evitar pérdidas, pero introduce riesgos de borrado, duplicación, datos obsoletos y exposición en dispositivos compartidos. Para eventos derivados de una operación transaccional, la garantía debe evolucionar a outbox durable del lado servidor en la misma transacción que el cambio de inventario. Eso pertenece a la robustez de captura, no a este pipeline de agregación. El pipeline reporta brechas; no inventa eventos ausentes.

### Reintentos de `POST /telemetry/events`

El cliente conserva el mismo `eventId` al reintentar el mismo evento; backoff exponencial con jitter y límite operativo evitan tormentas. HTTP 200 con ACK recibido significa que el servidor procesó el lote: `stored > 0` informa nuevas inserciones y `stored = 0` puede significar que todos los IDs ya existían (la respuesta actual no distingue duplicado de otros casos sin inserción). El cliente trata el ACK válido como final y no reenvía un evento confirmado. Un timeout o error transitorio sin ACK se reintenta conservando IDs. `Idempotency-Key` puede añadirse para idempotencia de request/lote, pero no reemplaza `eventId` ni es actualmente un requisito implementado. La ingesta actual usa `ON CONFLICT DO NOTHING`; mejoras para distinguir duplicados deben mantener compatibilidad con su ACK.

### Corridas concurrentes

El deployment Prefect tendrá límite de concurrencia y el cargador obtendrá un advisory lock PostgreSQL identificado por pipeline y semana. Si scheduler y POST manual coinciden, el segundo flow espera o se rechaza con estado claro; no se ejecutan publicaciones concurrentes de la misma partición. El lock se libera al cerrar conexión/finalizar la task. La restricción única y upsert siguen siendo una última barrera ante conflictos. Semanas diferentes podrían procesarse en paralelo si los límites de recursos y conexiones lo permiten.

## Destinos, contrato de salida y límites de v1

### Tabla de destino requerida

La tabla de métricas conserva exactamente el nombre y el grano del briefing. DDL de referencia (aplicado bajo esquema dedicado `reporting`):

```sql
create table reporting.weekly_office_program_performance (
  id uuid primary key default gen_random_uuid(),
  office text not null,
  programme_id text not null,
  week_start date not null,
  total_material_cost numeric not null default 0,
  kits_delivered_count integer not null default 0,
  shortage_events_count integer not null default 0,
  cost_variance_events_count integer not null default 0,
  currency text not null,
  computed_at timestamptz not null default now(),
  unique (office, programme_id, week_start)
);
```

El esquema `reporting` y tabla(s) de auditoría/checkpoint son destinos separados de la fuente. Las credenciales de lectura de `telemetry_events` y escritura de `reporting` deben ser de mínimo privilegio; la consulta del pipeline nunca actualiza ni elimina eventos fuente.

### Ejemplo de contrato del endpoint semanal

```json
{
  "week_start": "2026-07-13",
  "entries": [
    {
      "office": "valencia",
      "programme_id": "ventas-b2b",
      "total_material_cost": 1240.50,
      "kits_delivered_count": 18,
      "shortage_events_count": 1,
      "cost_variance_events_count": 0,
      "currency": "EUR"
    }
  ]
}
```

Es un ejemplo del contrato, no datos reales ni una medición de producción.

### Fuera de alcance de v1

- No reemplazar ni modificar `services/telemetry/analysis.py` ni `GET /telemetry/report`.
- No escribir resultados, estados ni checkpoints en `telemetry_events`.
- No calcular KPIs genéricos, matrículas, tasa de finalización, rentabilidad, ni analítica de telemetría de ingeniería.
- No convertir moneda ni agregar oficinas en una sola fila.
- No crear tipos de evento nuevos para suplir datos ausentes; los únicos eventos fuente son los cuatro enumerados.
- No implementar ahora Prefect, esquema/tablas, tasks ni rutas: este entregable es diseño. La implementación debe ir en `services/reporting/` y migraciones/esquemas dedicados en una fase posterior.
