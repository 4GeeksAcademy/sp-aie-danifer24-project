import numpy as np
import pandas as pd

from scripts.sales_forecast import (
    TARGET,
    build_forecasting_features,
    split_first_eight_years,
    temporal_cross_validation,
)


def sample_sales() -> pd.DataFrame:
    months = pd.date_range("2016-01-01", periods=120, freq="MS")
    seasonal = np.array([1.15 if month in (1, 2) else 0.8 if month == 8 else 1.0
                         for month in months.month])
    revenue = (100_000 + np.arange(120) * 900) * seasonal
    return pd.DataFrame(
        {
            TARGET: revenue,
            "active_contracts": [10] * 120,
            "avg_contract_value_usd": [10_000] * 120,
            "business_line": ["consolidated"] * 120,
        },
        index=months,
    ).rename_axis("month")


def training_partition() -> tuple[pd.DataFrame, pd.Series]:
    features, target = build_forecasting_features(sample_sales())
    x_train, y_train, _, _ = split_first_eight_years(features, target)
    return x_train, y_train


def test_temporal_cv_has_five_non_overlapping_chronological_folds():
    x_train, y_train = training_partition()

    folds, summary = temporal_cross_validation(x_train, y_train, n_splits=5)

    assert len(folds) == 5
    assert summary["folds"] == 5
    assert summary["mse_usd2_mean"] >= 0
    assert summary["mse_usd2_std"] >= 0
    for fold in folds:
        assert fold["train_start"] <= fold["train_end"]
        assert fold["validation_start"] <= fold["validation_end"]
        assert fold["train_end"] < fold["validation_start"]
        assert len(fold["predictions"]) == fold["validation_rows"]


def test_fold_predictions_do_not_depend_on_actual_validation_targets():
    x_train, y_train = training_partition()
    baseline_folds, _ = temporal_cross_validation(x_train, y_train, n_splits=5)

    # For each fold, dramatically change its validation labels. That fold's
    # training prefix is untouched, so its recursive forecasts must not change.
    for fold_number, original in enumerate(baseline_folds):
        changed_targets = y_train.copy()
        changed_targets.loc[
            original["validation_start"] : original["validation_end"]
        ] *= 100
        changed_folds, _ = temporal_cross_validation(
            x_train, changed_targets, n_splits=5
        )
        pd.testing.assert_series_equal(
            original["predictions"], changed_folds[fold_number]["predictions"]
        )


def test_temporal_cv_rejects_unsorted_training_data():
    x_train, y_train = training_partition()
    shuffled = x_train.iloc[::-1]
    shuffled_target = y_train.iloc[::-1]

    try:
        temporal_cross_validation(shuffled, shuffled_target, n_splits=5)
    except ValueError as error:
        assert "chronologically" in str(error)
    else:
        raise AssertionError("Unsorted training data should be rejected")
