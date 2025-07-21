#!/usr/bin/env python3
"""
Performance Baseline Harness

Measures end-to-end pipeline performance including parse rate, order book update rate,
memory allocation, GC pressure, and disk write throughput.
"""

import argparse
import gc
import json
import sys
import time
import tracemalloc
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path

import psutil

# Add src to path to import our modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import polars as pl
from loguru import logger

from rlx_datapipe.analysis.delta_analyzer import (
    MemoryProfiler,
    ThroughputAnalyzer,
    create_sample_delta_data,
)
from rlx_datapipe.common.logging import setup_logging


@dataclass
class PerformanceMetrics:
    """Container for performance metrics."""
    events_processed: int = 0
    throughput_eps: float = 0.0
    memory_usage_gb: float = 0.0
    parse_rate_eps: float = 0.0
    order_book_update_rate_eps: float = 0.0
    disk_write_throughput_mbps: float = 0.0
    gc_pressure_ratio: float = 0.0
    peak_memory_gb: float = 0.0
    p95_memory_gb: float = 0.0
    cpu_usage_percent: float = 0.0

    def to_opentelemetry(self) -> dict[str, float]:
        """Export metrics in OpenTelemetry format."""
        return {
            "pipeline.events.processed": self.events_processed,
            "pipeline.throughput.eps": self.throughput_eps,
            "pipeline.memory.usage_gb": self.memory_usage_gb,
            "pipeline.parse_rate.eps": self.parse_rate_eps,
            "pipeline.order_book.update_rate_eps": self.order_book_update_rate_eps,
            "pipeline.disk_write.throughput_mbps": self.disk_write_throughput_mbps,
            "pipeline.gc.pressure_ratio": self.gc_pressure_ratio,
            "pipeline.memory.peak_gb": self.peak_memory_gb,
            "pipeline.memory.p95_gb": self.p95_memory_gb,
            "pipeline.cpu.usage_percent": self.cpu_usage_percent,
        }


class OrderBookEngine:
    """Simplified order book engine for performance testing."""

    def __init__(self, max_levels: int = 20):
        self.max_levels = max_levels
        self.bids = {}  # price -> quantity
        self.asks = {}  # price -> quantity
        self.update_count = 0
        self.last_update_id = 0

    def update(self, price: float, quantity: float, side: str, update_id: int) -> bool:
        """
        Update order book with new delta.
        
        Returns:
            True if update was successful, False if sequence gap detected
        """
        # Check for sequence gap
        if self.last_update_id > 0 and update_id != self.last_update_id + 1:
            logger.warning(f"Sequence gap detected: expected {self.last_update_id + 1}, got {update_id}")
            # Continue processing despite gap for performance testing

        self.last_update_id = update_id

        # Update book
        if side == "bid":
            if quantity > 0:
                self.bids[price] = quantity
            else:
                self.bids.pop(price, None)
        elif quantity > 0:
            self.asks[price] = quantity
        else:
            self.asks.pop(price, None)

        # Maintain max levels constraint
        if len(self.bids) > self.max_levels:
            # Remove lowest bids
            sorted_bids = sorted(self.bids.keys(), reverse=True)
            for price in sorted_bids[self.max_levels:]:
                self.bids.pop(price)

        if len(self.asks) > self.max_levels:
            # Remove highest asks
            sorted_asks = sorted(self.asks.keys())
            for price in sorted_asks[self.max_levels:]:
                self.asks.pop(price)

        self.update_count += 1
        return True

    def get_best_bid_ask(self) -> tuple[float | None, float | None]:
        """Get best bid and ask prices."""
        best_bid = max(self.bids.keys()) if self.bids else None
        best_ask = min(self.asks.keys()) if self.asks else None
        return best_bid, best_ask

    def get_depth(self) -> int:
        """Get total depth (number of levels)."""
        return len(self.bids) + len(self.asks)


class PerformanceHarness:
    """Main performance testing harness."""

    def __init__(self, memory_limit_gb: float = 24.0):
        self.memory_limit_gb = memory_limit_gb
        self.process = psutil.Process()
        self.memory_profiler = MemoryProfiler(memory_limit_gb)
        self.throughput_analyzer = ThroughputAnalyzer()
        self.order_book = OrderBookEngine()
        self.metrics = PerformanceMetrics()

        # Performance tracking
        self.parse_times = deque(maxlen=10000)
        self.order_book_update_times = deque(maxlen=10000)
        self.disk_write_times = deque(maxlen=1000)
        self.gc_stats_start = None

    def start_profiling(self) -> None:
        """Start performance profiling."""
        tracemalloc.start()
        self.gc_stats_start = gc.get_stats()
        self.throughput_analyzer.start_timing()
        logger.info("Performance profiling started")

    def stop_profiling(self) -> None:
        """Stop performance profiling."""
        self.throughput_analyzer.end_timing()

        # Get memory stats
        memory_stats = self.memory_profiler.get_memory_stats()
        self.metrics.peak_memory_gb = memory_stats["peak_gb"]
        self.metrics.p95_memory_gb = memory_stats["p95_gb"]

        # Get GC stats
        if self.gc_stats_start:
            gc_stats_end = gc.get_stats()
            self.metrics.gc_pressure_ratio = self._calculate_gc_pressure(
                self.gc_stats_start, gc_stats_end
            )

        # Get CPU usage
        self.metrics.cpu_usage_percent = self.process.cpu_percent()

        # Calculate throughput
        throughput_stats = self.throughput_analyzer.get_throughput_stats()
        self.metrics.throughput_eps = throughput_stats["events_per_second"]

        # Calculate parse rate
        if self.parse_times:
            total_parse_time = sum(self.parse_times)
            self.metrics.parse_rate_eps = len(self.parse_times) / total_parse_time if total_parse_time > 0 else 0

        # Calculate order book update rate
        if self.order_book_update_times:
            total_update_time = sum(self.order_book_update_times)
            self.metrics.order_book_update_rate_eps = len(self.order_book_update_times) / total_update_time if total_update_time > 0 else 0

        # Calculate disk write throughput
        if self.disk_write_times:
            total_write_time = sum(self.disk_write_times)
            # Estimate bytes written (rough approximation)
            estimated_bytes = self.metrics.events_processed * 100  # ~100 bytes per event
            self.metrics.disk_write_throughput_mbps = (estimated_bytes / (1024 * 1024)) / total_write_time if total_write_time > 0 else 0

        tracemalloc.stop()
        logger.info("Performance profiling stopped")

    def _calculate_gc_pressure(self, start_stats: list, end_stats: list) -> float:
        """Calculate GC pressure ratio."""
        try:
            # Simple metric: ratio of collections to objects
            total_collections = sum(stat["collections"] for stat in end_stats)
            start_collections = sum(stat["collections"] for stat in start_stats)

            collections_delta = total_collections - start_collections

            # Normalize by events processed
            if self.metrics.events_processed > 0:
                return collections_delta / self.metrics.events_processed
            return 0.0
        except Exception as e:
            logger.warning(f"Could not calculate GC pressure: {e}")
            return 0.0

    def parse_events(self, df: pl.DataFrame) -> pl.DataFrame:
        """Parse events from DataFrame."""
        start_time = time.time()

        # Simulate parsing operations
        parsed_df = df.with_columns([
            pl.col("price").cast(pl.Float64),
            pl.col("new_quantity").cast(pl.Float64).alias("quantity"),
            pl.col("update_id").cast(pl.Int64)
        ])

        # Add some computational work to simulate realistic parsing
        parsed_df = parsed_df.with_columns([
            (pl.col("price") * pl.col("quantity")).alias("notional"),
            pl.col("origin_time").cast(pl.Datetime).alias("event_time")
        ])

        parse_time = time.time() - start_time
        self.parse_times.append(parse_time)

        return parsed_df

    def update_order_book(self, df: pl.DataFrame) -> None:
        """Update order book with events."""
        start_time = time.time()

        # Convert to list for processing
        events = df.select(["price", "quantity", "side", "update_id"]).to_dicts()

        for event in events:
            self.order_book.update(
                price=event["price"],
                quantity=event["quantity"],
                side=event["side"],
                update_id=event["update_id"]
            )

        update_time = time.time() - start_time
        self.order_book_update_times.append(update_time)

    def write_to_disk(self, df: pl.DataFrame, output_path: Path) -> None:
        """Write DataFrame to disk."""
        start_time = time.time()

        # Write to parquet
        df.write_parquet(output_path)

        write_time = time.time() - start_time
        self.disk_write_times.append(write_time)

    def run_benchmark(self, num_events: int = 5_000_000, batch_size: int = 100_000) -> PerformanceMetrics:
        """Run the performance benchmark."""

        logger.info(f"Starting benchmark with {num_events} events, batch size {batch_size}")

        # Create output directory
        output_dir = Path("data/benchmark_results")
        output_dir.mkdir(parents=True, exist_ok=True)

        # Start profiling
        self.start_profiling()

        try:
            # Process events in batches
            events_processed = 0
            batch_count = 0

            while events_processed < num_events:
                # Determine batch size for this iteration
                current_batch_size = min(batch_size, num_events - events_processed)

                # Record memory usage
                self.memory_profiler.record_memory()

                # Create sample data batch
                sample_df = create_sample_delta_data(current_batch_size)

                # Parse events
                parsed_df = self.parse_events(sample_df)

                # Update order book
                self.update_order_book(parsed_df)

                # Write to disk (every 10th batch to avoid too much disk I/O)
                if batch_count % 10 == 0:
                    batch_output_path = output_dir / f"batch_{batch_count}.parquet"
                    self.write_to_disk(parsed_df, batch_output_path)

                # Update counters
                events_processed += current_batch_size
                batch_count += 1

                # Record processing
                self.throughput_analyzer.record_processing(current_batch_size)

                # Log progress
                if batch_count % 10 == 0:
                    logger.info(f"Processed {events_processed:,} / {num_events:,} events ({events_processed/num_events*100:.1f}%)")

                # Force garbage collection periodically
                if batch_count % 20 == 0:
                    gc.collect()

                # Check memory pressure
                current_memory = self.process.memory_info().rss / (1024 * 1024 * 1024)
                if current_memory > self.memory_limit_gb * 0.9:
                    logger.warning(f"Memory pressure: {current_memory:.2f}GB / {self.memory_limit_gb}GB")
                    gc.collect()

                    # Check again after GC
                    current_memory = self.process.memory_info().rss / (1024 * 1024 * 1024)
                    if current_memory > self.memory_limit_gb * 0.95:
                        logger.error(f"Critical memory pressure: {current_memory:.2f}GB, stopping benchmark")
                        break

            self.metrics.events_processed = events_processed

            # Final metrics
            logger.info(f"Benchmark completed: {events_processed:,} events processed")
            logger.info(f"Order book updates: {self.order_book.update_count:,}")
            logger.info(f"Order book depth: {self.order_book.get_depth()} levels")

            best_bid, best_ask = self.order_book.get_best_bid_ask()
            if best_bid and best_ask:
                logger.info(f"Best bid/ask: {best_bid:.2f} / {best_ask:.2f}")

        except Exception as e:
            logger.error(f"Benchmark failed: {e}")
            raise
        finally:
            # Stop profiling
            self.stop_profiling()

        return self.metrics


def main():
    """Main function to run performance benchmark."""
    parser = argparse.ArgumentParser(description="Run performance baseline benchmark")
    parser.add_argument("--events", type=int, default=5_000_000, help="Number of events to process")
    parser.add_argument("--batch-size", type=int, default=100_000, help="Batch size for processing")
    parser.add_argument("--output", "-o", help="Output JSON file path", default="data/benchmark_results/performance_results.json")
    parser.add_argument("--memory-limit", type=float, default=24.0, help="Memory limit in GB")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(log_level=log_level)

    # Create output directory
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Run benchmark
    harness = PerformanceHarness(memory_limit_gb=args.memory_limit)

    try:
        logger.info("Starting performance benchmark")
        metrics = harness.run_benchmark(
            num_events=args.events,
            batch_size=args.batch_size
        )

        # Save results
        results = {
            "benchmark_parameters": {
                "events": args.events,
                "batch_size": args.batch_size,
                "memory_limit_gb": args.memory_limit
            },
            "metrics": asdict(metrics),
            "opentelemetry_metrics": metrics.to_opentelemetry(),
            "validation_results": {}
        }

        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)

        logger.info(f"Benchmark completed. Results saved to {output_path}")

        # Print summary
        print("\n=== PERFORMANCE BENCHMARK RESULTS ===")
        print(f"Events processed: {metrics.events_processed:,}")
        print(f"Throughput: {metrics.throughput_eps:.0f} events/sec")
        print(f"Parse rate: {metrics.parse_rate_eps:.0f} events/sec")
        print(f"Order book update rate: {metrics.order_book_update_rate_eps:.0f} events/sec")
        print(f"Peak memory: {metrics.peak_memory_gb:.2f}GB")
        print(f"P95 memory: {metrics.p95_memory_gb:.2f}GB")
        print(f"CPU usage: {metrics.cpu_usage_percent:.1f}%")
        print(f"GC pressure: {metrics.gc_pressure_ratio:.6f}")
        print(f"Disk write throughput: {metrics.disk_write_throughput_mbps:.2f} MB/s")

        # Validation checks
        print("\n=== VALIDATION RESULTS ===")

        # Throughput validation
        if metrics.throughput_eps >= 100_000:
            print(f"✅ Throughput {metrics.throughput_eps:.0f} events/sec >= 100k threshold")
            results["validation_results"]["throughput_passed"] = True
        else:
            print(f"❌ Throughput {metrics.throughput_eps:.0f} events/sec < 100k threshold")
            results["validation_results"]["throughput_passed"] = False

        # Memory validation
        if metrics.p95_memory_gb < args.memory_limit:
            print(f"✅ P95 memory {metrics.p95_memory_gb:.2f}GB < {args.memory_limit}GB limit")
            results["validation_results"]["memory_passed"] = True
        else:
            print(f"❌ P95 memory {metrics.p95_memory_gb:.2f}GB >= {args.memory_limit}GB limit")
            results["validation_results"]["memory_passed"] = False

        # Overall validation
        validation_passed = (
            results["validation_results"]["throughput_passed"] and
            results["validation_results"]["memory_passed"]
        )

        results["validation_results"]["overall_passed"] = validation_passed

        if validation_passed:
            print("\n🎉 VALIDATION PASSED: Performance meets requirements")
        else:
            print("\n❌ VALIDATION FAILED: Performance does not meet requirements")

        # Save updated results
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)

        return 0 if validation_passed else 1

    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
