# Tech Context

## Stack tecnologico actual

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

Toda operacion de red se concentra en services/api:

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
