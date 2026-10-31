# Auditoría de serialización del backend

**Fecha:** 2026-10-31
**Alcance:** endpoints HTTP de la aplicación FastAPI definidos en `services/api/main.py` y en sus routers incluidos. Revisión estática de las rutas, modelos de respuesta y valores retornados; no se modificó la implementación.

## Criterios

- **Ya serializado:** declara `response_model` explícito y ese esquema limita la respuesta a los campos apropiados para el endpoint.
- **Parcialmente serializado:** declara `response_model`, pero el esquema o la proyección necesita revisión por campos innecesarios, omisiones o desajuste con el cliente.
- **Sin serializar:** no declara `response_model` y responde con un `dict`, objeto u otro tipo sin esquema de salida explícito.

Las respuestas intencionales sin cuerpo (`204`) y las descargas de archivos se señalan como excepciones funcionales: no necesitan un modelo JSON, aunque no satisfacen literalmente el criterio de tener `response_model`.

## Rutas de autenticación (revisadas primero)

| Ruta | Método | Propósito | Respuesta actual | Estado | Observaciones |
|---|---|---|---|---|---|
| `/auth/forgot-password` | POST | Solicitar enlace de recuperación | Sin `response_model`; devuelve un `dict` con un mensaje genérico. | **Sin serializar** | No revela si el correo existe y no devuelve el email ni el token. El mensaje es apropiado; conviene tipar la respuesta genérica. |
| `/auth/reset-password` | POST | Restablecer contraseña con token | Sin `response_model`; devuelve un `dict` con un mensaje. | **Sin serializar** | No devuelve contraseña, hash, email ni token. Puede añadirse un esquema de respuesta para formalizar el contrato. |
| `/auth/change-password` | POST | Cambiar contraseña de la sesión autenticada | Sin `response_model`; devuelve un `dict` con un mensaje. | **Sin serializar** | No devuelve credenciales ni datos de usuario. La respuesta podría tiparse. |
| `/auth/login` | POST | Validar credenciales y emitir sesión | `TokenResponse`; devuelve `access_token` y `token_type`. | **Ya serializado** | No incluye email ni objeto de usuario; no expone contraseña ni hash. |
| `/auth/me` | GET | Consultar identidad, rol y perfil propios | `AuthMeResponse`; devuelve email, rol y `Profile`. | **Ya serializado** | Proyección explícita: no contiene `hashed_password`. El email es pertinente como identidad de la sesión. |

## Usuarios y perfiles

| Ruta | Método | Propósito | Respuesta actual | Estado | Observaciones |
|---|---|---|---|---|---|
| `/users` | POST | Registrar usuario y perfil | `UserResponse`; devuelve id, email, estado, rol y fecha de creación. | **Parcialmente serializado** | Excluye `hashed_password` y no devuelve la contraseña de entrada. Revisar si es necesario devolver el email inmediatamente después del registro: el cliente ya lo envió y la guía de auditoría recomienda justificar su eco en respuestas de autenticación/registro. |
| `/users` | GET | Listar usuarios | `list[UserResponse]`. | **Ya serializado** | Proyección sin hash. El email y los metadatos de cuenta forman parte del esquema de usuario; los controles de autorización para listar son una revisión separada de esta auditoría. |
| `/users/{user_id}` | GET | Consultar usuario por ID | `UserResponse`. | **Ya serializado** | Excluye `hashed_password`; serializa únicamente campos públicos del usuario. |
| `/users/{user_id}` | PUT | Actualizar email, contraseña, rol o estado | `UserResponse`. | **Ya serializado** | Incluso si se actualiza la contraseña, la respuesta proyectada no devuelve `password` ni `hashed_password`. |
| `/users/{user_id}` | DELETE | Eliminar usuario y perfil asociado | Sin `response_model`; responde `204 No Content` sin cuerpo. | **Sin serializar** *(excepción intencional)* | No hay representación JSON que serializar. El `204` sin cuerpo es apropiado; no requiere incorporar un esquema solo para este endpoint. |
| `/profiles/me` | GET | Consultar perfil propio | `Profile`. | **Ya serializado** | Campos limitados al perfil: id, user_id, nombre, teléfono y dirección; no incluye credenciales. |
| `/profiles/me` | PUT | Actualizar perfil propio | `Profile`. | **Ya serializado** | Devuelve la proyección tipada del perfil actualizado, sin credenciales. |

## Proveedores

| Ruta | Método | Propósito | Respuesta actual | Estado | Observaciones |
|---|---|---|---|---|---|
| `/suppliers` | POST | Crear proveedor | `SupplierResponse`; devuelve proveedor, timestamp e ID generado. | **Ya serializado** | Esquema de respuesta explícito; ID y `updated_at` son campos generados por el sistema. |
| `/suppliers` | GET | Listar proveedores, con filtros opcionales | `list[SupplierResponse]`. | **Ya serializado** | Los resultados se proyectan con el mismo esquema explícito. |
| `/suppliers/{id}` | GET | Consultar proveedor | `SupplierResponse`. | **Ya serializado** | Respuesta tipada. |
| `/suppliers/{id}/rate` | PATCH | Actualizar tarifa mensual | `SupplierResponse`. | **Ya serializado** | Devuelve el proveedor actualizado, no el registro TinyDB en bruto. |
| `/suppliers/{id}/status` | PATCH | Cambiar estado del proveedor | `SupplierResponse`. | **Ya serializado** | Devuelve el proveedor actualizado, no el registro TinyDB en bruto. |
| `/suppliers/{id}` | DELETE | Eliminar proveedor | Sin `response_model`; responde `204 No Content` sin cuerpo. | **Sin serializar** *(excepción intencional)* | No se devuelve un cuerpo JSON; el `204` es apropiado. |

## Incidencias

| Ruta | Método | Propósito | Respuesta actual | Estado | Observaciones |
|---|---|---|---|---|---|
| `/api/incidents/analyze` | POST | Analizar CSV y generar agregados | Sin `response_model`; devuelve un `dict` producido por `summary_for_api`. | **Sin serializar** | La respuesta es agregada y no devuelve filas crudas, descripciones ni emails. Se recomienda declarar un esquema Pydantic para fijar el contrato del resumen. |
| `/api/incidents/results/report` | GET | Descargar el último informe agregado | Sin `response_model`; devuelve `Response` con bytes CSV y `Content-Disposition`. | **Sin serializar** *(descarga intencional)* | Es una respuesta de archivo, no JSON. Mantener la respuesta binaria y documentar su media type es adecuado; no aplicar un modelo JSON. |
| `/api/incidents` | POST | Crear incidencia | `IncidentResponse`; devuelve los campos de incidencia, ID y timestamps. | **Ya serializado** | El payload se valida y transforma a `IncidentResponse`. |
| `/api/incidents` | GET | Listar incidencias con filtros opcionales | `list[IncidentResponse]`. | **Ya serializado** | Cada documento TinyDB se convierte a `IncidentResponse`. |
| `/api/incidents/summary` | GET | Obtener conteo total y desgloses | Sin `response_model`; devuelve un `dict` de agregados. | **Sin serializar** | El contenido está acotado a conteos, pero falta un esquema explícito para tipar y estabilizar el contrato. |
| `/api/incidents/{id}` | GET | Consultar una incidencia | `IncidentResponse`. | **Ya serializado** | El documento se convierte a esquema de salida con ID. |
| `/api/incidents/{id}/status` | PATCH | Transicionar el estado de una incidencia | `IncidentResponse`. | **Ya serializado** | Devuelve la incidencia actualizada mediante el esquema explícito. |

## Inventario

| Ruta | Método | Propósito | Respuesta actual | Estado | Observaciones |
|---|---|---|---|---|---|
| `/inventory/products` | GET | Listar productos con stock calculado | `list[AssetResponse]`. | **Ya serializado** | Incluye campos del activo, ID y stock actual calculado; no devuelve el ORM directamente. |
| `/inventory/products` | POST | Crear producto | `AssetResponse`. | **Ya serializado** | Devuelve producto validado con ID y stock calculado. |
| `/inventory/products/{id}` | GET | Consultar producto con stock | `AssetResponse`. | **Ya serializado** | Proyección explícita del activo y stock. |
| `/inventory/orders/inbound` | POST | Registrar entrada de inventario | `AssetEntryResponse`. | **Ya serializado** | Incluye datos de la entrada y metadatos generados (`id`, `created_at`, `user_uuid`); no devuelve la entidad SQLModel sin filtrar. |
| `/inventory/orders/outbound` | POST | Registrar salida de inventario | `AssetExitResponse`. | **Ya serializado** | Incluye datos de salida y metadatos de auditoría; modelo explícito. |
| `/inventory/orders` | GET | Listar entradas y salidas con producto asociado | `list[AssetEntryOrderResponse \| AssetExitOrderResponse]`. | **Ya serializado** | Unión de esquemas con `order_type` literal; incluye la proyección `AssetResponse` del activo asociado. |

## Documentación interactiva de FastAPI

FastAPI registra también estas rutas auxiliares por defecto. No son operaciones de negocio; se incluyen para que el inventario cubra las rutas HTTP de la aplicación:

| Ruta | Método | Propósito | Respuesta actual | Estado | Observaciones |
|---|---|---|---|---|---|
| `/openapi.json` | GET | Obtener el documento OpenAPI generado | Sin `response_model`; devuelve el documento OpenAPI como JSON. | **Sin serializar** *(ruta auxiliar generada)* | Esquema generado por FastAPI, no una respuesta de negocio; no requiere modelo de respuesta de aplicación. |
| `/docs` | GET | Mostrar Swagger UI | Sin `response_model`; devuelve HTML. | **Sin serializar** *(ruta auxiliar generada)* | Interfaz de documentación generada por FastAPI. |
| `/docs/oauth2-redirect` | GET | Completar el flujo OAuth de Swagger UI | Sin `response_model`; devuelve HTML/una respuesta de redirección según el flujo. | **Sin serializar** *(ruta auxiliar generada)* | Ruta auxiliar de la interfaz de documentación. |
| `/redoc` | GET | Mostrar ReDoc | Sin `response_model`; devuelve HTML. | **Sin serializar** *(ruta auxiliar generada)* | Interfaz de documentación generada por FastAPI. |

## Resumen

Se identificaron **35 rutas HTTP**: **22 ya serializadas**, **1 parcialmente serializada** y **12 sin serializar** según los criterios definidos. De estas últimas, **7 son rutas sin respuesta JSON de negocio** (dos `DELETE` con `204`, descarga CSV y cuatro auxiliares de documentación); las otras cinco son respuestas JSON sin `response_model` (las tres respuestas de auth y los endpoints de análisis CSV y resumen de incidencias).

### Prioridades sugeridas

1. Añadir esquemas de salida pequeños para las tres respuestas de auth que hoy devuelven mensajes en `dict`, preservando el mensaje genérico de recuperación.
2. Definir esquemas de respuesta para los agregados de análisis CSV y `/api/incidents/summary`.
3. Decidir y documentar si el email en la respuesta de registro es necesario para el siguiente paso del cliente; no se observó exposición de contraseñas ni hashes en las respuestas revisadas.

La auditoría es estática. No evalúa autorización, configuración de CORS, límites de tasa, errores HTTP ni exposición por logs, salvo cuando esos aspectos ayudan a describir el contrato de respuesta. El montaje de archivos estáticos en `/` y los manejadores de excepciones no se contabilizan como endpoints de API; el montaje sirve los recursos del backoffice y no define una operación JSON individual.
