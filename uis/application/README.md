# Nexova · Aplicación

Directorio de proveedores con Next.js y React, disponible en `/suppliers` y desde
el menú de la aplicación. La ruta `/` abre directamente el directorio.

## Ejecución

Arranca primero la API desde la raíz del repositorio:

```bash
python -m pip install -r services/api/requirements.txt
uv run seed
python -m uvicorn services.api.main:app --host 0.0.0.0 --port 8000
```

En otra terminal:

```bash
cd uis/application
npm install
npm run dev -- --hostname 0.0.0.0 --port 3000
```

Abre `http://localhost:3000/suppliers`.

Next redirige `/api/suppliers` a la API local en `http://127.0.0.1:8000`, sin
necesidad de configurar CORS. Para usar otra API, define `SUPPLIERS_API_URL` al
arrancar Next, por ejemplo:

```bash
SUPPLIERS_API_URL=http://127.0.0.1:8001 npm run dev
```

## Funcionalidad

- Tabla con nombre, país, categorías, tarifa mensual, renovación y estado.
- Búsqueda y filtros por país y categoría en React, sin recargar la página.
- Alta mediante POST, con moneda vinculada al país, selección de categorías y
  errores de la API visibles en el formulario.
- Edición de tarifa mediante PATCH y actualización inmediata del registro.
- Control de activación/suspensión por proveedor, con estados diferenciados.
- Renovaciones próximas a 60 días destacadas y resumen de costes activos sin
  mezclar EUR y USD.
- Estados de carga, error y lista vacía; formularios en diálogos y disposición
  móvil mediante CSS responsive.

## Validación

```bash
npm run typecheck
npm run lint
npm run build
```

Los tres comandos pasan. La integración HTTP de Next con FastAPI se verificó
sobre una base temporal: listado, alta, filtros, edición de tarifa, timestamp,
estado y rechazo de datos inválidos. No se añadieron archivos de pruebas.

La revisión visual e interactiva en Chromium queda pendiente: el contenedor no
dispone de las bibliotecas gráficas necesarias. La prueba alternativa de DOM
en memoria se interrumpió sin resultado.

`npm audit` mantiene cinco avisos altos de la cadena de dependencias de ESLint
por `braces`; no hay una versión publicada corregida compatible. La aplicación
utiliza Next 16.3.8, que corrige los avisos críticos detectados inicialmente.