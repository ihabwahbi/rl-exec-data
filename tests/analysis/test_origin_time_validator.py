"""Tests for origin_time validation logic."""

from datetime import datetime

import polars as pl
import pytest
from rlx_datapipe.analysis.origin_time_validator import OriginTimeValidator


@pytest.fixture()
def validator():
    """Create OriginTimeValidator instance for testing."""
    return OriginTimeValidator(current_time=datetime(2024, 1, 1, 12, 0, 0))


@pytest.fixture()
def clean_data():
    """Create clean test data with valid origin_time values."""
    return pl.DataFrame(
        {
            "origin_time": [
                "2024-01-01T10:00:00",
                "2024-01-01T10:01:00",
                "2024-01-01T10:02:00",
            ],
            "other_column": [1, 2, 3],
        }
    )


@pytest.fixture()
def dirty_data():
    """Create test data with various invalid origin_time values."""
    return pl.DataFrame(
        {
            "origin_time": [
                "2024-01-01T10:00:00",  # valid
                None,  # null
                "0",  # zero string
                "",  # empty string
                "1970-01-01T00:00:00",  # epoch zero
                "2024-01-01T15:00:00",  # future date (after current_time)
                "invalid_date",  # invalid format
                "2024-01-01T09:00:00",  # valid
            ],
            "other_column": [1, 2, 3, 4, 5, 6, 7, 8],
        }
    )


def test_validator_initialization():
    """Test OriginTimeValidator initialization."""
    validator = OriginTimeValidator()
    assert validator.current_time is not None

    custom_time = datetime(2024, 1, 1, 12, 0, 0)
    validator_custom = OriginTimeValidator(current_time=custom_time)
    assert validator_custom.current_time == custom_time


def test_check_null_values_clean_data(validator, clean_data):
    """Test null value checking with clean data."""
    null_count, null_percentage = validator.check_null_values(clean_data)

    assert null_count == 0
    assert null_percentage == 0.0


def test_check_null_values_dirty_data(validator, dirty_data):
    """Test null value checking with dirty data."""
    null_count, null_percentage = validator.check_null_values(dirty_data)

    assert null_count == 1
    assert null_percentage == 12.5  # 1 out of 8 rows


def test_check_null_values_missing_column(validator):
    """Test null value checking with missing origin_time column."""
    df = pl.DataFrame({"other_column": [1, 2, 3]})
    null_count, null_percentage = validator.check_null_values(df)

    assert null_count == 0
    assert null_percentage == 0.0


def test_check_zero_values_clean_data(validator, clean_data):
    """Test zero value checking with clean data."""
    zero_count, zero_percentage = validator.check_zero_values(clean_data)

    assert zero_count == 0
    assert zero_percentage == 0.0


def test_check_zero_values_dirty_data(validator, dirty_data):
    """Test zero value checking with dirty data."""
    zero_count, zero_percentage = validator.check_zero_values(dirty_data)

    assert zero_count == 3  # "0", "", "1970-01-01T00:00:00"
    assert zero_percentage == 37.5  # 3 out of 8 rows


def test_check_future_dates_clean_data(validator, clean_data):
    """Test future date checking with clean data."""
    future_count, future_percentage = validator.check_future_dates(clean_data)

    assert future_count == 0
    assert future_percentage == 0.0


def test_check_future_dates_dirty_data(validator, dirty_data):
    """Test future date checking with dirty data."""
    future_count, future_percentage = validator.check_future_dates(dirty_data)

    assert future_count == 1  # "2024-01-01T15:00:00" is after current_time (12:00:00)
    assert future_percentage == 12.5  # 1 out of 8 rows


def test_check_negative_values_clean_data(validator, clean_data):
    """Test negative value checking with clean data."""
    negative_count, negative_percentage = validator.check_negative_values(clean_data)

    assert negative_count == 0
    assert negative_percentage == 0.0


def test_check_negative_values_numeric_data(validator):
    """Test negative value checking with numeric timestamps."""
    df = pl.DataFrame(
        {
            "origin_time": [1640995200, -1, 1640995260],  # Mix of positive and negative
            "other_column": [1, 2, 3],
        }
    )

    negative_count, negative_percentage = validator.check_negative_values(df)

    assert negative_count == 1
    assert abs(negative_percentage - 33.33) < 0.01  # 1 out of 3 rows (approximately)


def test_check_invalid_format_clean_data(validator, clean_data):
    """Test invalid format checking with clean data."""
    invalid_count, invalid_percentage = validator.check_invalid_format(clean_data)

    assert invalid_count == 0
    assert invalid_percentage == 0.0


def test_check_invalid_format_dirty_data(validator, dirty_data):
    """Test invalid format checking with dirty data."""
    invalid_count, invalid_percentage = validator.check_invalid_format(dirty_data)

    assert invalid_count == 3  # "invalid_date", "", "0" can't be parsed as datetime
    assert invalid_percentage == 37.5  # 3 out of 8 rows


def test_validate_origin_time_clean_data(validator, clean_data):
    """Test comprehensive validation with clean data."""
    results = validator.validate_origin_time(clean_data, "trades")

    assert results["data_type"] == "trades"
    assert results["total_rows"] == 3
    assert results["valid_count"] == 3
    assert results["valid_percentage"] == 100.0
    assert results["total_invalid"] == 0
    assert results["total_invalid_percentage"] == 0.0

    # Check validation details
    details = results["validation_details"]
    assert details["null_values"]["count"] == 0
    assert details["zero_values"]["count"] == 0
    assert details["future_dates"]["count"] == 0
    assert details["negative_values"]["count"] == 0
    assert details["invalid_format"]["count"] == 0


def test_validate_origin_time_dirty_data(validator, dirty_data):
    """Test comprehensive validation with dirty data."""
    results = validator.validate_origin_time(dirty_data, "book")

    assert results["data_type"] == "book"
    assert results["total_rows"] == 8
    assert results["valid_count"] == 0  # No valid entries due to overlapping issues
    assert results["valid_percentage"] == 0.0
    assert results["total_invalid"] == 8  # All entries have some issue
    assert results["total_invalid_percentage"] == 100.0

    # Check validation details
    details = results["validation_details"]
    assert details["null_values"]["count"] == 1
    assert details["zero_values"]["count"] == 3
    assert details["future_dates"]["count"] == 1
    assert details["invalid_format"]["count"] == 3


def test_calculate_reliability_score(validator, clean_data):
    """Test reliability score calculation."""
    results = validator.validate_origin_time(clean_data, "trades")
    score = validator.calculate_reliability_score(results)

    assert score == 100.0


def test_is_reliable_for_chronological_sorting(validator, clean_data, dirty_data):
    """Test reliability determination for chronological sorting."""
    # Clean data should be reliable
    clean_results = validator.validate_origin_time(clean_data, "trades")
    assert validator.is_reliable_for_chronological_sorting(clean_results) is True

    # Dirty data should not be reliable
    dirty_results = validator.validate_origin_time(dirty_data, "book")
    assert validator.is_reliable_for_chronological_sorting(dirty_results) is False

    # Test with custom threshold (but dirty data has 0% reliability)
    assert (
        validator.is_reliable_for_chronological_sorting(
            dirty_results, reliability_threshold=0.0
        )
        is True
    )


def test_is_reliable_for_chronological_sorting_threshold(validator):
    """Test reliability determination with different thresholds."""
    # Create data with 90% reliability
    data = pl.DataFrame(
        {
            "origin_time": [
                "2024-01-01T10:00:00",  # valid
                "2024-01-01T10:01:00",  # valid
                "2024-01-01T10:02:00",  # valid
                "2024-01-01T10:03:00",  # valid
                "2024-01-01T10:04:00",  # valid
                "2024-01-01T10:05:00",  # valid
                "2024-01-01T10:06:00",  # valid
                "2024-01-01T10:07:00",  # valid
                "2024-01-01T10:08:00",  # valid
                None,  # invalid
            ]
        }
    )

    results = validator.validate_origin_time(data, "trades")

    # Should be reliable with 85% threshold
    assert (
        validator.is_reliable_for_chronological_sorting(
            results, reliability_threshold=85.0
        )
        is True
    )

    # Should not be reliable with 95% threshold
    assert (
        validator.is_reliable_for_chronological_sorting(
            results, reliability_threshold=95.0
        )
        is False
    )


def test_empty_dataframe(validator):
    """Test handling of empty DataFrames."""
    empty_df = pl.DataFrame({"origin_time": []})

    results = validator.validate_origin_time(empty_df, "trades")

    assert results["total_rows"] == 0
    assert results["valid_count"] == 0
    assert results["valid_percentage"] == 0.0
    assert results["total_invalid"] == 0
    assert results["total_invalid_percentage"] == 0.0
