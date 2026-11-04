# Instrumentación de Telemetría de Frontend

## Estado Actual (2026-11-04)

Se ha completado una **instrumentación amplia de telemetría** que cubre:

### ✅ Piso Técnico Transversal (en todas las apps)

1. **Page Views** (`backoffice_section_viewed`)
   - Se registra automáticamente cuando navegas a secciones principales
   - Captura: sección, tipo de entrada (direct/internal_link)
   - Apps: Backoffice, Website, Tracker

2. **Latencias de API** (`api_request_completed`)
   - Capturadas automáticamente en todas las llamadas HTTP
   - Métrica: route_template, método HTTP, status code, duración en ms
   - Invocado: Backoffice (inventory, auth, incidents, suppliers)

3. **Errores No Capturados** (`frontend_unhandled_error`)
   - Error Boundary: captura render errors en componentes
   - window.onerror: errores globales de script
   - unhandledrejection: promesas rechazadas sin manejo
   - Métrica: fingerprint SHA-256 sanitizado, fuente (error_boundary/window_error/unhandled_rejection), app_version

### ✅ Métricas Obligatorias de Negocio (Inventario)

Definidas en `packages/shared/telemetry-events.ts`:

1. **inbound_order_created** - Orden de entrada confirmada
2. **outbound_order_created** - Orden de salida confirmada
3. **stock_threshold_triggered** - Stock por debajo del mínimo
4. **direct_stock_edit_rejected** - Intento rechazado de edición directa
5. **kit_cost_variance_detected** - Variancia de costo > umbral
6. **inventory_order_validation_failed** - Validación fallida en formulario
7. **login_attempted** / **login_succeeded** / **login_failed** - Autenticación
8. **session_expired** - Sesión expirada
9. **frontend_data_load_completed** - Carga de datos completada (ready/empty/error)

Todas las métricas incluyen validaciones estrictas:
- Allowlist de propiedades por evento
- Enums cerrados para valores permitidos
- Validación de moneda por oficina (EUR/Valencia, USD/Miami)
- Sin PII directa (solo userId pseudonimizado con HMAC)

### 📦 Arquitectura

**packages/shared/**
- `telemetry-service.ts` - Cliente universal de telemetría, validación, cola en memoria, reintentos
- `telemetry-events.ts` - Funciones helpers para eventos de negocio

**uis/backoffice/, uis/website/, apps/talent-pipeline-tracker/**
- `lib/telemetry-hooks.tsx` - Hooks React para capturar page views, errores, cargas
- `app/client-layout.tsx` - ClientLayout que envuelve la app con Error Boundary y hooks
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
- ✅ UserId pseudonimizado (HMAC-SHA256 con clave privada)
- ✅ SessionId aleatorio persistente en sesión
- ✅ Reintentos exponenciales (500ms, 1s, 2s)
- ✅ sendBeacon() al cerrar/ocultar página

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

**Validado:** TypeScript, ESLint, Build (Backoffice, Website), Network en DevTools
