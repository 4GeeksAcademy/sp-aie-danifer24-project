# Informe de caching

## Objetivo y estado

Este informe registra la línea base anterior a implementar caching para `GET /inventory/products`. A fecha de 2026-11-02 no se ha implementado una caché; estas cifras corresponden al comportamiento sin caché.

## Medición antes del seed y sin caché

La medición se realizó contra la API de prueba en `http://127.0.0.1:8001`, conectada a PostgreSQL 16 local (`nexova_test` en el puerto 5433). La base estaba vacía. Se hicieron 20 solicitudes secuenciales a `GET /inventory/products`; todas devolvieron HTTP 200. Los tiempos se midieron desde el cliente e incluyen el transporte local y el procesamiento de la API.

| Métrica | Tiempo |
| --- | ---: |
| Mínimo | 1.9 ms |
| Mediana | 2.8 ms |
| Media | 7.3 ms |
| p95 | 7.9 ms |
| Máximo | 87.6 ms |

Filas antes del seed: 0 activos, 0 entradas y 0 salidas.

## Seed y medición posterior, todavía sin caché

Se ejecutó `services/api/seed_performance.py` únicamente contra la base local `nexova_test`. Insertó 1.000 activos, 3.000 entradas y 2.000 salidas. Se repitieron 20 solicitudes secuenciales al mismo endpoint; todas devolvieron HTTP 200.

| Métrica | Antes del seed | Después del seed |
| --- | ---: | ---: |
| Mínimo | 1.9 ms | 938.7 ms |
| Mediana | 2.8 ms | 992.8 ms |
| Media | 7.3 ms | 999.0 ms |
| p95 | 7.9 ms | 1,046.3 ms |
| Máximo | 87.6 ms | 1,047.0 ms |

Filas después del seed: 1.000 activos, 3.000 entradas y 2.000 salidas. La mediana creció aproximadamente 355 veces en este entorno. La muestra pre-seed era una base vacía y el máximo de 87.6 ms refleja ruido de arranque; por tanto, la razón entre medianas es orientativa, no una comparación de producción.

`GET /inventory/products` calcula el stock por activo consultando las sumas de entradas y salidas. Con 1.000 activos, la latencia cercana a un segundo lo convierte en un candidato de optimización. Antes de decidir caching y TTL, hay que considerar que el stock cambia con las operaciones de entrada y salida; una respuesta obsoleta no debe afectar a las comprobaciones de stock ni a la creación de pedidos.

Como comprobación exploratoria separada, la API configurada con la base remota existente respondió 20 veces con HTTP 200: 6 activos, 5 entradas y 4 salidas; media 194.1 ms y mediana 192.2 ms. No se modificó Supabase. Esa muestra no es comparable con las cifras locales por la diferencia de entorno y datos.

## Optimizaciones frontend

El foco es `uis/backoffice`, la interfaz Next.js que consume el inventario y el directorio de proveedores. Estas decisiones se basan en inspección estática del flujo; no se ha medido todavía la diferencia de bytes del bundle ni una traza de navegador antes/después.

| Candidato | Decisión y justificación |
| --- | --- |
| `CreateSupplierDialog` en `/suppliers` | Cargado con `next/dynamic` al pulsar «Nuevo proveedor». El formulario completo, sus campos opcionales y validaciones no se necesitan para consultar el listado y solo se usan en el flujo de alta. |
| `EditRateDialog` en `/suppliers` | Cargado con `next/dynamic` al pulsar la acción de editar tarifa. Es un diálogo separado y ocasional; diferirlo evita incluirlo en la carga inicial del directorio. Ambos diálogos muestran un estado de carga accesible durante la descarga del chunk. |
| Resumen de `/inventory/products` | `totalUnits` y `lowStockCount` recorren todos los activos. Se combinaron en una sola reducción `O(n)` dentro de `useMemo` con dependencia `[assets]`; cambiar el texto de búsqueda ya no repite ese trabajo. La lista filtrada conserva su memoización existente `[assets, search]`. |

Las dos oportunidades de lazy loading son componentes de interacción bajo demanda, no páginas completas que Next ya separa automáticamente por ruta. `useMemo` se limita al agregado lineal sobre el inventario; los cálculos triviales no se memoizaron.

## Próximos pasos

1. Analizar una optimización de consulta (agregación por lote) frente a una caché; el endpoint ejecuta agregaciones por activo y la medición local ya muestra un coste alto.
2. Si se implementa caché de listado, definir un TTL explícito y una estrategia de invalidación al crear entradas, salidas o productos.
3. Mantener sin caché las lecturas usadas para validar stock en operaciones de salida, salvo que se garantice consistencia suficiente.
4. Repetir las mismas 20 solicitudes tras cualquier optimización y documentar el resultado, el TTL y las implicaciones de frescura.
