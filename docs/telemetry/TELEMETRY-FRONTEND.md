# Instrumentación de Telemetría de Frontend

## Estado Actual (2026-11-04)

Hay una primera implementación cliente, **parcial y best-effort**, que usa el contrato `docs/telemetry/event-schemas.json`. No equivale a cobertura completa ni a persistencia. La validación de código también descarta eventos que no cumplen el contrato; una llamada a `track()` no garantiza que un evento se haya emitido.

### ✅ Piso Técnico Transversal (en todas las apps)

1. **Page Views** (`backoffice_section_viewed`)
  - Se registra en Backoffice tras validar la sesión, con sección canónica y `entry_type: unknown` cuando no se conoce el origen.
  - No se emite para Website o Tracker: el contrato exige un `userId` autenticado y su origen de navegación no está resuelto.

2. **Respuestas HTTP** (`api_request_completed`)
  - Emitidas en los clientes centrales de inventario, incidencias y proveedores del Backoffice.
  - No cubre todas las llamadas HTTP ni los fallos de transporte: el evento requiere un código HTTP real (100–599); no se inventa `status_code: 0` cuando no hubo respuesta.

3. **Errores No Capturados** (`frontend_unhandled_error`)
  - Error Boundary y listeners globales están instalados en Backoffice, Website y Tracker.
  - El fingerprint se calcula en el navegador usando Web Crypto y solo a partir de la clase de error y nombres de bundle saneados; no se hashean mensajes ni stacks crudos.
  - Se omite el evento si no existe una revisión de build hexadecimal de 7–40 caracteres, porque `unknown` no es válido para el schema.

### ⏳ Métricas de Inventario y otros eventos de negocio

Los cinco eventos obligatorios están definidos en el contrato, pero **no se emiten todavía**. Su fuente debe ser el backend después del commit o cuando confirme el rechazo/cruce de negocio; no se deben simular desde el navegador. Faltan metadatos/modelo indicados en `telemetry-plan.md` (programa, categoría de negocio, coste, umbral y detección explícita de edición directa).

El evento de oportunidad `inventory_order_validation_failed` se emite desde algunas validaciones de formularios de Backoffice, sin valores del formulario ni PII. Los eventos de login se emiten desde Backoffice; `session_expired` no se infiere de cualquier 401.

1. **inbound_order_created** - Orden de entrada confirmada
2. **outbound_order_created** - Orden de salida confirmada
3. **stock_threshold_triggered** - Stock por debajo del mínimo
4. **direct_stock_edit_rejected** - Intento rechazado de edición directa
5. **kit_cost_variance_detected** - Variancia de costo > umbral
6. **inventory_order_validation_failed** - Validación fallida en formulario
7. **login_attempted** / **login_succeeded** / **login_failed** - Autenticación
8. **session_expired** - Sesión expirada
9. **frontend_data_load_completed** - Contrato/helper disponibles; no hay instrumentación general activa de cargas

Los eventos implementados pasan por validaciones estrictas antes de encolarse:
- Allowlist de propiedades por evento
- Enums cerrados para valores permitidos
- Validación de moneda por oficina (EUR/Valencia, USD/Miami)
- Sin propiedades no permitidas; el `userId` pseudonimizado HMAC lo entrega el backend y no se calcula en cliente

### 📦 Arquitectura

**packages/shared/**
- `telemetry-service.ts` - Cliente universal de telemetría, validación, cola en memoria, reintentos best-effort y tentativa `sendBeacon` al ocultar/cerrar la página
- `telemetry-events.ts` - Funciones helpers para eventos de negocio

**uis/backoffice/, uis/website/, apps/talent-pipeline-tracker/**
- `lib/telemetry-hooks.tsx` - Error Boundary/listeners y utilidades de API/carga; no hay captura general activa de cargas ni page views públicos
- `app/client-layout.tsx` - ClientLayout que envuelve la app con Error Boundary y listeners globales
- `app/api/telemetry/events/route.ts` - Proxy Next.js que reenvia eventos al backend

**services/api/**
- `routes/telemetry.py` - Endpoint stub `POST /telemetry/events` que recibe y registra eventos
- `schemas.py` - Modelos Pydantic para validación de envelopes

### 🚀 Cómo Verificar

#### 1. Iniciar Stack (Backoffice + Backend)

```bash
# Terminal 1: Backend FastAPI
cd /workspaces/sp-aie-danifer24-project
DATABASE_URL=postgresql://user:pass@localhost/nexova \
uv run --with-requirements services/api/requirements.txt \
  uvicorn services.api.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2: Backoffice
npm --prefix uis/backoffice run dev -- --port 3001
```

#### 2. Abrir DevTools y Verificar Network

```
1. http://127.0.0.1:3001 → DevTools (F12)
2. Network tab → Filter "telemetry" o "api"
3. Navega entre secciones (home → inventory → suppliers)
4. Verifica que ves requests POST a /api/telemetry/events
5. Status: 200, Response: {"received": N}
```

#### 3. Ejemplo de Event Capturado

```json
{
  "events": [
    {
      "eventId": "123e4567-e89b-12d3-a456-426614174000",
      "timestamp": "2026-11-04T00:44:05.123Z",
      "sessionId": "123e4567-e89b-12d3-a456-426614174001",
      "userId": "u1_a1b2c3d4e5f6...",
      "event_type": "backoffice_section_viewed",
      "schemaVersion": "1.0.0",
      "requestId": "123e4567-e89b-12d3-a456-426614174002",
      "properties": {
        "section": "inventory_products",
        "entry_type": "internal_link"
      }
    }
  ]
}
```

### 🔧 Instrumentar Nuevos Eventos de Negocio

Para agregar un evento personalizado:

1. **Definir en event-schemas.json** (ya existe)
   - Agregar en `oneOf` con título, descripción, propiedades
   - Incluir allowlist y validaciones

2. **Crear helper en packages/shared/telemetry-events.ts**
   ```typescript
   export function trackMyEvent(data: MyEventData): void {
     telemetryService.track("my_event_type", data);
   }
   ```

3. **Usar en componente**
   ```typescript
   import { trackMyEvent } from "@packages/shared/telemetry-events";
   
   function MyComponent() {
     const handleClick = () => {
       trackMyEvent({ field1: "value", field2: 42 });
     };
     return <button onClick={handleClick}>Track Event</button>;
   }
   ```

### 📊 Validaciones Locales (Frontend)

El `TelemetryService` aplica **antes** de enviar:

- ✅ Allowlist de propiedades por evento type
- ✅ Tipos correctos (string, number, boolean, null)
- ✅ Longitud máxima de strings (200 caracteres)
- ✅ Enums cerrados (solo valores permitidos)
- ✅ Validaciones numéricas (rango, SafeInteger, etc.)
- ✅ Correlación moneda-oficina (EUR en Valencia, USD en Miami)
- ✅ Formato del `userId` pseudonimizado suministrado por el backend; no se calcula ni firma en el cliente
- SessionId UUID aleatorio guardado en `sessionStorage` mientras la sesión del navegador esté disponible
- Reintentos exponenciales acotados (500ms, 1s, 2s); la cola es en memoria y no sobrevive a una recarga
- `sendBeacon()` intenta enviar al ocultar/cerrar la página; `true` solo indica aceptación local del navegador, no ACK del servidor

La validación es estructural y no sustituye la verificación semántica/catálogos del backend. Los eventos inválidos se descartan silenciosamente para no interferir con la aplicación; los errores de telemetría no deben bloquear el trabajo del usuario.

### 📡 Backend Recibe

El endpoint `POST /telemetry/events` en FastAPI:

1. Valida que sea un batch con array de events
2. Registra cantidad y tipos de eventos (sin payload)
3. Devuelve `{"received": N}` (ACK)
4. **No persiste** en esta fase (stub)

### 🎯 Próximas Fases

1. **Persistencia**: Almacenar eventos en PostgreSQL
2. **Reportes**: Dashboard L&D (matrículas por programa, tasa de finalización)
3. **Alertas**: Notificaciones cuando se cumplen umbrales
4. **Auditoría**: Logs separados para compliance

---

**Estado de verificación:** TypeScript/ESLint/Build deben ejecutarse tras los cambios actuales. La prueba Network solo confirma el POST/ACK del stub; no demuestra persistencia, entrega durable ni que todos los eventos se emitan.
