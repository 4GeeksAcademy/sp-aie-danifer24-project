# Carpeta `services`

Esta carpeta contiene **todos los servicios backend** (APIs y workers en segundo plano) relacionados con la compañía para el proyecto transversal de AI Engineering.

Cada subcarpeta dentro de `services/` debe corresponder a **un servicio concreto** (por ejemplo `admin-api`, `data-processor-worker`) e incluir su propia documentación técnica y funcional.

- **Propósito principal**: centralizar toda la lógica backend, APIs y consumidores de colas que dan soporte a los casos de uso de la compañía.
- **Recomendación**: documenta en este archivo (o en sub-READMEs) los servicios que vayas añadiendo, su objetivo, tecnología usada y cómo ejecutarlos.

## Servicios disponibles

- [`api/`](./api/README.md): API FastAPI para validar y analizar CSV de incidencias, descargar el último informe y servir el backoffice estático.
- [`job_runner.py`](./job_runner.py): API de persistencia y ciclo de vida para trabajos nocturnos independientes en `public.job_runs`, incluidas consultas de bloqueo/idempotencia y manejo de estados fallidos. No sustituye la auditoría ETL de `reporting.pipeline_runs`.
- `job_runs.py`: reexportación compatible de `job_runner.py` para imports existentes.
