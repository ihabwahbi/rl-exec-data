"""
Performance benchmarking utilities for the reconstruction pipeline.

Provides tools to measure and validate performance against baselines.
"""
import os
import time
from pathlib import Path
from typing import Any

import psutil
from loguru import logger


class PerformanceBenchmark:
    """Performance benchmarking for data processing operations."""

    # Baseline performance targets from validated results
    BASELINE_THROUGHPUT = 336_000  # messages/second
    BASELINE_READ_SPEED_MB = 200   # MB/second minimum
    MEMORY_LIMIT_GB = 1.0          # Maximum memory usage

    def __init__(self):
        """Initialize performance benchmark."""
        self.process = psutil.Process(os.getpid())
        self.results = {}

    def benchmark_reader(
        self,
        reader_func,
        data_path: Path,
        batch_size: int | None = None
    ) -> dict[str, Any]:
        """Benchmark a data reader function.

        Args:
            reader_func: Reader function to benchmark
            data_path: Path to data file
            batch_size: Optional batch size

        Returns:
            Benchmark results dictionary
        """
        # Get file size
        file_size_bytes = data_path.stat().st_size
        file_size_mb = file_size_bytes / (1024 * 1024)

        # Memory before
        memory_before = self.process.memory_info().rss / (1024 * 1024 * 1024)  # GB

        # Start timing
        start_time = time.perf_counter()
        start_cpu = time.process_time()

        # Run reader
        total_rows = 0
        if batch_size:
            for batch in reader_func(batch_size=batch_size):
                total_rows += len(batch)
        else:
            df = reader_func()
            total_rows = len(df)

        # End timing
        end_time = time.perf_counter()
        end_cpu = time.process_time()

        # Memory after
        memory_after = self.process.memory_info().rss / (1024 * 1024 * 1024)  # GB
        memory_used = memory_after - memory_before

        # Calculate metrics
        wall_time = end_time - start_time
        cpu_time = end_cpu - start_cpu
        throughput = total_rows / wall_time if wall_time > 0 else 0
        read_speed_mb = file_size_mb / wall_time if wall_time > 0 else 0

        return {
            "total_rows": total_rows,
            "file_size_mb": file_size_mb,
            "wall_time_seconds": wall_time,
            "cpu_time_seconds": cpu_time,
            "throughput_messages_per_second": throughput,
            "read_speed_mb_per_second": read_speed_mb,
            "memory_used_gb": memory_used,
            "memory_peak_gb": memory_after,
            "meets_baseline_throughput": throughput >= self.BASELINE_THROUGHPUT,
            "meets_baseline_read_speed": read_speed_mb >= self.BASELINE_READ_SPEED_MB,
            "meets_memory_limit": memory_after <= self.MEMORY_LIMIT_GB
        }


    def benchmark_unification(
        self,
        unified_stream,
        trades_path: Path | None = None,
        book_snapshots_path: Path | None = None,
        book_deltas_path: Path | None = None
    ) -> dict[str, Any]:
        """Benchmark the unification process.

        Args:
            unified_stream: UnifiedEventStream instance
            trades_path: Path to trades data
            book_snapshots_path: Path to book snapshots
            book_deltas_path: Path to book deltas

        Returns:
            Benchmark results dictionary
        """
        # Memory before
        memory_before = self.process.memory_info().rss / (1024 * 1024 * 1024)  # GB

        # Start timing
        start_time = time.perf_counter()

        # Run unification
        df = unified_stream.merge_streams(
            trades_path=trades_path,
            book_snapshots_path=book_snapshots_path,
            book_deltas_path=book_deltas_path
        )

        # End timing
        end_time = time.perf_counter()

        # Memory after
        memory_after = self.process.memory_info().rss / (1024 * 1024 * 1024)  # GB

        # Calculate metrics
        wall_time = end_time - start_time
        total_events = len(df)
        throughput = total_events / wall_time if wall_time > 0 else 0
        memory_used = memory_after - memory_before

        # Get time range from data
        time_range_seconds = 0
        if "origin_time" in df.columns and len(df) > 0:
            time_range_ns = df["origin_time"].max() - df["origin_time"].min()
            time_range_seconds = time_range_ns / 1e9

        return {
            "total_events": total_events,
            "wall_time_seconds": wall_time,
            "throughput_events_per_second": throughput,
            "memory_used_gb": memory_used,
            "memory_peak_gb": memory_after,
            "time_range_seconds": time_range_seconds,
            "events_by_type": unified_stream._event_counts,
            "meets_baseline_throughput": throughput >= self.BASELINE_THROUGHPUT,
            "meets_memory_limit": memory_after <= self.MEMORY_LIMIT_GB
        }


    def log_results(self, results: dict[str, Any], test_name: str) -> None:
        """Log benchmark results.

        Args:
            results: Benchmark results dictionary
            test_name: Name of the test
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"Performance Benchmark: {test_name}")
        logger.info(f"{'='*60}")

        for key, value in results.items():
            if isinstance(value, float):
                logger.info(f"{key}: {value:.2f}")
            elif isinstance(value, bool):
                status = "✓ PASS" if value else "✗ FAIL"
                logger.info(f"{key}: {status}")
            else:
                logger.info(f"{key}: {value}")

        logger.info(f"{'='*60}\n")
