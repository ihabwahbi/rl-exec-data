#!/usr/bin/env python3
"""
I/O Endurance Analysis Script

Calculate total read/write volume for 12-month processing, measure sustained disk throughput,
and document SSD wear calculations (TBW) for hardware planning.
"""

import argparse
import json
import sys
import time
import os
import threading
from pathlib import Path
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass, asdict
import tempfile
import shutil
import psutil

# Add src to path to import our modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import polars as pl
import numpy as np
from loguru import logger

from rlx_datapipe.common.logging import setup_logging
from rlx_datapipe.analysis.delta_analyzer import create_sample_delta_data


@dataclass
class IORequirements:
    """Container for I/O requirements analysis."""
    # Data volume calculations
    total_read_volume_tb: float = 0.0
    total_write_volume_tb: float = 0.0
    compressed_read_volume_tb: float = 0.0
    uncompressed_read_volume_tb: float = 0.0
    
    # Throughput measurements
    sustained_read_mbps: float = 0.0
    sustained_write_mbps: float = 0.0
    peak_read_mbps: float = 0.0
    peak_write_mbps: float = 0.0
    
    # Hardware requirements
    ssd_tbw_required: float = 0.0
    ssd_lifetime_years: float = 0.0
    memory_bandwidth_mbps: float = 0.0
    
    # Processing time estimates
    single_thread_processing_days: float = 0.0
    parallel_processing_days: float = 0.0
    
    # Validation results
    can_sustain_150_200_mbps: bool = False
    meets_24_hour_processing: bool = False
    hardware_adequate: bool = False


class IOEnduranceAnalyzer:
    """Analyzes I/O requirements and endurance for 12-month processing."""
    
    def __init__(self, test_duration_seconds: int = 300):
        """
        Initialize I/O analyzer.
        
        Args:
            test_duration_seconds: Duration for sustained I/O testing
        """
        self.test_duration_seconds = test_duration_seconds
        self.requirements = IORequirements()
        
        # Market data assumptions (based on research)
        self.market_data_assumptions = {
            "symbols": ["BTC-USDT", "ETH-USDT", "SOL-USDT"],
            "events_per_hour": {
                "BTC-USDT": 8_000_000,  # High volume
                "ETH-USDT": 6_000_000,  # Medium-high volume
                "SOL-USDT": 4_000_000,  # Medium volume
            },
            "bytes_per_event": {
                "raw_delta": 120,  # JSON format
                "compressed_delta": 40,  # Parquet compressed
                "unified_event": 150,  # Unified schema
            },
            "compression_ratio": 0.33,  # 33% of original size
            "days_per_year": 365,
            "hours_per_day": 24,
        }
        
        # Hardware assumptions
        self.hardware_assumptions = {
            "ssd_tbw_rating": 3000,  # TBW rating for enterprise SSD
            "ssd_warranty_years": 5,
            "memory_bandwidth_gbps": 50,  # DDR4-3200 dual channel
            "cpu_cores": 8,  # Assuming 8-core processor
            "parallel_efficiency": 0.7,  # 70% efficiency for parallel processing
        }
    
    def calculate_data_volumes(self) -> Dict[str, float]:
        """Calculate total data volumes for 12-month processing."""
        logger.info("Calculating data volumes for 12-month processing")
        
        total_events = 0
        total_raw_bytes = 0
        total_compressed_bytes = 0
        total_unified_bytes = 0
        
        # Calculate for each symbol
        for symbol, events_per_hour in self.market_data_assumptions["events_per_hour"].items():
            # Events per year
            events_per_year = (
                events_per_hour * 
                self.market_data_assumptions["hours_per_day"] * 
                self.market_data_assumptions["days_per_year"]
            )
            
            total_events += events_per_year
            
            # Raw data volume
            raw_bytes = events_per_year * self.market_data_assumptions["bytes_per_event"]["raw_delta"]
            total_raw_bytes += raw_bytes
            
            # Compressed data volume
            compressed_bytes = events_per_year * self.market_data_assumptions["bytes_per_event"]["compressed_delta"]
            total_compressed_bytes += compressed_bytes
            
            # Unified event volume (output)
            unified_bytes = events_per_year * self.market_data_assumptions["bytes_per_event"]["unified_event"]
            total_unified_bytes += unified_bytes
            
            logger.info(f"{symbol}: {events_per_year:,} events/year, "
                       f"{raw_bytes / 1e12:.2f}TB raw, "
                       f"{compressed_bytes / 1e12:.2f}TB compressed")
        
        # Convert to TB
        self.requirements.uncompressed_read_volume_tb = total_raw_bytes / 1e12
        self.requirements.compressed_read_volume_tb = total_compressed_bytes / 1e12
        self.requirements.total_read_volume_tb = total_compressed_bytes / 1e12  # We read compressed
        self.requirements.total_write_volume_tb = total_unified_bytes / 1e12
        
        logger.info(f"Total events: {total_events:,}")
        logger.info(f"Total read volume (compressed): {self.requirements.total_read_volume_tb:.2f}TB")
        logger.info(f"Total write volume (unified): {self.requirements.total_write_volume_tb:.2f}TB")
        
        return {
            "total_events": total_events,
            "read_volume_tb": self.requirements.total_read_volume_tb,
            "write_volume_tb": self.requirements.total_write_volume_tb,
            "uncompressed_read_tb": self.requirements.uncompressed_read_volume_tb,
        }
    
    def calculate_processing_time(self, total_events: int) -> Dict[str, float]:
        """Calculate processing time estimates."""
        logger.info("Calculating processing time estimates")
        
        # Assume 100k events/sec throughput (validation target)
        target_throughput_eps = 100_000
        
        # Single-threaded processing time
        single_thread_seconds = total_events / target_throughput_eps
        single_thread_days = single_thread_seconds / (24 * 3600)
        
        # Parallel processing time (with efficiency factor)
        parallel_throughput = (
            target_throughput_eps * 
            self.hardware_assumptions["cpu_cores"] * 
            self.hardware_assumptions["parallel_efficiency"]
        )
        parallel_seconds = total_events / parallel_throughput
        parallel_days = parallel_seconds / (24 * 3600)
        
        self.requirements.single_thread_processing_days = single_thread_days
        self.requirements.parallel_processing_days = parallel_days
        
        logger.info(f"Single-threaded processing: {single_thread_days:.1f} days")
        logger.info(f"Parallel processing ({self.hardware_assumptions['cpu_cores']} cores): {parallel_days:.1f} days")
        
        # Check if meets 24-hour processing requirement
        # We need to process 1 month of data in 24 hours, not 12 months
        # So divide by 12 to get monthly processing time
        monthly_parallel_days = parallel_days / 12
        self.requirements.meets_24_hour_processing = monthly_parallel_days <= 1.0
        
        return {
            "single_thread_days": single_thread_days,
            "parallel_days": parallel_days,
            "meets_24h_target": self.requirements.meets_24_hour_processing,
        }
    
    def calculate_ssd_wear(self) -> Dict[str, float]:
        """Calculate SSD wear and lifetime."""
        logger.info("Calculating SSD wear and lifetime")
        
        # Total data written (read + write operations)
        total_written_tb = self.requirements.total_read_volume_tb + self.requirements.total_write_volume_tb
        
        # Add overhead for temporary files, checkpoints, etc.
        overhead_factor = 1.5  # 50% overhead
        total_written_with_overhead = total_written_tb * overhead_factor
        
        self.requirements.ssd_tbw_required = total_written_with_overhead
        
        # Calculate lifetime
        ssd_tbw_rating = self.hardware_assumptions["ssd_tbw_rating"]
        if total_written_with_overhead <= ssd_tbw_rating:
            # If we can do it in one processing run
            self.requirements.ssd_lifetime_years = self.hardware_assumptions["ssd_warranty_years"]
        else:
            # Calculate how many processing runs the SSD can handle
            processing_runs = ssd_tbw_rating / total_written_with_overhead
            self.requirements.ssd_lifetime_years = processing_runs * self.hardware_assumptions["ssd_warranty_years"]
        
        logger.info(f"SSD TBW required: {self.requirements.ssd_tbw_required:.2f}TB")
        logger.info(f"SSD lifetime: {self.requirements.ssd_lifetime_years:.1f} years")
        
        return {
            "tbw_required": self.requirements.ssd_tbw_required,
            "lifetime_years": self.requirements.ssd_lifetime_years,
            "adequate": self.requirements.ssd_lifetime_years >= 1.0,
        }
    
    def measure_sustained_throughput(self, test_size_mb: int = 10) -> Dict[str, float]:
        """Measure sustained disk throughput."""
        logger.info(f"Measuring sustained disk throughput for {self.test_duration_seconds} seconds")
        
        # Create test directory
        test_dir = Path(tempfile.mkdtemp(prefix="io_endurance_test_"))
        
        try:
            # Measure write throughput
            write_throughput = self._measure_write_throughput(test_dir, test_size_mb)
            
            # Measure read throughput
            read_throughput = self._measure_read_throughput(test_dir, test_size_mb)
            
            # Update requirements
            self.requirements.sustained_write_mbps = write_throughput["sustained_mbps"]
            self.requirements.sustained_read_mbps = read_throughput["sustained_mbps"]
            self.requirements.peak_write_mbps = write_throughput["peak_mbps"]
            self.requirements.peak_read_mbps = read_throughput["peak_mbps"]
            
            # Check if can sustain 150-200 MB/s
            min_required_mbps = 150
            
            # Use the lower of read/write as the limiting factor
            limiting_throughput = min(write_throughput["sustained_mbps"], read_throughput["sustained_mbps"])
            self.requirements.can_sustain_150_200_mbps = limiting_throughput >= min_required_mbps
            
            logger.info(f"Sustained write: {write_throughput['sustained_mbps']:.2f} MB/s")
            logger.info(f"Sustained read: {read_throughput['sustained_mbps']:.2f} MB/s")
            logger.info(f"Limiting throughput: {limiting_throughput:.2f} MB/s")
            
            return {
                "write_sustained_mbps": write_throughput["sustained_mbps"],
                "read_sustained_mbps": read_throughput["sustained_mbps"],
                "write_peak_mbps": write_throughput["peak_mbps"],
                "read_peak_mbps": read_throughput["peak_mbps"],
                "limiting_mbps": limiting_throughput,
                "meets_150_200_mbps": self.requirements.can_sustain_150_200_mbps,
            }
            
        finally:
            # Clean up test directory
            shutil.rmtree(test_dir, ignore_errors=True)
    
    def _measure_write_throughput(self, test_dir: Path, test_size_mb: int) -> Dict[str, float]:
        """Measure write throughput."""
        logger.info(f"Measuring write throughput with {test_size_mb}MB test size")
        
        # Create test data
        test_data = np.random.bytes(test_size_mb * 1024 * 1024)
        
        throughput_samples = []
        start_time = time.time()
        
        file_counter = 0
        while time.time() - start_time < self.test_duration_seconds:
            file_path = test_dir / f"test_write_{file_counter}.dat"
            
            # Measure single write
            write_start = time.time()
            with open(file_path, 'wb') as f:
                f.write(test_data)
                f.flush()
                os.fsync(f.fileno())  # Force write to disk
            
            write_time = time.time() - write_start
            throughput_mbps = test_size_mb / write_time
            throughput_samples.append(throughput_mbps)
            
            file_counter += 1
            
            # Small delay to prevent overwhelming the system
            time.sleep(0.1)
        
        # Calculate statistics
        sustained_mbps = np.mean(throughput_samples)
        peak_mbps = np.max(throughput_samples)
        
        logger.info(f"Write test completed: {len(throughput_samples)} samples")
        logger.info(f"Write sustained: {sustained_mbps:.2f} MB/s, peak: {peak_mbps:.2f} MB/s")
        
        return {
            "sustained_mbps": sustained_mbps,
            "peak_mbps": peak_mbps,
            "samples": len(throughput_samples),
        }
    
    def _measure_read_throughput(self, test_dir: Path, test_size_mb: int) -> Dict[str, float]:
        """Measure read throughput."""
        logger.info(f"Measuring read throughput with {test_size_mb}MB test size")
        
        # Create test files first
        test_files = []
        for i in range(10):  # Create 10 test files
            file_path = test_dir / f"test_read_{i}.dat"
            test_data = np.random.bytes(test_size_mb * 1024 * 1024)
            with open(file_path, 'wb') as f:
                f.write(test_data)
            test_files.append(file_path)
        
        # Clear file system cache (Linux)
        try:
            os.system("sync")
            # Note: echo 3 > /proc/sys/vm/drop_caches requires root
            # We'll just use sync to ensure writes are flushed
        except:
            pass
        
        throughput_samples = []
        start_time = time.time()
        
        file_index = 0
        while time.time() - start_time < self.test_duration_seconds:
            file_path = test_files[file_index % len(test_files)]
            
            # Measure single read
            read_start = time.time()
            with open(file_path, 'rb') as f:
                data = f.read()
            
            read_time = time.time() - read_start
            throughput_mbps = test_size_mb / read_time
            throughput_samples.append(throughput_mbps)
            
            file_index += 1
            
            # Small delay to prevent overwhelming the system
            time.sleep(0.1)
        
        # Calculate statistics
        sustained_mbps = np.mean(throughput_samples)
        peak_mbps = np.max(throughput_samples)
        
        logger.info(f"Read test completed: {len(throughput_samples)} samples")
        logger.info(f"Read sustained: {sustained_mbps:.2f} MB/s, peak: {peak_mbps:.2f} MB/s")
        
        return {
            "sustained_mbps": sustained_mbps,
            "peak_mbps": peak_mbps,
            "samples": len(throughput_samples),
        }
    
    def calculate_memory_bandwidth(self) -> Dict[str, float]:
        """Calculate memory bandwidth requirements."""
        logger.info("Calculating memory bandwidth requirements")
        
        # Estimate memory bandwidth needed for 100k events/sec
        target_eps = 100_000
        bytes_per_event_in_memory = 200  # Conservative estimate
        
        # Memory bandwidth = events/sec * bytes/event * overhead factor
        overhead_factor = 3  # 3x overhead for copying, processing, etc.
        required_mbps = (target_eps * bytes_per_event_in_memory * overhead_factor) / (1024 * 1024)
        
        # Available memory bandwidth
        available_gbps = self.hardware_assumptions["memory_bandwidth_gbps"]
        available_mbps = available_gbps * 1024
        
        self.requirements.memory_bandwidth_mbps = required_mbps
        
        logger.info(f"Required memory bandwidth: {required_mbps:.2f} MB/s")
        logger.info(f"Available memory bandwidth: {available_mbps:.2f} MB/s")
        
        return {
            "required_mbps": required_mbps,
            "available_mbps": available_mbps,
            "utilization_ratio": required_mbps / available_mbps,
            "adequate": required_mbps < available_mbps * 0.5,  # Use <50% of available
        }
    
    def run_full_analysis(self) -> IORequirements:
        """Run the complete I/O endurance analysis."""
        logger.info("Starting I/O endurance analysis")
        
        # Calculate data volumes
        volume_data = self.calculate_data_volumes()
        
        # Calculate processing time
        processing_data = self.calculate_processing_time(volume_data["total_events"])
        
        # Calculate SSD wear
        ssd_data = self.calculate_ssd_wear()
        
        # Measure sustained throughput
        throughput_data = self.measure_sustained_throughput()
        
        # Calculate memory bandwidth
        memory_data = self.calculate_memory_bandwidth()
        
        # Overall hardware adequacy
        self.requirements.hardware_adequate = (
            self.requirements.can_sustain_150_200_mbps and
            self.requirements.meets_24_hour_processing and
            ssd_data["adequate"] and
            memory_data["adequate"]
        )
        
        logger.info("I/O endurance analysis completed")
        
        return self.requirements


def main():
    """Main function to run I/O endurance analysis."""
    parser = argparse.ArgumentParser(description="Analyze I/O endurance requirements")
    parser.add_argument("--test-duration", type=int, default=60, help="Duration for I/O testing in seconds")
    parser.add_argument("--test-size", type=int, default=100, help="Test file size in MB")
    parser.add_argument("--output", "-o", help="Output JSON file path", default="data/io_analysis/io_requirements.json")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(log_level=log_level)
    
    # Create output directory
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Run analysis
    analyzer = IOEnduranceAnalyzer(test_duration_seconds=args.test_duration)
    
    try:
        logger.info("Starting I/O endurance analysis")
        requirements = analyzer.run_full_analysis()
        
        # Save results
        results = {
            "analysis_timestamp": time.time(),
            "test_parameters": {
                "test_duration_seconds": args.test_duration,
                "test_size_mb": args.test_size,
            },
            "requirements": asdict(requirements),
            "market_data_assumptions": analyzer.market_data_assumptions,
            "hardware_assumptions": analyzer.hardware_assumptions,
            "validation_results": {
                "can_sustain_throughput": requirements.can_sustain_150_200_mbps,
                "meets_processing_time": requirements.meets_24_hour_processing,
                "hardware_adequate": requirements.hardware_adequate,
                "ssd_lifetime_adequate": requirements.ssd_lifetime_years >= 1.0,
            }
        }
        
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        logger.info(f"Analysis completed. Results saved to {output_path}")
        
        # Print summary
        print("\n=== I/O ENDURANCE ANALYSIS RESULTS ===")
        print(f"Total read volume: {requirements.total_read_volume_tb:.2f}TB")
        print(f"Total write volume: {requirements.total_write_volume_tb:.2f}TB")
        print(f"SSD TBW required: {requirements.ssd_tbw_required:.2f}TB")
        print(f"SSD lifetime: {requirements.ssd_lifetime_years:.1f} years")
        print(f"Single-thread processing: {requirements.single_thread_processing_days:.1f} days")
        print(f"Parallel processing: {requirements.parallel_processing_days:.1f} days")
        print(f"Sustained read: {requirements.sustained_read_mbps:.2f} MB/s")
        print(f"Sustained write: {requirements.sustained_write_mbps:.2f} MB/s")
        
        # Validation results
        print("\n=== VALIDATION RESULTS ===")
        
        if requirements.can_sustain_150_200_mbps:
            print("✅ Can sustain 150-200 MB/s throughput")
        else:
            print("❌ Cannot sustain 150-200 MB/s throughput")
        
        if requirements.meets_24_hour_processing:
            print("✅ Meets 24-hour processing requirement")
        else:
            print("❌ Does not meet 24-hour processing requirement")
        
        if requirements.ssd_lifetime_years >= 1.0:
            print("✅ SSD lifetime adequate")
        else:
            print("❌ SSD lifetime insufficient")
        
        if requirements.hardware_adequate:
            print("\n🎉 HARDWARE ADEQUATE: All requirements met")
        else:
            print("\n❌ HARDWARE INADEQUATE: Some requirements not met")
        
        return 0 if requirements.hardware_adequate else 1
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())