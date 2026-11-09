# Nexova monthly sales forecast

Run from the repository root with the project environment:

```bash
uv run python scripts/sales_forecast.py
```

The script reads `data/raw/nexova_sales.csv`, trains on the first eight calendar
years (2016–2023), recursively forecasts and evaluates only on the two most recent years (2024–2025),
prints test metrics, and saves `reports/sales_forecast.png`. One year of early
history is used to warm up the 12-month lag features, so the first model-fit
month is January 2017. Test targets are never used to fit the model; during the
24-month holdout, previous forecasts (not actual test revenue) feed each next
month's lag and rolling features.

## Model choice

The dataset has only 96 raw training months (84 rows remain after lag warm-up).
Random Forest is a reasonable low-tuning baseline for this small dataset: it
averages many trees, supports a straightforward feature-importance explanation,
and can be evaluated quickly. XGBoost may improve accuracy, but its sequential
boosting and hyperparameter tuning add complexity that is not justified before
we establish a reliable held-out baseline. Random Forest is scale-insensitive,
so feature standardization is not needed for this model.

## Metrics and interpretation

All scores below are calculated on the untouched 2024–2025 test set:

- **MSE (USD²):** mean squared dollar error; it penalizes large misses heavily.
  The script also prints MSE as a percentage of squared mean monthly revenue.
- **PSI:** Population Stability Index comparing train and test revenue
  distributions using training-defined quantile buckets. Common rules of thumb
  are `<0.10` little shift, `0.10–0.25` moderate shift, and `>0.25` substantial
  shift. The CSV only has consolidated rows, so this cannot assess business-line
  mix PSI.
- **Gini:** `2 × AUC − 1`, where the test months are ranked as above/below the
  test-period median. It measures whether the model ranks higher-revenue months
  above lower-revenue months; it is not a magnitude-error metric.
- **K² Score:** squared Pearson correlation between actual and predicted test
  revenue. It measures co-movement, not agreement in dollar scale, and can be
  high even when predictions are systematically biased.
- **MAE (USD):** mean absolute dollar error, included as a direct business
  interpretation of the typical absolute miss.

A low MSE alone is not evidence of a dependable forecast: it is scale-dependent,
can hide bias or poor seasonal ranking, and may be misleading if measured on data
used during fitting. Read it alongside MAE, Gini, K², PSI and the chronological
holdout plot. None of these metrics by itself establishes an acceptable business
error threshold; Finance should define that threshold before a dashboard promise.

## Variability plot

The shaded P5–P95 band is the 5th–95th percentile of predictions from individual
forest trees. It visualizes ensemble disagreement, **not a calibrated 90%
prediction interval**; it does not include all measurement, model, or future
process uncertainty.