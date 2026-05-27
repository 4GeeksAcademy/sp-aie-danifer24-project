# App Talent Pipeline Tracker

## Contexto

Eres desarrollador web y tu trabajo es desarrollar un frontend para una aplicación que utilizará el departamento de rrhh que consuma una API REST para gestionar el pipeline de candidaturas. El sistema debe permitir ver todas las candidaturas de un vistazo, filtrarlas por estado y por etapa, y acceder al detalle de cada una sin perder el contexto del listado.

## Requisitos

Lo que la herramienta debe hacer:

1. Mostrar todas las candidaturas en un listado — nombre, puesto, estado actual y etapa actual de un vistazo.
2. Permitir filtrar por estado y por etapa, y buscar por nombre o email sin recargar la página.
3. Abrir la vista de detalle de un candidato y, desde ahí, cambiar su estado o etapa con una sola interacción.
4. Añadir notas internas a una candidatura y eliminarlas cuando ya no sean relevantes.
5. Registrar nuevas candidaturas directamente desde la interfaz y editar los datos de una cuando haya que corregir algo.

Definir tipos TypeScript para todas las estructuras de datos recibidas de la API

## Vistas

Se debe usar el sistema de rutas de Next.js, sin recargas completas de página

1. Página de listado de candidaturas (/): muestra todos los candidatos obtenidos desde GET /records
    - Nombre completo, puesto, estado actual y la etapa actual de cada candidato
    - Filtro por estado y filtro por etapa (useSearchParams)
    - Campo de búsqueda que filtre por nombre o email sin recargar
    - Estado de carga mientras se obtienen los datos y mensaje de error si falla
2. Página de detalle de candidatura (/candidates/[id]): obtiene y muestra los datos completos desde GET /records/:id
    - Nombre, email, teléfono, puesto, LinkedIn, enlace al CV, años de experiencia, estado, etapa y fecha de aplicación
    - Control para actualizar el estado PATCH /records/:id
    - Control para actualizar la etapa PATCH /records/:id
    - Listado de notas obtenidas GET /records/:id/notes
    - Añadir nota POST /records/:id/notes
    - Eliminar una nota DELETE /records/:id/notes/:note_id

Incluir formularios para registrar y editar candidaturas POST /records y PUT /records/:id, ambos formularios deben validar antes de enviarse y mostrar feedback tras el envío.

## Estructura

- /components
- /hooks (si aplica)
- /types
- /lib
- /services

## Tecnologías

Next.js(App Router), React y TypeScript, llamadas API con async/await. Cada operación debe tener al menos 3 estados en la UI: cargando, éxito y error. Tras PATCH, PUT o POST, actualizar la interfaz sin recarga completa.


