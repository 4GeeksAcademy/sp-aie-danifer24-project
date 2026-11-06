# Proyecto de Compañía - Ingeniería de IA — Plantilla para estudiantes

[![4Geeks Academy](https://img.shields.io/badge/4Geeks-Academy-blue)](https://4geeksacademy.com)
[![AI Engineering](https://img.shields.io/badge/track-AI%20Engineering-green)](https://4geeksacademy.com/es/programas-de-carrera/ingenieria-ia)

_Plantilla base para proyectos transversales del Programa de Carrera en Ingeniería de IA — 4Geeks Academy._

_Las instrucciones están [disponibles en inglés](./README.md)._

---

## Propósito

Este repositorio es la **plantilla de inicio** para los proyectos transversales. Trabajarás con escenarios de empresas reales (Brasaland, TrackFlow, Nexova) construyendo entregables que se corresponden con los hitos del curso (Web, Programación, Backend, Telemetría, RAG, Agentes, Workflows, Tiempo real).

- Crea una plantilla a partir de este repositorio.
- Reemplaza el `CONTEXT.md` placeholder por el contexto de tu empresa asignada.
- Usa `skills/` y los `README.md` por carpeta como guía de trabajo.

---

## Estado actual de la plantilla

Actualmente el repositorio ofrece una **estructura base de carpetas y documentación**, pero todavía no incluye aplicaciones ejecutables ni scripts globales en la raíz.

- `CONTEXT.md` es un placeholder y debe sustituirse por el contexto de la empresa asignada.
- No existe todavía un `AGENTS.md` en la raíz.
- Existe metadata del paquete compartido en `packages/shared/package.json` (`@repo/shared-types`), pero aún no hay runner de workspace en raíz.

---

## Estructura del repositorio

```text
ai-engineering-company-project-monorepo/
├── README.md
├── README.es.md
├── CONTEXT.md                # Placeholder a reemplazar con el contexto asignado
├── agents/                   # Patrones/plantillas de agentes y documentación de tools
├── data/                     # raw, process, pipelines, eval
├── docs/                     # Documentación de proyecto y arquitectura
├── infra/                    # Docker, Terraform, configuraciones de despliegue
├── internal/                 # CLIs, scripts de migración empaquetados, utilidades internas
├── mcps/                     # Servidores Model Context Protocol (MCP)
├── packages/
│   └── shared/               # Paquete compartido (@repo/shared-types)
├── scripts/                  # Convenciones/documentación de scripts
├── services/                 # APIs y workers en segundo plano
├── shared/                   # Recursos/convenciones compartidas a nivel repo
├── skills/                   # Skills reutilizables para agentes
├── uis/                      # Interfaces de usuario (React, Next.js, Streamlit, HTML)
└── workflows/                # Documentación de automatizaciones/orquestación
```

---

## Cómo empezar

1. **Usa este repositorio como plantilla** y crea tu propio repo de proyecto.
2. **Clona** tu repositorio (o ábrelo en Codespaces).
3. **Reemplaza** `CONTEXT.md` con el contexto completo de tu empresa asignada.
4. **Revisa** los `README.md` de cada carpeta raíz para entender responsabilidades (`uis/`, `services/`, `data/`, `skills/`, etc.).
5. **Empieza a implementar** entregables por hito en `uis/` y `services/`, reutilizando `packages/shared/` y `data/` según corresponda.

## Ejecución local con Docker Compose

Para ejecutar la infraestructura local (API, Redis, worker de Celery y Flower), usa ambos archivos de entorno en este orden:

```bash
docker compose --env-file .env --env-file .env.docker up -d --build
```

Cuando una variable está definida en ambos archivos, el archivo indicado después (`.env.docker`) tiene prioridad sobre el anterior (`.env`). Las variables exportadas en la shell pueden prevalecer sobre los archivos. La URL que deben compartir API, worker y Flower dentro de Compose es `REDIS_URL=redis://redis:6379/0`; `redis` es el nombre del servicio en la red Docker.

Comandos útiles, manteniendo el mismo orden de archivos:

```bash
docker compose --env-file .env --env-file .env.docker ps
docker compose --env-file .env --env-file .env.docker logs -f api worker redis flower
docker compose --env-file .env --env-file .env.docker stop worker
docker compose --env-file .env --env-file .env.docker start worker
docker compose --env-file .env --env-file .env.docker down
```

Para iniciar solo el worker (y Redis, si aún no está levantado), usa `docker compose --env-file .env --env-file .env.docker up -d worker`. El endpoint autenticado `POST /reporting/pipeline-runs` encola el deployment Prefect y devuelve `202` con `{ "task_id": "..." }`; consulta el resultado con `GET /tasks/{task_id}`. `GET /tasks/{task_id}` requiere la misma autenticación que las demás rutas protegidas. Flower está disponible en el puerto `5555` y permite observar workers y tareas; el worker también registra el identificador, número de intento, estado, duración y detalle de excepciones.

`.env` conserva la configuración/secretos locales compartidos; `.env.docker` debe contener los ajustes propios de Docker y puede sobrescribirlos cuando sea necesario. No publiques ninguno de esos archivos si contienen credenciales.

Las migraciones SQL de `services/api/migrations/` cambian el esquema de PostgreSQL: crean o actualizan tablas e índices que el código espera encontrar. Añadir un archivo de migración al repositorio **no lo ejecuta automáticamente**; debe aplicarse una vez a la base de datos prevista antes de usar la funcionalidad asociada. Por ejemplo, `005_celery_dead_letters.sql` crea el almacenamiento persistente de tareas Celery que agotan sus reintentos; es distinto de `job_runs` y `reporting.pipeline_runs`.

---

## Validación de TypeScript

Durante el desarrollo puedes validar tipos con:

```bash
npm run typecheck
```

Este comando ejecuta `tsc --noEmit` sobre los utilitarios del hito de programación.

---

## Hitos (referencia)

| Hito | Enfoque       | Entregables típicos                              |
| ---- | ------------- | ------------------------------------------------ |
| 0    | Prework       | Configuración del entorno, primeros prompts      |
| 1    | Web           | Sitio corporativo, formularios, SEO              |
| 2    | Programación  | Lógica de negocio, puntuación, cálculos          |
| 3    | UI con IA     | Interfaces generadas con IA                      |
| 4    | Next.js       | Portales, app de fidelización, UI de operaciones |
| 5    | Backend       | API central (ubicaciones, menús, ventas, etc.)   |
| 6    | Telemetría    | Pipeline de datos, dashboards                    |
| 7    | RAG y memoria | Base de conocimiento semántica, búsqueda         |
| 8    | Agentes       | Agentes de soporte, onboarding, formación        |
| 9    | Workflows     | Automatizaciones con n8n                         |
| 10   | Tiempo real   | Dashboards en vivo, alertas, streaming           |

---

## Enlaces

- [4Geeks Academy — Ingeniería de IA](https://4geeksacademy.com/es/programas-de-carrera/ingenieria-ia)
- [Cómo empezar un proyecto de código](https://4geeks.com/lesson/how-to-start-a-project)

---

## Contribuidores

Esta plantilla fue creada como parte del Programa de Carrera de Ingeniería de IA de 4Geeks Academy por [@marcogonzalo](https://www.linkedin.com/in/marcogonzalo) y [@alezanchezr](https://x.com/alesanchezr), junto a otros muchos colaboradores. Descubre más sobre nuestro [Curso de Ingeniería de IA](https://4geeksacademy.com/es/programas-de-carrera/ingenieria-ia) y sobre [otros cursos](https://4geeksacademy.com/es/comparar-programas).

Puedes encontrar otras plantillas y recursos similares en la [página de GitHub de 4Geeks Academy](https://github.com/4geeksacademy).

_Esta plantilla la mantiene 4Geeks Academy para el track de Ingeniería de IA. Uso exclusivo del programa._
