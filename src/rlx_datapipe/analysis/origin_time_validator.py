"""Origin time validation logic for data quality analysis."""

from datetime import datetime

import polars as pl
from loguru import logger


class OriginTimeValidator:
    """Validates origin_time field completeness and reliability."""

    def __init__(self, current_time: datetime | None = None):
        """Initialize validator.

        Args:
            current_time: Current time for future date validation (default: now)
        """
        self.current_time = current_time or datetime.now()
        logger.info(
            f"OriginTimeValidator initialized with current_time: {self.current_time}"
        )

    def check_null_values(self, df: pl.DataFrame) -> tuple[int, float]:
        """Check for null origin_time values.

        Args:
            df: DataFrame with origin_time column

        Returns:
            Tuple of (null_count, null_percentage)
        """
        if "origin_time" not in df.columns:
            logger.warning("origin_time column not found in DataFrame")
            return 0, 0.0

        total_rows = len(df)
        null_count = df["origin_time"].null_count()
        null_percentage = (null_count / total_rows * 100) if total_rows > 0 else 0.0

        logger.info(f"Null values: {null_count} ({null_percentage:.2f}%)")

        return null_count, null_percentage

    def check_zero_values(self, df: pl.DataFrame) -> tuple[int, float]:
        """Check for zero origin_time values.

        Args:
            df: DataFrame with origin_time column

        Returns:
            Tuple of (zero_count, zero_percentage)
        """
        if "origin_time" not in df.columns:
            logger.warning("origin_time column not found in DataFrame")
            return 0, 0.0

        total_rows = len(df)

        # Check for various zero representations as separate conditions
        zero_count = 0

        # Check for string zeros
        zero_count += df.filter(pl.col("origin_time") == "0").height
        zero_count += df.filter(pl.col("origin_time") == "").height
        zero_count += df.filter(pl.col("origin_time") == "1970-01-01T00:00:00").height
        zero_count += df.filter(pl.col("origin_time") == "1970-01-01 00:00:00").height

        # Check for numeric zeros (if possible)
        try:
            zero_count += df.filter(pl.col("origin_time") == 0).height
        except Exception:
            # Column is not numeric, skip numeric zero check
            pass

        zero_percentage = (zero_count / total_rows * 100) if total_rows > 0 else 0.0

        logger.info(f"Zero values: {zero_count} ({zero_percentage:.2f}%)")

        return zero_count, zero_percentage

    def check_future_dates(self, df: pl.DataFrame) -> tuple[int, float]:
        """Check for future origin_time values.

        Args:
            df: DataFrame with origin_time column

        Returns:
            Tuple of (future_count, future_percentage)
        """
        if "origin_time" not in df.columns:
            logger.warning("origin_time column not found in DataFrame")
            return 0, 0.0

        total_rows = len(df)

        try:
            # Convert to datetime if it's not already, handling null values
            df_with_datetime = df.with_columns(
                [
                    pl.col("origin_time")
                    .str.to_datetime(strict=False)
                    .alias("origin_time_dt")
                ]
            )

            future_count = df_with_datetime.filter(
                pl.col("origin_time_dt").is_not_null()
                & (pl.col("origin_time_dt") > pl.lit(self.current_time))
            ).height

            future_percentage = (
                (future_count / total_rows * 100) if total_rows > 0 else 0.0
            )

            logger.info(f"Future dates: {future_count} ({future_percentage:.2f}%)")

            return future_count, future_percentage

        except Exception as e:
            logger.error(f"Error checking future dates: {e}")
            return 0, 0.0

    def check_negative_values(self, df: pl.DataFrame) -> tuple[int, float]:
        """Check for negative origin_time values (if numeric).

        Args:
            df: DataFrame with origin_time column

        Returns:
            Tuple of (negative_count, negative_percentage)
        """
        if "origin_time" not in df.columns:
            logger.warning("origin_time column not found in DataFrame")
            return 0, 0.0

        total_rows = len(df)

        try:
            # Check if origin_time is numeric (timestamp)
            numeric_df = df.with_columns(
                [
                    pl.col("origin_time")
                    .cast(pl.Float64, strict=False)
                    .alias("origin_time_numeric")
                ]
            )

            negative_count = numeric_df.filter(pl.col("origin_time_numeric") < 0).height

            negative_percentage = (
                (negative_count / total_rows * 100) if total_rows > 0 else 0.0
            )

            logger.info(
                f"Negative values: {negative_count} ({negative_percentage:.2f}%)"
            )

            return negative_count, negative_percentage

        except Exception as e:
            logger.debug(
                f"Cannot check negative values (likely string timestamps): {e}"
            )
            return 0, 0.0

    def check_invalid_format(self, df: pl.DataFrame) -> tuple[int, float]:
        """Check for invalid datetime format in origin_time.

        Args:
            df: DataFrame with origin_time column

        Returns:
            Tuple of (invalid_count, invalid_percentage)
        """
        if "origin_time" not in df.columns:
            logger.warning("origin_time column not found in DataFrame")
            return 0, 0.0

        total_rows = len(df)

        try:
            # Try to parse as datetime and count failures
            df_with_parsed = df.with_columns(
                [
                    pl.col("origin_time")
                    .str.to_datetime(strict=False)
                    .alias("origin_time_parsed")
                ]
            )

            invalid_count = df_with_parsed.filter(
                pl.col("origin_time_parsed").is_null()
                & pl.col("origin_time").is_not_null()
            ).height

            invalid_percentage = (
                (invalid_count / total_rows * 100) if total_rows > 0 else 0.0
            )

            logger.info(f"Invalid format: {invalid_count} ({invalid_percentage:.2f}%)")

            return invalid_count, invalid_percentage

        except Exception as e:
            logger.error(f"Error checking invalid format: {e}")
            return 0, 0.0

    def validate_origin_time(self, df: pl.DataFrame, data_type: str) -> dict[str, any]:
        """Perform comprehensive origin_time validation.

        Args:
            df: DataFrame with origin_time column
            data_type: Type of data ('trades' or 'book')

        Returns:
            Dictionary with validation results
        """
        logger.info(f"Validating origin_time for {data_type} data ({len(df)} rows)")

        total_rows = len(df)

        # Perform all validation checks
        null_count, null_percentage = self.check_null_values(df)
        zero_count, zero_percentage = self.check_zero_values(df)
        future_count, future_percentage = self.check_future_dates(df)
        negative_count, negative_percentage = self.check_negative_values(df)
        invalid_count, invalid_percentage = self.check_invalid_format(df)

        # Calculate total invalid count
        total_invalid = (
            null_count + zero_count + future_count + negative_count + invalid_count
        )
        total_invalid_percentage = (
            (total_invalid / total_rows * 100) if total_rows > 0 else 0.0
        )

        # Calculate valid count
        valid_count = total_rows - total_invalid
        valid_percentage = (valid_count / total_rows * 100) if total_rows > 0 else 0.0

        results = {
            "data_type": data_type,
            "total_rows": total_rows,
            "valid_count": valid_count,
            "valid_percentage": valid_percentage,
            "total_invalid": total_invalid,
            "total_invalid_percentage": total_invalid_percentage,
            "validation_details": {
                "null_values": {"count": null_count, "percentage": null_percentage},
                "zero_values": {"count": zero_count, "percentage": zero_percentage},
                "future_dates": {
                    "count": future_count,
                    "percentage": future_percentage,
                },
                "negative_values": {
                    "count": negative_count,
                    "percentage": negative_percentage,
                },
                "invalid_format": {
                    "count": invalid_count,
                    "percentage": invalid_percentage,
                },
            },
        }

        logger.info(
            f"Validation complete: {valid_count}/{total_rows} "
            f"({valid_percentage:.2f}%) valid entries"
        )

        return results

    def calculate_reliability_score(self, validation_results: dict[str, any]) -> float:
        """Calculate reliability score based on validation results.

        Args:
            validation_results: Results from validate_origin_time()

        Returns:
            Reliability score (0-100)
        """
        return validation_results["valid_percentage"]

    def is_reliable_for_chronological_sorting(
        self, validation_results: dict[str, any], reliability_threshold: float = 95.0
    ) -> bool:
        """Determine if origin_time is reliable for chronological sorting.

        Args:
            validation_results: Results from validate_origin_time()
            reliability_threshold: Minimum reliability percentage required

        Returns:
            True if reliable for chronological sorting
        """
        reliability_score = self.calculate_reliability_score(validation_results)
        is_reliable = reliability_score >= reliability_threshold

        logger.info(
            f"Reliability score: {reliability_score:.2f}% "
            f"(threshold: {reliability_threshold}%)"
        )
        logger.info(f"Suitable for chronological sorting: {is_reliable}")

        return is_reliable
