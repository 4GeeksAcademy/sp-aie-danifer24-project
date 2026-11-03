# Tech Context

## Mapa del monorepo (verificado en main, 2026-11-03)

Este archivo es el punto de entrada tecnico para nuevas conversaciones. `AGENTS.md` exige leerlo junto con `projectbrief.md` y `progress.md`. Describe archivos versionados, no garantiza que servidores o bases locales sigan activos. Antes de actuar, comprobar rama y `git status`; no trasladar automaticamente el estado de otra rama.

### Aplicaciones y responsabilidades

| Carpeta | Stack | Responsabilidad | Puerto local sugerido |
| --- | --- | --- | --- |
| `uis/website/` | Next.js 16.2.6, React 19.2.4, TypeScript, App Router | Website publico | 3000 |
| `uis/backoffice/` | Next.js 16.2.6, React 19.2.4, TypeScript, App Router | Operaciones: inventario, incidencias y validacion tecnica | 3001 |
| `uis/application/` | Frontend Next.js independiente en esta rama | Proveedores, autenticacion y cuenta; no asumir que esta integrado en Backoffice | 3003 |
| `apps/talent-pipeline-tracker/` | Next.js 16.2.6, React 19.2.4, TypeScript, App Router | Candidaturas y procesos de seleccion | 3002 |
| `services/api/` | FastAPI, Pydantic 2, SQLModel, psycopg2, TinyDB | API comun: usuarios, auth, perfiles, proveedores, incidencias e inventario | 8000 |

Los puertos anteriores son convenciones de arranque local, no servicios garantizados ni puertos fijos del codigo. Los dos frontends usados habitualmente en la sesion son Website y Backoffice; `main` tambien conserva Application y Tracker.

### Backend y almacenamiento

- Entrada FastAPI: `services/api/main.py`, aplicacion `services.api.main:app`. Registra routers de proveedores, auth, perfiles, usuarios, incidencias e inventario, y sirve archivos estaticos de Backoffice en `/`.
- `services/api/database.py` carga `.env` en la raiz con `python-dotenv`, respetando variables ya exportadas. Requiere `DATABASE_URL` PostgreSQL y fuerza el driver `postgresql+psycopg2`.
- PostgreSQL almacena activos y movimientos de inventario mediante SQLModel. El lifespan de FastAPI crea las tablas y necesita una base accesible.
- TinyDB almacena usuarios, perfiles, proveedores, tokens de restablecimiento e incidencias. Ruta predeterminada: `data/suppliers.json`, configurable con `SUPPLIERS_DB_PATH`. Sus accesos se serializan con un lock de proceso; usar un worker.
- Autenticacion JWT con `JWT_SECRET_KEY` y `ACCESS_TOKEN_EXPIRE_MINUTES`. Los clientes comparten el token `nexova_access_token`; no guardar claves, tokens ni URLs con credenciales en este documento.
- `SUPPLIERS_API_URL` y `NEXT_PUBLIC_INVENTORY_API_URL` se usan para configurar destinos backend en las interfaces segun la ruta/app. Para diagnosticar un flujo, revisar el cliente y el proxy correspondientes; no asumir que todos usan la misma variable.

### Codigo compartido y documentos

- `packages/shared/`: parser CSV y utilidades/tipos compartidos, incluida sesion frontend.
- `src/types/` y `src/utils/`: modelos y utilidades TypeScript de busqueda, colecciones, transformaciones y validaciones, reutilizados en validacion tecnica.
- `services/api/routes/` y `services/api/routers/`: endpoints; `services/api/services/`: logica de negocio; `services/api/models.py` y `schemas.py`: modelos y contratos.
- `scripts/seed_incidents.py`: importacion de incidencias; `uv run seed`: seeder de proveedores declarado en `pyproject.toml`. Los seeds escriben datos: ejecutarlos solo contra destinos de prueba autorizados.
- `memory-bank/progress.md`: avances y pendientes. `memory-bank/projectbrief.md`: contexto de negocio. `docs/` y los informes de auditoria describen trabajos concretos; no sustituyen este mapa.

### Arranque sin Docker

Desde la raiz, en terminales separadas:

```bash
npm --prefix uis/website run dev -- --port 3000
npm --prefix uis/backoffice run dev -- --port 3001
uv run --with-requirements services/api/requirements.txt --with sqlmodel --with psycopg2-binary uvicorn services.api.main:app --host 0.0.0.0 --port 8000 --reload
```

Si se necesitan las otras interfaces:

```bash
npm --prefix uis/application run dev -- --port 3003
npm --prefix apps/talent-pipeline-tracker run dev -- --port 3002
```

Una `DATABASE_URL` exportada solo para el comando permite usar PostgreSQL local/de prueba sin sobrescribir `.env` ni Supabase. Las dependencias Python de proyecto estan en `pyproject.toml`; las de FastAPI en `services/api/requirements.txt`. Instalar dependencias npm en cada app si no existe `node_modules`.

### Validacion y diferencias entre ramas

- En `main`, Website, Backoffice y Tracker declaran `dev`, `build`, `start` y `lint`; no asumir que Backoffice tiene scripts `typecheck` o `test` en esta rama. Consultar el `package.json` de la app antes de ejecutar comandos.
- Backend: `uv run --with-requirements services/api/requirements.txt --group dev pytest services/api/tests`, con PostgreSQL de prueba accesible. `git diff --check` valida formato, no comportamiento.
- En `main` no existe `docker-compose.yml` en la raiz. `.env.docker` no se carga automaticamente por el backend; no asumir un wrapper Compose disponible.
- La rama `feature/caching-optimisation` contiene una estructura posterior: integracion de Application en Backoffice, Docker/Compose, informe de caching y optimizaciones frontend/backend. Verificar sus archivos al cambiar de rama; no describir esos cambios como presentes en `main`.
- No hay que releer todo el repositorio: partir de este mapa y abrir solo el modulo, instrucciones y validacion relevantes para la tarea.

## Notas del Talent Pipeline Tracker

Las secciones siguientes describen el tracker original, no todas las interfaces ni la API FastAPI. Sus limitaciones requieren verificacion local antes de tomarlas como estado vigente.

### Stack del tracker

- Framework principal: Next.js 16 (App Router) con React 19.
- Lenguaje: TypeScript 5 en modo estricto.
- Estilos: Tailwind CSS 4 mediante plugin de PostCSS.
- Calidad de codigo: ESLint 9 con configuraciones core-web-vitals y typescript de Next.
- Cliente HTTP: API Fetch nativa del navegador encapsulada en una capa de servicios.
- Tipado de dominio: modelos de candidatura, notas, respuestas paginadas y errores definidos en types.
- Gestion de estado en frontend: hooks de React (useState, useEffect, useMemo, useCallback) sin libreria externa de estado global.

## Decisiones de arquitectura tomadas

### 1) Arquitectura por capas en frontend

Se separo la app por responsabilidades:

- app: rutas y composicion de pantallas;
- components: piezas visuales reutilizables;
- hooks: logica de estado y efectos;
- services: comunicacion con API REST;
- lib: constantes de negocio y utilidades de transformacion/validacion;
- types: contratos tipados para requests y responses.

Esta separacion reduce acoplamiento entre UI y red, y facilita mantener o evolucionar cada capa de forma independiente.

### 2) Renderizado orientado a cliente

Las pantallas principales del tracker usan componentes cliente para priorizar interactividad inmediata (filtros, busqueda, paginacion, modales y formularios) sin recarga completa.

### 3) URL como fuente de verdad para filtros y paginacion

El listado usa query params para status, stage, search y page. Esto permite:

- mantener estado navegable y compartible;
- conservar contexto al ir al detalle y volver al listado;
- sincronizar UI y navegacion con replace sin recargar la pagina.

### 4) Capa de API centralizada

En el tracker, las operaciones de red se concentran en `apps/talent-pipeline-tracker/services/api.ts` (no confundir con `services/api/`, el backend FastAPI):

- construccion de URLs y query params en un solo punto;
- funcion request generica para GET, POST, PUT, PATCH y DELETE;
- manejo de errores unificado mediante ApiError;
- soporte de respuestas 204 y parseo defensivo de JSON.

Esto evita logica duplicada de fetch en componentes y estandariza el manejo de fallos.

### 5) Contrato de datos flexible frente a API mock

Se implemento parseo para respuestas en dos formatos (array plano o paginado), permitiendo compatibilidad con variaciones del backend sin romper UI.

### 6) Normalizacion de etiquetas de negocio

Los valores crudos de API para estado y etapa se traducen a etiquetas legibles en espanol mediante utilidades y constantes. Con esto se cumple el criterio de no exponer valores tecnicos al usuario final.

### 7) Validacion en frontera de formulario

La validacion de alta y edicion se ejecuta antes de enviar a API, con mensajes de error en UI y control de estados de envio (idle, loading, success, error).

### 8) Actualizacion de interfaz sin recarga

Despues de crear, editar, actualizar estado/etapa o gestionar notas, la UI se actualiza en cliente usando estado local y/o refetch puntual, manteniendo continuidad de uso.

## Restricciones tecnicas

### Restricciones del producto y contexto del hito

- Debe consumir la API REST central del tracker y respetar su contrato de campos.
- Debe funcionar con navegacion sin recarga completa (listado y detalle).
- Debe cubrir operaciones CRUD clave del flujo de candidaturas y notas.
- Debe mostrar estados de operacion en UI (cargando, exito, error).

### Restricciones actuales del codigo

- La URL base de API esta fija en codigo, por lo que no hay configuracion por entorno aun.
- No existe capa de cache avanzada ni libreria de data fetching dedicada; el flujo depende de estado local y llamadas manuales.
- No hay estado global centralizado; la coordinacion entre vistas se apoya en params de URL y callbacks.
- La metadata de layout sigue en estado base y requiere ajuste para alinearse a marca/producto.

### Restricciones operativas y de escalado

- La app depende de disponibilidad de la API mock externa para pruebas end-to-end.
- El control de errores esta implementado para UX, pero no hay telemetria central ni logging de cliente.
- El enfoque actual prioriza entrega funcional del flujo principal; capacidades como internacionalizacion completa, autorizacion o observabilidad avanzada no forman parte del alcance implementado hasta ahora.
