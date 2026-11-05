# Diseño: Pipeline de Desempeño de Negocio Nexova

**Estado:** diseño (sin código de orquestación)  
**Fuente primaria:** `telemetry_events` (solo lectura)  
**Destino del reporte:** `reporting.weekly_office_program_performance`  
**Orquestación propuesta:** Prefect

## Fase 1 — Estado actual y brecha

### Estado actual

Nexova instrumenta operaciones del sistema de inventario de material de formación, certificación e incorporación. La captura compartida de telemetría genera eventos con un envelope que incluye `eventId`, `timestamp`, `event_type` y `requestId`; `properties` contiene los atributos permitidos del evento. La ingesta FastAPI es `POST /telemetry/events` y persiste las propiedades en `telemetry_events.tags`, junto con el tipo, timestamp y metadatos del envelope. La tabla es append-only en PostgreSQL/Supabase. La clave primaria `event_id` y el `ON CONFLICT DO NOTHING` de la ingesta evitan insertar de nuevo el mismo `eventId`.

El contrato obligatorio de inventario incluye `inbound_order_created`, `outbound_order_created`, `stock_threshold_triggered`, `direct_stock_edit_rejected` y `kit_cost_variance_detected`. Para el pipeline de esta fase se usarán solamente los cuatro eventos que el briefing de data pipelines asigna a sus KPIs: `inbound_order_created`, `outbound_order_created`, `stock_threshold_triggered` y `kit_cost_variance_detected`. El campo aditivo `unit_cost` ya existe en el esquema de `inbound_order_created`; no hace falta modificar el contrato para este diseño. Los eventos también incluyen oficina, `programme_id`, moneda y los atributos operativos requeridos por su contrato.

El reporte técnico existente está separado: `services/telemetry/analysis.py` contiene funciones de análisis técnico y `GET /telemetry/report` vive en `services/api/routes/telemetry.py`. El endpoint devuelve volumen diario de eventos y tasa de error por tipo para un rango temporal, con normalización UTC y caché TTL. El módulo de análisis también contiene métricas técnicas de volumen de solicitudes, errores HTTP 5xx, latencia media/máxima y errores de carga frontend. Esas métricas son para ingeniería y observabilidad del sistema; esta propuesta no cambia ese módulo ni endpoint.

### Brecha de negocio

El reporte técnico no responde cuánto invierte cada oficina y programa en material durante una semana, cuántos kits entrega, cuántas veces cae el stock por debajo del mínimo ni cuántas anomalías de costo detecta. Tampoco presenta un consolidado legible para liderazgo. La pregunta no resuelta es: **¿cómo se comparan Valencia y Miami, por programa y semana, en costo de material, entregas y eventos de escasez o variación de costo?** Para responderla se necesita una transformación de negocio, una tabla de reporting propia y endpoints separados del reporte técnico.

## Fase 2 — Propósito, audiencia y alcance

El único entregable de la v1 es el **Reporte Semanal de Desempeño por Oficina y Programa**, un consolidado semanal que Laura (CEO) y Elena (Gerente de L&D) pueden consultar sin depender de un informe manual. Debe estar fresco la mañana del lunes. No expone eventos crudos ni está dirigido a depurar servicios.

El pipeline produce exactamente estos cuatro KPIs del briefing:

| KPI | Métrica de salida | Eventos fuente y regla |
| --- | --- | --- |
| Costo de material por oficina/programa | `total_material_cost` | Suma de `unit_cost × quantity` de `inbound_order_created`, en la moneda local y sin conversión. |
| Kits entregados | `kits_delivered_count` | Conteo de eventos confirmados `outbound_order_created` en la semana, según la agregación especificada en el briefing. |
| Frecuencia de escasez | `shortage_events_count` | Conteo de `stock_threshold_triggered`. |
| Frecuencia de variación de costo | `cost_variance_events_count` | Conteo de `kit_cost_variance_detected`. |

**Nota de definición para validar antes de implementación:** el contrato de salida y el briefing llaman a este KPI “kits entregados”, pero especifican contar eventos `outbound_order_created`; el evento también tiene `quantity`. La v1 seguirá el conteo de eventos establecido por el briefing, que representa órdenes/entregas confirmadas. Si negocio quiere contar unidades físicas cuando una orden lleva más de un kit, debe aprobarse explícitamente cambiar la regla a suma de `quantity` antes de implementar; no se mezclarán ambas definiciones.

### Grano, calendario y dimensiones

Una fila por `(office, programme_id, week_start)`, donde `week_start` es el lunes de la semana ISO en UTC. La extracción usa el intervalo temporal semiabierto `[week_start 00:00 UTC, next_week_start 00:00 UTC)`, aplicado al `timestamp` del evento (no al momento de recepción). Dimensiones permitidas: `office` (`valencia`/`miami`), `programme_id`, `week_start` y `currency`. Valencia se expresa en EUR y Miami en USD; no se suman ni convierten monedas. Los valores ausentes o no válidos de dimensiones/costo se contabilizan como rechazados de calidad y no se sustituyen por valores inventados.

La tabla de destino será exactamente `reporting.weekly_office_program_performance`, con el DDL y la restricción `unique (office, programme_id, week_start)` definidos en la sección “Tabla de destino” del briefing. El diseño no propone escribir los agregados en `telemetry_events`. Se podrán crear tablas auxiliares de auditoría bajo `reporting` para corridas/checkpoints, sin cambiar el nombre ni el propósito de la tabla de métricas.

### Prefect: composición de flow y tasks

Un deployment semanal de Prefect ejecutará el flow `weekly_office_program_performance`. Se programará para comenzar el lunes antes del horario de consulta acordado, con margen para reintentos; la zona del cron se fijará explícitamente y la ventana de datos siempre será UTC. Un endpoint manual futuro iniciará el mismo deployment con `week_start` opcional; no implementará una segunda lógica de cálculo.

Tasks propuestas, cada una con límites de reintento y logs estructurados:

1. `resolve_week`: valida/resuelve `week_start` (lunes UTC), fija el intervalo y un `run_id`; el default es la semana ISO calculada más reciente que esté completa.
2. `extract_events`: consulta en solo lectura las columnas necesarias de `telemetry_events`, limitadas por timestamp y a los cuatro tipos aprobados. Registra el total por tipo y el watermark/intervalo observado.
3. `validate_source`: valida oficina, programa, moneda, cantidades, costos, tipos de evento y `eventId`; cuenta y clasifica registros no utilizables sin registrar payloads sensibles.
4. `aggregate_business_kpis`: agrega con aritmética decimal para importes, dimensiones y ventana definidas; no genera cifras derivadas de eventos técnicos ajenos al entregable.
5. `load_week_partition`: hace upsert en la tabla de destino por clave única, con transacción y lock por semana. Reemplaza el resultado completo de la partición, no incrementa los totales existentes.
6. `publish_and_audit`: registra conteos, resultado, `computed_at`, ventana y estado final; marca la partición como publicada solo después de confirmar la carga.

El flow registra metadata de Prefect (`flow_run_id`, `task_run_id`, deployment, estado y timestamps) junto con el `run_id` de dominio. La política de reintentos usa backoff exponencial con jitter para fallos transitorios de DB/red; errores de contrato o de calidad que superen umbrales acordados fallan explícitamente y generan alerta, no se ocultan como éxito parcial.

### Interfaces de consulta y ejecución previstas

El diseño contempla un módulo nuevo `services/reporting/`, desacoplado de `services/telemetry/`, con sus schemas, consultas y router:

- `GET /reporting/weekly-office-program-performance?week_start=YYYY-MM-DD`: devuelve la semana solicitada o la última semana calculada, con `{ "week_start": ..., "entries": [...] }` y las columnas de negocio previstas en el briefing.
- `GET /reporting/pipeline-runs/latest`: expone estado y metadata de la corrida más reciente, incluida la semana procesada, estado, timestamps, conteos y error sanitizado cuando aplique.
- `POST /reporting/pipeline-runs`: dispara manualmente el deployment Prefect del mismo flow; devuelve el identificador de corrida aceptado, no ejecuta la transformación dentro del proceso HTTP.

Estos son elementos de diseño, no endpoints implementados en esta fase.

## Fase 3 — Idempotencia

### Duplicados en el origen

`eventId` identifica un evento lógico y debe conservarse entre reintentos del cliente. La deduplicación primaria ocurre en la capa de ingesta: `telemetry_events.event_id` es clave primaria y el insert ignora el conflicto. Así, si se reenvía una acción con el mismo `eventId` aunque cambie el timestamp de recepción, queda una sola fila. El `requestId` correlaciona una petición/operación con eventos relacionados; no es la clave de deduplicación. El pipeline trabaja sobre la tabla ya deduplicada y no vuelve a contar un `eventId` repetido si una futura extracción une fuentes auxiliares.

Como defensa adicional, las tareas de validación pueden registrar IDs vistos/repetidos dentro de una ventana y fallar o excluir duplicados de una extracción anómala, pero la autoridad de deduplicación está en la ingesta. No se usa timestamp, usuario ni `requestId` para deduplicar acciones distintas.

### Reintento tras una carga parcial

La unidad reintentable/publicable es la partición semanal `(week_start)`, y cada fila de la salida tiene la clave idempotente `(office, programme_id, week_start)`. El flow recalcula el conjunto semanal desde la fuente y aplica upsert; nunca suma el nuevo resultado encima del valor de reporting ya cargado. La opción preferida es reemplazar todas las filas de una semana en una transacción (o preparar y validar en staging y hacer el merge transaccional), actualizando los conteos y `computed_at` únicamente al publicar. Si una ejecución queda con commits parciales por limitaciones operativas, repetir la misma semana sobrescribe las mismas claves y completa las restantes sin duplicar totales. El pipeline_run fallido se conserva y una nueva corrida registra el intento de recuperación.

Los checkpoints persisten `run_id`, `week_start`, fase alcanzada (`resolved`, `extracted`, `transformed`, `loaded`, `published`), conteos y timestamps. Solo se reanuda directamente desde una etapa si el artefacto intermedio está persistido y validado; si no, se vuelve a extraer y recalcular la partición completa, que es la recuperación segura por defecto.

### Eventos tardíos e invalidación

Los eventos tardíos se asignan a la semana de su `timestamp` de negocio. Una tarea de reconciliación identifica las semanas afectadas desde el watermark/ventana de llegada, invalida lógicamente la publicación previa y relanza el flow para cada semana. El nuevo resultado se recalcula desde todos los eventos de esa partición y se hace upsert: no se incrementan contadores sobre la cifra anterior. La corrida nueva registra `late_data_recompute`, semana y conteos; la fila publicada conserva `computed_at` actualizado y el historial de corridas mantiene la evidencia de qué publicación se sustituyó.

La ventana de búsqueda de tardíos y política de retención del historial deben configurarse con el SLA de captura; inicialmente se recomienda reexaminar semanas recientes en cada corrida y permitir una reejecución manual de cualquier semana histórica.

## Fase 4 — Observabilidad y auditoría

### Corridas, heartbeats y silencio

Bajo `reporting` se propone una tabla genérica `pipeline_runs` para estado/metadata y una relación `pipeline_run_partitions` para las semanas procesadas. Como mínimo se guardan: `run_id`, nombre y versión del flow, IDs Prefect, tipo (scheduled/manual/recovery), `week_start`, estado, etapa/checkpoint, comienzo/fin/duración, conteos extraídos por `event_type`, aceptados/rechazados, filas agregadas/cargadas, watermark, intento, error sanitizado y `computed_at` publicado. En la relación de partición se puede conservar un resumen de IDs fuente/eventos por tipo para auditoría sin copiar los payloads personales.

Cada inicio y fin emite heartbeat. Un flow exitoso con cero eventos es un resultado distinto de un flow ausente/fallido: la salida cero solo se comunica si la consulta a fuente terminó correctamente, la ventana y permisos fueron verificados y los controles de calidad pasaron. Alertas operativas: ninguna corrida exitosa antes del límite de lunes, heartbeat/flow ausente, fuente inaccesible, retraso de watermark, tasa anormal de rechazados, partición vacía inesperada o fallo de publicación. Los umbrales de silencio por oficina se fijan con negocio/operaciones para no interpretar el cierre de una oficina como pérdida de datos.

### Trazabilidad evento → reporte

El `run_id` enlaza tasks, `pipeline_runs`, particiones y logs. En extracción se preservan `eventId`, `requestId`, `event_type` y `timestamp` como contexto de lineage; `eventId` permite localizar el registro fuente y `requestId` ayuda a correlacionar la operación de origen. Los logs y APIs de negocio solo exponen agregados y metadatos sanitizados, nunca payloads completos, usuarios o PII. La auditoría debe permitir reconstruir intervalo, número de eventos leídos por tipo, transformaciones/versionado y filas de salida publicadas, además de diferenciar un pico real de la relectura de una ventana duplicada.

### Crecimiento frente a pérdida de captura

Además de comparar KPIs semana contra semana, el monitor compara eventos por tipo/oficina con corridas, oficinas/sesiones que reportaron cuando esa señal esté disponible, rechazos, duplicados y salud de `POST /telemetry/events`. Un cambio en volumen se marca como “dato posiblemente incompleto” si hay retraso/ausencia de heartbeat, fallos HTTP, huecos de ingestión o cambio en la tasa de rechazo. No se infiere crecimiento del negocio exclusivamente a partir de un aumento de telemetría.

## Fase 5 — Recuperabilidad, transporte y concurrencia

### Caída de base de datos y checkpoints

Ante caída de PostgreSQL, la task falla con estado Prefect `Failed`, aplica reintentos acotados y deja el checkpoint de última fase confirmada. Una falla durante extracción o transformación retoma esa task si sus artefactos fueron guardados de forma durable; si no, vuelve a ejecutar desde extracción. Una falla durante carga revierte la transacción cuando sea posible y repite la partición semanal completa mediante upsert. `published` solo se marca después del commit de todas las filas del periodo; el endpoint de reporte consulta exclusivamente publicaciones completas.

### Buffer del frontend y límites de garantía

La instrumentación actual describe cola en memoria y reintentos, no un outbox durable offline. El diseño no asume que el navegador sea almacenamiento confiable: ante una desconexión larga, un buffer persistente de cliente con límite de tamaño/edad puede evitar pérdidas, pero introduce riesgos de borrado, duplicación, datos obsoletos y exposición en dispositivos compartidos. Para eventos derivados de una operación transaccional, la garantía debe evolucionar a outbox durable del lado servidor en la misma transacción que el cambio de inventario. Eso pertenece a la robustez de captura, no a este pipeline de agregación. El pipeline reporta brechas; no inventa eventos ausentes.

### Reintentos de `POST /telemetry/events`

El cliente conserva el mismo `eventId` al reintentar el mismo evento; backoff exponencial con jitter y límite operativo evitan tormentas. HTTP 200 con ACK recibido significa que el servidor procesó el lote: `stored > 0` informa nuevas inserciones y `stored = 0` puede significar que todos los IDs ya existían (la respuesta actual no distingue duplicado de otros casos sin inserción). El cliente trata el ACK válido como final y no reenvía un evento confirmado. Un timeout o error transitorio sin ACK se reintenta conservando IDs. `Idempotency-Key` puede añadirse para idempotencia de request/lote, pero no reemplaza `eventId` ni es actualmente un requisito implementado. La ingesta actual usa `ON CONFLICT DO NOTHING`; mejoras para distinguir duplicados deben mantener compatibilidad con su ACK.

### Corridas concurrentes

El deployment Prefect tendrá límite de concurrencia y el cargador obtendrá un advisory lock PostgreSQL identificado por pipeline y semana. Si scheduler y POST manual coinciden, el segundo flow espera o se rechaza con estado claro; no se ejecutan publicaciones concurrentes de la misma partición. El lock se libera al cerrar conexión/finalizar la task. La restricción única y upsert siguen siendo una última barrera ante conflictos. Semanas diferentes podrían procesarse en paralelo si los límites de recursos y conexiones lo permiten.

## Fase 6 — Destinos, contrato de salida y límites de v1

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
      "programme_id": "b2b-sales",
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
