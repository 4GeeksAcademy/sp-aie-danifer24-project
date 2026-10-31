# Informe de auditoría y cambios — frontend

## Resumen

Se centralizó en un custom hook la carga, validación, manejo de error y reintento de activos usada por tres páginas de inventario del Backoffice. También se extrajo una cabecera compartida en Website. Las métricas Lighthouse before/after se resumen en este informe y se detallan en [`AUDIT.md`](AUDIT.md).

## Correcciones aplicadas

| Cambio | Descripción | Impacto | Validación |
|---|---|---|---|
| Hook `useInventoryAssets` | Extrae a `uis/backoffice/hooks/useInventoryAssets.ts` la petición, el estado de carga/error, reintento, protección contra actualización después de desmontar y validación runtime consistente de los activos. Reutilizado por productos, entrada y salida. | Unifica el comportamiento de inventario y favorece consistencia y mantenibilidad. | ESLint enfocado y `tsc --noEmit` de Backoffice correctos. |
| Componente `SiteHeader` | Extrae a `uis/website/components/SiteHeader.tsx` la cabecera duplicada y se comparte entre portada y página de talento, conservando el contenido de navegación específico de cada ruta. | Reutiliza la cabecera y mantiene una navegación coherente entre páginas. | `npm run lint` y `npm run build` de Website correctos. Next muestra un warning de raíz del workspace por lockfiles múltiples, no bloqueante ni introducido por este cambio. |

La optimización de hidratación reduce el bloqueo del hilo principal en las vistas móviles mejoradas. Las mediciones posteriores muestran descensos de TBT móvil en tres vistas y CLS móvil de 0 en las cuatro. TBT es una métrica de laboratorio, no un Core Web Vital.

## Comparativa Lighthouse

La tabla presenta los valores Lighthouse before → after para las métricas comparadas.

| Ruta | Dispositivo | Rendimiento | TBT | CLS |
|---|---|---:|---:|---:|
| Backoffice — portada | Desktop | 100 → 100 | 0 → 0 ms | 0.022 → 0.022 |
| Backoffice — portada | Mobile | 95 → 98 | 240 → 140 ms (−100; −41.7%) | 0.058 → 0 |
| Backoffice — proveedores | Desktop | 100 → 100 | 0 → 0 ms | 0.031 → 0.031 |
| Backoffice — proveedores | Mobile | 97 → 98 | 180 → 120 ms (−60; −33.3%) | 0 → 0 |
| Website — talento | Desktop | 100 → 100 | 0 → 0 ms | 0 → 0 |
| Website — talento | Mobile | 97 → 100 | 200 → 80 ms (−120; −60%) | 0 → 0 |
| Website — portada | Desktop | 100 → 100 | 0 → 0 ms | 0 → 0 |
| Website — portada | Mobile | 100 → 100 | 70 → 70 ms (sin cambio) | 0 → 0 |

Las puntuaciones móviles suben en tres vistas y se mantienen en Website portada; el TBT baja en tres y se mantiene en esa portada. CLS móvil pasa a 0 en las cuatro. El LCP móvil se mantiene en Proveedores y Talento y cambia de 1.2 s a 1.3 s en Website portada.

## Valoración de impacto

El mayor impacto **de producto/robustez** es la validación uniforme de activos y el comportamiento común de error/reintento en las tres rutas; `SiteHeader` reduce duplicación visual en Website. La optimización de hidratación contribuye a la reducción de TBT móvil: de 240 a 140 ms en portada del Backoffice, de 180 a 120 ms en Proveedores y de 200 a 80 ms en Talento; Website portada se mantiene en 70 ms. El CLS queda en 0 en las cuatro vistas. TBT es una métrica de laboratorio complementaria, no un Core Web Vital; LCP y CLS permanecen bajo los umbrales de laboratorio de referencia.

Las capturas before/after están organizadas en `audit/before/` y `audit/after/`.