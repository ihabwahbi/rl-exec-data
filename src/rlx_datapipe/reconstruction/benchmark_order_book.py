"""Performance benchmark for order book engine."""

import gc
import time
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import polars as pl
import psutil
from loguru import logger

from rlx_datapipe.common.decimal_utils import float_to_scaled_int64
from rlx_datapipe.reconstruction.delta_feed_processor import DeltaFeedProcessor
from rlx_datapipe.reconstruction.order_book_engine import OrderBookEngine
from rlx_datapipe.reconstruction.order_book_optimized import (
    apply_delta_batch_optimized,
    update_bounded_levels,
)


class OrderBookBenchmark:
    """Benchmark suite for order book performance."""
    
    def __init__(
        self,
        symbol: str = "BTCUSDT",
        target_throughput: int = 336_000,  # messages/second baseline
        memory_limit_mb: int = 1024,
    ):
        """
        Initialize benchmark.
        
        Args:
            symbol: Trading symbol
            target_throughput: Target messages per second
            memory_limit_mb: Memory limit in MB
        """
        self.symbol = symbol
        self.target_throughput = target_throughput
        self.memory_limit_mb = memory_limit_mb
        self.results = {}
        
        # Get process for memory monitoring
        self.process = psutil.Process()
        
        logger.info(
            f"OrderBookBenchmark initialized with target={target_throughput:,} msg/s, "
            f"memory_limit={memory_limit_mb}MB"
        )
    
    def generate_test_data(
        self,
        num_deltas: int,
        num_snapshots: int = 10,
        price_range: tuple = (40000, 50000),
        quantity_range: tuple = (0.01, 10.0),
    ) -> Dict[str, pl.DataFrame]:
        """
        Generate synthetic test data.
        
        Args:
            num_deltas: Number of delta updates
            num_snapshots: Number of snapshots
            price_range: Price range for generation
            quantity_range: Quantity range
            
        Returns:
            Dictionary with test data
        """
        logger.info(f"Generating {num_deltas:,} deltas and {num_snapshots} snapshots")
        
        # Generate delta updates
        np.random.seed(42)
        
        delta_data = {
            "update_id": np.arange(1000, 1000 + num_deltas),
            "origin_time": np.arange(num_deltas) * 1000,  # 1ms apart
            "price": np.random.uniform(price_range[0], price_range[1], num_deltas),
            "new_quantity": np.random.uniform(quantity_range[0], quantity_range[1], num_deltas),
            "side": np.random.choice(["BID", "ASK"], num_deltas),
        }
        
        # Some updates are removals
        removal_mask = np.random.random(num_deltas) < 0.1
        delta_data["new_quantity"][removal_mask] = 0.0
        
        deltas_df = pl.DataFrame(delta_data)
        
        # Generate snapshots
        snapshot_levels = 20
        snapshots = []
        
        for i in range(num_snapshots):
            # Generate bid levels
            bid_prices = np.linspace(
                price_range[0], 
                np.mean(price_range) - 10,
                snapshot_levels
            )
            bid_quantities = np.random.uniform(
                quantity_range[0],
                quantity_range[1],
                snapshot_levels
            )
            
            # Generate ask levels
            ask_prices = np.linspace(
                np.mean(price_range) + 10,
                price_range[1],
                snapshot_levels
            )
            ask_quantities = np.random.uniform(
                quantity_range[0],
                quantity_range[1],
                snapshot_levels
            )
            
            snapshot_data = {
                "origin_time": [i * num_deltas // num_snapshots * 1000] * (2 * snapshot_levels),
                "update_id": [1000 + i * num_deltas // num_snapshots] * (2 * snapshot_levels),
                "side": ["BID"] * snapshot_levels + ["ASK"] * snapshot_levels,
                "price": np.concatenate([bid_prices, ask_prices]),
                "quantity": np.concatenate([bid_quantities, ask_quantities]),
            }
            
            snapshots.append(pl.DataFrame(snapshot_data))
        
        snapshots_df = pl.concat(snapshots)
        
        return {
            "deltas": deltas_df,
            "snapshots": snapshots_df,
        }
    
    def benchmark_basic_engine(
        self,
        test_data: Dict[str, pl.DataFrame],
    ) -> Dict:
        """
        Benchmark basic order book engine.
        
        Args:
            test_data: Test data dictionary
            
        Returns:
            Benchmark results
        """
        logger.info("Running basic engine benchmark")
        
        # Initialize engine
        engine = OrderBookEngine(
            symbol=self.symbol,
            max_levels=20,
            gc_interval=100_000,
        )
        
        # Convert prices to scaled int64
        deltas_df = test_data["deltas"].with_columns([
            test_data["deltas"]["price"].map_elements(
                lambda x: float_to_scaled_int64(x),
                return_dtype=pl.Int64,
            ).alias("price"),
            test_data["deltas"]["new_quantity"].map_elements(
                lambda x: float_to_scaled_int64(x),
                return_dtype=pl.Int64,
            ).alias("new_quantity"),
        ])
        
        # Measure performance
        gc.collect()
        start_memory = self.process.memory_info().rss / 1024 / 1024
        start_time = time.time()
        
        # Process in chunks
        chunk_size = 10_000
        total_rows = len(deltas_df)
        
        for start_idx in range(0, total_rows, chunk_size):
            end_idx = min(start_idx + chunk_size, total_rows)
            chunk = deltas_df[start_idx:end_idx]
            
            engine.process_delta_batch(chunk)
        
        end_time = time.time()
        end_memory = self.process.memory_info().rss / 1024 / 1024
        
        # Calculate metrics
        elapsed_time = end_time - start_time
        throughput = total_rows / elapsed_time
        memory_used = end_memory - start_memory
        
        results = {
            "name": "Basic Engine",
            "total_messages": total_rows,
            "elapsed_time": elapsed_time,
            "throughput": throughput,
            "memory_used_mb": memory_used,
            "gap_stats": engine.get_statistics()["gap_statistics"],
        }
        
        logger.info(
            f"Basic engine: {throughput:,.0f} msg/s, {memory_used:.1f}MB memory"
        )
        
        return results
    
    def benchmark_optimized_operations(
        self,
        test_data: Dict[str, pl.DataFrame],
    ) -> Dict:
        """
        Benchmark JIT-optimized operations.
        
        Args:
            test_data: Test data dictionary
            
        Returns:
            Benchmark results
        """
        logger.info("Running optimized operations benchmark")
        
        # Prepare data
        deltas_df = test_data["deltas"]
        prices = deltas_df["price"].map_elements(
            lambda x: float_to_scaled_int64(x),
            return_dtype=pl.Int64,
        ).to_numpy()
        quantities = deltas_df["new_quantity"].map_elements(
            lambda x: float_to_scaled_int64(x),
            return_dtype=pl.Int64,
        ).to_numpy()
        sides = (deltas_df["side"] == "ASK").cast(pl.Int8).to_numpy()
        
        # Initialize book arrays
        max_levels = 20
        bid_prices = np.zeros(max_levels, dtype=np.int64)
        bid_quantities = np.zeros(max_levels, dtype=np.int64)
        bid_count = 0
        ask_prices = np.zeros(max_levels, dtype=np.int64)
        ask_quantities = np.zeros(max_levels, dtype=np.int64)
        ask_count = 0
        
        # Warm up JIT
        for i in range(100):
            update_bounded_levels(
                bid_prices, bid_quantities, bid_count, max_levels,
                prices[i], quantities[i], True
            )
        
        # Measure performance
        gc.collect()
        start_memory = self.process.memory_info().rss / 1024 / 1024
        start_time = time.time()
        
        # Process in batches
        batch_size = 10_000
        total_rows = len(prices)
        
        for start_idx in range(0, total_rows, batch_size):
            end_idx = min(start_idx + batch_size, total_rows)
            
            result = apply_delta_batch_optimized(
                bid_prices, bid_quantities, bid_count,
                ask_prices, ask_quantities, ask_count,
                max_levels,
                prices[start_idx:end_idx],
                quantities[start_idx:end_idx],
                sides[start_idx:end_idx],
                end_idx - start_idx,
            )
            
            bid_count, ask_count = result[0], result[1]
        
        end_time = time.time()
        end_memory = self.process.memory_info().rss / 1024 / 1024
        
        # Calculate metrics
        elapsed_time = end_time - start_time
        throughput = total_rows / elapsed_time
        memory_used = end_memory - start_memory
        
        results = {
            "name": "Optimized Operations",
            "total_messages": total_rows,
            "elapsed_time": elapsed_time,
            "throughput": throughput,
            "memory_used_mb": memory_used,
            "speedup": None,  # Will be calculated later
        }
        
        logger.info(
            f"Optimized operations: {throughput:,.0f} msg/s, {memory_used:.1f}MB memory"
        )
        
        return results
    
    def run_full_benchmark(
        self,
        num_deltas: int = 1_000_000,
        num_snapshots: int = 10,
    ) -> Dict:
        """
        Run full benchmark suite.
        
        Args:
            num_deltas: Number of delta updates to test
            num_snapshots: Number of snapshots
            
        Returns:
            Complete benchmark results
        """
        logger.info(f"Starting full benchmark with {num_deltas:,} deltas")
        
        # Generate test data
        test_data = self.generate_test_data(num_deltas, num_snapshots)
        
        # Run benchmarks
        basic_results = self.benchmark_basic_engine(test_data)
        optimized_results = self.benchmark_optimized_operations(test_data)
        
        # Calculate speedup
        optimized_results["speedup"] = (
            optimized_results["throughput"] / basic_results["throughput"]
        )
        
        # Check against target
        meets_target = basic_results["throughput"] >= self.target_throughput
        memory_ok = basic_results["memory_used_mb"] < self.memory_limit_mb
        
        # Summary results
        self.results = {
            "summary": {
                "target_throughput": self.target_throughput,
                "achieved_throughput": basic_results["throughput"],
                "meets_target": meets_target,
                "memory_limit_mb": self.memory_limit_mb,
                "memory_used_mb": basic_results["memory_used_mb"],
                "memory_ok": memory_ok,
                "optimization_speedup": optimized_results["speedup"],
            },
            "basic_engine": basic_results,
            "optimized_ops": optimized_results,
        }
        
        self._print_results()
        
        return self.results
    
    def _print_results(self) -> None:
        """Print formatted benchmark results."""
        summary = self.results["summary"]
        
        print("\n" + "=" * 60)
        print("ORDER BOOK ENGINE BENCHMARK RESULTS")
        print("=" * 60)
        
        print(f"\nTarget Performance:")
        print(f"  - Throughput: {summary['target_throughput']:,} msg/s")
        print(f"  - Memory Limit: {summary['memory_limit_mb']} MB")
        
        print(f"\nAchieved Performance:")
        print(f"  - Throughput: {summary['achieved_throughput']:,.0f} msg/s")
        print(f"  - Memory Used: {summary['memory_used_mb']:.1f} MB")
        print(f"  - Meets Target: {'✓' if summary['meets_target'] else '✗'}")
        print(f"  - Memory OK: {'✓' if summary['memory_ok'] else '✗'}")
        
        print(f"\nOptimization Results:")
        print(f"  - JIT Speedup: {summary['optimization_speedup']:.2f}x")
        
        print("\n" + "=" * 60)


def main():
    """Run benchmark from command line."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Order Book Engine Benchmark")
    parser.add_argument(
        "--deltas",
        type=int,
        default=1_000_000,
        help="Number of delta updates to benchmark",
    )
    parser.add_argument(
        "--target",
        type=int,
        default=336_000,
        help="Target throughput (msg/s)",
    )
    parser.add_argument(
        "--memory",
        type=int,
        default=1024,
        help="Memory limit (MB)",
    )
    
    args = parser.parse_args()
    
    benchmark = OrderBookBenchmark(
        target_throughput=args.target,
        memory_limit_mb=args.memory,
    )
    
    results = benchmark.run_full_benchmark(num_deltas=args.deltas)
    
    # Return exit code based on meeting targets
    if results["summary"]["meets_target"] and results["summary"]["memory_ok"]:
        return 0
    else:
        return 1


if __name__ == "__main__":
    exit(main())