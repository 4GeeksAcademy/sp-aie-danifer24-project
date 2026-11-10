import numpy as np
import pandas as pd

from scripts.sales_forecast import (
    TARGET,
    build_forecasting_features,
    generate_learning_curve,
    split_first_eight_years,
)


def training_partition() -> tuple[pd.DataFrame, pd.Series]:
    months = pd.date_range("2016-01-01", periods=120, freq="MS")
    seasonal = np.array([1.15 if month in (1, 2) else 0.8 if month == 8 else 1.0
                         for month in months.month])
    sales = pd.DataFrame(
        {
            TARGET: (100_000 + np.arange(120) * 900) * seasonal,
            "business_line": ["consolidated"] * 120,
        },
        index=months,
    ).rename_axis("month")
    features, target = build_forecasting_features(sales)
    x_train, y_train, _, _ = split_first_eight_years(features, target)
    return x_train, y_train


def test_learning_curve_keeps_validation_after_every_training_prefix(tmp_path):
    x_train, y_train = training_partition()
    output = tmp_path / "curve.png"

    result = generate_learning_curve(
        x_train, y_train, output, validation_size=14, min_train_size=14, step=14
    )

    validation_start, validation_end = result["validation_period"]
    assert output.exists()
    assert len(result["points"]) >= 2
    assert result["points"][-1]["train_size"] == len(x_train) - 14
    for point in result["points"]:
        assert point["train_size"] < len(x_train) - 14 + 1
        assert np.isfinite(point["train_mae_usd"])
        assert np.isfinite(point["train_rmse_usd"])
        assert np.isfinite(point["validation_mae_usd"])
        assert np.isfinite(point["validation_rmse_usd"])
    assert validation_start == x_train.index[-14]
    assert validation_end == x_train.index[-1]


def test_learning_curve_is_independent_of_validation_actuals(tmp_path):
    x_train, y_train = training_partition()
    original = generate_learning_curve(
        x_train, y_train, tmp_path / "original.png", validation_size=14,
        min_train_size=14, step=14
    )
    changed = y_train.copy()
    changed.iloc[-14:] *= 100
    altered = generate_learning_curve(
        x_train, changed, tmp_path / "altered.png", validation_size=14,
        min_train_size=14, step=14
    )

    np.testing.assert_allclose(
        [point["train_mae_usd"] for point in original["points"]],
        [point["train_mae_usd"] for point in altered["points"]],
        rtol=1e-12,
        atol=1e-6,
    )
