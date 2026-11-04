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
3. Iniciar sesión y abrir una sección protegida de Backoffice, o ejecutar una acción que tenga instrumentación explícita.
4. Ver requests POST a `/api/telemetry/events`. El proxy de desarrollo puede devolver **200** con un ACK del stub.

No todas las navegaciones ni llamadas HTTP generan eventos. El `200` y la respuesta `{"received": N}` solo indican que el stub recibió el batch; no prueban persistencia ni entrega durable. Las vistas de sección se registran tras validar sesión. Los eventos obligatorios de inventario aún no se emiten.

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

## Validaciones del cliente (alcance limitado)

El cliente valida las propiedades, tipos, enums, límites y correlación de moneda/oficina de los eventos implementados. Rechaza propiedades desconocidas y descarta eventos que no pasan la validación; no es un saneador general de PII. La validación de servidor y el schema siguen siendo necesarios.

`userId` es un pseudónimo HMAC generado por el backend y obtenido del endpoint de identidad autenticada; no se calcula ni firma en el navegador. La pseudonimización no equivale a anonimización.

La cola/reintentos están en memoria y son best-effort. `sendBeacon()` solo intenta enviar al ocultar/cerrar la página; su aceptación local no confirma recepción del servidor.

---

## Referencia: Event Types disponibles

| Event | Estado/captura actual |
|-------|-------------------------|
| `backoffice_section_viewed` | Backoffice, tras validar sesión; requiere identidad pseudonimizada |
| `api_request_completed` | Algunas llamadas centrales de inventario, incidencias y proveedores; no cobertura global |
| `frontend_unhandled_error` | Error Boundary y listeners globales en las tres apps; puede omitirse si falta fingerprint o versión válida |
| `inventory_order_validation_failed` | Algunas validaciones de formularios de Backoffice |
| `login_attempted`, `login_succeeded`, `login_failed` | Flujos de login instrumentados de Backoffice |
| Eventos obligatorios de inventario | Definidos en contrato, pero no emitidos aún; deben originarse en backend |
| `frontend_data_load_completed` | Definido/validado, pero sin instrumentación activa general |

Referencia completa: [TELEMETRY-FRONTEND.md](./TELEMETRY-FRONTEND.md)
