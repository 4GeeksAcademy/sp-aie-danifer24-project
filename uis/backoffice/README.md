# Nexova Backoffice

Aplicación interna única de Nexova en Next.js + TypeScript. Integra el directorio de proveedores que antes vivía en `uis/application`, junto con inventario, incidencias y herramientas internas.

## Alcance

- Inicio con accesos a proveedores, inventario, incidencias y validación técnica: `/`.
- Directorio de proveedores: `/suppliers`, con búsqueda, filtros, altas, tarifas, estado y renovaciones.
- Inventario: `/inventory/products`, movimientos de entrada/salida e historial de pedidos.
- Gestor de incidencias: `/incidents` y `/incidents/new`.
- Centro de validación técnica: `/validacion-tecnica`.
- Autenticación y cuenta: `/login`, `/register`, recuperación/restablecimiento de contraseña y `/account/profile`.
- El login comparte el JWT y los endpoints de FastAPI con las operaciones protegidas; la API upstream se configura con `SUPPLIERS_API_URL`.
- Las pruebas de autenticación y perfil están en `tests/` y usan Jest + jsdom.

## Comandos

```bash
npm install
npm run dev -- --hostname 0.0.0.0 --port 3001
npm run typecheck
npm run lint
npm test
npm run build
```

## Telemetría de Backoffice (temporal)

Todo el tracking del Backoffice entra por `lib/telemetry.ts` y su función
`track()`. En despliegues con el proxy same-origin, deja
`NEXT_PUBLIC_TELEMETRY_ENDPOINT` sin definir o configúralo como
`/api/telemetry/events`; el proxy envía a `TELEMETRY_ENDPOINT` del entorno
servidor. En desarrollo, si este último no está definido, se usa
`http://127.0.0.1:8000/telemetry/events`. En producción el proxy falla cerrado
con 503 si no hay destino configurado.

La identidad de telemetría requiere `TELEMETRY_PSEUDONYM_KEY` (clave dedicada,
al menos 32 bytes) y `TELEMETRY_ENVIRONMENT` en FastAPI. No se usa el JWT ni el
ID interno como `userId`; sin pseudónimo disponible, `track()` omite los eventos
que el contrato marca como dependientes del usuario. Mantén la clave solo en el
entorno servidor; no la declares con prefijo `NEXT_PUBLIC_`.

El servicio crea el envelope y aplica una allowlist local, acumula hasta 20
eventos o 10 segundos y reintenta tres veces. `sendBeacon` al ocultar/cerrar la
página es de mejor esfuerzo, no garantía de persistencia. El receptor actual es
un stub temporal, sin autenticación ni almacenamiento.

La captura existente cubre login, navegación autorizada, cargas de datos,
respuestas HTTP y validaciones. No se emiten aún los cinco eventos obligatorios
de negocio: la API carece de programa/categoría contractual, coste, mínimo
configurable y detección explícita de edición directa rechazada. No rellenar esos
campos con valores inferidos ni declarar la cobertura completa. La instrumentación
no se comparte con Website, Application ni Talent Pipeline Tracker.

## Estructura principal

- `app/page.tsx`: centro de operaciones y accesos a las áreas internas.
- `app/suppliers/page.tsx`: directorio de proveedores.
- `app/incidents/page.tsx`: listado, filtros, transiciones de estado y resumen de incidencias.
- `app/incidents/new/page.tsx`: formulario de registro de incidencias.
- `app/inventory/`: productos, entradas, salidas e historial.
- `app/login/`, `app/register/`, `app/forgot-password/`, `app/reset-password/` y `app/account/`: autenticación y perfil.
- `lib/incidents.ts`: contratos, etiquetas de negocio y comunicación con la API de incidencias.
- `lib/suppliers.ts`: contratos, validación y cliente HTTP del directorio.
- `lib/api-proxy.ts`: proxy same-origin para proveedores, registro y perfil.
- `app/validacion-tecnica/page.tsx`: vista de validacion tecnica en `/validacion-tecnica`.
- `components/TestingPlayground.tsx`: controles de validacion y resultado JSON.
- `src/types/models.ts`: tipos de dominio (origen compartido en monorepo).
- `src/utils/*.ts`: utilidades del hito (origen compartido en monorepo).
- `lib/sample-data.ts`: datos de prueba.
