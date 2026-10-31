# Auditoría de serialización del backend

**Fecha:** 2026-10-31

**Alcance:** endpoints HTTP de la aplicación FastAPI definidos en `services/api/main.py` y en sus routers incluidos. Esta auditoría registra la clasificación inicial (fase 1) y las decisiones de implementación posteriores (fase 2).

### Leyenda de estado

- ✅ **Verificado (fase 3):** contrato de respuesta implementado y comprobado. En respuestas JSON hay un esquema explícito adecuado; en `204`, descargas y documentación auxiliar, el contrato sin modelo JSON está declarado o generado intencionalmente y documentado.
- ⚠️ **Pendiente de verificación:** contrato implementado, pero todavía no verificado.
- ❌ **Pendiente de implementación:** contrato de salida todavía sin resolver.

Las marcas de las tablas reflejan el estado final de verificación de la fase 3. Las observaciones conservan el hallazgo histórico de fase 1 y las decisiones de implementación de fase 2.

## Criterios de clasificación inicial (fase 1)

- **Ya serializado:** declara `response_model` explícito y ese esquema limita la respuesta a los campos apropiados para el endpoint.
- **Parcialmente serializado:** declara `response_model`, pero el esquema o la proyección necesita revisión por campos innecesarios, omisiones o desajuste con el cliente.
- **Sin serializar:** no declara `response_model` y responde con un `dict`, objeto u otro tipo sin esquema de salida explícito.

Las respuestas intencionales sin cuerpo (`204`) y las descargas de archivos se señalan como excepciones funcionales: no necesitan un modelo JSON, aunque no satisfacen literalmente el criterio de tener `response_model`.

## Rutas de autenticación (revisadas primero)

| Ruta | Método | Propósito | Respuesta actual | Estado | Observaciones |
|---|---|---|---|---|---|
| `/auth/forgot-password` | POST | Solicitar enlace de recuperación | Fase 1: sin `response_model`; devolvía un `dict` con mensaje genérico. | ✅ **Verificado** | Fase 2: `MessageResponse`. Mensaje uniforme; no devuelve email, contraseña ni token. |
| `/auth/reset-password` | POST | Restablecer contraseña con token | Fase 1: sin `response_model`; devolvía un `dict` con mensaje. | ✅ **Verificado** | Fase 2: `MessageResponse`. No devuelve email ni secretos. |
| `/auth/change-password` | POST | Cambiar contraseña de la sesión autenticada | Fase 1: sin `response_model`; devolvía un `dict` con mensaje. | ✅ **Verificado** | Fase 2: `MessageResponse`; no retorna datos de cuenta o credenciales. |
| `/auth/login` | POST | Validar credenciales y emitir sesión | `TokenResponse`; devuelve `access_token` y `token_type`. | ✅ **Verificado** | Respuesta intencionalmente limitada al token de sesión y su tipo; no incluye email ni contraseñas. |
| `/auth/me` | GET | Consultar identidad, rol y perfil propios | `AuthMeResponse`; devuelve email, rol y proyección del perfil. | ✅ **Verificado** | El email propio es necesario para la vista de cuenta. El perfil anidado contiene solo nombre, teléfono y dirección; excluye ID de usuario. |

## Usuarios y perfiles

| Ruta | Método | Propósito | Respuesta actual | Estado | Observaciones |
|---|---|---|---|---|---|
| `/users` | POST | Registrar usuario y perfil | Inicialmente `UserResponse`; devolvía id, email, estado, rol y fecha de creación. | ✅ **Verificado** | Fase 2: `RegistrationResponse` devuelve solo mensaje genérico; no devuelve email, contraseña ni hash. El request de registro sigue separado (`UserCreate`). |
| `/users` | GET | Listar usuarios | `list[UserResponse]`. | ✅ **Verificado** | Fase 2 mantiene la proyección sin hash. El email y metadatos de cuenta forman parte del esquema; autorización de listado queda fuera del alcance de serialización. |
| `/users/{user_id}` | GET | Consultar usuario por ID | `UserResponse`. | ✅ **Verificado** | Fase 2 mantiene el esquema que excluye `hashed_password` y serializa únicamente campos públicos del usuario. |
| `/users/{user_id}` | PUT | Actualizar email, contraseña, rol o estado | `UserResponse`. | ✅ **Verificado** | Fase 2 mantiene la respuesta proyectada; incluso al cambiar contraseña no devuelve `password` ni `hashed_password`. |
| `/users/{user_id}` | DELETE | Eliminar usuario y perfil asociado | Sin modelo de respuesta; `204 No Content` sin cuerpo. | ✅ **Verificado** *(204 intencional)* | Fase 2: decorador declara `response_model=None`; el `204` no tiene representación JSON. |
| `/profiles/me` | GET | Consultar perfil propio | Inicialmente `Profile`. | ✅ **Verificado** | Fase 2: `ProfileResponse` devuelve nombre, teléfono y dirección; omite `id` y `user_id`, que el cliente no consume. |
| `/profiles/me` | PUT | Actualizar perfil propio | Inicialmente `Profile`. | ✅ **Verificado** | Entrada `ProfileUpdate` separada de `ProfileResponse`; respuesta limitada a los campos de perfil usados por el cliente. |

## Proveedores

| Ruta | Método | Propósito | Respuesta actual | Estado | Observaciones |
|---|---|---|---|---|---|
| `/suppliers` | POST | Crear proveedor | `SupplierResponse`; devuelve proveedor, timestamp e ID generado. | ✅ **Verificado** | Fase 2 mantiene el esquema de salida; ID y `updated_at` son campos generados por el sistema. |
| `/suppliers` | GET | Listar proveedores, con filtros opcionales | `list[SupplierResponse]`. | ✅ **Verificado** | Fase 2 mantiene resultados proyectados con el esquema explícito. |
| `/suppliers/{id}` | GET | Consultar proveedor | `SupplierResponse`. | ✅ **Verificado** | Fase 2 mantiene la respuesta tipada. |
| `/suppliers/{id}/rate` | PATCH | Actualizar tarifa mensual | `SupplierResponse`. | ✅ **Verificado** | Fase 2 devuelve el proveedor actualizado, no el registro TinyDB en bruto. |
| `/suppliers/{id}/status` | PATCH | Cambiar estado del proveedor | `SupplierResponse`. | ✅ **Verificado** | Fase 2 devuelve el proveedor actualizado, no el registro TinyDB en bruto. |
| `/suppliers/{id}` | DELETE | Eliminar proveedor | Sin modelo de respuesta; `204 No Content` sin cuerpo. | ✅ **Verificado** *(204 intencional)* | Fase 2: decorador declara `response_model=None`; no corresponde cuerpo JSON. |

## Incidencias

| Ruta | Método | Propósito | Respuesta actual | Estado | Observaciones |
|---|---|---|---|---|---|
| `/api/incidents/analyze` | POST | Analizar CSV y generar agregados | Inicialmente sin `response_model`; dict agregado de `summary_for_api`. | ✅ **Verificado** | Fase 2: `CsvAnalysisResponse`; solo métricas agregadas. No retorna filas, descripciones ni emails de origen. Request sigue siendo multipart (`UploadFile`), no hay modelo de respuesta reutilizado como entrada. |
| `/api/incidents/results/report` | GET | Descargar el último informe agregado | Fase 1: sin modelo JSON; `Response` con bytes CSV y `Content-Disposition`. | ✅ **Verificado** *(descarga intencional)* | Fase 2: decorador declara `response_model=None`; conserva descarga binaria, no JSON. |
| `/api/incidents` | POST | Crear incidencia | `IncidentResponse`; devuelve los campos de incidencia, ID y timestamps. | ✅ **Verificado** | Fase 2 mantiene payload validado y transformado a `IncidentResponse`. |
| `/api/incidents` | GET | Listar incidencias con filtros opcionales | `list[IncidentResponse]`. | ✅ **Verificado** | Fase 2 mantiene cada documento TinyDB convertido a `IncidentResponse`. |
| `/api/incidents/summary` | GET | Obtener conteo total y desgloses | Inicialmente sin `response_model`; devolvía `dict` de agregados. | ✅ **Verificado** | Fase 2: `IncidentSummaryResponse`, solo total y conteos por dimensiones. |
| `/api/incidents/{id}` | GET | Consultar una incidencia | `IncidentResponse`. | ✅ **Verificado** | Fase 2 mantiene conversión del documento a esquema de salida con ID. |
| `/api/incidents/{id}/status` | PATCH | Transicionar el estado de una incidencia | `IncidentResponse`. | ✅ **Verificado** | Fase 2 devuelve la incidencia actualizada mediante el esquema explícito. |

## Inventario

| Ruta | Método | Propósito | Respuesta actual | Estado | Observaciones |
|---|---|---|---|---|---|
| `/inventory/products` | GET | Listar productos con stock calculado | `list[AssetResponse]`. | ✅ **Verificado** | Fase 2 mantiene campos del activo, ID y stock calculado; no devuelve el ORM directamente. |
| `/inventory/products` | POST | Crear producto | `AssetResponse`. | ✅ **Verificado** | Fase 2 devuelve producto validado con ID y stock calculado. |
| `/inventory/products/{id}` | GET | Consultar producto con stock | `AssetResponse`. | ✅ **Verificado** | Fase 2 mantiene proyección explícita del activo y stock. |
| `/inventory/orders/inbound` | POST | Registrar entrada de inventario | Inicialmente `AssetEntryResponse` heredaba el esquema de entrada e incluía `user_uuid`. | ✅ **Verificado** | Fase 2: `AssetEntryCreate` separado de `AssetEntryResponse`; respuesta solo con cantidad, proveedor, oficina, fecha e ID. Omite `asset_id` y UUID del usuario. |
| `/inventory/orders/outbound` | POST | Registrar salida de inventario | Inicialmente `AssetExitResponse` heredaba el esquema de entrada e incluía `user_uuid`. | ✅ **Verificado** | Fase 2: `AssetExitCreate` separado de `AssetExitResponse`; respuesta contiene los campos propios del movimiento y no el UUID interno. |
| `/inventory/orders` | GET | Listar entradas y salidas con producto asociado | Inicialmente lista tipada con objeto de activo anidado y UUID del usuario. | ✅ **Verificado** | Fase 2: unión de proyecciones planas con `order_type`, ID/cantidad/fecha, proveedor para entradas, tipo/destinatario para salidas y `asset_name`/`asset_sku`. Se omiten el objeto Asset completo, `asset_id` y UUID del usuario; la UI recibe solo los datos operativos que representa. |

## Documentación interactiva de FastAPI

FastAPI registra también estas rutas auxiliares por defecto. No son operaciones de negocio; se incluyen para que el inventario cubra las rutas HTTP de la aplicación:

| Ruta | Método | Propósito | Respuesta actual | Estado | Observaciones |
|---|---|---|---|---|---|
| `/openapi.json` | GET | Obtener el documento OpenAPI generado | FastAPI genera el documento OpenAPI como JSON. | ✅ **Verificado** *(auxiliar generada)* | Ruta automática, no una operación de negocio; no tiene un decorador de la aplicación al que asignar `response_model`. |
| `/docs` | GET | Mostrar Swagger UI | Ruta auxiliar automática; devuelve HTML, sin modelo JSON de negocio. | ✅ **Verificado** *(auxiliar generada)* | FastAPI genera esta página HTML; no necesita esquema de respuesta de negocio. La UI respondió HTTP 200 en la prueba manual. |
| `/docs/oauth2-redirect` | GET | Completar el flujo OAuth de Swagger UI | Ruta auxiliar automática; HTML/redirección según el flujo. | ✅ **Verificado** *(auxiliar generada)* | FastAPI genera esta ruta de soporte; no representa datos de negocio. |
| `/redoc` | GET | Mostrar ReDoc | Ruta auxiliar automática; devuelve HTML, sin modelo JSON de negocio. | ✅ **Verificado** *(auxiliar generada)* | FastAPI genera esta página HTML; no necesita esquema de respuesta de negocio. |

## Resumen

La fase 1 inventarió **35 rutas HTTP**: **22 ya serializadas**, **1 parcialmente serializada** y **12 sin serializar** (clasificación histórica). En fase 2 se añadieron modelos de salida a todas las rutas JSON de negocio que carecían de ellos y se ajustaron las proyecciones parciales. En fase 3, las **35 de 35 rutas** quedan ✅ **verificadas**: respuestas JSON con esquemas/proyecciones adecuados; `response_model=None` explícito para las dos operaciones `204` y la descarga CSV; rutas auxiliares automáticas correctamente identificadas como HTML/OpenAPI. Los requests de escritura mantienen esquemas de entrada separados de los de respuesta.

### Verificación de fase 3

- Suite completa existente: `uv run --with-requirements services/api/requirements.txt pytest services/api/tests -q` — **57 passed**, 7 subtests passed y 1 warning no bloqueante de deprecación de Starlette/httpx.
- Prueba manual mediante Swagger UI (`GET /docs`, HTTP 200) y los contratos publicados en `/openapi.json`, usando TestClient y TinyDB en memoria, sin modificar datos persistentes ni enviar correos:
	- `POST /users` — HTTP 201; JSON contiene únicamente `message`, conforme a `RegistrationResponse`. Se comprobó que email y contraseña no aparecen en el cuerpo.
	- `POST /auth/login` — HTTP 200; JSON contiene `access_token` y `token_type`, conforme a `TokenResponse`.
	- `GET /auth/me` — HTTP 200 con bearer token; JSON contiene `email`, `role` y `profile`, y el perfil solo `name`, `phone`, `address`, conforme a `AuthMeResponse` y `ProfileResponse`.
- Los tres esquemas de respuesta también se localizaron en el OpenAPI de `/docs`. Esta verificación manual comprueba rutas representativas; la suite cubre los casos automatizados, pero no equivale a ejecutar manualmente cada una de las 35 rutas.

### Prioridades sugeridas

1. Verificar consumidores externos de `POST /users`: ahora reciben un mensaje genérico en lugar de una proyección de usuario; la interfaz Backoffice no usa el cuerpo de registro y hace login por separado.
2. Confirmar en despliegue que OpenAPI documenta correctamente `response_model=None` para respuestas no JSON (archivo, 204 y páginas auxiliares).

### Decisiones de relaciones

- `/auth/me`: conservar el perfil como objeto anidado y limitarlo a nombre, teléfono y dirección; el email raíz corresponde al usuario autenticado y se necesita para la pantalla de cuenta. Se excluyen claves de usuario/perfil.
- `/profiles/me`: proyección plana (nombre, teléfono, dirección); no se envían IDs que el formulario no consume.
- `/inventory/orders`: no anidar `AssetResponse` ni devolver el `asset_id`; aplanar la relación a `asset_name` y `asset_sku`, y conservar proveedor (entrada), tipo de salida y destinatario (salida) porque son datos operativos visibles en el historial. El identificador de usuario no se devuelve porque no se muestra ni se necesita.
- `/inventory/orders/inbound` y `/outbound`: no devolver clave foránea del activo ni UUID interno del usuario; los datos de movimiento no necesitan objetos relacionados en el acuse de escritura.

La auditoría es estática. No evalúa autorización, configuración de CORS, límites de tasa, errores HTTP ni exposición por logs, salvo cuando esos aspectos ayudan a describir el contrato de respuesta. El montaje de archivos estáticos en `/` y los manejadores de excepciones no se contabilizan como endpoints de API; el montaje sirve los recursos del backoffice y no define una operación JSON individual.
