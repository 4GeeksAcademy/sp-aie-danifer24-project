# ARCHITECTURE_PROPOSAL

## 1. Objetivo

Definir una propuesta de arquitectura backend para Nexova que sirva como base comun para sus operaciones principales (seleccion, ventas, RRHH interno, formacion y soporte), priorizando mantenibilidad, trazabilidad y evolucion incremental.

Esta propuesta no esta enfocada en un solo producto puntual, sino en un backend corporativo que permita exponer capacidades de negocio por API y que pueda crecer por modulos en proximos sprints.

## 2. Patron arquitectonico recomendado

### Decision

Se recomienda una arquitectura en capas con monolito modular orientado a dominio, implementada en FastAPI.

### Justificacion

- Frente a MVC puro: MVC es util en aplicaciones CRUD sencillas, pero Nexova requiere reglas de negocio que cruzan estados, procesos y analitica. Mantener esa logica en controladores aumentaria el acoplamiento rapidamente.
- Frente a microservicios desde el inicio: dividir por servicios demasiado pronto multiplica complejidad operativa (deploy, observabilidad, contratos, debug) sin evidencia actual de que el equipo necesite ese costo fijo.
- Frente a serverless como base total: serverless encaja bien para tareas event-driven o jobs, pero para un nucleo transaccional y API de uso constante conviene un servicio persistente con trazabilidad unificada.
- Ventaja del monolito modular: permite separar dominios de negocio con fronteras claras y conservar simplicidad de despliegue.

### Recomendacion complementaria

Mantener una estrategia hibrida: nucleo API en FastAPI y uso selectivo de funciones asincronas para procesos de background (notificaciones, ingestas, enriquecimiento de datos o tareas de scoring offline).

## 3. Dominios de negocio propuestos

Tomando el contexto de Nexova, el backend deberia organizarse inicialmente en estos dominios:

1. Recruitment: candidatos, vacantes, procesos, matching y notas.
2. Sales: cuentas, prospectos, actividades y estado del pipeline comercial.
3. Internal HR: onboarding, politicas, solicitudes y seguimiento interno.
4. Training: catalogo, inscripciones, progreso y recomendaciones formativas.
5. Support: tickets, SLA, base de conocimiento y seguimiento operacional.
6. Executive Insights: KPIs transversales, agregaciones y reportes ejecutivos.
7. IAM and Audit: autenticacion, autorizacion, roles y trazabilidad.
8. Integrations: conectores con CRM, ATS legacy, correo y herramientas externas.

## 4. Criterio de separacion: dominio + responsabilidad tecnica

Se propone combinar dos ejes:

- Separacion principal por dominio de negocio para ownership claro.
- Separacion interna por responsabilidad tecnica para mantener capas desacopladas.

Dentro de cada dominio se replica la misma estructura: router, schemas, service y repository. Asi se evita mezclar transporte HTTP, logica de negocio y acceso a datos.

## 5. Estructura de carpetas propuesta para FastAPI

```text
apps/
  nexova-backend/
    app/
      main.py
      api/
        router.py
        deps.py
        v1/
          recruitment.py
          sales.py
          hr.py
          training.py
          support.py
          insights.py
          auth.py
          health.py
      core/
        config.py
        logging.py
        security.py
        exceptions.py
      db/
        base.py
        session.py
        models/
          recruitment.py
          sales.py
          hr.py
          training.py
          support.py
          audit.py
      domains/
        recruitment/
          schemas.py
          service.py
          repository.py
          rules.py
        sales/
          schemas.py
          service.py
          repository.py
        hr/
          schemas.py
          service.py
          repository.py
        training/
          schemas.py
          service.py
          repository.py
        support/
          schemas.py
          service.py
          repository.py
        insights/
          schemas.py
          service.py
          repository.py
      integrations/
        hubspot/
          client.py
        email/
          client.py
        ats/
          client.py
      jobs/
        scheduler.py
        tasks.py
      tests/
        unit/
        integration/
      alembic/
      pyproject.toml
      README.md
```

## 6. Organizacion de endpoints y routers

### Principio

Router por dominio, todos agregados bajo /api/v1 para versionado y compatibilidad hacia atras.

### Ejemplo de organizacion por dominio

Recruitment:

- GET /api/v1/recruitment/candidates
- POST /api/v1/recruitment/candidates
- GET /api/v1/recruitment/vacancies
- PATCH /api/v1/recruitment/processes/{process_id}/stage

Sales:

- GET /api/v1/sales/leads
- POST /api/v1/sales/activities
- PATCH /api/v1/sales/deals/{deal_id}/status

Internal HR:

- GET /api/v1/hr/employees
- POST /api/v1/hr/onboarding/checklists
- GET /api/v1/hr/requests

Training:

- GET /api/v1/training/catalog
- POST /api/v1/training/enrollments
- GET /api/v1/training/progress/{employee_id}

Support:

- GET /api/v1/support/tickets
- POST /api/v1/support/tickets
- PATCH /api/v1/support/tickets/{ticket_id}/status

Executive Insights:

- GET /api/v1/insights/kpis
- GET /api/v1/insights/weekly-summary

Auth and system:

- POST /api/v1/auth/login
- POST /api/v1/auth/refresh
- GET /api/v1/health

### Convenciones para routers

- Un prefix por dominio y tags consistentes para OpenAPI.
- DTOs de request y response separados de modelos ORM.
- Errores normalizados y codigos HTTP consistentes.
- Validaciones en entrada y reglas de negocio en services, no en routers.

## 7. Estructura habitual de FastAPI y su impacto en esta propuesta

Tras revisar convenciones comunes de proyectos FastAPI, hay patrones que aparecen de forma recurrente:

1. main.py como bootstrap de aplicacion y registro de routers.
2. Separacion entre api, core, models y schemas.
3. Uso de deps.py para inyeccion de dependencias (db session, auth, permisos).
4. Capa de servicios para casos de uso y reglas de negocio.
5. Capa de repositorios para acceso a persistencia.
6. Configuracion centralizada por entorno con variables de entorno.

Esta propuesta adopta esos patrones porque:

- reduce curva de aprendizaje para nuevos developers de Python/FastAPI;
- facilita pruebas unitarias por capa;
- permite escalar por dominios sin reorganizaciones disruptivas;
- mejora gobernanza tecnica del equipo desde el sprint inicial.

## 8. Organizacion cuando frontend y backend son sistemas separados

### 8.1 Modelo de repositorio

Opcion recomendada hoy: monorepo con apps separadas (frontend y backend), para coordinar contratos rapidamente durante fase de construccion.

Opcion futura: separar repos cuando haya equipos con ciclos de release distintos o necesidades fuertes de seguridad/aislamiento.

### 8.2 Comunicacion por API

- Contrato REST versionado y documentado en OpenAPI.
- Definir politica de versionado (breaking changes solo en nueva version).
- Integrar validaciones de contrato en CI para detectar incompatibilidades.

### 8.3 Variables de entorno

Frontend:

- NEXT_PUBLIC_API_BASE_URL
- NEXT_PUBLIC_APP_ENV

Backend:

- APP_ENV
- DATABASE_URL
- SECRET_KEY
- ALLOWED_ORIGINS
- LOG_LEVEL

Practica clave: no hardcodear endpoints ni secretos; usar .env.example por aplicacion y secretos solo en entorno seguro.

### 8.4 CORS

- Configurar lista blanca explicita de origenes por ambiente.
- Evitar comodines en produccion.
- Revisar credentials, headers permitidos y metodos permitidos segun estrategia de autenticacion.

## 9. Riesgos y puntos de atencion

1. Fronteras de dominio difusas
Si no se define ownership por dominio, aparecen duplicidades de logica y conflictos entre equipos.

2. Acoplamiento entre capas por decisiones rapidas
Si los routers terminan con SQL o reglas complejas, cae la testabilidad y sube el costo de cambios.

3. Contrato API inestable
Cambios sin versionado ni governance pueden romper clientes frontend y automatizaciones internas.

4. Observabilidad insuficiente
Sin logs estructurados, metricas y trazas, el equipo no podra diagnosticar incidentes en operaciones criticas.

5. CORS y entorno mal gobernados
Errores de configuracion entre dev/staging/prod pueden bloquear integraciones o exponer riesgos de seguridad.

## 10. Decisiones tecnicas iniciales sugeridas para el proximo sprint

1. Establecer esqueleto FastAPI con estructura modular por dominios.
2. Definir contrato OpenAPI inicial para recruitment, auth y health.
3. Configurar pipeline base de calidad (lint, tests, typing, formato).
4. Implementar estrategia minima de logs estructurados y manejo de errores.
5. Definir matriz de entornos (dev, staging, prod) y politica de variables.
6. Documentar convenciones de nombrado, versionado y ownership por dominio.

## 11. Recomendacion final

Para Nexova, la opcion mas equilibrada es iniciar con FastAPI en capas sobre un monolito modular orientado a dominio, con foco en contratos estables y observabilidad desde el inicio.

Este enfoque permite entregar valor rapido, mantiene controlada la complejidad y deja abierta una evolucion ordenada hacia componentes desacoplados donde realmente haga falta.
