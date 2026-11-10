"""Prepare Nexova monthly revenue data for leakage-safe forecasting."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler

TARGET = "revenue_usd"
REQUIRED_COLUMNS = {"month", TARGET, "business_line"}


def load_sales_data(path: str | Path) -> pd.DataFrame:
    """Load consolidated sales and normalize dates/target values.

    Empty strings and common textual null markers are parsed as missing values.
    Rows without a usable month are discarded; missing or non-positive revenue
    remains missing so it cannot silently become a training/evaluation label.
    """
    frame = pd.read_csv(
        path,
        skipinitialspace=True,
        na_values=["", " ", "NA", "N/A", "null", "None"],
    )
    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"Sales dataset is missing required columns: {sorted(missing)}")

    frame = frame.loc[frame["business_line"].astype("string").str.strip().eq("consolidated")].copy()
    frame["month"] = pd.to_datetime(frame["month"], errors="coerce")
    frame = frame.dropna(subset=["month"])
    frame["month"] = frame["month"].dt.to_period("M").dt.to_timestamp()
    frame[TARGET] = pd.to_numeric(frame[TARGET], errors="coerce")
    frame.loc[frame[TARGET] <= 0, TARGET] = float("nan")

    if frame["month"].duplicated().any():
        duplicates = frame.loc[frame["month"].duplicated(), "month"].dt.strftime("%Y-%m").tolist()
        raise ValueError(f"Dataset has duplicate consolidated months: {duplicates}")

    frame = frame.set_index("month").sort_index()
    if frame.empty:
        raise ValueError("Dataset contains no valid consolidated monthly records")

    # Reindex the monthly calendar so absent months are explicitly missing.
    # Revenue is forward-filled only for historical lag construction (causal);
    # the original target stays missing and those rows are not scored/trained.
    monthly_index = pd.date_range(frame.index.min(), frame.index.max(), freq="MS")
    frame = frame.reindex(monthly_index)
    frame.index.name = "month"
    return frame


def build_forecasting_features(sales: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Build calendar and past-only revenue features without future leakage."""
    if TARGET not in sales.columns:
        raise ValueError(f"Sales frame must contain {TARGET!r}")
    if not isinstance(sales.index, pd.DatetimeIndex):
        raise ValueError("Sales frame must be indexed by monthly timestamps")

    target = pd.to_numeric(sales[TARGET], errors="coerce").rename(TARGET)
    history = target.ffill()  # causal imputation for lag inputs only
    month_number = sales.index.month
    features = pd.DataFrame(index=sales.index)
    features["month_sin"] = [math.sin(2 * math.pi * month / 12) for month in month_number]
    features["month_cos"] = [math.cos(2 * math.pi * month / 12) for month in month_number]
    features["time_index"] = range(len(sales))
    features["revenue_lag_1"] = history.shift(1)
    features["revenue_lag_12"] = history.shift(12)
    features["revenue_rolling_mean_3"] = history.shift(1).rolling(3, min_periods=3).mean()
    features["revenue_rolling_mean_12"] = history.shift(1).rolling(12, min_periods=12).mean()
    return features, target


def split_first_eight_years(
    features: pd.DataFrame,
    target: pd.Series,
    train_years: int = 8,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    """Split chronologically at the start of year nine, excluding unusable rows.

    The test period is determined from the first month in the full dataset;
    no test observations are used to fit preprocessing or the model.
    """
    if features.empty or target.empty:
        raise ValueError("Cannot split an empty sales dataset")
    if not features.index.equals(target.index):
        raise ValueError("Features and target must have matching monthly indexes")
    if train_years < 1:
        raise ValueError("train_years must be at least 1")

    first_month = features.index.min()
    boundary = first_month + pd.DateOffset(years=train_years)
    usable = features.notna().all(axis=1) & target.notna() & target.gt(0)
    train_mask = usable & (features.index < boundary)
    test_mask = usable & (features.index >= boundary)

    if not train_mask.any() or not test_mask.any():
        raise ValueError("Not enough usable observations in both temporal partitions")

    return (
        features.loc[train_mask].copy(),
        target.loc[train_mask].copy(),
        features.loc[test_mask].copy(),
        target.loc[test_mask].copy(),
    )


def scale_feature_partitions(
    x_train: pd.DataFrame,
    x_test: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, StandardScaler]:
    """Standardize features using training statistics only.

    Random Forest is tree-based and does not require scaling for correctness;
    this helper is provided for scale-sensitive model comparisons and ensures
    any scaler is never fitted on the held-out period.
    """
    if list(x_train.columns) != list(x_test.columns):
        raise ValueError("Training and test features must have identical columns")
    if x_train.empty or x_test.empty:
        raise ValueError("Both training and test features must be non-empty")

    scaler = StandardScaler()
    scaled_train = pd.DataFrame(
        scaler.fit_transform(x_train), index=x_train.index, columns=x_train.columns
    )
    scaled_test = pd.DataFrame(
        scaler.transform(x_test), index=x_test.index, columns=x_test.columns
    )
    return scaled_train, scaled_test, scaler


def recursive_forest_forecast(
    model: RandomForestRegressor,
    train_history: pd.Series,
    test_features: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray]:
    """Forecast a holdout recursively so actual holdout revenue is never a lag."""
    history = pd.to_numeric(train_history, errors="coerce").ffill().dropna().astype(float)
    if history.empty or test_features.empty:
        raise ValueError("Training history and test features must be non-empty")

    tree_predictions: list[np.ndarray] = []
    for timestamp, calendar_features in test_features.iterrows():
        row = calendar_features.copy()
        row["revenue_lag_1"] = history.iloc[-1]
        row["revenue_lag_12"] = history.iloc[-12] if len(history) >= 12 else history.iloc[0]
        row["revenue_rolling_mean_3"] = history.tail(3).mean()
        row["revenue_rolling_mean_12"] = history.tail(12).mean()
        values = row.to_numpy(dtype=float).reshape(1, -1)
        per_tree = np.asarray([tree.predict(values)[0] for tree in model.estimators_])
        tree_predictions.append(per_tree)
        # Append the ensemble forecast, not the (held-out) actual target.
        history.loc[timestamp] = float(per_tree.mean())

    predictions_by_tree = np.vstack(tree_predictions)
    return predictions_by_tree.mean(axis=1), predictions_by_tree


def calculate_error_metrics(
    actual_values: pd.Series | np.ndarray,
    predictions: pd.Series | np.ndarray,
) -> dict[str, float]:
    """Return dollar-interpretable MAE and RMSE for one evaluation partition."""
    actual = np.asarray(actual_values, dtype=float)
    predicted = np.asarray(predictions, dtype=float)
    if len(actual) != len(predicted) or len(actual) == 0:
        raise ValueError("Predictions must match a non-empty target")
    if not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise ValueError("Targets and predictions must be finite")
    return {
        "mae_usd": float(np.mean(np.abs(actual - predicted))),
        "rmse_usd": float(np.sqrt(mean_squared_error(actual, predicted))),
    }


def calculate_metrics(
    y_train: pd.Series,
    y_test: pd.Series,
    predictions: np.ndarray,
    bins: int = 10,
) -> dict[str, float]:
    """Calculate test MSE, target-distribution PSI, ranking Gini and K².

    The provided dataset contains only consolidated revenue, so PSI measures
    train-to-test revenue distribution shift (not business-line mix shift).
    Gini is 2*AUC-1 for ranking above/below the test-median revenue; K² is
    squared Pearson correlation of actual and predicted test revenue. These
    definitions keep the requested scores interpretable for regression.
    """
    actual = np.asarray(y_test, dtype=float)
    predicted = np.asarray(predictions, dtype=float)
    train_values = np.asarray(y_train, dtype=float)
    if len(actual) != len(predicted) or len(actual) == 0:
        raise ValueError("Predictions must match a non-empty test target")
    if not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise ValueError("Targets and predictions must be finite")

    # Training quantiles define fixed buckets, avoiding test-informed bin edges.
    edges = np.unique(np.quantile(train_values, np.linspace(0, 1, bins + 1)))
    if len(edges) < 2:
        psi = 0.0
    else:
        edges[0] = -np.inf
        edges[-1] = np.inf
        train_counts, _ = np.histogram(train_values, bins=edges)
        test_counts, _ = np.histogram(actual, bins=edges)
        train_share = np.clip(train_counts / train_counts.sum(), 1e-6, None)
        test_share = np.clip(test_counts / test_counts.sum(), 1e-6, None)
        psi = float(np.sum((test_share - train_share) * np.log(test_share / train_share)))

    high_revenue = actual >= np.median(actual)
    gini = (
        float(2 * roc_auc_score(high_revenue, predicted) - 1)
        if np.unique(high_revenue).size == 2
        else float("nan")
    )
    if len(actual) > 1 and np.std(actual) > 0 and np.std(predicted) > 0:
        k2 = float(np.corrcoef(actual, predicted)[0, 1] ** 2)
    else:
        k2 = float("nan")

    mse = float(mean_squared_error(actual, predicted))
    mean_revenue = float(np.mean(actual))
    error_metrics = calculate_error_metrics(actual, predicted)
    return {
        **error_metrics,
        "mse_usd2": mse,
        "mse_pct_of_mean_revenue": float(100 * mse / (mean_revenue**2)) if mean_revenue else float("nan"),
        "psi_revenue_distribution": psi,
        "gini_high_revenue_ranking": gini,
        "k2_squared_correlation": k2,
        "mae_usd": float(np.mean(np.abs(actual - predicted))),
    }


def make_forest_model() -> RandomForestRegressor:
    """Create the fixed Random Forest baseline used by every evaluation fold."""
    return RandomForestRegressor(
        n_estimators=500,
        min_samples_leaf=2,
        max_features=0.8,
        random_state=42,
        n_jobs=-1,
    )


def temporal_cross_validation(
    x_train: pd.DataFrame,
    y_train: pd.Series,
    n_splits: int = 5,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """Evaluate sequential forecast folds, recursively forecasting each horizon.

    The train indices in each TimeSeriesSplit fold are a chronological prefix;
    validation is the immediately following contiguous block. All revenue-based
    validation features are recomputed from that fold's training observations
    and its own earlier predictions by ``recursive_forest_forecast``. Thus the
    prebuilt shifted/rolling columns never expose validation actuals, while the
    fold's training history remains available as legitimate prior context.
    """
    if not x_train.index.equals(y_train.index):
        raise ValueError("Training features and target must have matching indexes")
    if not x_train.index.is_monotonic_increasing:
        raise ValueError("Training observations must be sorted chronologically")
    if n_splits < 2 or len(x_train) <= n_splits:
        raise ValueError("Not enough training rows for the requested temporal folds")

    splitter = TimeSeriesSplit(n_splits=n_splits)
    fold_results: list[dict[str, Any]] = []

    for fold_number, (train_positions, validation_positions) in enumerate(
        splitter.split(x_train), start=1
    ):
        # Explicitly enforce temporal order and no overlap; never shuffle.
        if train_positions.max() >= validation_positions.min():
            raise AssertionError(f"Fold {fold_number} mixes train and validation order")
        fold_x_train = x_train.iloc[train_positions]
        fold_y_train = y_train.iloc[train_positions]
        fold_x_validation = x_train.iloc[validation_positions]
        fold_y_validation = y_train.iloc[validation_positions]
        if fold_x_train.index.max() >= fold_x_validation.index.min():
            raise AssertionError(f"Fold {fold_number} is not strictly chronological")

        model = make_forest_model()
        model.fit(fold_x_train, fold_y_train)
        # Only actual history through the fold's train end is passed in. The
        # recursive forecaster appends its predictions, not validation labels.
        fold_history = y_train.loc[:fold_y_train.index.max()]
        predictions, _ = recursive_forest_forecast(
            model, fold_history, fold_x_validation
        )
        train_predictions = model.predict(fold_x_train)
        fold_train_errors = calculate_error_metrics(fold_y_train, train_predictions)
        fold_validation_errors = calculate_error_metrics(fold_y_validation, predictions)
        fold_mse = float(mean_squared_error(fold_y_validation, predictions))
        fold_results.append(
            {
                "fold": fold_number,
                "train_start": fold_x_train.index.min(),
                "train_end": fold_x_train.index.max(),
                "validation_start": fold_x_validation.index.min(),
                "validation_end": fold_x_validation.index.max(),
                "train_rows": len(fold_x_train),
                "validation_rows": len(fold_x_validation),
                "train_mae_usd": fold_train_errors["mae_usd"],
                "train_rmse_usd": fold_train_errors["rmse_usd"],
                "validation_mae_usd": fold_validation_errors["mae_usd"],
                "validation_rmse_usd": fold_validation_errors["rmse_usd"],
                "predictions": pd.Series(
                    predictions, index=fold_y_validation.index, name="prediction"
                ),
                "mse_usd2": fold_mse,
            }
        )

    mse_values = np.asarray([fold["mse_usd2"] for fold in fold_results])
    summary = {
        "mse_usd2_mean": float(mse_values.mean()),
        "mse_usd2_std": float(mse_values.std(ddof=1)),
        "folds": float(n_splits),
    }
    return fold_results, summary


def generate_learning_curve(
    x_train: pd.DataFrame,
    y_train: pd.Series,
    output_path: str | Path,
    validation_size: int = 14,
    min_train_size: int = 14,
    step: int = 7,
) -> dict[str, Any]:
    """Plot train/validation MSE as a chronological training prefix grows.

    The most recent ``validation_size`` training observations form one fixed,
    contiguous validation horizon. All candidate training prefixes end before
    it. Validation predictions are rolled forward recursively so actual
    validation revenues never enter lag/rolling features.
    """
    if not x_train.index.equals(y_train.index):
        raise ValueError("Training features and target must have matching indexes")
    if not x_train.index.is_monotonic_increasing:
        raise ValueError("Training observations must be sorted chronologically")
    if validation_size < 1 or step < 1 or min_train_size < 1:
        raise ValueError("validation_size, min_train_size, and step must be positive")
    max_train_size = len(x_train) - validation_size
    if max_train_size < min_train_size:
        raise ValueError("Not enough rows for the learning curve train/validation split")

    validation_x = x_train.iloc[-validation_size:]
    validation_y = y_train.iloc[-validation_size:]
    sizes = list(range(min_train_size, max_train_size + 1, step))
    if sizes[-1] != max_train_size:
        sizes.append(max_train_size)

    points: list[dict[str, float | int]] = []
    for size in sizes:
        prefix_x = x_train.iloc[:size]
        prefix_y = y_train.iloc[:size]
        if prefix_x.index.max() >= validation_x.index.min():
            raise AssertionError("Learning-curve train prefix overlaps validation period")
        model = make_forest_model()
        model.fit(prefix_x, prefix_y)
        train_predictions = model.predict(prefix_x)
        train_error_metrics = calculate_error_metrics(prefix_y, train_predictions)
        validation_predictions, _ = recursive_forest_forecast(
            model, prefix_y, validation_x
        )
        validation_error_metrics = calculate_error_metrics(
            validation_y, validation_predictions
        )
        points.append(
            {
                "train_size": size,
                "train_mae_usd": train_error_metrics["mae_usd"],
                "train_rmse_usd": train_error_metrics["rmse_usd"],
                "validation_mae_usd": validation_error_metrics["mae_usd"],
                "validation_rmse_usd": validation_error_metrics["rmse_usd"],
            }
        )

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 6))
    sizes_array = [point["train_size"] for point in points]
    ax.plot(sizes_array, [point["train_mae_usd"] for point in points],
            marker="o", label="MAE entrenamiento")
    ax.plot(sizes_array, [point["validation_mae_usd"] for point in points],
            marker="o", label="MAE validación")
    ax.plot(sizes_array, [point["train_rmse_usd"] for point in points],
            marker="s", linestyle="--", label="RMSE entrenamiento")
    ax.plot(sizes_array, [point["validation_rmse_usd"] for point in points],
            marker="s", linestyle="--", label="RMSE validación")
    ax.set(
        title="Curva de aprendizaje — pronóstico de ingresos Nexova",
        xlabel="Tamaño del conjunto de entrenamiento (meses)",
        ylabel="Error (USD)",
    )
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(destination, dpi=160)
    plt.close(fig)
    return {
        "points": points,
        "validation_period": (validation_x.index.min(), validation_x.index.max()),
        "plot_path": destination,
    }


def train_and_evaluate(
    csv_path: str | Path,
    output_path: str | Path = "reports/sales_forecast.png",
    cv_splits: int = 5,
    learning_curve_path: str | Path = "data/eval/sales_forecast_learning_curve.png",
) -> dict[str, Any]:
    """Train, evaluate, and plot a leakage-safe chronological sales forecast."""
    sales = load_sales_data(csv_path)
    features, target = build_forecasting_features(sales)
    x_train, y_train, x_test, y_test = split_first_eight_years(features, target)

    # Use only the first eight years for model selection. Each fold is a
    # chronological expanding-window split with a recursive holdout forecast.
    cv_folds, cv_summary = temporal_cross_validation(x_train, y_train, n_splits=cv_splits)
    learning_curve = generate_learning_curve(
        x_train, y_train, learning_curve_path
    )

    # With only 96 raw training months (84 after the 12-month lag warm-up), a
    # Random Forest is a practical low-tuning baseline. Its ensemble averages
    # many trees; XGBoost's sequential boosting would require more tuning time.
    model = make_forest_model()
    model.fit(x_train, y_train)
    # Roll the 24-month holdout forward recursively: after the first test month,
    # lag features use prior forecasts rather than actual holdout observations.
    train_history = target.loc[:x_train.index.max()]
    predictions, tree_predictions = recursive_forest_forecast(model, train_history, x_test)
    train_predictions = model.predict(x_train)
    train_error_metrics = calculate_error_metrics(y_train, train_predictions)
    validation_error_metrics = calculate_error_metrics(y_test, predictions)

    # Tree-to-tree quantiles visualize model spread. This is an empirical
    # ensemble variability band, not a calibrated statistical prediction interval.
    lower = np.percentile(tree_predictions, 5, axis=1)
    upper = np.percentile(tree_predictions, 95, axis=1)
    metrics = calculate_metrics(y_train, y_test, predictions)

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(y_test.index, y_test.values, marker="o", label="Ingresos reales", color="#243b53")
    ax.plot(y_test.index, predictions, marker="o", label="Random Forest", color="#147d92")
    ax.fill_between(y_test.index, lower, upper, color="#49a6a6", alpha=0.22,
                    label="Variabilidad entre árboles (P5–P95)")
    ax.set(title="Pronóstico de ventas: prueba 2024–2025", xlabel="Mes", ylabel="Ingresos (USD)")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(destination, dpi=160)
    plt.close(fig)

    return {
        "model": model,
        "metrics": metrics,
        "train_error_metrics": train_error_metrics,
        "validation_error_metrics": validation_error_metrics,
        "cv_folds": cv_folds,
        "cv_summary": cv_summary,
        "learning_curve": learning_curve,
        "predictions": pd.Series(predictions, index=y_test.index, name="prediction"),
        "lower": pd.Series(lower, index=y_test.index, name="p05_tree"),
        "upper": pd.Series(upper, index=y_test.index, name="p95_tree"),
        "train_period": (x_train.index.min(), x_train.index.max()),
        "test_period": (x_test.index.min(), x_test.index.max()),
        "train_rows": len(x_train),
        "test_rows": len(x_test),
        "plot_path": destination,
    }


def main() -> None:
    """Run the forecast using repository defaults and report test metrics."""
    root = Path(__file__).resolve().parents[1]
    result = train_and_evaluate(root / "data/raw/nexova_sales.csv", root / "reports/sales_forecast.png")
    print(f"Train: {result['train_period'][0]:%Y-%m}–{result['train_period'][1]:%Y-%m} "
          f"({result['train_rows']} usable months)")
    print(f"Test:  {result['test_period'][0]:%Y-%m}–{result['test_period'][1]:%Y-%m} "
          f"({result['test_rows']} months)")
    print("Temporal CV (expanding window, recursive one-step rollout per fold):")
    for fold in result["cv_folds"]:
        print(
            f"  Fold {fold['fold']}: train {fold['train_start']:%Y-%m}–{fold['train_end']:%Y-%m} "
            f"({fold['train_rows']}), validation "
            f"{fold['validation_start']:%Y-%m}–{fold['validation_end']:%Y-%m} "
            f"({fold['validation_rows']}), MSE={fold['mse_usd2']:,.2f} USD²"
        )
    cv = result["cv_summary"]
    print(f"CV MSE: {cv['mse_usd2_mean']:,.2f} ± {cv['mse_usd2_std']:,.2f} USD² "
          f"(mean ± sample SD, {int(cv['folds'])} folds)")
    print("MAE/RMSE (entrenamiento vs. validación 2024–2025):")
    for label, error_metrics in (
        ("Entrenamiento", result["train_error_metrics"]),
        ("Validación", result["validation_error_metrics"]),
    ):
        print(
            f"  {label}: MAE={error_metrics['mae_usd']:,.2f} USD; "
            f"RMSE={error_metrics['rmse_usd']:,.2f} USD"
        )
    print("Métricas adicionales de prueba:")
    for name, value in result["metrics"].items():
        print(f"{name}: {value:,.6f}")
    print(f"Forecast visualization: {result['plot_path']}")
    curve = result["learning_curve"]
    print(f"Learning curve validation: {curve['validation_period'][0]:%Y-%m}–"
          f"{curve['validation_period'][1]:%Y-%m}")
    print(f"Learning curve: {curve['plot_path']}")
    print(
        "Métrica orientada a negocio: RMSE, porque castiga cuadráticamente los "
        "errores grandes; una sobreestimación importante puede inducir compromisos "
        "de presupuesto que los ingresos reales no cubran. MAE se conserva como "
        "referencia robusta del error absoluto típico."
    )


if __name__ == "__main__":
    main()
