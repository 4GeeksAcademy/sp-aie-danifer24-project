# Informe técnico de evaluación — pronóstico de ventas Nexova

**Fecha:** 2026-11-10  
**Modelo evaluado:** Random Forest Regressor (500 árboles, `min_samples_leaf=2`, `max_features=0.8`, `random_state=42`)  
**Objetivo:** ingresos mensuales consolidados (`revenue_usd`)

## Dictamen

**Clasificación: sobreajuste / brecha de generalización (overfitting operativo).**

El modelo ajusta bastante mejor los datos de entrenamiento que los períodos posteriores. La brecha aparece en el holdout 2024–2025 y en los cinco folds de validación temporal. La curva de aprendizaje mejora al añadir historia, pero conserva una brecha importante en su mayor tamaño de entrenamiento.

Esto describe el comportamiento medido; no demuestra que la causa sea únicamente memorizar ruido. Una causa probable y concreta es el desajuste entre la dinámica de los ingresos —crecimiento positivo y estacionalidad— y un Random Forest de regresión, que no extrapola naturalmente una tendencia creciente más allá de los valores vistos en sus árboles. En el pronóstico recursivo, además, el modelo reutiliza sus propias predicciones en los lags, lo que puede acumular errores a lo largo del horizonte.

## Evidencia

### Holdout cronológico 2024–2025

Se entrenó con los primeros ocho años y se evaluó recursivamente en los últimos dos. Las ventas reales del holdout no se incorporaron a las features de meses posteriores.

| Partición | MAE | RMSE |
|---|---:|---:|
| Entrenamiento: 84 meses utilizables, 2017-01–2023-12 | 15.446,14 USD | 19.229,07 USD |
| Validación: 24 meses, 2024-01–2025-12 | 41.470,61 USD | 53.382,27 USD |

El RMSE de validación es aproximadamente **2,78 veces** el de entrenamiento; el MAE, aproximadamente **2,69 veces**. No es el patrón de errores bajos y cercanos que justificaría clasificar el modelo como bien ajustado.

### Validación cruzada temporal

Se usó `TimeSeriesSplit` con cinco folds expansivos y bloques cronológicos de validación de 14 meses. En cada fold, el entrenamiento termina antes de que empiece la validación. Las predicciones son recursivas: las ventas reales del bloque de validación no alimentan las features de pronósticos posteriores.

| Fold | Filas de entrenamiento / validación | RMSE entrenamiento | RMSE validación | MAE validación |
|---:|---:|---:|---:|---:|
| 1 | 14 / 14 | 36.728,11 USD | 56.113,05 USD | 41.435,47 USD |
| 2 | 28 / 14 | 24.281,43 USD | 50.682,56 USD | 38.118,00 USD |
| 3 | 42 / 14 | 20.793,65 USD | 57.537,95 USD | 46.436,01 USD |
| 4 | 56 / 14 | 18.586,78 USD | 46.442,97 USD | 37.686,92 USD |
| 5 | 70 / 14 | 18.189,33 USD | 70.394,71 USD | 63.521,29 USD |

El MSE de validación fue **3.228.075.522 ± 1.069.915.823 USD²** (media ± desviación estándar muestral). El RMSE de validación supera al de entrenamiento en los cinco folds y varía entre 46.442,97 y 70.394,71 USD. Esto evidencia una brecha persistente y sensibilidad al tramo temporal evaluado.

### Curva de aprendizaje

La curva usa una ventana fija de validación de 14 meses, 2022-11–2023-12, mientras amplía el prefijo cronológico de entrenamiento. La imagen correspondiente es `sales_forecast_learning_curve.png`.

Con 70 meses de entrenamiento, el RMSE es **18.189,33 USD** en entrenamiento y **70.394,71 USD** en validación: una brecha de aproximadamente **3,87 veces**. La validación mejora desde 182.427,25 USD con 14 meses hasta el último punto, por lo que disponer de más historia ayuda, pero no elimina la brecha. La mejora no es monótona en todos los puntos, algo posible al comparar segmentos temporales diferentes.

## Acción correctiva concreta

**Probar un modelo con tendencia extrapolable y estacionalidad mensual, y conservar el Random Forest solo como corrector de residuos si la validación demuestra que aporta valor.**

Experimento propuesto:

1. Ajustar una regresión con `time_index` y variables de calendario cíclicas (seno y coseno del mes), usando exclusivamente cada prefijo de entrenamiento.
2. Evaluar sus pronósticos recursivos en los mismos cinco folds y en el holdout, con las mismas fechas y controles contra fuga.
3. Comparar RMSE medio y desviación estándar entre folds, MAE y brecha entre entrenamiento y validación con el baseline Random Forest. Aceptar el cambio solo si reduce el error de validación sin empeorar materialmente su variabilidad.
4. Si persisten patrones no explicados, evaluar el Random Forest sobre los residuos de la tendencia, ajustando su complejidad dentro de esos mismos folds. No seleccionar el modelo mirando los resultados del holdout 2024–2025.

Esta acción responde a una causa específica: el contexto describe crecimiento anual positivo y estacionalidad recurrente, mientras que los árboles no prolongan por sí solos la tendencia fuera del rango observado. La regresión temporal modela explícitamente el crecimiento; las variables de calendario representan los patrones mensuales. El Random Forest sobre residuos puede capturar fluctuaciones restantes sin depender de los árboles para extrapolar el nivel futuro.

## Alcance y cautelas

- El contexto señala que una sobreestimación puede influir en compromisos presupuestarios, pero no cuantifica un costo distinto para sobreestimar frente a subestimar. MAE y RMSE penalizan ambos sentidos; RMSE da más peso a los errores grandes, pero no es una función de costo unilateral.
- El CSV provisto contiene la fila `consolidated`; por tanto, el PSI calculado describe el cambio en la distribución de ingresos consolidados, no el mix entre headhunting, outsourcing y formación.
- La banda P5–P95 entre árboles representa dispersión del ensemble, no un intervalo de predicción calibrado.
- Estos resultados evalúan el dataset proporcionado; no garantizan por sí solos el desempeño con ingresos reales futuros.