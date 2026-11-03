# Informe de caching

## Objetivo y estado

Este informe registra la línea base de inventario sin caché y las decisiones de frontend/backend. Los números de latencia de inventario corresponden a mediciones sin caché; el backend cachea ahora el listado y el resumen de incidencias.

## Medición antes del seed y sin caché

La medición se realizó contra la API de prueba en `http://127.0.0.1:8001`, conectada a PostgreSQL 16 local (`nexova_test` en el puerto 5433). La base estaba vacía. Se hicieron 20 solicitudes secuenciales a `GET /inventory/products`; todas devolvieron HTTP 200. Los tiempos se midieron desde el cliente e incluyen el transporte local y el procesamiento de la API.

| Métrica | Tiempo |
| --- | ---: |
| Mínimo | 1.9 ms |
| Mediana | 2.8 ms |
| Media | 7.3 ms |
| p95 | 7.9 ms |
| Máximo | 87.6 ms |

Filas antes del seed: 0 activos, 0 entradas y 0 salidas.

## Seed y medición posterior, todavía sin caché

Se ejecutó `services/api/seed_performance.py` únicamente contra la base local `nexova_test`. Insertó 1.000 activos, 3.000 entradas y 2.000 salidas. Se repitieron 20 solicitudes secuenciales al mismo endpoint; todas devolvieron HTTP 200.

| Métrica | Antes del seed | Después del seed |
| --- | ---: | ---: |
| Mínimo | 1.9 ms | 938.7 ms |
| Mediana | 2.8 ms | 992.8 ms |
| Media | 7.3 ms | 999.0 ms |
| p95 | 7.9 ms | 1,046.3 ms |
| Máximo | 87.6 ms | 1,047.0 ms |

Filas después del seed: 1.000 activos, 3.000 entradas y 2.000 salidas. La mediana creció aproximadamente 355 veces en este entorno. La muestra pre-seed era una base vacía y el máximo de 87.6 ms refleja ruido de arranque; por tanto, la razón entre medianas es orientativa, no una comparación de producción.

`GET /inventory/products` calcula el stock por activo consultando las sumas de entradas y salidas. Con 1.000 activos, la latencia cercana a un segundo lo convierte en un candidato de optimización. El listado tiene ahora TTL de 5 s e invalidación tras escrituras de producto y movimientos. La lectura individual usada para comprobaciones de disponibilidad sigue sin caché.

Como comprobación exploratoria separada, la API configurada con la base remota existente respondió 20 veces con HTTP 200: 6 activos, 5 entradas y 4 salidas; media 194.1 ms y mediana 192.2 ms. No se modificó Supabase. Esa muestra no es comparable con las cifras locales por la diferencia de entorno y datos.

## Análisis backend por endpoint

La API declara 31 endpoints de negocio. Las frecuencias siguientes son **estimaciones**, no conteos de tráfico: el middleware de timing registra duración por petición, pero no agrega frecuencias. Se infieren del flujo de Backoffice y del tipo de operación. Coste bajo significa acceso puntual/validación sencilla; medio, escaneo o actualización de una tabla; alto, trabajo proporcional al conjunto de datos o cómputo/IO externo. La estabilidad indica cuánto suelen cambiar los datos que devuelve cada lectura.

| Endpoint | Coste | Frecuencia estimada | Cambio de datos subyacentes | Decisión |
| --- | --- | --- | --- | --- |
| `POST /users` | Medio: hash de contraseña y escritura | Baja | Alta durante registro | No cachear; escritura y resultado de alta |
| `GET /users` | Medio: lista de usuarios | Baja | Media | No cachear; devuelve datos de cuenta |
| `GET /users/{user_id}` | Bajo: búsqueda por ID | Baja | Media | No cachear; respuesta privada y dependiente de permisos |
| `PUT /users/{user_id}` | Medio: validación y escritura | Baja | Alta al editar | No cachear; mutación de cuenta |
| `DELETE /users/{user_id}` | Medio: borrado y limpieza de perfil | Baja | Alta al borrar | No cachear; mutación de cuenta |
| `POST /auth/forgot-password` | Medio/alto: TinyDB y posible envío externo | Baja | Alta por token de un solo uso | No cachear; respuesta ligada a una cuenta/operación |
| `POST /auth/reset-password` | Medio: validar token y cambiar hash | Baja | Alta | No cachear; operación sensible |
| `POST /auth/change-password` | Alto: verificar y generar hash | Baja | Alta | No cachear; credenciales sensibles |
| `POST /auth/login` | Alto: verificación bcrypt | Media | Cambia con estado/contraseña de usuario | No cachear; token y resultado son personales |
| `GET /auth/me` | Bajo: usuario y perfil por ID | Alta durante navegación autenticada | Baja | No cachear; sesión y perfil privados |
| `GET /profiles/me` | Bajo: lectura por ID | Media | Baja | No cachear; información personal |
| `PUT /profiles/me` | Bajo/medio: validación y escritura | Baja | Alta en cada edición | No cachear; perfil privado |
| `POST /suppliers` | Medio: validar y escribir | Baja | Alta al crear | No cachear; mutación |
| `GET /suppliers` | Medio: escaneo TinyDB y filtros opcionales | Media/alta al abrir el directorio | Baja salvo cambios de proveedor | No seleccionado: conjunto pequeño y privado/auth; medir antes de cachear |
| `GET /suppliers/{id}` | Bajo: búsqueda por ID | Baja | Baja | No seleccionado: coste reducido y respuesta autenticada |
| `PATCH /suppliers/{id}/rate` | Bajo/medio: lectura y escritura | Baja | Alta al cambiar tarifa | No cachear; mutación |
| `PATCH /suppliers/{id}/status` | Bajo/medio: lectura y escritura | Baja | Alta al cambiar estado | No cachear; mutación |
| `DELETE /suppliers/{id}` | Bajo/medio: lectura y borrado | Baja | Alta al borrar | No cachear; mutación |
| `POST /api/incidents/analyze` | Alto y variable: leer/validar CSV y calcular métricas | Baja | Por petición; reemplaza el último informe del proceso | No cachear; entrada y resultado dependen del archivo/usuario |
| `GET /api/incidents/results/report` | Bajo: devolver CSV ya generado | Baja | Cambia al analizar otro archivo | No cachear; informe de sesión/proceso autenticado |
| `POST /api/incidents` | Medio: validar y escribir TinyDB | Baja | Alta por cada alta | No cachear; invalida listado y resumen |
| `GET /api/incidents` | Medio/alto: escaneo y filtros TinyDB | Alta: al abrir la vista y cada cambio de filtros | Baja/media; cambia al crear o cambiar estado | **Cacheado 30 s**, por usuario y filtros; invalidación en escrituras |
| `GET /api/incidents/summary` | Alto: escanea todos los documentos y agrega cuatro dimensiones | Alta: al abrir la vista y después de cambiar estado | Baja/media respecto de las lecturas | **Cacheado 30 s**, por usuario; invalidación en escrituras |
| `GET /api/incidents/{id}` | Bajo: búsqueda por ID | Media al consultar un detalle | Baja, salvo cambio de estado | No cacheado: no es un flujo frecuente confirmado; datos autenticados |
| `PATCH /api/incidents/{id}/status` | Medio: lectura, validación de transición y escritura | Media en seguimiento | Alta en cada cambio | No cachear; invalida listado y resumen |
| `GET /inventory/products` | Alto: dos agregaciones por activo; mediana local ≈993 ms con 1.000 activos | Alta al abrir inventario | Media/alta: entradas/salidas cambian stock | **Cacheado 5 s**; invalidado al crear producto o movimiento; la lectura individual sigue fresca |
| `POST /inventory/products` | Bajo/medio: insertar activo | Baja | Alta al crear producto | No cachear; cambia catálogo y stock visible |
| `GET /inventory/products/{id}` | Medio: lectura y dos agregaciones para un activo | Media durante operaciones | Alta: el stock cambia | No cachear; se usa para comprobar disponibilidad |
| `POST /inventory/orders/inbound` | Medio: bloqueo, validar activo y escribir entrada | Media según actividad de almacén | Alta | No cachear; cambia stock y catálogo |
| `POST /inventory/orders/outbound` | Alto: calcular stock, validar cantidad y escribir salida | Media según actividad de almacén | Alta | No cachear; la disponibilidad debe ser actual |
| `GET /inventory/orders` | Alto al crecer: leer activos y movimientos, enriquecer y ordenar | Media al abrir historial | Media/alta: cada orden agrega filas | No seleccionado; coste crece, pero historial cambia con cada orden y requiere medición |

Además, FastAPI expone rutas automáticas de documentación (`/openapi.json`, `/docs`, `/redoc` y `/docs/oauth2-redirect`) y la raíz sirve el Backoffice estático; tienen coste bajo, baja frecuencia de datos cambiantes y no son candidatas a esta caché de negocio.

### Candidatos y política aplicada

El listado y el resumen de incidencias cumplen coste de escaneo/agregación, llamadas repetidas desde `/incidents` y cambios menos frecuentes que las lecturas. El cliente carga el listado al entrar y al modificar filtros; solicita el resumen al entrar y después de cambiar un estado. No hay telemetría agregada para afirmar ratios de producción, por lo que la frecuencia es una hipótesis informada por el flujo de UI. El listado de productos también presenta coste medido cercano a un segundo y se vuelve a cargar al abrir inventario; sus escrituras conocidas invalidan la caché.

En una comprobación local sintética con 1.000 incidencias en TinyDB `MemoryStorage`, `TestClient` midió listado 129.8 ms en frío y 19.1 ms de mediana en 20 hits; resumen 5.7 ms en frío y 4.1 ms de mediana en hits. En PostgreSQL local con 1.000 activos, 3.000 entradas y 2.000 salidas, el listado de productos midió 1,186.1 ms en frío y 8.5 ms de mediana en 20 hits. Son mediciones de laboratorio locales, no de producción; serialización, carga del host y memoria explican parte del coste residual.

- TTL: incidencias 30 segundos; productos 5 segundos. Cada caché está acotada y usa expulsión LRU para limitar memoria.
- Claves: listado de incidencias `user_id + status + origin + branch + category`; resumen `user_id`. Aunque esos datos son globales hoy, el usuario autenticado forma parte de cada clave para no compartir resultados privados entre sesiones. El catálogo de productos no es personalizado y usa una sola clave.
- Invalidación: `POST /api/incidents` y `PATCH /api/incidents/{id}/status` limpian listado y resumen. `POST /inventory/products`, `/inventory/orders/inbound` y `/inventory/orders/outbound` limpian el listado de productos. Una generación impide que una lectura iniciada antes de invalidar vuelva a introducir una respuesta obsoleta. Las copias profundas evitan que una respuesta mutada altere el valor guardado.
- Alcance: caché en memoria por proceso. La aplicación debe ejecutarse con un worker para que invalidación sea inmediata entre peticiones; con varios workers, cada proceso mantiene su propia caché y una mutación externa puede quedar obsoleta como máximo hasta el TTL.

No se cachean rutas de autenticación, sesión, perfil, usuarios, análisis CSV ni `GET /inventory/products/{id}`, que se usa para consultar stock actual. Las respuestas de incidencias sí están autenticadas y sus claves incluyen el ID del usuario.

## Optimizaciones frontend

El foco es `uis/backoffice`, la interfaz Next.js que consume el inventario y el directorio de proveedores. Estas decisiones se basan en inspección estática del flujo; no se ha medido todavía la diferencia de bytes del bundle ni una traza de navegador antes/después.

| Candidato | Decisión y justificación |
| --- | --- |
| `CreateSupplierDialog` en `/suppliers` | Cargado con `next/dynamic` al pulsar «Nuevo proveedor». El formulario completo, sus campos opcionales y validaciones no se necesitan para consultar el listado y solo se usan en el flujo de alta. |
| `EditRateDialog` en `/suppliers` | Cargado con `next/dynamic` al pulsar la acción de editar tarifa. Es un diálogo separado y ocasional; diferirlo evita incluirlo en la carga inicial del directorio. Ambos diálogos muestran un estado de carga accesible durante la descarga del chunk. |
| Resumen de `/inventory/products` | `totalUnits` y `lowStockCount` recorren todos los activos. Se combinaron en una sola reducción `O(n)` dentro de `useMemo` con dependencia `[assets]`; cambiar el texto de búsqueda ya no repite ese trabajo. La lista filtrada conserva su memoización existente `[assets, search]`. |

Las dos oportunidades de lazy loading son componentes de interacción bajo demanda, no páginas completas que Next ya separa automáticamente por ruta. `useMemo` se limita al agregado lineal sobre el inventario; los cálculos triviales no se memoizaron.

Beneficio frontend estimado:

- `CreateSupplierDialog` y `EditRateDialog` dejan de formar parte del código que necesita ejecutarse al abrir el directorio; sus módulos solo se solicitan al iniciar alta o edición. Se difiere la descarga, parseo y ejecución de esos formularios del camino inicial. No se midieron bytes de chunks ni LCP antes/después, así que no se atribuye una reducción numérica.
- El resumen memoizado evita recalcular `totalUnits` y `lowStockCount` en cada render por cambio de búsqueda. Antes eran dos recorridos de `n` activos por render; ahora se hace una sola reducción de `n` elementos cuando cambia la referencia de `assets`, y cero recorridos del resumen al escribir en el buscador. El filtro de resultados sigue siendo `O(n)` cuando cambia la búsqueda. No se midió tiempo de CPU; el beneficio es estructural y estimado.

## Intercambio entre frescura y rendimiento

| Lectura cacheada | TTL | Frescura aceptada y motivo |
| --- | ---: | --- |
| `GET /api/incidents` y `GET /api/incidents/summary` | 30 s | Son vistas de seguimiento, no se usan para autorizar ni validar una mutación. Las escrituras de alta y cambio de estado invalidan ambas cachés en el mismo proceso, por lo que la lectura posterior al cambio ve el dato nuevo. Se acepta que una escritura externa o atendida por otro worker pueda tardar hasta 30 s en reflejarse, a cambio de evitar escanear TinyDB en cada lectura del panel. Si se requiere visibilidad inmediata entre procesos, esta caché local debe sustituirse por invalidación compartida o un TTL menor. |
| `GET /inventory/products` | 5 s | La pantalla es un resumen visual y no es la fuente de verdad para aceptar órdenes. Las escrituras locales de producto/entrada/salida invalidan el listado; si otra instancia escribe, la UI puede mostrar stock anterior hasta 5 s. `GET /inventory/products/{id}` y la validación de stock de salida consultan la base directamente, así que una copia obsoleta no autoriza una salida inválida. El TTL corto limita la discrepancia visual y conserva la mejora en la ruta costosa. |

En todos los casos, el límite de obsolescencia aplica a expiración temporal cuando no se ejecuta una invalidación conocida; los TTL no reemplazan la invalidación. Las claves de incidencias incluyen el usuario autenticado y los filtros, evitando compartir resultados privados.

## Próximos pasos

1. Instrumentar conteos de peticiones por endpoint y usuario/estado agregado (sin datos personales) para reemplazar las frecuencias estimadas por telemetría.
2. Medir `GET /api/incidents` y `/summary` con un conjunto representativo de incidencias, antes y después de la caché, e informar hit ratio y latencias.
3. Considerar una agregación SQL por lote para `GET /inventory/products` y mantener las comprobaciones de salida sobre lecturas frescas.
