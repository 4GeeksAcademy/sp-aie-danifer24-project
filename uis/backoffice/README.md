# Nexova Backoffice

Aplicacion interna en Next.js + TypeScript.

## Alcance

- Vista de entrada basica de backoffice en la ruta `/`.
- Gestor de incidencias centralizadas: `/incidents` (panel y métricas) y `/incidents/new` (registro).
- Centro de validacion tecnica en la ruta `/validacion-tecnica`.
- Funciones de filtros, busquedas, scoring, reportes y validaciones en TypeScript.
- La logica de negocio se importa desde `src/utils` y `src/types` (sin copiar codigo).
- UI para ejecutar pruebas manuales y visualizar salida JSON.

## Comandos

```bash
npm install
npm run dev
npm run lint
npm run build
```

## Estructura principal

- `app/page.tsx`: vista de bienvenida / estructura base de dashboard en `/`.
- `app/incidents/page.tsx`: listado, filtros, transiciones de estado y resumen de incidencias.
- `app/incidents/new/page.tsx`: formulario de registro de incidencias.
- `lib/incidents.ts`: contratos, etiquetas de negocio y comunicación con la API de incidencias.
- `app/validacion-tecnica/page.tsx`: vista de validacion tecnica en `/validacion-tecnica`.
- `components/TestingPlayground.tsx`: controles de validacion y resultado JSON.
- `src/types/models.ts`: tipos de dominio (origen compartido en monorepo).
- `src/utils/*.ts`: utilidades del hito (origen compartido en monorepo).
- `lib/sample-data.ts`: datos de prueba.
