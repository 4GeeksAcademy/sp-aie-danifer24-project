# Plan de pruebas

Este documento registra el alcance previsto antes de implementar las suites y explica cómo ejecutarlas. Todas las pruebas usan almacenamiento temporal/mocks; no crean usuarios en la base de datos real ni envían correos reales.

## Backend — pytest + FastAPI

Suites: `services/api/tests/test_register.py`, `services/api/tests/test_login.py`, `services/api/tests/test_token.py`, `services/api/tests/test_forgot_password.py`, `services/api/tests/test_reset_password.py` y `services/api/tests/test_change_password.py`, con `TestClient`, TinyDB en memoria y servicio de correo simulado. Los casos ampliados se mantienen en `services/api/tests/test_auth_extended.py` y `services/api/tests/test_password_reset.py`. Los tests residen en la raíz del proyecto FastAPI (`services/api`).

Desde la raíz del repositorio:

```bash
uv run --with-requirements services/api/requirements.txt pytest services/api/tests
uv run --with-requirements services/api/requirements.txt pytest services/api/tests --cov=services.api.routes.auth --cov=services.api.security --cov=services.api.services.passwords --cov-report=term-missing
```

Las órdenes se ejecutan desde la raíz del monorepo e incluyen la instalación de dependencias de ejecución definidas por la API. Pytest descubre las suites en `services/api/tests/`, incluida la suite unittest de recuperación. La segunda mide rutas, seguridad y servicios de contraseña. Cada endpoint tiene un módulo dedicado con camino feliz, caso límite y modo de fallo.

| Endpoint | Camino feliz | Casos límite | Modos de fallo / seguridad |
|---|---|---|---|
| `POST /auth/login` | Credenciales válidas devuelven `200`, JWT de acceso y tipo `bearer`; el JWT sirve en `/auth/me`. | Email con mayúsculas/espacios se normaliza; email mal formado o payload incompleto/extráneo devuelve `422`. | Contraseña errónea, cuenta inexistente o desactivada devuelve `401` sin revelar cuál dato falló. |
| `GET /auth/me` | Bearer válido devuelve email, rol y perfil asociado. | Usuario válido sin perfil devuelve `404` estructurado. | Falta el bearer, token malformado, caducado, manipulado, reset-token en lugar de access-token, usuario borrado/desactivado devuelven `401`. |
| `POST /auth/forgot-password` | Usuario activo recibe un token de recuperación por el correo simulado y la respuesta es genérica. | Correo desconocido, inactivo o con espacios/mayúsculas conserva respuesta genérica; no revela existencia de cuenta. | Fallo del proveedor de correo no cambia la respuesta pública ni deja secretos en logs; no se envía correo a usuario inactivo. |
| `POST /auth/reset-password` | Token válido cambia la contraseña, permite login con la nueva y no con la anterior. | Token válido es de un solo uso, expira a 30 minutos; emitir otro invalida enlaces anteriores; contraseñas en límites de 8–72 bytes y comportamiento UTF-8. | Token ausente/malformado, expirado, manipulado, ya usado, de sesión, ligado a hash de contraseña anterior, o usuario eliminado/inactivo devuelve error controlado; el token no permite autenticar sesión. |
| `POST /auth/change-password` | Sesión y contraseña actual correctas cambian la contraseña; la nueva permite login. | Contraseña nueva respeta límites de longitud en caracteres/bytes y campos obligatorios se validan una vez autenticado. | Sin sesión/credenciales inválidas devuelve `401`; contraseña actual errónea o enlace reset invalidado devuelve error controlado. |

También se comprobarán las respuestas de validación estructuradas y que las excepciones internas no expongan detalles sensibles. La base TinyDB se crea en memoria por prueba y el envío de email se simula, para que la suite sea repetible y aislada.

## Frontend — Jest + ts-jest + TypeScript

Suites: `uis/application/tests/auth.test.ts`, `uis/application/tests/account.test.ts` y `uis/application/tests/shared-session.test.ts`, probando las funciones de `lib/auth.ts`, `lib/passwords.ts`, `lib/account.ts` y `packages/shared/auth/session.ts`. Jest mantiene el root del monorepo para instrumentar la utilidad compartida. Se ejecuta desde `uis/application`:

```bash
npm test
npm run test:coverage
```

Jest usa `ts-jest`, `jest-environment-jsdom`, el alias `@/` y `jsdom`; `fetch` se sustituye por mocks. Los casos de SSR y almacenamiento inaccesible también se cubren sin contactar servicios externos.

| Área | Camino feliz | Casos límite | Modos de fallo |
|---|---|---|---|
| Cliente auth | Login envía email normalizado y devuelve `access_token`; registrar cuenta acepta `2xx`; guardar, leer y borrar token opera sobre la clave esperada. | SSR sin `window`; respuestas con JSON inválido o esquema de login inesperado; errores 409/422 de registro mapeados a campos. | Rechazo de red, `401`, `5xx`, localStorage bloqueado; mensajes no deben incluir respuesta interna/token. |
| Contraseñas | Forgot/reset envían endpoint y payload correctos; cambio añade bearer existente. | Entradas y respuesta vacía `2xx`; validación `400` específica para contraseña actual y reset; `422` legible. | Red caída, `5xx`, sesión ausente o `401` durante cambio; token guardado se elimina ante sesión inválida. |
| Cuenta/perfil | GET del perfil autenticado y PUT de cambios transmiten bearer, JSON y devuelven respuesta tipada. | Aborto explícito de petición; respuesta JSON inválida; código `404`. | Sesión ausente o caducada (`401`) limpia token; `403`, `5xx` y fallo de red muestran error controlado. |
| Sesión compartida | `signIn` normaliza email y almacena el token; `readSessionToken` y `clearSessionToken` leen/limpian; `validateSession` envía el bearer y acepta una identidad válida. | Almacenamiento de navegador no disponible y aborto de la petición. | Credenciales inválidas, token ausente/revocado, respuesta malformada, `5xx` y fallo de red se rechazan de forma controlada. |

Se reemplazarán `fetch` y `localStorage` con dobles de prueba; ninguna suite frontend contactará la API real. No se planean pruebas visuales de componentes ni E2E en este alcance.

## Por qué estos casos

Se priorizan los límites de confianza del flujo de autenticación (enumeración de cuentas, JWT inválido/reutilizado, autorización y secretos), el ciclo completo de recuperación/cambio de contraseña, y las traducciones de fallos HTTP que usa la interfaz. Los casos de límites de contraseña cubren las restricciones reales de bcrypt (72 bytes UTF-8), y la base en memoria/mocks evita efectos externos y hace cada ejecución independiente.

## Verificación realizada

- Backend desde la raíz del monorepo: `uv run --with-requirements services/api/requirements.txt pytest services/api/tests -q` — **57 passed**, además de 7 subtests.
- Cobertura: `uv run --with-requirements services/api/requirements.txt pytest services/api/tests --cov=services.api.routes.auth --cov=services.api.security --cov=services.api.services.passwords --cov-report=term-missing -q` — **93% total** en autenticación (auth routes 96%, security 90%, password service 93%), sobre el mínimo requerido de 70%.
- Frontend actualizado: `cd uis/application && npm run test:coverage` — **3 suites y 18 tests passed**; cobertura total de líneas **91.77%**, sentencias **87.97%**, ramas **84.84%** y funciones **84%**, incluyendo 100% de líneas en `packages/shared/auth/session.ts`. `npm run typecheck` y `npm run lint` pasaron sin errores ni warnings.
- Cobertura de utilidades de autenticación: incluye `lib/auth.ts`, `lib/passwords.ts`, `lib/account.ts` y `packages/shared/auth/session.ts`; las pruebas de sesión comprueban éxito, tokens ausentes/revocados, respuestas inválidas, errores de red/servidor, almacenamiento bloqueado y aborto. No se detectaron bugs en estas pruebas, por lo que no hubo cambios funcionales que corregir.
- Los informes generados bajo `coverage/` quedan excluidos de ESLint y de la recolección de cobertura para que no contaminen las validaciones.
- La suite FastAPI muestra un aviso deprecado de Starlette: su `TestClient` importa `httpx` con una ruta que recomienda `httpx2`; no afecta al resultado. La instalación frontend informó 25 vulnerabilidades (20 moderadas, 5 altas); revisar por separado antes de aplicar actualizaciones automáticas.
