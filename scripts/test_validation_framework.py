#!/usr/bin/env python3
"""Test script to validate the framework with golden samples from Story 1.2.1.

This script:
1. Loads golden sample files from data/golden_samples/
2. Runs the validation pipeline with multiple validators
3. Generates a comprehensive report
4. Verifies performance with real high-volume data
"""

import json
import sys
from pathlib import Path
from datetime import datetime
import time
import psutil
from loguru import logger

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.rlx_datapipe.validation.pipeline import ValidationPipeline
from src.rlx_datapipe.validation.validators.timing import (
    ChronologicalOrderValidator,
    SequenceGapValidator
)
from src.rlx_datapipe.validation.statistical import (
    KSValidator,
    PowerLawValidator,
    BasicStatsCalculator
)
from src.rlx_datapipe.validation.loaders import GoldenSampleLoader


def get_file_info(file_path: Path) -> dict:
    """Get file information including size and compression ratio."""
    stats = file_path.stat()
    size_mb = stats.st_size / (1024 * 1024)
    
    # If compressed, estimate compression ratio
    if file_path.suffix == '.gz':
        # Rough estimate based on typical JSONL compression
        estimated_uncompressed = size_mb * 8  # JSONL typically compresses 8:1
        compression_ratio = estimated_uncompressed / size_mb
    else:
        compression_ratio = 1.0
        estimated_uncompressed = size_mb
    
    return {
        "path": str(file_path),
        "size_mb": round(size_mb, 2),
        "estimated_uncompressed_mb": round(estimated_uncompressed, 2),
        "compression_ratio": round(compression_ratio, 2),
        "modified": datetime.fromtimestamp(stats.st_mtime).isoformat()
    }


def count_events_quick(file_path: Path) -> int:
    """Quickly count events in a file."""
    loader = GoldenSampleLoader()
    count = 0
    
    # Count trades (usually fewer, quicker to count)
    for batch in loader.extract_trades(file_path):
        count += len(batch)
    
    return count


def run_validation_test(golden_file: Path, comparison_file: Path = None) -> dict:
    """Run full validation test on golden sample files.
    
    Args:
        golden_file: Path to golden sample file
        comparison_file: Path to comparison file (if None, use same file)
        
    Returns:
        Test results dictionary
    """
    if comparison_file is None:
        comparison_file = golden_file
        logger.info("Using same file for self-validation test")
    
    logger.info(f"Running validation test on: {golden_file.name}")
    
    # Get file info
    file_info = get_file_info(golden_file)
    logger.info(f"  File size: {file_info['size_mb']} MB (compressed)")
    logger.info(f"  Estimated uncompressed: {file_info['estimated_uncompressed_mb']} MB")
    
    # Quick event count
    logger.info("Counting events...")
    start = time.perf_counter()
    event_count = count_events_quick(golden_file)
    count_duration = time.perf_counter() - start
    logger.info(f"  Found {event_count:,} trade events in {count_duration:.2f}s")
    
    # Create validation pipeline
    pipeline = ValidationPipeline(max_workers=4)
    
    # Add validators
    logger.info("Adding validators to pipeline...")
    
    # Timing validators
    pipeline.add_validator(ChronologicalOrderValidator())
    pipeline.add_validator(SequenceGapValidator(max_gap_ratio=0.001))  # 0.1% gap tolerance
    
    # Statistical validators
    pipeline.add_validator(BasicStatsCalculator({
        "mean_relative_diff": 0.001,  # Very tight for self-validation
        "std_relative_diff": 0.001,
        "median_relative_diff": 0.001
    }))
    pipeline.add_validator(KSValidator(alpha=0.01))  # Should pass for identical data
    
    # Power law validator for trade sizes
    pipeline.add_validator(PowerLawValidator(expected_alpha=2.4, tolerance=0.5))
    
    # Set up checkpoint file
    checkpoint_file = Path(f"validation_checkpoint_{golden_file.stem}.json")
    
    # Monitor system resources
    process = psutil.Process()
    initial_memory = process.memory_info().rss / (1024 * 1024)
    
    # Run validation
    logger.info("Starting validation pipeline...")
    start_time = time.perf_counter()
    
    try:
        report = pipeline.run(
            golden_sample_path=golden_file,
            comparison_path=comparison_file,
            checkpoint_file=checkpoint_file
        )
        
        # Get final memory usage
        final_memory = process.memory_info().rss / (1024 * 1024)
        memory_increase = final_memory - initial_memory
        
        # Compile results
        results = {
            "success": True,
            "file_info": file_info,
            "event_count": event_count,
            "count_duration": round(count_duration, 2),
            "validation": {
                "overall_passed": report.overall_passed,
                "total_duration": round(report.total_duration, 2),
                "peak_memory_mb": round(report.peak_memory_mb, 2),
                "memory_increase_mb": round(memory_increase, 2),
                "validators_run": len(report.results),
                "validators_passed": sum(1 for r in report.results if r.passed),
                "results": [r.to_dict() for r in report.results]
            },
            "performance": {
                "events_per_second": round(event_count / report.total_duration, 2),
                "mb_per_second": round(file_info['size_mb'] / report.total_duration, 2),
                "validation_overhead_percent": round((report.total_duration / count_duration - 1) * 100, 2)
            }
        }
        
        # Clean up checkpoint if successful
        if checkpoint_file.exists():
            checkpoint_file.unlink()
            
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        results = {
            "success": False,
            "error": str(e),
            "file_info": file_info,
            "event_count": event_count if 'event_count' in locals() else None
        }
    
    return results


def main():
    """Run validation tests on golden samples."""
    logger.info("=" * 60)
    logger.info("Golden Sample Validation Framework Test")
    logger.info("=" * 60)
    
    # Find golden samples
    golden_dir = Path("data/golden_samples")
    if not golden_dir.exists():
        logger.error(f"Golden samples directory not found: {golden_dir}")
        sys.exit(1)
    
    # Test with high volume sample (most challenging)
    high_volume_dir = golden_dir / "high_volume"
    if high_volume_dir.exists():
        # Get the largest file
        high_volume_files = sorted(
            high_volume_dir.glob("*.jsonl.gz"),
            key=lambda f: f.stat().st_size,
            reverse=True
        )
        
        if high_volume_files:
            # Skip incomplete files
            valid_files = [f for f in high_volume_files if not f.name.endswith('.incomplete')]
            
            if valid_files:
                test_file = valid_files[0]
                logger.info(f"\nTesting with high-volume file: {test_file.name}")
                
                results = run_validation_test(test_file)
                
                # Generate report
                report_path = Path(f"validation_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
                with open(report_path, 'w') as f:
                    json.dump(results, f, indent=2)
                
                logger.info(f"\nReport saved to: {report_path}")
                
                # Print summary
                if results['success']:
                    logger.info("\n" + "=" * 60)
                    logger.info("VALIDATION TEST SUMMARY")
                    logger.info("=" * 60)
                    logger.info(f"File: {test_file.name}")
                    logger.info(f"Size: {results['file_info']['size_mb']} MB")
                    logger.info(f"Events: {results['event_count']:,}")
                    logger.info(f"Overall Result: {'PASSED' if results['validation']['overall_passed'] else 'FAILED'}")
                    logger.info(f"Validators: {results['validation']['validators_passed']}/{results['validation']['validators_run']} passed")
                    logger.info(f"Duration: {results['validation']['total_duration']}s")
                    logger.info(f"Performance: {results['performance']['events_per_second']:,} events/sec")
                    logger.info(f"Memory Peak: {results['validation']['peak_memory_mb']} MB")
                    
                    # Show individual validator results
                    logger.info("\nValidator Results:")
                    for result in results['validation']['results']:
                        status = "✓" if result['passed'] else "✗"
                        logger.info(f"  {status} {result['validator']}: {result['duration']:.2f}s")
                        if result.get('error'):
                            logger.error(f"    Error: {result['error']}")
                else:
                    logger.error(f"\nValidation failed: {results.get('error', 'Unknown error')}")
                    
                # Test with different file comparisons if we have multiple files
                if len(valid_files) > 1:
                    logger.info("\n" + "=" * 60)
                    logger.info("Testing cross-file validation...")
                    logger.info("=" * 60)
                    
                    # Compare first two files
                    cross_results = run_validation_test(valid_files[0], valid_files[1])
                    
                    cross_report_path = Path(f"validation_cross_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
                    with open(cross_report_path, 'w') as f:
                        json.dump(cross_results, f, indent=2)
                    
                    logger.info(f"\nCross-validation report saved to: {cross_report_path}")
                    
                    if cross_results['success']:
                        logger.info(f"Cross-validation result: {'PASSED' if cross_results['validation']['overall_passed'] else 'FAILED'}")
            else:
                logger.error("No valid high-volume files found")
                sys.exit(1)
    else:
        logger.error("No high-volume samples found")
        sys.exit(1)
    
    logger.info("\n" + "=" * 60)
    logger.info("Validation framework test complete!")
    logger.info("=" * 60)


if __name__ == "__main__":
    # Configure logging
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    
    main()