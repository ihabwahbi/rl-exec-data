#!/usr/bin/env python3
"""
Delta Feed Analysis Script

Analyzes book_delta_v2 data quality metrics including sequence gaps,
completeness, and memory usage projections for validation purposes.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import psutil

# Add src to path to import our modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import polars as pl
from loguru import logger

from rlx_datapipe.common.logging import setup_logging


class DeltaFeedAnalyzer:
    """Analyzes book_delta_v2 data for sequence gaps and performance metrics."""

    def __init__(self, memory_limit_gb: float = 24.0):
        """
        Initialize analyzer with memory constraints.
        
        Args:
            memory_limit_gb: Maximum memory usage limit in GB
        """
        self.memory_limit_gb = memory_limit_gb
        self.memory_limit_bytes = memory_limit_gb * 1024 * 1024 * 1024

        # Track metrics
        self.metrics = {
            "total_events": 0,
            "sequence_gaps": {
                "count": 0,
                "max_gap": 0,
                "mean_gap": 0.0,
                "gap_ratio_percent": 0.0,
                "gaps_by_size": {}
            },
            "memory_usage": {
                "peak_gb": 0.0,
                "p95_gb": 0.0,
                "events_per_gb": 0.0
            },
            "throughput": {
                "events_per_second": 0.0,
                "mb_per_second": 0.0
            },
            "data_quality": {
                "valid_update_ids": 0,
                "invalid_update_ids": 0,
                "valid_prices": 0,
                "invalid_prices": 0,
                "valid_quantities": 0,
                "invalid_quantities": 0
            }
        }

        # Memory tracking
        self.memory_samples = []
        self.process = psutil.Process()

    def analyze_file(self, file_path: Path) -> dict:
        """
        Analyze a single book_delta_v2 file.
        
        Args:
            file_path: Path to the parquet file
            
        Returns:
            Dictionary containing analysis results
        """
        logger.info(f"Analyzing file: {file_path}")

        try:
            # Read the file with memory monitoring
            start_time = time.time()
            self._record_memory_usage()

            # Read with streaming if file is large
            file_size_mb = file_path.stat().st_size / (1024 * 1024)
            logger.info(f"File size: {file_size_mb:.2f} MB")

            if file_size_mb > 1000:  # > 1GB, use streaming
                return self._analyze_streaming(file_path)
            return self._analyze_batch(file_path)

        except Exception as e:
            logger.error(f"Error analyzing file {file_path}: {e}")
            return {"error": str(e)}

    def _analyze_batch(self, file_path: Path) -> dict:
        """Analyze file in single batch."""
        start_time = time.time()

        # Load data
        df = pl.read_parquet(file_path)
        self._record_memory_usage()

        # Basic validation
        if df.is_empty():
            logger.warning(f"File {file_path} is empty")
            return {"error": "Empty file"}

        # Check for required columns
        required_cols = ["update_id", "origin_time", "side", "price", "new_quantity"]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            logger.error(f"Missing required columns: {missing_cols}")
            return {"error": f"Missing columns: {missing_cols}"}

        # Sort by update_id for sequence analysis
        df = df.sort("update_id")
        self._record_memory_usage()

        # Analyze sequence gaps
        self._analyze_sequence_gaps(df)

        # Analyze data quality
        self._analyze_data_quality(df)

        # Calculate throughput
        end_time = time.time()
        processing_time = end_time - start_time
        self.metrics["throughput"]["events_per_second"] = len(df) / processing_time

        # Calculate memory efficiency
        peak_memory_gb = max(self.memory_samples) / (1024 * 1024 * 1024)
        self.metrics["memory_usage"]["peak_gb"] = peak_memory_gb
        self.metrics["memory_usage"]["events_per_gb"] = len(df) / peak_memory_gb if peak_memory_gb > 0 else 0

        # Calculate P95 memory usage
        if len(self.memory_samples) > 0:
            p95_index = int(len(self.memory_samples) * 0.95)
            self.metrics["memory_usage"]["p95_gb"] = sorted(self.memory_samples)[p95_index] / (1024 * 1024 * 1024)

        return self.metrics

    def _analyze_streaming(self, file_path: Path) -> dict:
        """Analyze file using streaming to handle large files."""
        logger.info("Using streaming analysis for large file")

        # Use batch reading for large files
        batch_size = 100000  # 100k records per batch
        total_events = 0
        last_update_id = None

        start_time = time.time()

        try:
            # Read in batches
            for batch in pl.read_parquet(file_path, batch_size=batch_size):
                self._record_memory_usage()

                # Process each batch
                if not batch.is_empty():
                    batch = batch.sort("update_id")

                    # Analyze sequence gaps within batch
                    self._analyze_sequence_gaps_batch(batch, last_update_id)

                    # Update counters
                    total_events += len(batch)

                    # Get last update_id for next batch
                    last_update_id = batch.select(pl.col("update_id").max()).item()

                # Check memory usage
                current_memory_gb = self.process.memory_info().rss / (1024 * 1024 * 1024)
                if current_memory_gb > self.memory_limit_gb * 0.9:
                    logger.warning(f"Memory usage {current_memory_gb:.2f}GB approaching limit")

        except Exception as e:
            logger.error(f"Error in streaming analysis: {e}")
            return {"error": str(e)}

        # Calculate final metrics
        end_time = time.time()
        processing_time = end_time - start_time
        self.metrics["total_events"] = total_events
        self.metrics["throughput"]["events_per_second"] = total_events / processing_time

        # Calculate memory efficiency
        peak_memory_gb = max(self.memory_samples) / (1024 * 1024 * 1024)
        self.metrics["memory_usage"]["peak_gb"] = peak_memory_gb
        self.metrics["memory_usage"]["events_per_gb"] = total_events / peak_memory_gb if peak_memory_gb > 0 else 0

        return self.metrics

    def _analyze_sequence_gaps(self, df: pl.DataFrame) -> None:
        """Analyze sequence gaps in update_id column."""
        logger.info("Analyzing sequence gaps...")

        # Calculate differences between consecutive update_ids
        update_ids = df.select("update_id").to_series().to_list()

        if len(update_ids) < 2:
            logger.warning("Not enough data to analyze sequence gaps")
            return

        gaps = []
        for i in range(1, len(update_ids)):
            diff = update_ids[i] - update_ids[i-1]
            if diff > 1:
                gaps.append(diff - 1)  # Gap size (excluding the expected increment of 1)

        self.metrics["total_events"] = len(df)
        self.metrics["sequence_gaps"]["count"] = len(gaps)

        if gaps:
            self.metrics["sequence_gaps"]["max_gap"] = max(gaps)
            self.metrics["sequence_gaps"]["mean_gap"] = sum(gaps) / len(gaps)

            # Calculate gap ratio
            total_possible_gaps = update_ids[-1] - update_ids[0]
            actual_gaps = sum(gaps)
            self.metrics["sequence_gaps"]["gap_ratio_percent"] = (actual_gaps / total_possible_gaps) * 100

            # Group gaps by size
            gap_sizes = {}
            for gap in gaps:
                size_bucket = self._get_gap_size_bucket(gap)
                gap_sizes[size_bucket] = gap_sizes.get(size_bucket, 0) + 1

            self.metrics["sequence_gaps"]["gaps_by_size"] = gap_sizes

            logger.info(f"Found {len(gaps)} sequence gaps, max gap: {max(gaps)}, ratio: {self.metrics['sequence_gaps']['gap_ratio_percent']:.4f}%")
        else:
            logger.info("No sequence gaps found")

    def _analyze_sequence_gaps_batch(self, batch: pl.DataFrame, last_update_id: int | None) -> None:
        """Analyze sequence gaps within a batch (for streaming)."""
        update_ids = batch.select("update_id").to_series().to_list()

        # Check gap from previous batch
        if last_update_id is not None and len(update_ids) > 0:
            gap = update_ids[0] - last_update_id
            if gap > 1:
                self.metrics["sequence_gaps"]["count"] += 1
                gap_size = gap - 1
                self.metrics["sequence_gaps"]["max_gap"] = max(self.metrics["sequence_gaps"]["max_gap"], gap_size)

        # Check gaps within batch
        for i in range(1, len(update_ids)):
            diff = update_ids[i] - update_ids[i-1]
            if diff > 1:
                self.metrics["sequence_gaps"]["count"] += 1
                gap_size = diff - 1
                self.metrics["sequence_gaps"]["max_gap"] = max(self.metrics["sequence_gaps"]["max_gap"], gap_size)

    def _analyze_data_quality(self, df: pl.DataFrame) -> None:
        """Analyze data quality metrics."""
        logger.info("Analyzing data quality...")

        # Check update_id validity
        valid_update_ids = df.filter(pl.col("update_id") > 0).height
        self.metrics["data_quality"]["valid_update_ids"] = valid_update_ids
        self.metrics["data_quality"]["invalid_update_ids"] = len(df) - valid_update_ids

        # Check price validity (should be positive)
        try:
            valid_prices = df.filter(pl.col("price") > 0).height
            self.metrics["data_quality"]["valid_prices"] = valid_prices
            self.metrics["data_quality"]["invalid_prices"] = len(df) - valid_prices
        except Exception as e:
            logger.warning(f"Error checking price validity: {e}")

        # Check quantity validity (should be >= 0)
        try:
            valid_quantities = df.filter(pl.col("new_quantity") >= 0).height
            self.metrics["data_quality"]["valid_quantities"] = valid_quantities
            self.metrics["data_quality"]["invalid_quantities"] = len(df) - valid_quantities
        except Exception as e:
            logger.warning(f"Error checking quantity validity: {e}")

    def _get_gap_size_bucket(self, gap: int) -> str:
        """Categorize gaps by size."""
        if gap <= 10:
            return "1-10"
        if gap <= 100:
            return "11-100"
        if gap <= 1000:
            return "101-1000"
        return "1000+"

    def _record_memory_usage(self) -> None:
        """Record current memory usage."""
        memory_bytes = self.process.memory_info().rss
        self.memory_samples.append(memory_bytes)

        # Check if we're approaching memory limit
        memory_gb = memory_bytes / (1024 * 1024 * 1024)
        if memory_gb > self.memory_limit_gb * 0.9:
            logger.warning(f"Memory usage {memory_gb:.2f}GB approaching limit of {self.memory_limit_gb}GB")


def main():
    """Main function to run delta feed analysis."""
    parser = argparse.ArgumentParser(description="Analyze book_delta_v2 data quality")
    parser.add_argument("input_path", help="Path to input parquet file or directory")
    parser.add_argument("--output", "-o", help="Output JSON file path", default="delta_analysis_results.json")
    parser.add_argument("--memory-limit", type=float, default=24.0, help="Memory limit in GB (default: 24.0)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(log_level=log_level)

    # Validate input path
    input_path = Path(args.input_path)
    if not input_path.exists():
        logger.error(f"Input path does not exist: {input_path}")
        sys.exit(1)

    # Initialize analyzer
    analyzer = DeltaFeedAnalyzer(memory_limit_gb=args.memory_limit)

    # Analyze files
    results = {
        "analysis_timestamp": time.time(),
        "input_path": str(input_path),
        "memory_limit_gb": args.memory_limit,
        "files_analyzed": [],
        "combined_metrics": {}
    }

    try:
        if input_path.is_file():
            # Single file analysis
            file_results = analyzer.analyze_file(input_path)
            results["files_analyzed"] = [str(input_path)]
            results["combined_metrics"] = file_results
        else:
            # Directory analysis
            parquet_files = list(input_path.glob("*.parquet"))
            if not parquet_files:
                logger.error(f"No parquet files found in {input_path}")
                sys.exit(1)

            logger.info(f"Found {len(parquet_files)} parquet files")

            # For now, analyze first file as proof of concept
            # In production, we'd aggregate metrics across all files
            file_results = analyzer.analyze_file(parquet_files[0])
            results["files_analyzed"] = [str(parquet_files[0])]
            results["combined_metrics"] = file_results

    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        results["error"] = str(e)

    # Save results
    output_path = Path(args.output)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    logger.info(f"Analysis complete. Results saved to {output_path}")

    # Print summary
    if "error" not in results:
        metrics = results["combined_metrics"]
        if "error" not in metrics:
            logger.info(f"Total events: {metrics['total_events']}")
            logger.info(f"Sequence gaps: {metrics['sequence_gaps']['count']}")
            logger.info(f"Gap ratio: {metrics['sequence_gaps']['gap_ratio_percent']:.4f}%")
            logger.info(f"Peak memory: {metrics['memory_usage']['peak_gb']:.2f}GB")
            logger.info(f"Throughput: {metrics['throughput']['events_per_second']:.0f} events/sec")

            # Check validation criteria
            logger.info("\\n=== VALIDATION RESULTS ===")

            gap_ratio = metrics["sequence_gaps"]["gap_ratio_percent"]
            if gap_ratio < 0.1:
                logger.info(f"✅ Gap ratio {gap_ratio:.4f}% < 0.1% threshold")
            else:
                logger.error(f"❌ Gap ratio {gap_ratio:.4f}% >= 0.1% threshold")

            p95_memory = metrics["memory_usage"]["p95_gb"]
            if p95_memory < 24.0:
                logger.info(f"✅ P95 memory {p95_memory:.2f}GB < 24GB threshold")
            else:
                logger.error(f"❌ P95 memory {p95_memory:.2f}GB >= 24GB threshold")

            throughput = metrics["throughput"]["events_per_second"]
            if throughput >= 100000:
                logger.info(f"✅ Throughput {throughput:.0f} events/sec >= 100k threshold")
            else:
                logger.error(f"❌ Throughput {throughput:.0f} events/sec < 100k threshold")


if __name__ == "__main__":
    main()
