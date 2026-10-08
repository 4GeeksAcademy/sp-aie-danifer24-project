# Progreso del proyecto

## Gestor centralizado de incidencias

- Definidos modelos Pydantic y enums de incidencia, con validacion de campos, estado y timestamps UTC de sistema.
- Centralizados parser y validador de CSV; implementado `scripts/seed_incidents.py` con transformaciones del legado, reporte de filas invalidas e idempotencia por ticket o fallback titulo/fecha. Verificado con 96 altas, 4 filas invalidas y 0 altas en la segunda ejecucion; conteos de estados y categorias coinciden con el contexto.
- Implementados endpoints autenticados para alta, listado con filtros, detalle, cambio de estado y resumen por estado/categoria/origen/sucursal. Se validan transiciones y estados finales; listas y resumen funcionan con la base vacia.
- Errores de validacion de incidencias se presentan como HTTP 400 con campos; se preserva HTTP 422 en endpoints existentes. Excepciones inesperadas devuelven un mensaje 500 generico.
- Documentados API y seed en `services/api/README.md`. Verificacion: pruebas aisladas de endpoints con TinyDB en memoria, `compileall`, `git diff --check` y 12 pruebas de restablecimiento de contrasena correctas.
- Backoffice: agregado menu global y paginas `/incidents` y `/incidents/new`. El formulario mantiene sede requerida visible, muestra todas las sedes del contexto, enfatiza sede para origen sucursal, presenta errores por campo y confirma/limpia tras el alta.
- El panel lista incidencias con filtros por estado, origen y sede, estados de carga/error/reintento y vacios diferenciados; los cambios de estado son optimistas y revierten ante fallo. El resumen por estado, categoria, origen y sede tiene carga, reintento y ciclo de actualizacion independiente, y conserva las metricas visibles durante recargas o errores.
- Agregados proxies Next autenticados `/api/incidents` (incluyendo resumen, detalle y cambio de estado), con destino configurable mediante `SUPPLIERS_API_URL`. Los errores tecnicos no se exponen como detalles internos al usuario.
- Validacion frontend en `uis/backoffice`: `npm run lint`, `npx tsc --noEmit`, `npm run build` y `git diff --check` correctos. El build reconoce paginas de incidencias y sus cuatro rutas proxy. No hay suite automatizada de UI ni validacion visual en navegador.

## Auditoría y mejoras de gestión de errores (2026-10-08)

- Creado `docs/auditoria-gestion-errores.md` con hallazgos priorizados para frontend, API y scripts; el alcance es estático y el documento conserva recomendaciones pendientes para legacy JS y el seeder.
- En `uis/application` y `uis/backoffice`, los clientes HTTP convierten errores de transporte, parseo y respuesta en mensajes controlados; se validan respuestas antes de renderizar datos de proveedores, perfil e incidencias.
- Los formularios limpian estado `busy` mediante `finally`; cargas de incidencias también limpian `loading` en `finally`. Los errores de cambio de estado del panel ofrecen reintento, y los fallbacks evitan fallos de render con datos opcionales.
- Verificación: lint, typecheck y build correctos en Application y Backoffice; `git diff --check` correcto. Website no tiene dependencias instaladas en el workspace y no fue modificado; las apps no ofrecen suite automatizada de UI.

## Gestión de errores del backend (2026-10-08)

- Los handlers FastAPI devuelven códigos estables (`code`) y `status_code` junto a `detail` compatible; las validaciones sanitizan el nombre de campo y mensajes, y los fallos no manejados responden 500 genérico mientras el log registra solo el tipo de excepción.
- El endpoint de análisis CSV cierra siempre el archivo cargado, convierte fallos de lectura en 500 controlado y mantiene validaciones 400/415/422.
- El único cliente externo de la API, Resend, limita los `try/except` a parseo de URL, construcción de request y transporte; controla errores HTTP, URL y timeout sin registrar token, destinatario, URL ni cuerpo.
- Verificación backend: 16 pruebas pasan, incluyendo respuestas estructuradas 400/404/422/500, fallos de transporte y ausencia de secretos en logs; `compileall` y `git diff --check` correctos.
- Scripts Python: lectores/parseo CSV conservan errores de dominio sanitizados; errores de escritura y procesamiento imprimen mensajes controlados a stderr y terminan con código no cero. Importaciones parciales del seeder de incidencias también devuelven `1`; errores de mapeo ya no incluyen valores de filas.
- Revisados los `print` del alcance: el análisis solo emite agregados, el seeder muestra códigos por fila, y `pandas_clean.py` reporta metadatos sin imprimir nombres de columnas ni filas. No se encontraron llamadas `console.error` en `uis/`.
- Verificación de scripts: `py_compile` pasa; suite backend 16/16; fallos simulados de ambos seeders devuelven código 1; CSV inexistente en `scripts/analyze.py` devuelve código 2. No se ejecutaron seeds contra la base de datos real.

## Estado actual (resumen ejecutivo)

El desarrollo del Talent Pipeline Tracker se encuentra en una fase avanzada y ya cubre el flujo operativo principal de gestion de candidaturas en Nexova.

- La base documental del proyecto esta definida y alineada con el contexto de negocio.
- El equipo cuenta con una experiencia funcional completa para gestionar candidaturas: visualizacion, seguimiento y actualizacion del proceso.
- Ya estan habilitadas las operaciones clave del ciclo diario: alta de candidaturas, actualizacion de estado y etapa, y gestion de notas internas.
- La solucion prioriza continuidad operativa: el trabajo se realiza sin recargas completas y con retroalimentacion visible en cada accion.

En terminos de impacto, el proyecto ya reduce friccion en la operacion de seleccion y mejora la visibilidad del pipeline para el equipo.

## Hito 09: modelo de proveedores

- Implementados SupplierCreate (entrada sin updated_at) y Supplier (respuesta con timestamp UTC generado por el sistema) en services/api/models.py.
- Validados campos requeridos, estados active/suspended, categorias permitidas, tarifa positiva finita, moneda por pais y fecha opcional de renovacion.
- Pydantic 2 y TinyDB 4 declarados como dependencias directas de la API.
- Seeder implementado con los 15 proveedores exactos del contexto; valida con Pydantic y evita duplicados por nombre y pais sin sobrescribir registros existentes.
- Comando `uv run seed` configurado mediante pyproject.toml. Almacenamiento por defecto en data/suppliers.json, configurable con SUPPLIERS_DB_PATH.
- Verificacion previa: 11 pruebas correctas; archivos de pruebas retirados despues por peticion del desarrollador. Comando real ejecutado dos veces en una base temporal: 15 insertados y luego 0.
- Implementados los seis endpoints /suppliers: alta (201), listado con filtros country/category, detalle, cambio de tarifa, cambio de estado y borrado fisico (204), con 404 para IDs inexistentes y 422 para entradas invalidas.
- SupplierResponse expone el doc_id de TinyDB como id; entradas separadas SupplierRateUpdate y SupplierStatusUpdate rechazan campos del sistema. Cada cambio real de tarifa registra updated_at UTC; el cambio de estado no altera esa fecha.
- Router registrado antes del frontend estatico. Acceso TinyDB serializado dentro de un proceso; ejecutar con un solo worker y sin seeder concurrente.
- Verificacion de endpoints: 51 comprobaciones HTTP correctas con TestClient y una base temporal, sin crear archivos de pruebas. Sin errores del editor ni de git diff --check.
- Frontend Next y React creado en uis/application con autorizacion para su configuracion independiente. Directorio /suppliers accesible desde el menu y apertura directa desde /.
- Implementados listado responsive, busqueda y filtros locales, formulario de alta, errores de API, edicion de tarifa inmediata, controles de activacion/suspension y estados diferenciados. Renovaciones proximas a 60 dias destacadas y totales separados por moneda.
- Proxy Next /api/suppliers hacia FastAPI, configurable con SUPPLIERS_API_URL (por defecto http://127.0.0.1:8000).
- Verificacion frontend: typecheck, lint y build correctos; flujos HTTP comprobados mediante proxy sobre una base temporal sin tocar datos reales ni crear archivos de pruebas.
- Pendiente: revision visual/interactiva en navegador de escritorio y movil. Chromium bloqueado por bibliotecas graficas ausentes; alternativa DOM interrumpida sin resultado. Cinco avisos altos de auditoria quedan en dependencias de ESLint (braces sin version corregida publicada); Next actualizado a 16.3.8.

## Autenticacion y cuenta: frontend (2026-10-07)

- Implementado /login con email y password, POST /auth/login mediante proxy Next, JWT en localStorage bajo nexova_access_token y redireccion a /suppliers.
- El directorio adjunta Authorization: Bearer en sus solicitudes; sin token o con respuesta 401 vuelve a /login y elimina el token rechazado.
- Implementado /register con nombre, telefono y direccion opcionales, POST /users seguido de login automatico. Errores 422 por campo y correo duplicado (409); mensaje diferenciado si se crea la cuenta pero falla el login.
- Implementado /account/profile: carga email y perfil con GET /auth/me, email de solo lectura y actualizacion de nombre, telefono y direccion con PUT /profiles/me autenticado. Campos vacios enviados como null, confirmacion de guardado, reintento de carga y enlace Mi cuenta.
- Verificacion actual: lint y typecheck correctos; comprobaciones en memoria de registro, login, almacenamiento JWT y errores 422/409/401 correctas. Servicio de cuenta previamente comprobado en memoria para GET, PUT, bearer token, null y sesion ausente/caducada.
- Rutas /login, /register y /account/profile comprobadas con HTTP 200; proxies comprobados con respuestas reales 422 y 401 de FastAPI, sin crear cuentas de prueba.
- El paquete frontend no dispone de script de pruebas automatizadas. Pendiente: validacion visual y flujos completos de registro, login y guardado de perfil en navegador con una cuenta valida.
- Commits funcionales creados con confirmacion del desarrollador: 62f1eba (login y proteccion del directorio), dbcb943 (registro) y a077972 (perfil de cuenta). Cada snapshot del indice paso TypeScript y ESLint de forma independiente; documentacion de progreso separada en el cuarto commit.

## Restablecimiento de contrasena (2026-10-07)

- Backend: POST /auth/forgot-password responde de forma generica y crea JWT de un solo uso con expiracion de 30 minutos; solo se persiste el digest. POST /auth/reset-password verifica firma, uso, expiracion y vinculo al hash anterior. POST /auth/change-password requiere sesion bearer y contrasena actual valida.
- Email transaccional con Resend por HTTPS; RESEND_API_KEY, RESEND_FROM_EMAIL y PASSWORD_RESET_URL se leen solo del entorno. El email incluye HTML responsive, texto plano y enlace alternativo; fallos de envio se registran sin secretos ni tokens.
- Frontend: paginas /forgot-password y /reset-password, cambio autenticado en /account/change-password, validacion de confirmacion, mensajes claros, link desde login y aviso posterior al reset. Las rutas publicas se excluyen del guard.
- El estado exitoso del boton de solicitud no muestra el efecto de espera aunque el boton permanece deshabilitado para evitar duplicados.
- Verificacion: 12 pruebas backend pasan; typecheck y lint de application pasan. Pruebas backend simulan Resend; no se verifico entrega real del proveedor ni se enviaron correos.
- Pendiente crear commits separados de backend/tests, frontend y documentacion. Los mensajes se deben confirmar antes de crear los commits.

## Proteccion de rutas internas (2026-10-07)

- Aniadido SessionGuard cliente compartido: valida el JWT de localStorage consultando /api/auth/me, bloquea la vista durante la comprobacion y redirige a /login si falta o no es valido. Revalida al cambiar ruta, recuperar foco, recibir cambios de almacenamiento y cada minuto; muestra reintento ante errores de conexion.
- Integrado en los layouts de uis/application, uis/backoffice y apps/talent-pipeline-tracker. Las rutas publicas /login y /register de application quedan excluidas; el website publico no tiene cambios.
- Aniadidos login y proxies /api/auth/me y /api/auth/login en backoffice y tracker, usando la API FastAPI y el almacenamiento JWT compartidos. Eliminada la proteccion duplicada del listado de proveedores, ahora cubierta por el guard del layout.
- Validacion: lint y typecheck correctos en application y backoffice. En tracker los archivos modificados pasan ESLint; lint completo conserva cuatro errores preexistentes en app/candidates/[id]/page.tsx y hooks/useCandidatesList.ts, y typecheck completo un error preexistente en services/api.ts:76 (GetRecordsParams no asignable al tipo query). No se modificaron esos archivos.
- Endpoints locales de login con credenciales invalidas y de sesion sin token devuelven 401 en backoffice (3001) y tracker (3002). Sin pruebas visuales con Chromium porque falta libatk-1.0.so.0 en el contenedor.
- Commits creados con confirmacion del desarrollador: 1dac059 (utilidades compartidas), 0f7d709 (application), e0d1a35 (backoffice) y 54ab31b (tracker). La documentacion de progreso se registra en un commit separado.

## Proximos pasos del tracker

1. Cerrar ajustes de presentacion y coherencia de marca para la entrega del hito.
2. Ejecutar validacion funcional integral del flujo completo de candidaturas.
3. Reforzar calidad en validaciones y manejo de errores para reducir riesgo operativo.
4. Completar checklist de entrega y criterios de despliegue.
5. Preparar el proyecto para la siguiente iteracion de mejora y escalado.