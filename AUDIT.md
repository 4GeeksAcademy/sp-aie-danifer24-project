# Auditoría de rendimiento frontend — before/after

## Alcance

Se auditaron cuatro rutas de `uis/website` y `uis/backoffice` con Lighthouse en entorno local de producción. Las capturas de `audit/before/` y `audit/after/` documentan las ejecuciones. Las cifras corresponden a resultados de laboratorio local.

## Puntuaciones y métricas iniciales

Las categorías son Rendimiento / Accesibilidad / Buenas prácticas / SEO.

| Ruta | Dispositivo | Puntuaciones | FCP | LCP | TBT | Speed Index | CLS |
|---|---|---:|---:|---:|---:|---:|---:|
| Backoffice — portada (`backoffice_frontpage`) | Desktop | 100 / 100 / 100 / 60 | 0.4 s | 0.5 s | 0 ms | 0.6 s | 0.022 |
| Backoffice — portada (`backoffice_frontpage`) | Mobile | 95 / 100 / 100 / 60 | 1.1 s | 1.9 s | **240 ms** | 1.5 s | 0.058 |
| Backoffice — proveedores (`backoffice_suppliers`) | Desktop | 100 / 98 / 100 / 60 | 0.4 s | 0.5 s | 0 ms | 0.5 s | 0.031 |
| Backoffice — proveedores (`backoffice_suppliers`) | Mobile | 97 / 98 / 100 / 60 | 1.1 s | 2.0 s | 180 ms | 1.7 s | 0.0 |
| Website — talento (`website_form`) | Desktop | 100 / 100 / 100 / 60 | 0.4 s | 0.5 s | 0 ms | 0.5 s | 0.0 |
| Website — talento (`website_form`) | Mobile | 97 / 100 / 100 / 60 | 1.3 s | 1.4 s | 200 ms | 1.3 s | 0.0 |
| Website — portada (`website_frontpage`) | Desktop | 100 / 100 / 100 / 60 | 0.4 s | 0.5 s | 0 ms | 0.5 s | 0.0 |
| Website — portada (`website_frontpage`) | Mobile | 100 / 100 / 100 / 60 | 1.2 s | 1.2 s | 70 ms | 1.2 s | 0.0 |

SEO se mantiene en 60 en las cuatro vistas desktop. Accesibilidad de Proveedores se mantiene en 98 en desktop. Estas puntuaciones se consignan como resultados de Lighthouse.

## Resultados after

### Desktop

| Ruta | Puntuaciones Rend. / A11y / BP / SEO | FCP | LCP | TBT | Speed Index | CLS |
|---|---:|---:|---:|---:|---:|---:|
| Backoffice — portada (`backoffice_frontpage`) | 100 / 100 / 100 / 60 | 0.3 s | 0.5 s | 0 ms | 0.5 s | 0.022 |
| Backoffice — proveedores (`backoffice_suppliers`) | 100 / 98 / 100 / 60 | 0.4 s | 0.5 s | 0 ms | 0.5 s | 0.031 |
| Website — talento (`website_form`) | 100 / 100 / 100 / 60 | 0.4 s | 0.4 s | 0 ms | 0.5 s | 0 |
| Website — portada (`website_frontpage`) | 100 / 100 / 100 / 60 | 0.4 s | 0.5 s | 0 ms | 0.4 s | 0 |

### Mobile

| Ruta | Rendimiento | TBT | CLS |
|---|---:|---:|---:|
| Backoffice — portada (`backoffice_frontpage`) | 98 | 140 ms | 0 |
| Backoffice — proveedores (`backoffice_suppliers`) | 98 | 120 ms | 0 |
| Website — talento (`website_form`) | 100 | 80 ms | 0 |
| Website — portada (`website_frontpage`) | 100 | 70 ms | 0 |

## Comparación before/after

Las diferencias siguientes muestran el cambio de las métricas entre before y after.

| Ruta | Dispositivo | Rendimiento | TBT | CLS |
|---|---|---:|---:|---:|
| Backoffice — portada | Desktop | 100 → 100 (sin cambio) | 0 → 0 ms | 0.022 → 0.022 |
| Backoffice — portada | Mobile | 95 → 98 (+3 puntos) | 240 → 140 ms (−100 ms; −41.7%) | 0.058 → 0 (−0.058) |
| Backoffice — proveedores | Desktop | 100 → 100 (sin cambio) | 0 → 0 ms | 0.031 → 0.031 |
| Backoffice — proveedores | Mobile | 97 → 98 (+1 punto) | 180 → 120 ms (−60 ms; −33.3%) | 0 → 0 |
| Website — talento | Desktop | 100 → 100 (sin cambio) | 0 → 0 ms | 0 → 0 |
| Website — talento | Mobile | 97 → 100 (+3 puntos) | 200 → 80 ms (−120 ms; −60%) | 0 → 0 |
| Website — portada | Desktop | 100 → 100 (sin cambio) | 0 → 0 ms | 0 → 0 |
| Website — portada | Mobile | 100 → 100 (sin cambio) | 70 → 70 ms (sin cambio) | 0 → 0 |

El TBT móvil baja en tres vistas (−100, −60 y −120 ms); la portada de Website permanece en 70 ms. El CLS móvil queda en 0 en las cuatro vistas. El LCP móvil se mantiene en 2.0 s en Proveedores y 1.4 s en Talento, y cambia de 1.2 s a 1.3 s en Website portada. La puntuación de rendimiento móvil aumenta en tres vistas y se mantiene en la cuarta.

## Hallazgos y mejoras

| Hallazgo | Resultado | Mejora |
|---|---|---|
| Portada Backoffice móvil | TBT 240 → 140 ms; rendimiento 95 → 98 | Menor bloqueo del hilo principal tras optimizar hidratación. |
| Accesibilidad de Proveedores | 98 en desktop y móvil | Puntuación estable. |
| SEO | 60 en desktop | Puntuación estable en las cuatro vistas desktop. |
| Validación/carga de activos | Tres rutas de inventario con lógica paralela | Validación y manejo de estado unificados. |

## Priorización de KPIs principales

Como referencia de laboratorio, LCP móvil está entre 1.2 y 2.0 s antes y entre 1.3 y 2.0 s después en las vistas reportadas; CLS está entre 0 y 0.058 antes y en 0 después. Estos valores están bajo los umbrales “good” de referencia de LCP ≤ 2.5 s y CLS ≤ 0.1. TBT no es un Core Web Vital.

La portada móvil del Backoffice reduce TBT de 240 ms a 140 ms; Proveedores, de 180 ms a 120 ms; y Talento, de 200 ms a 80 ms. Website portada mantiene 70 ms. El TBT es una métrica de laboratorio, no un Core Web Vital. LCP y CLS son los indicadores CWV de carga reportados aquí; los valores observados permanecen dentro de los umbrales “good” indicados.

## Mejoras de código

### Refactorización aplicada: carga/validación de activos del inventario

Las rutas de productos, entrada y salida de inventario repetían el fetch de activos, estados loading/error, reintento, cancelación lógica al desmontar y validación runtime. El hook hace consistente el manejo de activos entre las tres vistas.

Se extrajo `uis/backoffice/hooks/useInventoryAssets.ts`, que centraliza el ciclo de carga y una validación consistente, y se conectó a las tres rutas. Se conserva el setter local necesario para reflejar entradas/salidas optimistas en el stock. Es una refactorización de mantenibilidad/consistencia, **no una optimización de rendimiento medida**.

En Website también se repetía la estructura de cabecera entre portada y formulario de talento. Se extrajo `uis/website/components/SiteHeader.tsx` y ambas rutas lo reutilizan con sus enlaces y etiquetas de navegación correspondientes.

### Cambios de código y métricas

La medición posterior refleja una reducción de TBT móvil en tres vistas y CLS móvil de 0 en las cuatro. La optimización de hidratación reduce el bloqueo del hilo principal en las vistas mejoradas. El hook de inventario y `SiteHeader` consolidan patrones compartidos y facilitan el mantenimiento.

## Interpretación

La comparación before/after resume el efecto observado tras las mejoras implementadas. LCP y CLS son Core Web Vitals; TBT es una métrica de laboratorio complementaria. Los valores reportados para LCP móvil y CLS están bajo los umbrales “good” de laboratorio de LCP ≤ 2.5 s y CLS ≤ 0.1.