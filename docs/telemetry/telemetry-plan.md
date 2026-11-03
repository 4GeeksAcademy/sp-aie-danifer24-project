# Plan de telemetria de Nexova

## Fase 1: catalogo de oportunidades de datos

Fecha: 2026-11-03. Alcance: inventario y flujos relacionados del Backoffice, autenticacion, rendimiento, errores y navegacion. Fuente normativa: `contexts/06-telemetry/CONTEXT.md`. Este documento propone captura futura: no afirma que los eventos ya se emitan ni implementa instrumentacion, almacenamiento o seeds. La fase 2 exporta contratos JSON Schema, no codigo de captura.

Las hipotesis son preguntas de negocio que se contrastaran con datos, no resultados medidos. Los cinco eventos del contexto son obligatorios; las oportunidades adicionales son exploracion y se priorizaran por utilidad y coste, no por cantidad de eventos.

## Contrato de negocio y brechas actuales

Las entidades del plan se llaman exactamente `Product`, `InboundOrder` y `OutboundOrder`. Un `Product` representa material de formacion/certificacion o incorporacion y pertenece a un programa o area. Dimensiones de inventario en `properties`:

| Campo minimo | Dominio del contexto y tratamiento |
| --- | --- |
| `office` | `valencia` o `miami`; independiente del idioma de interfaz |
| `product_id` | Identificador del `Product`, nunca su nombre libre |
| `product_category` | `training_kit`, `certification` o `onboarding_equipment` |
| `programme_id` | Identificador estable del programa/area; por ejemplo `ventas-b2b` o `liderazgo-basico` |
| `quantity` | Unidades de la orden, del movimiento causante o del intento rechazado segun evento; no sustituir un dato desconocido por cero |
| `currency` | `EUR` en Valencia y `USD` en Miami; sin conversion ni suma entre monedas |

Estos seis campos se mantienen para los eventos de inventario con producto identificado. En navegacion sin seleccion de producto no se inventan valores: se captura un evento de navegacion, no una orden incompleta. Si un intento es malformado y no permite determinar producto/cantidad, se captura validacion generica y se mide como brecha de cobertura del evento obligatorio; la fase de contrato debe resolver esta excepcion sin contaminar dimensiones.

Brechas verificadas en `services/api/schemas.py`, `services/api/routers/inventory.py` y formularios de ordenes:

- El codigo llama a las entidades `Asset`, `AssetEntry` y `AssetExit` y usa `asset_id`. En telemetria se requiere `Product`/`InboundOrder`/`OutboundOrder` y `product_id`; la correspondencia de identificadores debe ser explicita, no un cambio silencioso del contrato API.
- Las categorias actuales son `hardware`, `peripherals`, `office_supplies`, `training_materials`. No equivalen automaticamente a las tres categorias exigidas: se necesita clasificacion de negocio por producto, validada por L&D/RRHH, no inferencia por nombre.
- La API usa `Valencia`/`Miami`; la dimension de telemetria se normalizara explicitamente a `valencia`/`miami` y la moneda se derivara de esa oficina, nunca del idioma.
- No existen en los inputs actuales programa, coste unitario, moneda, minimo configurable ni identificador estructurado del proveedor de entrada. `supplier` es texto libre y `assigned_to` puede contener nombres: ninguno se copia a telemetria.
- Stock se calcula como entradas menos salidas; las salidas comprueban stock fresco bajo bloqueo. El listado puede usar cache de 5 s: umbrales y coste deben calcularse en backend sobre datos confirmados, no sobre el listado cacheado.
- No hay ruta de edicion directa de stock. Los esquemas rechazan campos extra y una ruta inexistente puede responder 405, pero no todo 422/405 es intento de saltarse el control. Se requiere detectar explicitamente el campo/accion de stock, conservar el rechazo y no habilitar una escritura directa para instrumentarla.
- El indicador visual de stock bajo no es un minimo configurado por producto. Se necesita definir el umbral para el evento obligatorio y el historico producto/proveedor/moneda para variacion de coste.
- El contexto no define el envelope estandar. Version, identificador de evento, fecha UTC, correlacion, entorno y actor se concretaran en fase de contrato; no se presenta un esquema inventado como requisito del contexto.

## Mapa del flujo de inventario

Referencias verificadas: `uis/backoffice/app/session-guard.tsx`, `app/navigation.tsx`, `hooks/useInventoryAssets.ts`, `app/inventory/orders/inbound/page.tsx`, `app/inventory/orders/outbound/page.tsx`, `lib/inventory.ts`, `services/api/routers/inventory.py` y `services/api/schemas.py`.

| Paso | Comportamiento actual y punto de instrumentacion propuesto |
| --- | --- |
| 1. Acceso | `SessionGuard` valida sesion al entrar, recuperar foco, recibir storage y cada 60 s; registrar acceso concedido o fallo, sin token. Las pantallas publicas quedan fuera del guard. |
| 2. Consulta de productos | Navegacion a `/inventory/products`, carga en `useInventoryAssets`, busqueda y reintento; medir carga y estados vacio/error. Los GET de productos actuales son publicos aunque la UI exige sesion: no atribuirles un actor autenticado sin evidencia. |
| 3. Apertura de orden | Rutas `/inventory/orders/inbound` y `/inventory/orders/outbound`; comenzar una instancia de flujo al iniciar interaccion con el formulario. |
| 4. Seleccion y disponibilidad | Entrada selecciona producto del catalogo; salida llama a `getAsset` para stock fresco. Registrar consulta resuelta/fallida y duracion, no nombres ni destinatario. |
| 5. Validacion local | Entero positivo, producto seleccionado, proveedor en entrada y destinatario requerido para allocation; distinguir error local y validacion del navegador de un rechazo backend. |
| 6. Envio | Cliente envia `POST /inventory/orders/inbound` o `/outbound` con bearer. Registrar intento con correlacion de flujo; no contar el intento como orden creada. |
| 7. Autorizacion y validacion servidor | `CurrentUser`, esquemas, existencia de producto y cantidad disponible; registrar rechazo de acceso/validacion o stock insuficiente sin copiar mensajes que incluyan nombres. |
| 8. Intento de stock directo | Deteccion futura de intento explicito sobre stock fuera de orden en frontera API; emitir `direct_stock_edit_rejected` solo si el sistema lo rechaza y se reconoce esa intencion. No usar cualquier error de campo o metodo como sustituto. |
| 9. Confirmacion de escritura | `create_entry`/`create_exit` hacen commit, invalidan cache y retornan 201. La fuente autoritativa de `inbound_order_created`/`outbound_order_created` sera backend tras commit; rollback no genera creacion. |
| 10. Reglas de negocio | Sobre stock confirmado detectar cruce por debajo del minimo; sobre entrada confirmada comparar coste con historico. Umbral e historico son capacidades pendientes. |
| 11. Cierre o abandono | UI muestra exito y limpia campos; registrar confirmacion visible o abandono con el ultimo paso conocido. Un timeout cliente no prueba rollback: correlacionar con orden confirmada en backend antes de clasificar. |

## Catalogo obligatorio

Clasificacion de todas las filas: **obligatorio (viene del contexto)**. No renombrar estos `event_type` ni reemplazarlos por oportunidades similares.

| `event_type` | Disparo y evidencia requerida | Justificacion completa |
| --- | --- | --- |
| `inbound_order_created` | Backend despues del commit de `InboundOrder`; cantidades y coste por programa/oficina. Punto actual: `create_entry`; faltan programa, categoria contractual y coste. | Capturamos `inbound_order_created` porque necesitamos saber cuanto material se produce o compra, para que programa y con que costo, lo que nos permite tomar la decision de planificar la produccion de material segun demanda esperada de matriculas (Elena). |
| `outbound_order_created` | Backend despues del commit de `OutboundOrder`; una entrega confirmada, sin nombre de receptor. Punto actual: `create_exit`. | Capturamos `outbound_order_created` porque necesitamos saber que programas consumen mas material y a que ritmo, lo que nos permite tomar la decision de anticipar necesidades de reposicion antes de una ola grande de matriculas (Elena). |
| `stock_threshold_triggered` | Cruce confirmado `stock_before >= minimum` a `stock_after < minimum` por producto/oficina; igualdad no dispara. Cantidad del movimiento causante; registrar minimo y stock anterior/posterior. Rearmar al recuperar el minimo; lecturas repetidas bajo minimo no son nuevos cruces. | Capturamos `stock_threshold_triggered` porque necesitamos saber con que frecuencia un programa se queda sin material disponible, lo que nos permite tomar la decision de ajustar el umbral minimo o acelerar la reimpresion o reproduccion de ese material. |
| `direct_stock_edit_rejected` | Backend rechaza un intento explicitamente reconocido de cambiar stock fuera de orden; incluir codigo de motivo permitido y producto resoluble, nunca payload completo. Deteccion especifica pendiente. | Capturamos `direct_stock_edit_rejected` porque necesitamos saber si el personal intenta saltarse el control de trazabilidad del material, lo que nos permite tomar la decision de reforzar capacitacion o permisos en la oficina donde esto ocurre con mas frecuencia (Patricia). |
| `kit_cost_variance_detected` | Entrada confirmada cuyo coste unitario difiere mas del umbral respecto al historico del mismo material/proveedor y moneda. Propuesta a validar: media ponderada por cantidad de entradas anteriores en 90 dias, excluir la actual; `abs(actual-base)/base > 0.10`. Sin base positiva no emitir ni convertir monedas. | Capturamos `kit_cost_variance_detected` porque necesitamos saber cuando un proveedor de material sube precios de forma anomala, lo que nos permite tomar la decision de alertar a Elena y Laura para renegociar o buscar proveedor alterno. |

El 10% es un ejemplo del contexto, no un limite definitivo aprobado. Media, ventana y alerta son propuestas; se confirmaran con L&D. Guardar direction de variacion permite separar subida de bajada sin alterar el evento. Montos por moneda, sin datos personales ni nombre del proveedor; identificador estructurado necesario para el historico.

## Catalogo de oportunidades identificadas

Clasificacion de **cada fila siguiente: oportunidad identificada (propuesta en esta fase)**. No son obligaciones del contexto. Punto de captura identifica codigo existente o una capacidad futura; no supone que ya exista un emisor.

### Inventario: conversion, trazabilidad y reposicion

| `event_type` | Punto de captura / dimensiones utiles | Justificacion completa |
| --- | --- | --- |
| `inventory_order_started` | Primer cambio de campo en inbound/outbound; tipo de flujo, paso; usar evento de flujo sin producto hasta seleccion. | Capturamos `inventory_order_started` porque necesitamos saber cuantas tareas de recepcion o entrega se inician realmente, lo que nos permite tomar la decision de priorizar el flujo con mayor volumen de trabajo. |
| `inventory_product_selected` | Seleccion en ambos formularios; producto/programa tras resolver datos fiables, sin etiqueta visible. | Capturamos `inventory_product_selected` porque necesitamos saber en que programas se concentran las intenciones de recepcion o entrega, lo que nos permite tomar la decision de preparar material para la demanda prevista y distinguirla de entregas reales. |
| `inventory_stock_lookup_completed` | `selectAsset`/`getAsset` en salida; resultado y duracion, no respuesta completa. | Capturamos `inventory_stock_lookup_completed` porque necesitamos saber si consultar disponibilidad retrasa o bloquea entregas, lo que nos permite tomar la decision de optimizar la consulta de stock o mejorar su reintento. |
| `inventory_order_validation_failed` | `submit`, invalid del navegador o esquemas API; capa, tipo orden, campo permitido, reason_code, no valor introducido. | Capturamos `inventory_order_validation_failed` porque necesitamos saber que reglas generan mas intentos fallidos, lo que nos permite tomar la decision de mejorar mensajes, defaults o capacitacion sin relajar restricciones. |
| `inventory_order_submitted` | Cliente inmediatamente antes de POST; correlacion de flujo y tipo, sin body completo. | Capturamos `inventory_order_submitted` porque necesitamos saber cuantos intentos llegan al envio, lo que nos permite tomar la decision de localizar la caida entre validacion y confirmacion. |
| `outbound_order_insufficient_stock_rejected` | `create_exit`, antes de commit al superar disponible; quantity solicitada y stock observado fiable. | Capturamos `outbound_order_insufficient_stock_rejected` porque necesitamos saber que programas no pueden completar entregas por falta de material, lo que nos permite tomar la decision de adelantar reposicion o redistribuir existencias entre oficinas. |
| `inventory_order_persistence_failed` | Frontera de transaccion si rollback; clase normalizada del error, no SQL ni parametros. | Capturamos `inventory_order_persistence_failed` porque necesitamos saber si fallos de base de datos interrumpen recepciones o entregas, lo que nos permite tomar la decision de corregir la infraestructura o introducir recuperacion segura. |
| `inventory_order_confirmation_displayed` | UI al mostrar exito tras POST; correlacion con orden confirmada. | Capturamos `inventory_order_confirmation_displayed` porque necesitamos saber si las ordenes guardadas llegan a confirmarse visualmente, lo que nos permite tomar la decision de corregir timeouts y evitar reenvios por incertidumbre. |
| `inventory_order_abandoned` | Clasificacion futura del flujo sin confirmacion; salida de ruta o inactividad, ultimo paso y causa observable. | Capturamos `inventory_order_abandoned` porque necesitamos saber en que paso se interrumpen recepciones o entregas, lo que nos permite tomar la decision de simplificar el formulario o resolver el bloqueo mas frecuente. |
| `inventory_stock_recovered` | Futuro cruce confirmado de bajo minimo a `stock_after >= minimum`; complementa evento obligatorio. | Capturamos `inventory_stock_recovered` porque necesitamos saber cuanto tarda un programa en recuperar material tras una alerta, lo que nos permite tomar la decision de ajustar acuerdos de reposicion y stock de seguridad. |
| `inventory_history_viewed` | `/inventory/orders`, tras acceso autorizado; navegacion, sin copiar historial. | Capturamos `inventory_history_viewed` porque necesitamos saber cuanto se utiliza la trazabilidad de movimientos, lo que nos permite tomar la decision de mejorar consulta y filtros del historial para auditoria operativa. |
| `inventory_search_completed` | Busqueda de productos estabilizada, longitud por rango y numero de resultados; no texto buscado. | Capturamos `inventory_search_completed` porque necesitamos saber si los operadores encuentran el material necesario, lo que nos permite tomar la decision de mejorar la clasificacion y los filtros cuando abundan busquedas sin resultados. |

### Autenticacion y continuidad de sesion

| `event_type` | Punto de captura / dimensiones utiles | Justificacion completa |
| --- | --- | --- |
| `login_attempted` | Envio en `/login`/POST auth; correlacion anonima, sin email ni password. | Capturamos `login_attempted` porque necesitamos saber cuantos accesos se intentan frente a los completados, lo que nos permite tomar la decision de priorizar mejoras del acceso a operaciones. |
| `login_succeeded` | `/auth/login` tras verificar credenciales; no JWT ni perfil. | Capturamos `login_succeeded` porque necesitamos saber cuando el personal logra entrar al sistema, lo que nos permite tomar la decision de planificar soporte en las franjas de mayor actividad. |
| `login_failed` | Rechazo de login o fallo de transporte; motivo publico normalizado, no existencia de cuenta. | Capturamos `login_failed` porque necesitamos saber si los accesos fallan por credenciales o indisponibilidad, lo que nos permite tomar la decision de reforzar ayuda de acceso o reparar el servicio segun la causa. |
| `session_access_granted` | Guard tras `validateSession`, origen entry/focus/interval/retry. | Capturamos `session_access_granted` porque necesitamos saber cuanto tarda la comprobacion que habilita cada flujo, lo que nos permite tomar la decision de reducir comprobaciones redundantes manteniendo autorizacion. |
| `session_expired` | Backend solo si valida que JWT ha expirado; nunca inferir expiracion de cualquier 401. Capacidad de clasificacion pendiente. | Capturamos `session_expired` porque necesitamos saber cuantas tareas se interrumpen por vencimiento real de sesion, lo que nos permite tomar la decision de ajustar la politica de duracion o avisar antes de perder continuidad. |
| `session_validation_failed` | Guard y seguridad API; distinguir invalid/missing/inactive/network/unknown de expired cuando se sepa. | Capturamos `session_validation_failed` porque necesitamos saber si las comprobaciones bloquean a operadores por errores tecnicos o credenciales invalidas, lo que nos permite tomar la decision de separar reintento de reautenticacion. |
| `authorization_denied` | 403 en frontera API con ruta plantilla; no recursos privados completos. | Capturamos `authorization_denied` porque necesitamos saber donde los permisos impiden tareas legitimas, lo que nos permite tomar la decision de revisar roles y formacion sin ampliar acceso indiscriminadamente. |
| `logout_completed` | Boton del guard tras limpiar sesion; solo accion explicita. | Capturamos `logout_completed` porque necesitamos saber que sesiones se cierran deliberadamente y cuales se interrumpen, lo que nos permite tomar la decision de distinguir fin de jornada de problemas de acceso. |
| `password_recovery_requested` | `/auth/forgot-password`, respuesta generica; no comprobar ni registrar existencia de email. | Capturamos `password_recovery_requested` porque necesitamos saber cuanto depende el acceso del proceso de recuperacion, lo que nos permite tomar la decision de mejorar ayuda de autenticacion. |
| `password_reset_completed` | `/auth/reset-password` tras cambio confirmado; sin token/hash. | Capturamos `password_reset_completed` porque necesitamos saber si las solicitudes de recuperacion consiguen restablecer acceso, lo que nos permite tomar la decision de mejorar entrega y usabilidad del enlace sin revelar cuentas. |

### Rendimiento y fiabilidad

| `event_type` | Punto de captura / dimensiones utiles | Justificacion completa |
| --- | --- | --- |
| `api_request_completed` | Middleware timing de `main.py`, despues de respuesta; duracion, metodo, status, ruta plantilla, entorno. | Capturamos `api_request_completed` porque necesitamos saber que endpoints concentran volumen y latencia, lo que nos permite tomar la decision de priorizar optimizaciones con evidencia en lugar de intuicion. |
| `api_request_failed` | Handler de excepciones/no respuesta en main; fallo tecnico, no 400 esperado de negocio, sin stack/payload crudo. | Capturamos `api_request_failed` porque necesitamos saber que fallos inesperados impiden operaciones, lo que nos permite tomar la decision de asignar prioridad a incidentes de infraestructura o codigo. |
| `frontend_data_load_completed` | Hooks de inventario y cargas de proveedores/incidencias/perfil; duracion, seccion, ready/empty/error, no filas. | Capturamos `frontend_data_load_completed` porque necesitamos saber cuanto espera el operador hasta ver datos utilizables, lo que nos permite tomar la decision de optimizar proxy, API o render segun la seccion. |
| `frontend_retry_completed` | Reintentar catalogo, resumen, perfil o sesion; resultado y motivo normalizado. | Capturamos `frontend_retry_completed` porque necesitamos saber si los reintentos recuperan tareas bloqueadas, lo que nos permite tomar la decision de conservarlos, mejorarlos o dejar de ocultar errores persistentes. |
| `frontend_response_invalid` | Validadores de `lib/inventory`, proveedores e incidencias; version/endpoint, no objeto rechazado. | Capturamos `frontend_response_invalid` porque necesitamos saber si contratos incompatibles rompen vistas aun con HTTP 200, lo que nos permite tomar la decision de coordinar despliegues y endurecer validacion de contratos. |
| `frontend_unhandled_error` | Futuro boundary Next y listeners error/unhandledrejection; fingerprint sanitizado y version, no mensaje/stack sin filtrar. | Capturamos `frontend_unhandled_error` porque necesitamos saber que excepciones escaparon a los catch y dejaron pantallas inutilizables, lo que nos permite tomar la decision de reparar el componente de mayor impacto. |
| `frontend_route_load_completed` | Navegacion Next hasta contenido utilizable; ruta plantilla, duracion y cold/warm si observable. | Capturamos `frontend_route_load_completed` porque necesitamos saber que secciones tardan en abrir aun con API rapida, lo que nos permite tomar la decision de ajustar bundles, lazy loading y estados de carga. |
| `frontend_web_vital_observed` | Captura futura LCP/INP/CLS, nombre y valor, ruta/version; muestras de laboratorio separadas de usuarios reales. | Capturamos `frontend_web_vital_observed` porque necesitamos saber si carga, interaccion o desplazamientos visuales dificultan trabajar, lo que nos permite tomar la decision de priorizar el cuello de botella real de experiencia. |
| `api_cache_lookup_completed` | TTLCache en productos/incidencias; hit/miss/expired por familia, nunca clave ni user_id crudo. | Capturamos `api_cache_lookup_completed` porque necesitamos saber si las caches reducen trabajo o acumulan misses, lo que nos permite tomar la decision de ajustar TTL, invalidacion y capacidad con evidencia. |

### Navegacion y otras operaciones de Backoffice

| `event_type` | Punto de captura / dimensiones utiles | Justificacion completa |
| --- | --- | --- |
| `backoffice_section_viewed` | `usePathname` tras acceso del guard; seccion permitida, no URL/query completos. | Capturamos `backoffice_section_viewed` porque necesitamos saber que secciones visitan mas los operadores, lo que nos permite tomar la decision de priorizar navegacion y mejoras de las tareas recurrentes. |
| `backoffice_navigation_selected` | Links del menu; origen y destino canonicos. | Capturamos `backoffice_navigation_selected` porque necesitamos saber que recorridos requieren mas cambios de pantalla, lo que nos permite tomar la decision de acercar acciones relacionadas en la navegacion. |
| `supplier_operation_completed` | Alta/edicion tarifa/cambio estado, backend tras escritura; tipo y resultado, sin contacto/notas. | Capturamos `supplier_operation_completed` porque necesitamos saber que mantenimiento del directorio consume mas trabajo o falla, lo que nos permite tomar la decision de mejorar los formularios y permisos de proveedores. |
| `supplier_filter_completed` | Filtros del directorio; dimensiones permitidas y resultado, no busqueda libre. | Capturamos `supplier_filter_completed` porque necesitamos saber si las categorias permiten localizar proveedores, lo que nos permite tomar la decision de revisar la taxonomia y reducir busquedas fallidas. |
| `incident_created` | POST incidencias tras commit; categoria/origen normalizados, sin titulo ni descripcion. | Capturamos `incident_created` porque necesitamos saber que problemas operativos se reportan mas, lo que nos permite tomar la decision de asignar esfuerzo preventivo a la categoria dominante. |
| `incident_status_transition_completed` | PATCH status, confirmacion o rechazo; anterior/nuevo y reason_code, no contenido. | Capturamos `incident_status_transition_completed` porque necesitamos saber donde se estanca el seguimiento o se intentan transiciones invalidas, lo que nos permite tomar la decision de revisar procedimientos y capacitacion. |
| `incident_summary_viewed` | Resumen del panel cargado o fallo; duracion y filtros de contexto, no incidencias individuales. | Capturamos `incident_summary_viewed` porque necesitamos saber si el resumen operativo se consulta y esta disponible, lo que nos permite tomar la decision de mejorar la vista usada para priorizar incidencias. |
| `profile_update_completed` | PUT perfil, resultado; no campos/valores personales. | Capturamos `profile_update_completed` porque necesitamos saber si la autogestion de cuenta falla y genera soporte, lo que nos permite tomar la decision de corregir validaciones o mensajes del formulario. |
| `backoffice_form_abandoned` | Dialogos de proveedores, perfil y nueva incidencia; tipo/ultimo paso, excluye ordenes ya cubiertas por evento de inventario. | Capturamos `backoffice_form_abandoned` porque necesitamos saber que formularios generan mas trabajo iniciado sin completar, lo que nos permite tomar la decision de simplificar el flujo con mayor abandono verificable. |

## Interpretacion, privacidad y cobertura

- Oficina del evento se obtiene de la orden/producto resuelto por servidor. Sin autenticar o sin conocer oficina, no inferirla por IP, idioma o ubicacion del navegador; segmentar el evento de acceso como no atribuible a oficina, sin inventar programa.
- Solo propiedades en allowlist. Prohibidos nombres, email, telefonos, destinatarios, credenciales, JWT, tokens de recuperacion, cuerpos, notas, textos de busqueda, CSV y URLs completas. El contexto excluye datos personales; no capturar actor crudo en properties. Un identificador pseudonimo en envelope requeriria validacion de privacidad y acceso restringido en fase posterior.
- No contar lecturas/prefetch/StrictMode como tareas nuevas. Navegacion tras ruta efectiva y acceso concedido; deduplicar montajes. Eventos de creacion tienen fuente backend unica y clave de deduplicacion basada en orden confirmada y event_type; un reintento de entrega del evento no es nueva orden.
- Intento de envio, creacion confirmada y confirmacion visible son hitos distintos del mismo flujo, no tres entregas. Diferenciar validacion local/backend y fallo de transporte; timeout no equivale a rechazo de la orden.
- Abandono es una clasificacion provisional: propuesta de 30 minutos sin actividad o navegacion fuera con formulario iniciado, excluir flujos confirmados, reanudados o afectados por caida de sesion/red. `pagehide` no garantiza entrega ni intencion; reconciliar posteriormente. Duraciones y regla final se acuerdan en fase de contrato.
- Frecuencias y tasas con denominador explicito: conversion ordenes confirmadas/flujos iniciados reconciliados; fallos credenciales/intentos login; rechazos stock/envios outbound; activaciones minimo/cruces reales; latencia por ruta y status. No sumar cantidades de intentos a cantidades entregadas ni costos EUR con USD.
- Las entregas de kits son una aproximacion al consumo de material, no matriculas ni finalizaciones de formacion. Esas metricas futuras requieren integrar la fuente educativa; no inferirlas de `outbound_order_created`.
- Prioridad inicial: cinco obligatorios y sus brechas, continuidad de autenticacion, validacion/stock y confirmacion de ordenes. Despues fiabilidad, rendimiento y navegacion; posteriormente mantenimiento de proveedores/cuenta e incidencias. Muestreo de alto volumen, retencion y responsables por evento se decidiran sin eliminar cobertura obligatoria.

## Criterios de cierre de esta fase y siguientes pasos

Fase 1 documentada: cinco eventos obligatorios exactos, once puntos del flujo y catalogo amplio justificado en inventario, autenticacion, rendimiento, errores, navegacion y operaciones adyacentes. Se descartan capturas sin decision: cada tecla de formulario, body completo de error, texto de busqueda y datos personales no aportan una decision proporcional a su riesgo/coste.

La fase 2 siguiente define envelope y contratos versionados. La instrumentacion futura resolvera con L&D/RRHH programa, clasificacion de productos, minimo y coste historico. El dataset sugerido sigue pendiente: 6-8 Product en tres categorias, tres programas, 12-15 InboundOrder y 12-15 OutboundOrder entre oficinas, dos cruces de minimo y una variacion de coste. No ejecutado ni generado en esta fase.

## Fase 2: event envelope y esquemas

Contrato exportado: `docs/telemetry/event-schemas.json`, JSON Schema draft-07, version `1.0.0`. Este es el archivo canonico tras renombrar `event_schemas.json`; no hay dos contratos distintos. `oneOf` contiene los cinco obligatorios y nueve oportunidades de la fase 1 en cinco categorias: negocio/inventario, autenticacion, rendimiento, errores y navegacion. Los otros 31 eventos del catalogo quedan pendientes de contrato, no eliminados.

Se preservan los nombres exactos del contexto y del catalogo: entidades en snake_case seguidas de accion/resultado consistente (`created`, `triggered`, `rejected`, `detected`, `attempted`, `succeeded`, `failed`, `expired`, `completed`, `viewed`). No renombrar `api_request_completed` a un ejemplo nuevo como `api_latency_recorded`; un evento y su version deben tener significado estable.

### Envelope obligatorio

| Campo | Tipo | Obligatoriedad y significado |
| --- | --- | --- |
| `eventId` | string UUID v4 | Obligatorio; identifica el evento y se conserva en reintentos de entrega. No generar otro UUID en cada reenvio. |
| `timestamp` | string ISO 8601 UTC | Obligatorio; ocurrencia, por ejemplo `2026-11-03T12:00:00.123Z`, no recepcion. Fecha real validada con FormatChecker; suffix Z obligatorio. |
| `sessionId` | string UUID v4 o null | Campo obligatorio; UUID aleatorio de sesion de telemetria, no cookie de autenticacion/JWT. Null para procesos sin sesion fiable. |
| `userId` | string `u1_` + 64 hex o null | Campo obligatorio; HMAC-SHA256 del ID interno autenticado con namespace de entorno y clave secreta dedicada. Null sin identidad validada, en intentos/fallos login y sesion expirada. No usar email ni ID crudo. |
| `event_type` | string | Obligatorio; debe coincidir exactamente con una rama del contrato, no basta cumplir la regex. |
| `schemaVersion` | string constante `1.0.0` | Obligatorio; cualquier otra version se rechaza con este contrato. Publicar un contrato nuevo para cambios, sin reinterpretar historico. |
| `requestId` | string UUID v4 | Obligatorio; correlacion de peticion HTTP o de operacion local que no genera HTTP, no ID de usuario. |
| `properties` | object | Obligatorio; solo claves declaradas para ese evento. No se permite ninguna clave adicional en el envelope ni en properties. |

UUIDs canonicos en minusculas. `sessionId` se mantiene durante la sesion de telemetria y se rota al iniciar/cerrar identidad o tras la ventana de inactividad de 30 minutos propuesta; no persiste como fingerprint de dispositivo. El backend comprueba los IDs de correlacion externos y su longitud/formato, sustituye los invalidos y devuelve el requestId efectivo al cliente. No obtiene el usuario de headers arbitrarios: lo deriva de autenticacion verificada. Los eventos locales crean requestId de operacion; no se fabrica una peticion HTTP ni se confunde este ID con sessionId.

`requestId` se conserva al atravesar frontend/proxy/FastAPI y vincula, por ejemplo, creacion de orden y umbral causado por ella; cada evento tiene distinto eventId. Un nuevo intento HTTP puede tener otro requestId. La deduplicacion de negocio usa entidad de orden + ID + event_type, ademas de eventId para reenvios; no deduplicar por usuario/timestamp. Estos mecanismos son contrato de diseno, todavia no implementados.

### Propiedades comunes de inventario (I)

I significa exactamente estas seis claves, no una bolsa abierta de atributos. Sus tipos y descripciones reutilizables estan en `definitions` del JSON; sus claves se declaran explicitamente en cada evento:

| Propiedad | Tipo | Obligatorio/opcional | Descripcion |
| --- | --- | --- | --- |
| `office` | enum string valencia/miami | Obligatoria en cinco eventos del contexto | Oficina operativa resuelta, sin relacion con idioma. |
| `product_id` | integer >= 1 | Obligatoria | ID de Product; correspondencia explicita con Asset.id, sin inventar otra identidad. |
| `product_category` | enum string | Obligatoria | training_kit/certification/onboarding_equipment aprobada por negocio, no categoria tecnica inferida. |
| `programme_id` | string slug, 1-64 caracteres | Obligatoria | ID de catalogo de programa/area verificado, no texto libre ni nombre de persona. |
| `quantity` | integer | Obligatoria | >=1 para ordenes y movimiento causante; >=0 como stock absoluto intentado en direct_stock_edit_rejected. |
| `currency` | enum string EUR/USD | Obligatoria | Valencia EUR, Miami USD. El JSON rechaza correspondencias incorrectas. |

`inventory_order_validation_failed` admite I como bloque opcional: o se conocen los seis campos o no se envia ninguno. quantity puede ser negativa si eso causa la validacion; si no es entero o no hay metadata fiable, omitir el bloque entero. Los obligatorios del contexto no aceptan null/sentinelas para completar I: un rechazo malformado no clasificable se registra como validacion generica y como limitacion de cobertura, no se inventan valores ni se declara instrumentacion obligatoria completa.

### Allowlist explicita de cada evento

En esta tabla todas las propiedades no marcadas opcionales son obligatorias. Los nombres, tipos, required, limites, enums y descripcion individual completos estan en `oneOf[*].properties.properties` del JSON; `$ref` reutiliza solo definiciones declaradas en ese mismo archivo. `x-classification`, `x-category` y `x-privacy` son anotaciones de diseno, no claves permitidas en eventos emitidos.

| event_type | Grupo / categoria | Allowlist de properties y descripcion |
| --- | --- | --- |
| `inbound_order_created` | Obligatorio / inventario | I; `order_id` integer positivo (InboundOrder), `supplier_id` integer positivo estructurado, `unit_cost` number >=0 en moneda de oficina. Despues del commit. |
| `outbound_order_created` | Obligatorio / inventario | I; `order_id` integer positivo (OutboundOrder). Despues del commit; no assigned_to ni receptor. |
| `stock_threshold_triggered` | Obligatorio / inventario | I; `order_id` integer positivo del movimiento causante; `stock_before`, `stock_after` integer >=0; `minimum_stock` integer >=1 configurado. |
| `direct_stock_edit_rejected` | Obligatorio / inventario | I; `reason_code` constante direct_stock_write_forbidden. quantity describe stock absoluto intentado, no una salida. No confundir cualquier 405/422 con este evento. |
| `kit_cost_variance_detected` | Obligatorio / inventario | I; `order_id`, `supplier_id` integer positivos; `unit_cost` number >=0; `baseline_unit_cost` number >0; `variance_ratio`, `threshold_ratio` number >0; `direction` enum increase/decrease; `baseline_window_days` constante 90; `baseline_order_count` integer >=1. |
| `inventory_order_validation_failed` | Oportunidad / inventario | `order_type` enum inbound/outbound; `layer` enum browser/frontend/backend; `field` enum product_id/quantity/supplier_id/assigned_to/stock/other; `reason_code` enum required/invalid_type/out_of_range/unknown_product/direct_stock_write_forbidden/other; I opcional como bloque. No valores introducidos. |
| `login_attempted` | Oportunidad / autenticacion | `source` constante backoffice. userId null; envio del formulario, sin datos de credenciales. |
| `login_succeeded` | Oportunidad / autenticacion | `source` constante backoffice; `duration_ms` number entre 0 y 86400000. userId pseudonimizado obligatorio. |
| `login_failed` | Oportunidad / autenticacion | `reason_code` enum invalid_credentials/network_error/service_unavailable/invalid_response/unknown; `layer` enum frontend/backend; `duration_ms` number acotado. userId null, no distinguir cuenta inexistente/inactiva de password incorrecta. |
| `session_expired` | Oportunidad / autenticacion | `reason_code` constante token_expired; `source` constante backend. userId null. Solo firma y expiracion comprobadas, no inferencia a partir de 401. |
| `api_request_completed` | Oportunidad / rendimiento | `route_template` enum de plantillas API/unmatched/auxiliary; `method` enum GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS; `status_code` integer 100-599; `duration_ms` number acotado. Incluye exitos y rechazos HTTP, no payload. |
| `frontend_data_load_completed` | Oportunidad / rendimiento | `section` enum de secciones canonicas; `outcome` enum ready/empty/error; `duration_ms` number acotado; `reason_code` opcional enum network_error/invalid_response/unauthorized/service_unavailable/unknown, permitido solo cuando outcome=error. |
| `frontend_unhandled_error` | Oportunidad / errores | `section` enum; `source` enum error_boundary/window_error/unhandled_rejection; `error_code` enum render_error/chunk_load_error/unhandled_rejection/unknown; `fingerprint` string SHA-256 (64 hex); `app_version` string revision de build (7-40 hex). Sin mensaje/stack crudo. |
| `backoffice_section_viewed` | Oportunidad / navegacion | `section` enum; `entry_type` enum direct/menu/internal_link/history/unknown. Vista real tras acceso autorizado, no prefetch o cada render; userId pseudonimizado obligatorio. |

En esta version duraciones son milisegundos medidos con reloj monotono, no diferencias de timestamps entre hosts; ratios son fracciones (0.10 = 10%). Los importes preservan moneda y precision definida por negocio; JSON Schema comprueba tipos, pero no debe convertir cantidades monetarias con floats durante el calculo contable.

### PII, sanitizacion y seguridad por evento

Todos los contratos permiten sessionId aleatorio y, salvo los casos anonimos indicados, userId pseudonimizado: **pseudonimizacion no es anonimato**. El envelope puede seguir siendo dato personal vinculable y exige acceso restringido, finalidad definida, retencion aprobada y agregacion en reportes. HMAC se genera solo en backend con clave dedicada, distinta de JWT, nunca publicada al navegador. El prefijo u1 identifica politica de pseudonimo; su rotacion exige actualizar contrato y politica de enlaces historicos.

- Los cinco eventos de inventario contienen metadata comercial; coste/proveedor son sensibles para negocio y direct_stock_edit_rejected puede revelar conducta laboral. Solo IDs de catalogo validos, sin nombre de proveedor, kit, candidato, cliente, consultor o notas. El schema restringe forma, pero la capa de emision debe verificar que programme_id procede del catalogo y no de un nombre escrito como slug.
- `inventory_order_validation_failed` enumera campo y motivo, no valor. Si la entrada no permite completar I de forma segura, enviar solo la parte generica. No copiar error.detail de salida porque puede contener el nombre del activo.
- `login_attempted`, `login_failed` y `session_expired` exigen userId null. Ninguno permite email/password/claims, IP o JWT. Login succeeded solo expone HMAC del actor verificado, nunca token emitido. La validacion de firma/expiracion es responsabilidad del backend; no confiar en claims de token invalido.
- `api_request_completed` sustituye ruta real por plantilla declarada; desconocida pasa a unmatched y docs/estaticos a auxiliary. No query, headers, authorization, cuerpos o SQL. `frontend_data_load_completed` enumera resultado y no envia datos cargados ni mensaje libre.
- `frontend_unhandled_error` sanitiza antes de hash: clase y ubicaciones de codigo del build, sin texto de excepcion, query, rutas locales personales ni contenido del usuario. No basta hashear una cadena con PII. Si no se puede sanear, usar codigo unknown y ubicacion generica del build. Deduplicar boundary/listeners del mismo fallo.
- `backoffice_section_viewed` admite solo secciones conocidas; la revision de build y section se obtienen de fuentes internas, no de entradas libres. Actividad laboral se usa agregada, no para clasificar rendimiento individual.

Regla comun: construir un objeto nuevo seleccionando allowlist, validar antes de emitir y **rechazar** lo inesperado; no capturar todo y limpiarlo posteriormente. Schema no demuestra ausencia de PII por si solo: UUID/HMAC/slug deben provenir de fuentes fiables. Tamano, frecuencia, retencion, consentimiento/base legal y autorizacion del canal se concretaran antes de captura productiva. No incluir stack/messages/rawPayload ni siquiera como extensiones.

### Validaciones semanticas fuera de draft-07

El schema valida presencia, tipos, enums, versiones, formatos y allowlists. Estas reglas adicionales son obligatorias en el emisor/ingesta de la fase de captura, porque draft-07 no compara valores numericos entre campos ni consulta bases:

- Ordenes creadas solo despues de commit y con actor verificado. No confiar en un evento de exito frontend para inventario contable.
- Umbral: comprobar `stock_before >= minimum_stock`, `stock_after < minimum_stock` y coherencia de quantity con el movimiento confirmado. No duplicar por leer stock bajo; rearmar al recuperarse el minimo.
- Variacion: ventana 90 dias propuesta, base ponderada por quantity con entradas anteriores del mismo Product/proveedor/moneda, excluir la actual. Comprobar ratio, direction y `variance_ratio > threshold_ratio`; igualdad no dispara, sin base positiva no hay evento. Umbral de ejemplo 0.10 requiere aprobacion L&D; no imponerlo por defecto ni convertir monedas.
- La existencia de Product, proveedor y programa y su relacion/oficina se comprueba con catalogos. No inferir programa de nombre ni mapear hardware automaticamente a una categoria formativa.
- Si se desconoce usuario o sesion fiable, enviar null donde se permite; los contratos que exigen userId se posponen/rechazan, no se rellena pseudonimo inventado. Evento de expiracion exige causa confirmada, no cualquier rechazo de acceso.
- UUID externo valido no prueba autorizacion ni identidad. Correlacion y deduplicacion se verifican en el canal de ingesta, separado de autenticacion y del stock.

### Validacion realizada y uso del archivo

Se valido el metaschema draft-07, un ejemplo aceptado por cada uno de los 14 eventos y 80 casos rechazados de allowlists, email/ID crudo, version, fecha imposible, categoria tecnica indebida y oficina/moneda. Usar `jsonschema[format]` y `FormatChecker` para comprobar semanticamente date-time; sin dependencias de formatos la validacion de calendario puede omitirse.

Ejemplo de validacion de un archivo de evento, sin emitirlo:

```bash
uv run --with 'jsonschema[format]' python - evento.json <<'PY'
import json
import sys
from pathlib import Path
from jsonschema import Draft7Validator, FormatChecker

schema = json.loads(Path('docs/telemetry/event-schemas.json').read_text())
Draft7Validator.check_schema(schema)
event = json.loads(Path(sys.argv[1]).read_text())
Draft7Validator(schema, format_checker=FormatChecker()).validate(event)
print('Evento valido segun contrato estructural; verificar tambien reglas de negocio.')
PY
```

Los esquemas son diseno; no se implemento emisor, endpoint de captura, claves HMAC, cambios al modelo, ni almacenamiento. Antes de instrumentar los cinco obligatorios, resolver las brechas y aprobar privacidad y reglas de negocio. Las restantes oportunidades del catalogo no se envian con schemaVersion 1.0.0 hasta tener una rama oneOf explicita.

## Estrategia de entrega y procesamiento

Esta seccion cubre **cada uno de los 14 eventos con esquema 1.0.0**, no los 31 candidatos pendientes de contrato. Stream significa procesamiento continuo orientado a detectar una situacion operativa; batch significa procesamiento periodico para tendencias o decisiones que admiten espera. La tabla define objetivos de latencia de diseno, no SLA medidos ni tecnologia de transporte ya desplegada. Todos los eventos conservan timestamp de ocurrencia: batch no significa generar el evento al finalizar el lote.

| event_type | Procesamiento y ventana propuesta | Justificacion por urgencia de la decision |
| --- | --- | --- |
| `inbound_order_created` | **batch**, cada 15 minutos | Elena planifica produccion y compra segun recepciones y demanda esperada, no necesita reaccionar a cada lote en segundos. Una espera de 15 minutos permite comparar cantidades por programa/oficina sin esperar al reporte semanal. El stock transaccional se actualiza inmediatamente fuera de telemetria. |
| `outbound_order_created` | **batch**, cada 15 minutos | El ritmo de consumo orienta reposicion y planificacion de matriculas en ventanas de actividad; no requiere una alerta por cada kit entregado. Las situaciones de escasez se detectan por el evento de umbral en stream, sin depender de completar este lote. |
| `stock_threshold_triggered` | **stream**, objetivo <=60 segundos desde commit | Un programa sin material puede bloquear la siguiente entrega. Elena debe poder acelerar reposicion o redistribucion antes de seguir acumulando entregas fallidas; esperar 15 minutos podria prolongar una interrupcion evitable. |
| `direct_stock_edit_rejected` | **stream**, objetivo <=60 segundos desde rechazo | Repetidos intentos de saltarse trazabilidad necesitan revision operativa temprana para distinguir confusion de uso indebido. La alerta es para investigar o dar soporte, no castigar automaticamente; el rechazo de stock ocurre sincronamente en API y no depende de telemetria. |
| `kit_cost_variance_detected` | **batch**, cada hora | Renegociar o buscar proveedor requiere comparar importes e historico y una revision humana, no una reaccion por segundo. Una hora permite avisar a Elena/Laura dentro de la jornada; no bloquea recepciones ni sustituye controles de compras. Si aparecen compras masivas automatizadas, revisar esta tolerancia. |
| `inventory_order_validation_failed` | **batch**, cada 15 minutos | Mejorar defaults, mensajes y capacitacion requiere patrones de fallos, no intervenir por cada campo invalido. La UI devuelve feedback inmediato independientemente del lote. No sustituye al rechazo obligatorio de stock directo ni al aviso de umbral. |
| `login_attempted` | **stream**, objetivo <=60 segundos | El volumen de intentos es denominador necesario para detectar rapido una ola de fallos o acceso anomalo que impida operar. Debe procesarse con los resultados de login en la misma ventana, no dejar el denominador retrasado en batch. |
| `login_succeeded` | **stream**, objetivo <=60 segundos | Contrastar accesos conseguidos con intentos/fallos permite distinguir actividad normal de una interrupcion del acceso. El procesamiento rapido habilita soporte oportuno durante el inicio de jornada; los reportes de tendencia se agregan despues. |
| `login_failed` | **stream**, objetivo <=60 segundos | Un aumento de fallos de credenciales o indisponibilidad puede impedir que un equipo comience sus tareas. Soporte necesita detectar el problema pronto y distinguirlo de un fallo aislado; no se bloquean cuentas automaticamente desde la telemetria. |
| `session_expired` | **batch**, cada 5 minutos | Ajustar duracion de sesion o avisos previos depende de patrones de interrupcion, no de cada token vencido. La reautenticacion del usuario es inmediata en el sistema; cinco minutos permiten investigar concentraciones sin convertir cada expiracion normal en alerta. |
| `api_request_completed` | **stream**, objetivo <=60 segundos | Latencia, volumen y 5xx pueden anticipar indisponibilidad del inventario o autenticacion. Esperar un reporte periodico impediria intervenir antes de que se acumulen tareas bloqueadas; evaluar por plantilla, status y ventana, no alertar por cada request lento. |
| `frontend_data_load_completed` | **batch**, cada 5 minutos | Priorizar mejoras de carga por seccion requiere distribuciones y comparacion ready/empty/error. Cinco minutos son suficientes para orientar soporte e investigacion; incidentes API y excepciones no capturadas tienen canales stream para fallos urgentes. |
| `frontend_unhandled_error` | **stream**, objetivo <=60 segundos para la primera deteccion | Una excepcion no capturada puede dejar la pantalla inutilizable sin feedback. Detectarla rapido por build y fingerprint permite revertir un despliegue o reparar el componente antes de que mas operadores se bloqueen. |
| `backoffice_section_viewed` | **batch**, cada hora | Reorganizar navegacion y priorizar funcionalidades depende de patrones de uso, no de la visita individual. Una hora de espera no cambia la decision ni la capacidad de completar ordenes y evita vigilancia operativa por usuario en tiempo real. |

Stream tambien alimentara agregados diarios y semanales; no se duplican hechos de negocio para cada reporte. Batch procesa ventanas por timestamp y oficina/programa cuando corresponda, nunca suma monedas diferentes. Las ventanas de intentos/resultados de login admitiran eventos tardios y no confundiran un intento aun sin resultado con un fallo de credenciales.

### Entrega fiable, limites y modo degradado

- Para eventos obligatorios ligados a commit, proponer outbox durable en la misma transaccion que la orden y conservar eventId al reenviar; para rechazos, almacenamiento durable separado sin convertir el rechazo en escritura de stock. Estas capacidades no existen todavia y deben implementarse antes de afirmar entrega garantizada. Fallar al publicar no debe reportarse al cliente como si la orden ya confirmada hubiera fallado.
- Propuesta de reintento del transporte: backoff exponencial con jitter, de 1 segundo hasta 60 segundos, limite de 24 horas. Tras el limite, conservar el evento en cola de incidencias durable y alertar, sin borrarlo silenciosamente. Entrega al menos una vez exige deduplicar eventId y la identidad de orden/event_type; no se promete exactly-once.
- Separar colas/prioridades de alertas stream y procesamiento batch para que un pico de visitas no retrase un umbral. Cola batch cada 15 minutos/hora segun tabla; pagina cerrada o caida de red no debe resetear timestamps ni ventanas. No se garantiza persistencia de eventos frontend si el navegador termina antes de entregar.
- Limite propuesto de transporte frontend: hasta 50 eventos o 64 KiB por envio, lo que ocurra antes, y flush cada 10 segundos si hay pendientes. Stream se envia sin esperar ese flush. Los lotes transportan eventos individuales con el envelope actual; un contenedor de lote/ACK necesita contrato de transporte futuro, no propiedades nuevas dentro de properties.
- Rechazar payloads fuera de allowlist o version no soportada antes de almacenar; registrar solo contador y motivo sanitizado en diagnostico, no el payload rechazado. Autenticar canal, validar requestId/sessionId y limitar abuso; UUID/HMAC no demuestran veracidad del evento.
- Un rate limit de ingesta contra abuso no es muestreo analitico. Reportar perdidas, backlog y latencia de entrega para no interpretar ausencia de datos como ausencia de problemas. Objetivos stream se degradan durante outage: visibilizar atraso y reconciliar al recuperar.

### Throttle, debounce y deduplicacion

| Evento / fuente de frecuencia | Regla propuesta | Proteccion de significado |
| --- | --- | --- |
| Cinco eventos obligatorios | **Sin throttle, debounce ni muestreo** de hechos distintos; solo deduplicar la misma ocurrencia | No omitir una orden, un rechazo reconocido, un cruce ni una variacion para ahorrar transporte. Un producto que permanece bajo minimo no genera eventos nuevos en cada GET; rearmar al recuperar el minimo es regla de negocio, no throttle temporal. |
| `login_attempted`, `login_succeeded`, `login_failed` | Sin debounce de intentos/resultados; deduplicar deteccion frontend/backend de la misma ocurrencia con origen autoritativo y correlacion | Si el usuario envia dos intentos distintos, contar dos; agrupar alertas por ventana, no reducir el denominador. Limites de seguridad del endpoint no se alteran desde el plan. |
| `session_expired` | Una deteccion por sesion/episodio de expiracion, no por cada comprobacion de guard/focus/interval | Preservar detecciones de sesiones distintas. Reautenticacion inicia otra sesion; colisiones o sessionId null requieren deduplicacion de la misma peticion, no agrupar todos los anonimos. |
| `inventory_order_validation_failed` | Emitir al validar envio o recibir invalid del navegador, no en cada tecla; para el mismo intento/field/reason/layer, deduplicar dentro de 1 segundo | Envios distintos siempre se conservan. Se cuenta validacion de tareas, no numero de pulsaciones; no debounce backend de rechazos distintos. |
| `api_request_completed` | Una muestra por request terminado, **sin throttle ni sampling inicial**; buffering de transporte permitido | Conservar duraciones para p95 y denominadores por ruta/status. No sustituir 100 requests por un evento promedio: el schema no define histogramas ni sampling weights. Si volumen obliga a muestrear, versionar contrato y publicar sesgo/cobertura antes de hacerlo. |
| `frontend_data_load_completed` | Un evento por carga real finalizada; deduplicar callbacks de la misma carga, no limitar cargas distintas. En futura busqueda remota, debounce de **300 ms** antes de iniciar consulta | Debounce cambia consultas disparadas, no borra errores o resultados de consultas ya hechas. No es una modificacion del buscador local actual. Abort por cambio de ruta no se etiqueta como error final sin definir resultado de cancelacion en otro contrato. |
| `frontend_unhandled_error` | Enviar inmediatamente la primera deteccion; deduplicar el mismo fallo captado por boundary/listeners. Para repeticiones identicas por fingerprint/build/sesion, throttle de **60 s** con lider inicial | Evita tormenta que inutilice el canal. Esta politica mide sesiones/episodios afectados, **no frecuencia total de excepciones**; no afirmar conteo exacto ni añadir repeat_count no declarado. Nuevos fingerprints/builds no esperan; mantener un contador diagnostico de suprimidos con contrato futuro. |
| `backoffice_section_viewed` | Emitir tras ruta efectiva y autorizacion; excluir prefetch, StrictMode y rerenders. Debounce de **300 ms** para transiciones intermedias que nunca mostraron seccion utilizable | Una vista ya confirmada no se descarta al navegar rapido. No coalescer A -> B -> A cuando las tres secciones se mostraron; medir visitas reales, no clicks sin contenido. |

Buffering batch y backpressure no cambian eventId ni descartan silenciosamente eventos. Las restricciones elegidas son propuestas de captura futura, no codigo implementado. Los contadores internos de throttle no forman parte del schema 1.0.0 y no se enviaran como extensiones.

## Riesgos y exclusiones del plan

### Eventos o capturas descartados

| Considerado | Decision y motivo |
| --- | --- |
| Evento por pulsacion/valor en formularios | Descartado: gran volumen, riesgo de PII y ninguna decision mejor que validacion al envio y pasos de flujo; no registrar keystrokes. |
| Busqueda libre con texto completo | Descartada: puede contener nombre/email de proveedor o persona. La oportunidad inventory_search_completed del catalogo permanece pendiente de schema y solo admitiria rangos de longitud/resultados, no texto. |
| Evento de stock por cada GET o render bajo minimo | Descartado: duplicaria alertas y confundiria lecturas con activaciones reales. El evento obligatorio usa cruce confirmado y minimo configurado. |
| Evento generico direct_stock_edit_rejected para todo 405/422 | Descartado: sobreatribuye intencion de saltarse controles. Solo intento explicito reconocido; validaciones no clasificables van al evento generico y quedan como brecha de cobertura. |
| Clicks, coordenadas, scroll continuo y session replay | Descartados: alto coste y riesgo de vigilancia/PII; navegacion por seccion y pasos de tarea bastan para priorizar usabilidad. |
| Fingerprinting por IP/user-agent/dispositivo | Descartado: permite seguimiento innecesario y no habilita la decision de reposicion o mejora de flujos; usar sesion aleatoria limitada. |
| Matricula/finalizacion inferida de entrega de kit | Descartada: entrega no acredita matricula ni finalizacion. Integrar una fuente educativa en un proyecto posterior. |
| Reporte de productividad o ranking individual del operador | Descartado: visitas, rechazos y latencia no representan desempeno laboral; decisiones operativas se apoyan en agregados y revision humana. |

Los otros 31 eventos del catalogo de fase 1 **no estan descartados**: no tienen esquema en esta entrega y no se capturaran hasta definir contrato, fuente y beneficio de prioridad. No confundir exclusion definitiva con aplazamiento por coste/alcance.

### Datos excluidos y riesgos residuales

- No capturar nombres, emails, telefonos, direcciones, credenciales, JWT, tokens de recuperacion, cookies de auth, datos de clientes/candidatos/consultores, assigned_to, notas, texto CSV, texto de busqueda, request/response bodies, SQL con parametros, URLs/query/referrer completos, stacks o mensajes de error sin sanitizar. No ampliar allowlists por comodidad de diagnostico.
- Costes e identificadores estructurados de proveedor son necesarios para la metrica obligatoria de variacion, pero sensibles comercialmente: conservar moneda original, limitar acceso y mostrar reportes agregados. No excluir estos campos necesarios por privacidad y luego afirmar que la metrica de coste esta cubierta.
- sessionId y userId HMAC siguen siendo vinculables: riesgo de reidentificacion por grupos pequenos y patron horario. Evitar reportes individuales, restringir acceso y aprobar retencion/minimo de agrupacion antes de produccion; el plan no afirma cumplimiento legal automatico por usar HMAC.
- Brechas de categoria/programa/minimo/coste impiden emision completa de obligatorios hasta corregir el dominio. No rellenar unknown/0 ni inferir oficina del idioma para aparentar cobertura. La metadata enviada por cliente no es autoritativa.
- Reintentos, mensajes tardios y orden distinto pueden duplicar alertas o distorsionar ventanas. Deduplicar ocurrencia, conservar timestamp y permitir reconciliacion de batch. La alerta de umbral se fundamenta en el cruce almacenado, no en comparar con otro evento de llegada posterior.
- Caidas frontend, bloqueo de telemetria o red pueden sesgar cargas y navegacion; distinguir ausencia de captura de abandono o cero errores. La validacion de stock, autenticacion y trazabilidad transaccional no dependen del canal de telemetria.
- Throttle de errores reduce visibilidad de repeticiones identicas: explicitar que los informes describen episodios/sesiones y no numero total de throws. En esta version no existe un contador agregado validable para recuperar esa frecuencia.
- Volumen API, cardinalidad de IDs y outbox pendiente de implementar pueden superar coste previsto. Medir tamanos/colas y limitar retencion, no hacer sampling oculto de obligatorios ni cambiar payloads sin version. No se asume Redis, Kafka u otra tecnologia por preferencia tecnica.

La estrategia es documental: quedan pendientes implementacion de entrega/ACK, colas durables, mediciones de backlog/perdidas y aprobacion operativa de ventanas. Este cambio no modifica JSON Schema, negocio ni datos de inventario.
