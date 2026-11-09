from __future__ import annotations

import pandas as pd
import pytest
from sklearn.ensemble import RandomForestRegressor

from scripts.sales_forecast import (
    TARGET,
    build_forecasting_features,
    load_sales_data,
    recursive_forest_forecast,
    scale_feature_partitions,
    split_first_eight_years,
)


def sample_sales() -> pd.DataFrame:
    months = pd.date_range("2016-01-01", periods=120, freq="MS")
    revenue = [100_000 + i * 1_000 for i in range(120)]
    return pd.DataFrame(
        {
            TARGET: revenue,
            "active_contracts": [10] * 120,
            "avg_contract_value_usd": [10_000] * 120,
            "business_line": ["consolidated"] * 120,
        },
        index=months,
    ).rename_axis("month")


def test_split_uses_first_eight_years_for_training_and_last_two_for_test():
    features, target = build_forecasting_features(sample_sales())

    x_train, y_train, x_test, y_test = split_first_eight_years(features, target)

    assert x_train.index.min() == pd.Timestamp("2017-01-01")  # first year lacks 12-month history
    assert x_train.index.max() == pd.Timestamp("2023-12-01")
    assert x_test.index.min() == pd.Timestamp("2024-01-01")
    assert x_test.index.max() == pd.Timestamp("2025-12-01")
    assert len(x_test) == len(y_test) == 24
    assert x_train.index.max() < x_test.index.min()


def test_test_year_values_cannot_leak_into_training_features_or_labels():
    original = sample_sales()
    features, target = build_forecasting_features(original)
    x_train, y_train, _, _ = split_first_eight_years(features, target)

    modified = original.copy()
    modified.loc[modified.index >= "2024-01-01", TARGET] *= 10
    modified_features, modified_target = build_forecasting_features(modified)
    changed_x_train, changed_y_train, _, _ = split_first_eight_years(
        modified_features, modified_target
    )

    pd.testing.assert_frame_equal(x_train, changed_x_train)
    pd.testing.assert_series_equal(y_train, changed_y_train)
    assert y_train.index.max() < pd.Timestamp("2024-01-01")


def test_missing_target_values_are_not_used_as_labels(tmp_path):
    csv_path = tmp_path / "sales.csv"
    sales_data = sample_sales().reset_index()
    sales_data.loc[1, TARGET] = float("nan")
    sales_data.to_csv(csv_path, index=False)

    sales = load_sales_data(csv_path)
    features, target = build_forecasting_features(sales)
    x_train, y_train, x_test, y_test = split_first_eight_years(features, target)

    assert pd.isna(target.loc["2016-02-01"])
    assert pd.Timestamp("2016-02-01") not in y_train.index
    assert pd.Timestamp("2016-02-01") not in y_test.index


def test_missing_month_is_reindexed_and_lag_imputation_is_causal(tmp_path):
    csv_path = tmp_path / "sales.csv"
    csv_path.write_text(
        "month,revenue_usd,active_contracts,avg_contract_value_usd,business_line\n"
        "2016-01-01,100,1,100,consolidated\n"
        "2016-03-01,300,1,100,consolidated\n",
        encoding="utf-8",
    )

    sales = load_sales_data(csv_path)
    features, target = build_forecasting_features(sales)

    assert pd.Timestamp("2016-02-01") in sales.index
    assert pd.isna(target.loc["2016-02-01"])
    # By March, the missing February revenue was imputed from January only.
    assert features.loc["2016-03-01", "revenue_lag_1"] == pytest.approx(100)


def test_loader_rejects_duplicate_months(tmp_path):
    csv_path = tmp_path / "sales.csv"
    csv_path.write_text(
        "month,revenue_usd,active_contracts,avg_contract_value_usd,business_line\n"
        "2016-01-01,100,1,100,consolidated\n"
        "2016-01-15,110,1,100,consolidated\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate"):
        load_sales_data(csv_path)


def test_scaler_is_fitted_on_training_only():
    x_train = pd.DataFrame({"revenue_lag_1": [0.0, 10.0]})
    x_test = pd.DataFrame({"revenue_lag_1": [100.0]})

    scaled_train, scaled_test, scaler = scale_feature_partitions(x_train, x_test)

    assert scaler.mean_[0] == pytest.approx(5.0)
    assert scaled_train["revenue_lag_1"].mean() == pytest.approx(0.0)
    assert scaled_test.loc[0, "revenue_lag_1"] > 1.0


def test_recursive_forecast_does_not_read_actual_test_targets():
    train = sample_sales().iloc[:96]
    train_features, train_target = build_forecasting_features(train)
    train_mask = train_features.notna().all(axis=1) & train_target.notna()
    model = RandomForestRegressor(n_estimators=10, random_state=42).fit(
        train_features.loc[train_mask], train_target.loc[train_mask]
    )

    whole = sample_sales()
    features, target = build_forecasting_features(whole)
    _, _, test_features, test_target = split_first_eight_years(features, target)
    altered_features = test_features.copy()
    lag_columns = [column for column in altered_features if column.startswith("revenue_")]
    altered_features.loc[:, lag_columns] *= 100

    original_prediction, _ = recursive_forest_forecast(model, train_target, test_features)
    altered_prediction, _ = recursive_forest_forecast(model, train_target, altered_features)

    pd.testing.assert_series_equal(
        pd.Series(original_prediction, index=test_target.index),
        pd.Series(altered_prediction, index=test_target.index),
    )
