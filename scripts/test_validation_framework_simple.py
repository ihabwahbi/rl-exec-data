#!/usr/bin/env python3
"""Simplified test script to validate the framework with golden samples.

This script:
1. Loads one of the golden sample files
2. Runs a subset of validators without checkpoint support
3. Generates a simple report
4. Tests performance with real data
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
    BasicStatsCalculator
)
from src.rlx_datapipe.validation.loaders import GoldenSampleLoader


def get_file_stats(file_path: Path) -> dict:
    """Get basic file statistics."""
    stats = file_path.stat()
    size_mb = stats.st_size / (1024 * 1024)
    
    # Quick count of messages
    loader = GoldenSampleLoader()
    message_count = 0
    trade_count = 0
    
    for msg in loader.load_messages(file_path, show_progress=False):
        message_count += 1
        if '@trade' in msg.get('stream', ''):
            trade_count += 1
    
    return {
        "path": str(file_path),
        "size_mb": round(size_mb, 2),
        "total_messages": message_count,
        "trade_messages": trade_count,
        "orderbook_messages": message_count - trade_count
    }


def main():
    """Run simplified validation test."""
    logger.info("=" * 60)
    logger.info("Golden Sample Validation Framework Test (Simplified)")
    logger.info("=" * 60)
    
    # Find golden samples
    golden_dir = Path("data/golden_samples/high_volume")
    if not golden_dir.exists():
        logger.error(f"Golden samples directory not found: {golden_dir}")
        sys.exit(1)
    
    # Get first valid file
    golden_files = [f for f in golden_dir.glob("*.jsonl.gz") 
                    if not f.name.endswith('.incomplete')]
    
    if not golden_files:
        logger.error("No valid golden sample files found")
        sys.exit(1)
    
    test_file = golden_files[0]
    logger.info(f"\nSelected test file: {test_file.name}")
    
    # Get file statistics
    logger.info("Analyzing file...")
    file_stats = get_file_stats(test_file)
    
    logger.info(f"  Size: {file_stats['size_mb']} MB (compressed)")
    logger.info(f"  Total messages: {file_stats['total_messages']:,}")
    logger.info(f"  Trade messages: {file_stats['trade_messages']:,}")
    logger.info(f"  Orderbook messages: {file_stats['orderbook_messages']:,}")
    
    # Create pipeline without checkpointing
    pipeline = ValidationPipeline(max_workers=2)
    
    # Add only essential validators
    logger.info("\nAdding validators...")
    pipeline.add_validator(ChronologicalOrderValidator())
    pipeline.add_validator(SequenceGapValidator(max_gap_ratio=0.001))
    pipeline.add_validator(BasicStatsCalculator({
        "mean_relative_diff": 0.001,
        "std_relative_diff": 0.001,
        "median_relative_diff": 0.001
    }))
    
    # Monitor system resources
    process = psutil.Process()
    initial_memory = process.memory_info().rss / (1024 * 1024)
    
    # Run validation (self-validation with same file)
    logger.info("\nRunning validation pipeline...")
    start_time = time.perf_counter()
    
    try:
        # Run without checkpoint support
        report = pipeline.run(
            golden_sample_path=test_file,
            comparison_path=test_file,
            checkpoint_file=None  # No checkpointing
        )
        
        # Calculate performance metrics
        duration = time.perf_counter() - start_time
        final_memory = process.memory_info().rss / (1024 * 1024)
        memory_increase = final_memory - initial_memory
        
        # Print results
        logger.info("\n" + "=" * 60)
        logger.info("VALIDATION RESULTS")
        logger.info("=" * 60)
        logger.info(f"Overall Status: {'PASSED' if report.overall_passed else 'FAILED'}")
        logger.info(f"Total Duration: {duration:.2f}s")
        logger.info(f"Memory Usage: {report.peak_memory_mb:.2f} MB (peak)")
        logger.info(f"Memory Increase: {memory_increase:.2f} MB")
        logger.info(f"Processing Speed: {file_stats['total_messages'] / duration:,.0f} messages/sec")
        
        logger.info("\nIndividual Validator Results:")
        for result in report.results:
            status = "PASS" if result.passed else "FAIL"
            logger.info(f"  [{status}] {result.validator_name}: {result.duration_seconds:.2f}s")
            if result.error_message:
                logger.error(f"       Error: {result.error_message}")
            elif result.passed and 'interpretation' in result.metrics:
                logger.info(f"       {result.metrics['interpretation']}")
        
        # Save simplified report
        report_data = {
            "test_file": test_file.name,
            "file_stats": file_stats,
            "validation": {
                "overall_passed": report.overall_passed,
                "duration_seconds": round(duration, 2),
                "peak_memory_mb": round(report.peak_memory_mb, 2),
                "messages_per_second": round(file_stats['total_messages'] / duration, 2)
            },
            "validators": [
                {
                    "name": r.validator_name,
                    "passed": r.passed,
                    "duration": round(r.duration_seconds, 2),
                    "error": r.error_message
                }
                for r in report.results
            ]
        }
        
        report_path = Path(f"validation_test_simple_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(report_path, 'w') as f:
            json.dump(report_data, f, indent=2)
        
        logger.info(f"\nReport saved to: {report_path}")
        
        # Test with different files if available
        if len(golden_files) > 1:
            logger.info("\n" + "=" * 60)
            logger.info("CROSS-FILE VALIDATION TEST")
            logger.info("=" * 60)
            
            test_file2 = golden_files[1]
            logger.info(f"Comparing {test_file.name} vs {test_file2.name}")
            
            # Clear validators and add only chronological validator
            pipeline.clear_validators()
            pipeline.add_validator(ChronologicalOrderValidator())
            
            cross_report = pipeline.run(
                golden_sample_path=test_file,
                comparison_path=test_file2,
                checkpoint_file=None
            )
            
            logger.info(f"Cross-validation result: {'PASSED' if cross_report.overall_passed else 'FAILED'}")
            
    except Exception as e:
        logger.error(f"Validation failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    logger.info("\n" + "=" * 60)
    logger.info("Test completed successfully!")
    logger.info("=" * 60)


if __name__ == "__main__":
    # Configure logging
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )
    
    main()