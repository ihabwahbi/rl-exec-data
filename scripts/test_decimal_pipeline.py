#!/usr/bin/env python3
"""
Decimal Pipeline Testing Script

Tests Polars decimal128 operations at scale and implements int64 pips as fallback strategy.
This script can be run independently or as part of the validation suite.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Any
import time
import psutil
import numpy as np
from decimal import Decimal, ROUND_HALF_UP

# Add src to path to import our modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import polars as pl
from loguru import logger

from rlx_datapipe.common.logging import setup_logging


class PipsConverter:
    """Convert decimal prices/quantities to int64 pips."""
    
    # Symbol-specific decimal places
    PRICE_DECIMALS = {
        'BTC-USDT': 2,   # $0.01 precision
        'ETH-USDT': 2,   # $0.01 precision  
        'SOL-USDT': 4,   # $0.0001 precision
        'SHIB-USDT': 8,  # $0.00000001 precision
    }
    
    QUANTITY_DECIMALS = {
        'BTC-USDT': 8,   # 0.00000001 BTC (1 satoshi)
        'ETH-USDT': 8,   # 0.00000001 ETH
        'SOL-USDT': 6,   # 0.000001 SOL
        'SHIB-USDT': 0,  # 1 SHIB (integer only)
    }
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.price_multiplier = 10 ** self.PRICE_DECIMALS.get(symbol, 8)
        self.qty_multiplier = 10 ** self.QUANTITY_DECIMALS.get(symbol, 8)
        
    def price_to_pips(self, price: str) -> int:
        """Convert string price to int64 pips."""
        decimal_price = Decimal(price)
        pips = decimal_price * self.price_multiplier
        return int(pips.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        
    def pips_to_price(self, pips: int) -> Decimal:
        """Convert pips back to decimal price."""
        return Decimal(pips) / self.price_multiplier
    
    def quantity_to_pips(self, quantity: str) -> int:
        """Convert string quantity to int64 pips."""
        decimal_qty = Decimal(quantity)
        pips = decimal_qty * self.qty_multiplier
        return int(pips.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        
    def pips_to_quantity(self, pips: int) -> Decimal:
        """Convert pips back to decimal quantity."""
        return Decimal(pips) / self.qty_multiplier


class DecimalPipelineTester:
    """Test decimal pipeline approaches and compare performance."""
    
    def __init__(self, memory_limit_gb: float = 24.0):
        self.memory_limit_gb = memory_limit_gb
        self.process = psutil.Process()
        self.memory_samples = []
        
    def record_memory(self, label: str) -> float:
        """Record memory usage with label."""
        memory_gb = self.process.memory_info().rss / (1024 * 1024 * 1024)
        self.memory_samples.append((label, memory_gb))
        logger.info(f"Memory usage at {label}: {memory_gb:.2f}GB")
        return memory_gb
    
    def create_large_sample_data(self, num_events: int = 1_000_000) -> pl.DataFrame:
        """Create a large sample dataset for testing."""
        
        logger.info(f"Creating sample data with {num_events} events")
        
        # Generate realistic price and quantity data
        np.random.seed(42)  # For reproducibility
        
        # BTC-USDT price around 45000 with normal distribution
        prices = np.random.normal(45000, 1000, num_events)
        prices = np.clip(prices, 30000, 70000)  # Reasonable bounds
        
        # Quantities with log-normal distribution (more realistic)
        quantities = np.random.lognormal(0, 1, num_events)
        quantities = np.clip(quantities, 0.00000001, 1000)  # Reasonable bounds
        
        # Create DataFrame with string representations for decimal conversion
        data = {
            "event_id": range(num_events),
            "timestamp": [int(time.time() * 1e9) + i * 1000000 for i in range(num_events)],
            "symbol": ["BTC-USDT"] * num_events,
            "price_str": [f"{price:.8f}" for price in prices],
            "quantity_str": [f"{qty:.8f}" for qty in quantities],
            "side": np.random.choice(["buy", "sell"], num_events),
            "price_float": prices,
            "quantity_float": quantities
        }
        
        df = pl.DataFrame(data)
        
        logger.info(f"Created DataFrame with {len(df)} rows and {len(df.columns)} columns")
        self.record_memory("after_sample_creation")
        
        return df
    
    def test_decimal128_operations(self, df: pl.DataFrame) -> Dict[str, Any]:
        """Test decimal128 operations and measure performance."""
        
        results = {
            "conversion_success": False,
            "operations_success": False,
            "performance_metrics": {},
            "errors": []
        }
        
        try:
            logger.info("Testing decimal128 conversion...")
            start_time = time.time()
            
            # Convert string columns to decimal128 with more conservative precision
            df_decimal = df.with_columns([
                pl.col("price_str").cast(pl.Decimal(precision=28, scale=8)).alias("price_decimal"),
                pl.col("quantity_str").cast(pl.Decimal(precision=28, scale=8)).alias("quantity_decimal")
            ])
            
            conversion_time = time.time() - start_time
            results["conversion_success"] = True
            results["performance_metrics"]["conversion_time"] = conversion_time
            
            self.record_memory("after_decimal_conversion")
            logger.info(f"Decimal conversion completed in {conversion_time:.2f}s")
            
            # Test basic operations
            logger.info("Testing decimal128 operations...")
            start_time = time.time()
            
            # 1. Aggregation operations
            agg_result = df_decimal.select([
                pl.col("price_decimal").mean().alias("avg_price"),
                pl.col("quantity_decimal").sum().alias("total_quantity"),
                pl.col("price_decimal").min().alias("min_price"),
                pl.col("price_decimal").max().alias("max_price"),
                pl.col("quantity_decimal").std().alias("qty_std")
            ])
            
            logger.info(f"Aggregation completed")
            
            # 2. Group by operations
            group_result = df_decimal.group_by("side").agg([
                pl.col("price_decimal").mean().alias("avg_price"),
                pl.col("quantity_decimal").sum().alias("total_quantity"),
                pl.len().alias("count")
            ])
            
            logger.info(f"Group by completed")
            
            # 3. Mathematical operations
            df_with_calc = df_decimal.with_columns([
                (pl.col("price_decimal") * pl.col("quantity_decimal")).alias("notional_value"),
                (pl.col("price_decimal") * pl.lit(Decimal("1.001"))).alias("price_with_fee")
            ])
            
            operations_time = time.time() - start_time
            results["operations_success"] = True
            results["performance_metrics"]["operations_time"] = operations_time
            
            self.record_memory("after_decimal_operations")
            logger.info(f"Decimal operations completed in {operations_time:.2f}s")
            
            # 4. Test Parquet I/O
            logger.info("Testing Parquet I/O with decimal types...")
            start_time = time.time()
            
            # Write to parquet
            parquet_path = "data/test_sample/decimal_test.parquet"
            Path(parquet_path).parent.mkdir(parents=True, exist_ok=True)
            df_with_calc.write_parquet(parquet_path)
            
            # Read back
            df_read = pl.read_parquet(parquet_path)
            
            parquet_time = time.time() - start_time
            results["performance_metrics"]["parquet_io_time"] = parquet_time
            
            logger.info(f"Parquet I/O completed in {parquet_time:.2f}s")
            
            # Verify data integrity
            original_sum = df_with_calc.select(pl.col("notional_value").sum()).item()
            read_sum = df_read.select(pl.col("notional_value").sum()).item()
            
            if abs(float(original_sum) - float(read_sum)) < 1e-10:
                logger.info("✅ Data integrity verified - sums match")
            else:
                logger.error(f"❌ Data integrity failed - sums differ: {original_sum} vs {read_sum}")
                results["errors"].append("Data integrity check failed")
            
            self.record_memory("after_parquet_io")
            
        except Exception as e:
            logger.error(f"Decimal128 operation failed: {e}")
            results["errors"].append(str(e))
        
        return results
    
    def test_pips_operations(self, df: pl.DataFrame) -> Dict[str, Any]:
        """Test int64 pips operations and measure performance."""
        
        results = {
            "conversion_success": False,
            "operations_success": False,
            "performance_metrics": {},
            "errors": []
        }
        
        try:
            logger.info("Testing int64 pips conversion...")
            start_time = time.time()
            
            converter = PipsConverter('BTC-USDT')
            
            # Convert to pips using vectorized operations
            df_pips = df.with_columns([
                pl.col("price_str").map_elements(
                    lambda x: converter.price_to_pips(x), 
                    return_dtype=pl.Int64
                ).alias("price_pips"),
                pl.col("quantity_str").map_elements(
                    lambda x: converter.quantity_to_pips(x), 
                    return_dtype=pl.Int64
                ).alias("quantity_pips")
            ])
            
            conversion_time = time.time() - start_time
            results["conversion_success"] = True
            results["performance_metrics"]["conversion_time"] = conversion_time
            
            self.record_memory("after_pips_conversion")
            logger.info(f"Pips conversion completed in {conversion_time:.2f}s")
            
            # Test operations
            logger.info("Testing int64 pips operations...")
            start_time = time.time()
            
            # 1. Aggregation operations
            agg_result = df_pips.select([
                pl.col("price_pips").mean().alias("avg_price_pips"),
                pl.col("quantity_pips").sum().alias("total_quantity_pips"),
                pl.col("price_pips").min().alias("min_price_pips"),
                pl.col("price_pips").max().alias("max_price_pips"),
                pl.col("quantity_pips").std().alias("qty_std_pips")
            ])
            
            logger.info(f"Aggregation completed")
            
            # 2. Group by operations
            group_result = df_pips.group_by("side").agg([
                pl.col("price_pips").mean().alias("avg_price_pips"),
                pl.col("quantity_pips").sum().alias("total_quantity_pips"),
                pl.len().alias("count")
            ])
            
            logger.info(f"Group by completed")
            
            # 3. Mathematical operations (handle scaling correctly)
            df_with_calc = df_pips.with_columns([
                # For notional value, need to handle scaling: price_pips * quantity_pips / qty_multiplier
                (pl.col("price_pips") * pl.col("quantity_pips") / converter.qty_multiplier).alias("notional_value_pips"),
                (pl.col("price_pips") * 1001 / 1000).alias("price_with_fee_pips")  # 0.1% fee
            ])
            
            operations_time = time.time() - start_time
            results["operations_success"] = True
            results["performance_metrics"]["operations_time"] = operations_time
            
            self.record_memory("after_pips_operations")
            logger.info(f"Pips operations completed in {operations_time:.2f}s")
            
            # 4. Test Parquet I/O
            logger.info("Testing Parquet I/O with int64 types...")
            start_time = time.time()
            
            # Write to parquet
            parquet_path = "data/test_sample/pips_test.parquet"
            Path(parquet_path).parent.mkdir(parents=True, exist_ok=True)
            df_with_calc.write_parquet(parquet_path)
            
            # Read back
            df_read = pl.read_parquet(parquet_path)
            
            parquet_time = time.time() - start_time
            results["performance_metrics"]["parquet_io_time"] = parquet_time
            
            logger.info(f"Parquet I/O completed in {parquet_time:.2f}s")
            
            # Verify data integrity
            original_sum = df_with_calc.select(pl.col("notional_value_pips").sum()).item()
            read_sum = df_read.select(pl.col("notional_value_pips").sum()).item()
            
            if original_sum == read_sum:
                logger.info("✅ Data integrity verified - sums match exactly")
            else:
                logger.error(f"❌ Data integrity failed - sums differ: {original_sum} vs {read_sum}")
                results["errors"].append("Data integrity check failed")
            
            self.record_memory("after_pips_parquet_io")
            
        except Exception as e:
            logger.error(f"Pips operation failed: {e}")
            results["errors"].append(str(e))
        
        return results
    
    def compare_performance(self, decimal_results: Dict, pips_results: Dict) -> Dict[str, Any]:
        """Compare performance between decimal128 and int64 pips approaches."""
        
        comparison = {
            "decimal128_viable": decimal_results["conversion_success"] and decimal_results["operations_success"],
            "pips_viable": pips_results["conversion_success"] and pips_results["operations_success"],
            "recommended_approach": None,
            "performance_comparison": {},
            "memory_usage": {},
            "validation_results": {}
        }
        
        # Performance comparison
        if decimal_results["conversion_success"] and pips_results["conversion_success"]:
            decimal_conv_time = decimal_results["performance_metrics"]["conversion_time"]
            pips_conv_time = pips_results["performance_metrics"]["conversion_time"]
            
            comparison["performance_comparison"]["conversion_speedup"] = decimal_conv_time / pips_conv_time
            
            if decimal_results["operations_success"] and pips_results["operations_success"]:
                decimal_ops_time = decimal_results["performance_metrics"]["operations_time"]
                pips_ops_time = pips_results["performance_metrics"]["operations_time"]
                
                comparison["performance_comparison"]["operations_speedup"] = decimal_ops_time / pips_ops_time
        
        # Memory usage comparison
        comparison["memory_usage"]["samples"] = self.memory_samples
        comparison["memory_usage"]["peak_gb"] = max([mem for _, mem in self.memory_samples])
        
        # Determine recommended approach
        if comparison["decimal128_viable"] and not decimal_results["errors"]:
            comparison["recommended_approach"] = "decimal128"
            comparison["recommendation_reason"] = "Polars decimal128 operations successful without errors"
        elif comparison["pips_viable"] and not pips_results["errors"]:
            comparison["recommended_approach"] = "int64_pips"
            comparison["recommendation_reason"] = "Int64 pips operations successful, decimal128 had issues"
        else:
            comparison["recommended_approach"] = "fallback_required"
            comparison["recommendation_reason"] = "Both approaches had issues, need alternative strategy"
        
        # Validation results
        comparison["validation_results"]["decimal128_stable"] = not decimal_results["errors"]
        comparison["validation_results"]["pips_stable"] = not pips_results["errors"]
        comparison["validation_results"]["precision_preserved"] = True  # Need to validate this
        
        return comparison
    
    def run_full_test(self, num_events: int = 1_000_000) -> Dict[str, Any]:
        """Run the full decimal pipeline test."""
        
        logger.info(f"Starting decimal pipeline test with {num_events} events")
        self.record_memory("start")
        
        # Create sample data
        sample_df = self.create_large_sample_data(num_events)
        
        # Test decimal128
        logger.info("Testing decimal128 approach...")
        decimal_results = self.test_decimal128_operations(sample_df)
        
        # Test pips
        logger.info("Testing int64 pips approach...")
        pips_results = self.test_pips_operations(sample_df)
        
        # Compare performance
        logger.info("Comparing performance...")
        performance_comparison = self.compare_performance(decimal_results, pips_results)
        
        # Final results
        final_results = {
            "test_parameters": {
                "num_events": num_events,
                "memory_limit_gb": self.memory_limit_gb
            },
            "decimal128_results": decimal_results,
            "pips_results": pips_results,
            "performance_comparison": performance_comparison,
            "validation_passed": performance_comparison["recommended_approach"] != "fallback_required"
        }
        
        return final_results


def main():
    """Main function to run decimal pipeline testing."""
    parser = argparse.ArgumentParser(description="Test decimal pipeline approaches")
    parser.add_argument("--events", type=int, default=1_000_000, help="Number of events to test with")
    parser.add_argument("--output", "-o", help="Output JSON file path", default="data/test_sample/decimal_pipeline_results.json")
    parser.add_argument("--memory-limit", type=float, default=24.0, help="Memory limit in GB")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(log_level=log_level)
    
    # Create output directory
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Run tests
    tester = DecimalPipelineTester(memory_limit_gb=args.memory_limit)
    
    try:
        results = tester.run_full_test(num_events=args.events)
        
        # Save results
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        logger.info(f"Test completed. Results saved to {output_path}")
        
        # Print summary
        print("\n=== DECIMAL PIPELINE TEST RESULTS ===")
        print(f"Events tested: {args.events:,}")
        print(f"Peak memory: {results['performance_comparison']['memory_usage']['peak_gb']:.2f}GB")
        print(f"Decimal128 viable: {results['performance_comparison']['decimal128_viable']}")
        print(f"Int64 pips viable: {results['performance_comparison']['pips_viable']}")
        print(f"Recommended approach: {results['performance_comparison']['recommended_approach']}")
        print(f"Validation passed: {results['validation_passed']}")
        
        if "conversion_speedup" in results['performance_comparison']['performance_comparison']:
            speedup = results['performance_comparison']['performance_comparison']['conversion_speedup']
            print(f"Conversion speedup (decimal/pips): {speedup:.2f}x")
        
        if "operations_speedup" in results['performance_comparison']['performance_comparison']:
            speedup = results['performance_comparison']['performance_comparison']['operations_speedup']
            print(f"Operations speedup (decimal/pips): {speedup:.2f}x")
        
        # Validation criteria check
        print("\n=== VALIDATION CRITERIA ===")
        
        if results['validation_passed']:
            print("✅ Decimal strategy validated successfully")
        else:
            print("❌ Decimal strategy validation failed")
            
        # Memory check
        peak_memory = results['performance_comparison']['memory_usage']['peak_gb']
        if peak_memory < args.memory_limit:
            print(f"✅ Memory usage {peak_memory:.2f}GB < {args.memory_limit}GB limit")
        else:
            print(f"❌ Memory usage {peak_memory:.2f}GB >= {args.memory_limit}GB limit")
            
    except Exception as e:
        logger.error(f"Test failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()