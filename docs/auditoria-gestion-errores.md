# Auditoría de gestión de errores

Fecha: 2026-10-08
Alcance: revisión estática de las aplicaciones Next.js en `uis/`, la API FastAPI en `services/` y los scripts Python de `scripts/`. No se modificó código durante la auditoría.

## Hallazgos

### Medio

#### Datos de entrada potencialmente sensibles en la salida del seeder

- **Categoría:** Filtración de datos sensibles
- **Ubicación:** [`scripts/seed_incidents.py`](../scripts/seed_incidents.py#L56), [`scripts/seed_incidents.py`](../scripts/seed_incidents.py#L58), [`scripts/seed_incidents.py`](../scripts/seed_incidents.py#L153)
- **Problema:** Los errores de mapeo interpolan los valores CSV recibidos para `status` y `category`, y luego imprimen el detalle de cada fila inválida. Si una fila está desplazada o mal formada, esos campos pueden contener otros valores de la fila, incluidos datos personales, que acabarían en la consola o en logs del proceso.
- **Corrección sugerida:** Informar códigos de validación estables y el número de fila; no incluir valores de entrada en mensajes de error.
- **Estado:** Resuelto el 2026-10-08. Los errores de mapeo ahora imprimen códigos estables, número de fila y no interpolan valores CSV.

#### Importación parcial reportada como exitosa

- **Categoría:** Sin `sys.exit` con error en scripts
- **Ubicación:** [`scripts/seed_incidents.py`](../scripts/seed_incidents.py#L150), [`scripts/seed_incidents.py`](../scripts/seed_incidents.py#L154)
- **Problema:** Cuando hay filas inválidas, el seeder las descarta y las informa, pero `main()` devuelve `0`. La automatización puede interpretar como completa una importación con registros omitidos.
- **Corrección sugerida:** Devolver un código distinto de cero si hay filas descartadas, o definir un modo explícito para permitir importaciones parciales.
- **Estado:** Resuelto el 2026-10-08. El seeder informa las filas descartadas en stderr y devuelve código `1` si la importación es parcial.

### Bajo

#### Mensajes técnicos del navegador mostrados al usuario

- **Categoría:** Exposición de errores en crudo
- **Ubicación:** [`uis/backoffice/app.js`](../uis/backoffice/app.js#L261), [`uis/backoffice/app.js`](../uis/backoffice/app.js#L285)
- **Problema:** Los bloques `catch` muestran `error.message` directamente. Un fallo de red o de `response.json()` puede presentar mensajes técnicos del navegador en la interfaz.
- **Corrección sugerida:** Mostrar un mensaje genérico para errores de transporte o parseo y reservar mensajes controlados para errores de API conocidos.

#### Recuperación de contraseña captura excepciones demasiado amplias — Resuelto

- **Categoría:** Catch demasiado amplio
- **Ubicación:** [`services/api/services/email.py`](../services/api/services/email.py#L13), [`services/api/services/email.py`](../services/api/services/email.py#L48)
- **Problema:** El `except Exception` cubre configuración, construcción del mensaje, serialización y envío. Un defecto de programación también queda clasificado como un fallo genérico de entrega.
- **Corrección sugerida:** Distinguir fallos esperados de configuración/transporte de errores inesperados, conservando la respuesta genérica externa del flujo de recuperación.
- **Estado:** Resuelto el 2026-10-08. `send_reset_email` separa validación de configuración, creación de la solicitud y transporte; solo captura errores esperados, y los logs no incluyen valores sensibles.

#### Comprobación de sesión sin reintento en el backoffice heredado

- **Categoría:** Sin llamada a la acción para el usuario
- **Ubicación:** [`uis/backoffice/app.js`](../uis/backoffice/app.js#L88), [`uis/backoffice/app.js`](../uis/backoffice/app.js#L92)
- **Problema:** Si la comprobación inicial de sesión falla, solo se muestra un aviso; no hay un control para volver a intentarla y el usuario debe recargar la página.
- **Corrección sugerida:** Añadir una acción que vuelva a ejecutar la comprobación de `/auth/me`.

## Categorías sin hallazgos confirmados

- No se identificaron operaciones asíncronas sin manejo local o global de errores que pudieran quedar sin tratar.
- No se identificaron bloques `catch` vacíos o `except: pass` dentro del alcance revisado.
- Las pantallas Next.js que cargan datos revisadas exponen estados de carga/error y mecanismos de recuperación adecuados.
- Los fallos fatales de los scripts de `scripts/` producen códigos de salida distintos de cero; la importación parcial del seeder se registra arriba como caso específico.

## Verificación

La auditoría fue estática. No se ejecutaron pruebas ni se modificó código de aplicación. El paquete `uis/backoffice` no define una suite automatizada de pruebas de interfaz.