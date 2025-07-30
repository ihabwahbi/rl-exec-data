"""
Delta Feed Analysis Module

Provides classes and functions for analyzing book_delta_v2 data quality,
including sequence gap detection and performance metrics.
"""

import time
from typing import Any

import polars as pl
import psutil
from loguru import logger


class SequenceGapAnalyzer:
    """Analyzes sequence gaps in delta feed data."""

    def __init__(self):
        """Initialize the sequence gap analyzer."""
        self.gaps: list[int] = []
        self.total_events = 0
        self.max_gap = 0
        self.mean_gap = 0.0
        self.gap_ratio_percent = 0.0

    def analyze_gaps(self, update_ids: list[int]) -> dict[str, Any]:
        """
        Analyze sequence gaps in a list of update IDs.

        Args:
            update_ids: List of update IDs (should be sorted)

        Returns:
            Dictionary containing gap analysis results
        """
        if len(update_ids) < 2:
            logger.warning("Not enough data to analyze sequence gaps")
            return {
                "count": 0,
                "max_gap": 0,
                "mean_gap": 0.0,
                "gap_ratio_percent": 0.0,
                "gaps_by_size": {},
            }

        # Calculate gaps
        gaps = []
        for i in range(1, len(update_ids)):
            diff = update_ids[i] - update_ids[i - 1]
            if diff > 1:
                gaps.append(diff - 1)  # Gap size (excluding expected increment of 1)

        self.gaps = gaps
        self.total_events = len(update_ids)

        # Calculate statistics
        if gaps:
            self.max_gap = max(gaps)
            self.mean_gap = sum(gaps) / len(gaps)

            # Calculate gap ratio
            total_possible_gaps = update_ids[-1] - update_ids[0]
            actual_gaps = sum(gaps)
            self.gap_ratio_percent = (
                (actual_gaps / total_possible_gaps) * 100
                if total_possible_gaps > 0
                else 0.0
            )

            # Group gaps by size
            gaps_by_size = {}
            for gap in gaps:
                size_bucket = self._get_gap_size_bucket(gap)
                gaps_by_size[size_bucket] = gaps_by_size.get(size_bucket, 0) + 1
        else:
            self.max_gap = 0
            self.mean_gap = 0.0
            self.gap_ratio_percent = 0.0
            gaps_by_size = {}

        return {
            "count": len(gaps),
            "max_gap": self.max_gap,
            "mean_gap": self.mean_gap,
            "gap_ratio_percent": self.gap_ratio_percent,
            "gaps_by_size": gaps_by_size,
        }

    def _get_gap_size_bucket(self, gap: int) -> str:
        """Categorize gaps by size."""
        if gap <= 10:
            return "1-10"
        elif gap <= 100:
            return "11-100"
        elif gap <= 1000:
            return "101-1000"
        else:
            return "1000+"


class DataQualityAnalyzer:
    """Analyzes data quality metrics for delta feed data."""

    def __init__(self):
        """Initialize the data quality analyzer."""
        self.metrics = {
            "valid_update_ids": 0,
            "invalid_update_ids": 0,
            "valid_prices": 0,
            "invalid_prices": 0,
            "valid_quantities": 0,
            "invalid_quantities": 0,
        }

    def analyze_quality(self, df: pl.DataFrame) -> dict[str, int]:
        """
        Analyze data quality metrics.

        Args:
            df: DataFrame with delta feed data

        Returns:
            Dictionary containing quality metrics
        """
        total_rows = len(df)

        # Check update_id validity (should be positive)
        try:
            valid_update_ids = df.filter(pl.col("update_id") > 0).height
            self.metrics["valid_update_ids"] = valid_update_ids
            self.metrics["invalid_update_ids"] = total_rows - valid_update_ids
        except Exception as e:
            logger.warning(f"Error checking update_id validity: {e}")
            self.metrics["valid_update_ids"] = 0
            self.metrics["invalid_update_ids"] = total_rows

        # Check price validity (should be positive)
        try:
            valid_prices = df.filter(pl.col("price") > 0).height
            self.metrics["valid_prices"] = valid_prices
            self.metrics["invalid_prices"] = total_rows - valid_prices
        except Exception as e:
            logger.warning(f"Error checking price validity: {e}")
            self.metrics["valid_prices"] = 0
            self.metrics["invalid_prices"] = total_rows

        # Check quantity validity (should be >= 0)
        try:
            valid_quantities = df.filter(pl.col("new_quantity") >= 0).height
            self.metrics["valid_quantities"] = valid_quantities
            self.metrics["invalid_quantities"] = total_rows - valid_quantities
        except Exception as e:
            logger.warning(f"Error checking quantity validity: {e}")
            self.metrics["valid_quantities"] = 0
            self.metrics["invalid_quantities"] = total_rows

        return self.metrics


class MemoryProfiler:
    """Profiles memory usage during data processing."""

    def __init__(self, limit_gb: float = 24.0):
        """
        Initialize memory profiler.

        Args:
            limit_gb: Memory limit in GB
        """
        self.limit_gb = limit_gb
        self.limit_bytes = limit_gb * 1024 * 1024 * 1024
        self.samples: list[int] = []
        self.process = psutil.Process()

    def record_memory(self) -> float:
        """
        Record current memory usage.

        Returns:
            Current memory usage in GB
        """
        memory_bytes = self.process.memory_info().rss
        self.samples.append(memory_bytes)

        memory_gb = memory_bytes / (1024 * 1024 * 1024)

        # Warning if approaching limit
        if memory_gb > self.limit_gb * 0.9:
            logger.warning(
                f"Memory usage {memory_gb:.2f}GB approaching limit of {self.limit_gb}GB"
            )

        return memory_gb

    def get_memory_stats(self) -> dict[str, float]:
        """
        Get memory usage statistics.

        Returns:
            Dictionary with memory statistics
        """
        if not self.samples:
            return {"peak_gb": 0.0, "p95_gb": 0.0, "mean_gb": 0.0, "min_gb": 0.0}

        # Convert to GB
        samples_gb = [sample / (1024 * 1024 * 1024) for sample in self.samples]

        # Calculate statistics
        peak_gb = max(samples_gb)
        p95_gb = (
            sorted(samples_gb)[int(len(samples_gb) * 0.95)]
            if len(samples_gb) > 0
            else 0.0
        )
        mean_gb = sum(samples_gb) / len(samples_gb)
        min_gb = min(samples_gb)

        return {
            "peak_gb": peak_gb,
            "p95_gb": p95_gb,
            "mean_gb": mean_gb,
            "min_gb": min_gb,
        }


class ThroughputAnalyzer:
    """Analyzes processing throughput metrics."""

    def __init__(self):
        """Initialize throughput analyzer."""
        self.start_time: float | None = None
        self.end_time: float | None = None
        self.events_processed = 0
        self.bytes_processed = 0

    def start_timing(self) -> None:
        """Start timing measurement."""
        self.start_time = time.time()

    def end_timing(self) -> None:
        """End timing measurement."""
        self.end_time = time.time()

    def record_processing(self, events: int, bytes_size: int = 0) -> None:
        """
        Record processing metrics.

        Args:
            events: Number of events processed
            bytes_size: Size in bytes (optional)
        """
        self.events_processed += events
        self.bytes_processed += bytes_size

    def get_throughput_stats(self) -> dict[str, float]:
        """
        Get throughput statistics.

        Returns:
            Dictionary with throughput metrics
        """
        if self.start_time is None or self.end_time is None:
            return {
                "events_per_second": 0.0,
                "mb_per_second": 0.0,
                "processing_time_seconds": 0.0,
            }

        processing_time = self.end_time - self.start_time

        if processing_time <= 0:
            return {
                "events_per_second": 0.0,
                "mb_per_second": 0.0,
                "processing_time_seconds": 0.0,
            }

        events_per_second = self.events_processed / processing_time
        mb_per_second = (self.bytes_processed / (1024 * 1024)) / processing_time

        return {
            "events_per_second": events_per_second,
            "mb_per_second": mb_per_second,
            "processing_time_seconds": processing_time,
        }


def validate_book_delta_schema(df: pl.DataFrame) -> tuple[bool, list[str]]:
    """
    Validate that DataFrame has the expected book_delta_v2 schema.

    Args:
        df: DataFrame to validate

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    required_columns = ["update_id", "origin_time", "side", "price", "new_quantity"]
    errors = []

    # Check for required columns
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        errors.append(f"Missing required columns: {missing_columns}")

    # Check data types (if columns exist)
    if "update_id" in df.columns:
        if not df["update_id"].dtype.is_integer():
            errors.append("update_id must be integer type")

    if "origin_time" in df.columns:
        if not df["origin_time"].dtype.is_integer():
            errors.append("origin_time must be integer type (nanoseconds)")

    if "side" in df.columns:
        if df["side"].dtype != pl.Utf8:
            errors.append("side must be string type")

    # Check for empty DataFrame
    if df.is_empty():
        errors.append("DataFrame is empty")

    return len(errors) == 0, errors


def create_sample_delta_data(num_events: int = 1000) -> pl.DataFrame:
    """
    Create sample book_delta_v2 data for testing.

    Args:
        num_events: Number of events to create

    Returns:
        DataFrame with sample delta data
    """
    import random

    # Generate sample data
    data = {
        "update_id": list(range(1, num_events + 1)),
        "origin_time": [
            int(time.time() * 1e9) + i * 1000000 for i in range(num_events)
        ],
        "side": [random.choice(["bid", "ask"]) for _ in range(num_events)],
        "price": [
            round(45000 + random.uniform(-1000, 1000), 2) for _ in range(num_events)
        ],
        "new_quantity": [round(random.uniform(0, 10), 8) for _ in range(num_events)],
    }

    # Introduce some gaps for testing
    if num_events > 100:
        # Add some gaps in update_id sequence
        gap_positions = random.sample(
            range(10, num_events - 10), min(5, num_events // 100)
        )
        for pos in sorted(gap_positions, reverse=True):
            gap_size = random.randint(2, 20)
            for i in range(pos, num_events):
                data["update_id"][i] += gap_size

    return pl.DataFrame(data)
