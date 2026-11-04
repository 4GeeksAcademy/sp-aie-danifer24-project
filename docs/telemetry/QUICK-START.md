# Guía Rápida: Telemetría de Frontend

## Verificar que los eventos se envían

### 1. Abrir DevTools Network en Backoffice

```bash
# Terminal 1: Backend
uv run --with-requirements services/api/requirements.txt \
  uvicorn services.api.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2: Backoffice
npm --prefix uis/backoffice run dev -- --port 3001
```

### 2. En el navegador

1. http://127.0.0.1:3001
2. F12 → Network → Filtrar por "telemetry"
3. Navegar entre secciones
4. Ver requests POST a `/api/telemetry/events` con status **200**

### 3. Ejemplo de respuesta esperada

```json
{
  "received": 1
}
```

---

## Instrumentar un nuevo evento de negocio

### Paso 1: Definir en event-schemas.json (ya existe)

Revisar que tu evento está en `docs/telemetry/event-schemas.json` con:
- `title` (nombre del evento)
- `properties` (campos)
- `allowlist` de propiedades permitidas

### Paso 2: Crear helper en telemetry-events.ts

```typescript
// packages/shared/telemetry-events.ts
export function trackMyEvent(data: MyEventData): void {
  telemetryService.track("my_event_type", data);
}
```

### Paso 3: Usar en componente

```typescript
import { trackMyEvent } from "@packages/shared/telemetry-events";

function MyComponent() {
  const handleAction = () => {
    trackMyEvent({
      field1: "value",
      field2: 42,
    });
  };
  
  return <button onClick={handleAction}>Trigger Event</button>;
}
```

---

## Errores comunes

### Error: "Cannot find module @packages/shared/telemetry-service"

**Solución:** Actualizar `tsconfig.json` de tu app:

```json
{
  "compilerOptions": {
    "paths": {
      "@/*": ["./*"],
      "@packages/shared/*": ["../../packages/shared/*"]
    }
  }
}
```

### Error: Eventos no llegan al backend

**Verificar:**
1. DevTools Network: ¿ves requests a `/api/telemetry/events`?
2. Status code: ¿es 200?
3. Backend logs: ¿ves "Telemetry batch received"?

**Debug:**
```javascript
// En DevTools Console
fetch('/api/telemetry/events', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    events: [{
      eventId: crypto.randomUUID(),
      timestamp: new Date().toISOString(),
      sessionId: crypto.randomUUID(),
      userId: null,
      event_type: 'login_attempted',
      schemaVersion: '1.0.0',
      requestId: crypto.randomUUID(),
      properties: { source: 'backoffice' }
    }]
  })
}).then(r => r.json()).then(console.log);
```

---

## Validaciones aplicadas automáticamente

✅ **Allowlist:** Solo propiedades permitidas  
✅ **Enums:** Solo valores cerrados  
✅ **Tipos:** string, number, boolean, null  
✅ **Tamaño:** strings máx 200 caracteres  
✅ **Moneda:** EUR si office=valencia, USD si office=miami  
✅ **Sin PII:** Nombres, emails, tokens rechazados  
✅ **UserId:** Pseudonimizado con HMAC-SHA256  

---

## Referencia: Event Types disponibles

| Event | Props | Obliga UserId |
|-------|-------|--------------|
| `backoffice_section_viewed` | section, entry_type | ✅ |
| `api_request_completed` | route_template, method, status_code, duration_ms | ❌ |
| `frontend_unhandled_error` | section, source, error_code, fingerprint, app_version | ❌ |
| `inbound_order_created` | office, product_id, ... | ✅ |
| `outbound_order_created` | office, product_id, ... | ✅ |
| `login_attempted` | source | ❌ |
| `login_succeeded` | source, duration_ms | ✅ |
| `login_failed` | reason_code, layer, duration_ms | ❌ |

Referencia completa: [TELEMETRY-FRONTEND.md](./TELEMETRY-FRONTEND.md)
