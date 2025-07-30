#!/usr/bin/env python3
"""Fixed origin_time analysis for real Crypto Lake data with proper datetime handling."""

import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import polars as pl
from loguru import logger


def analyze_origin_time_completeness(file_path: Path):
    """Analyze origin_time completeness in the real data."""
    logger.info(f"🔍 Analyzing {file_path}")

    # Read the data
    df = pl.read_parquet(file_path)

    total_rows = len(df)
    logger.info(f"📊 Total rows: {total_rows:,}")

    # Analysis results
    results = {
        "file": file_path.name,
        "data_type": "trades",
        "total_rows": total_rows,
        "null_count": 0,
        "null_percentage": 0.0,
        "zero_count": 0,
        "zero_percentage": 0.0,
        "future_count": 0,
        "future_percentage": 0.0,
        "invalid_count": 0,
        "invalid_percentage": 0.0
    }

    if "origin_time" in df.columns:
        # Check nulls
        null_count = df.filter(pl.col("origin_time").is_null()).height
        results["null_count"] = null_count
        results["null_percentage"] = (null_count / total_rows * 100) if total_rows > 0 else 0

        # Check for epoch zero (1970-01-01)
        epoch_zero = datetime(1970, 1, 1)
        zero_count = df.filter(pl.col("origin_time") == epoch_zero).height
        results["zero_count"] = zero_count
        results["zero_percentage"] = (zero_count / total_rows * 100) if total_rows > 0 else 0

        # Check for future dates
        current_time = datetime.now()
        future_count = df.filter(pl.col("origin_time") > current_time).height
        results["future_count"] = future_count
        results["future_percentage"] = (future_count / total_rows * 100) if total_rows > 0 else 0

        # Total invalid
        results["invalid_count"] = null_count + zero_count + future_count
        results["invalid_percentage"] = results["null_percentage"] + results["zero_percentage"] + results["future_percentage"]

        # Get date range
        min_time = df.select(pl.col("origin_time").min()).item()
        max_time = df.select(pl.col("origin_time").max()).item()
        results["date_range"] = {
            "min": min_time.isoformat() if min_time else None,
            "max": max_time.isoformat() if max_time else None
        }

    return results


def generate_report(results):
    """Generate analysis report."""
    print("\n" + "=" * 80)
    print("ORIGIN_TIME ANALYSIS - REAL CRYPTO LAKE DATA RESULTS")
    print("=" * 80)
    print("Dataset: Crypto Lake BTC-USDT (Real production data from Epic 0)")
    print(f"Period: {results['date_range']['min']} to {results['date_range']['max']}")
    print()
    print("TRADES TABLE:")
    print(f"- Total rows: {results['total_rows']:,}")
    print(f"- Origin_time null: {results['null_percentage']:.2f}%")
    print(f"- Origin_time zero (epoch): {results['zero_percentage']:.2f}%")
    print(f"- Origin_time future: {results['future_percentage']:.2f}%")
    print(f"- Total invalid: {results['invalid_percentage']:.2f}%")

    # Recommendation
    print("\n" + "=" * 80)
    print("RECOMMENDATION (Based on REAL DATA)")
    print("=" * 80)

    if results["invalid_percentage"] < 5:
        print("✅ PROCEED: origin_time can be used as primary chronological key")
        print("Strategy: origin_time_primary")
        print("Confidence: HIGH")
        print(f"Reason: Only {results['invalid_percentage']:.2f}% invalid timestamps")
        return 0
    if results["invalid_percentage"] < 10:
        print("⚠️ PROCEED_WITH_CAUTION: origin_time needs fallback strategy")
        print("Strategy: origin_time_with_fallback")
        print("Confidence: MEDIUM")
        print(f"Reason: {results['invalid_percentage']:.2f}% invalid timestamps require mitigation")
        return 1
    print("❌ BLOCKED: origin_time is unreliable")
    print("Strategy: alternative_required")
    print("Confidence: LOW")
    print(f"Reason: {results['invalid_percentage']:.2f}% invalid timestamps exceed threshold")
    return 2


def save_report(results):
    """Save detailed report to markdown."""
    output_dir = Path("data/analysis")
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = output_dir / "origin_time_real_data_report.md"

    with open(report_path, "w") as f:
        f.write("# Origin Time Completeness Report - REAL DATA\n\n")
        f.write(f"**Generated**: {datetime.now().isoformat()}\n")
        f.write("**Data Source**: Real Crypto Lake Data from Epic 0\n\n")

        f.write("## Executive Summary\n\n")
        f.write(f"Analysis of {results['total_rows']:,} real trade records from Crypto Lake ")
        f.write(f"shows that origin_time has {results['invalid_percentage']:.2f}% invalid values.\n\n")

        f.write("## Detailed Results\n\n")
        f.write("### Data Overview\n")
        f.write(f"- **File**: {results['file']}\n")
        f.write(f"- **Total Records**: {results['total_rows']:,}\n")
        f.write(f"- **Date Range**: {results['date_range']['min']} to {results['date_range']['max']}\n\n")

        f.write("### Origin Time Quality\n")
        f.write(f"- **Null Values**: {results['null_count']:,} ({results['null_percentage']:.2f}%)\n")
        f.write(f"- **Zero/Epoch Values**: {results['zero_count']:,} ({results['zero_percentage']:.2f}%)\n")
        f.write(f"- **Future Timestamps**: {results['future_count']:,} ({results['future_percentage']:.2f}%)\n")
        f.write(f"- **Total Invalid**: {results['invalid_count']:,} ({results['invalid_percentage']:.2f}%)\n\n")

        f.write("## Recommendation\n\n")
        if results["invalid_percentage"] < 5:
            f.write("✅ **USE ORIGIN_TIME AS PRIMARY KEY**\n\n")
            f.write("The origin_time field is highly reliable with less than 5% invalid values. ")
            f.write("It can be safely used as the primary chronological ordering key.\n")
        elif results["invalid_percentage"] < 10:
            f.write("⚠️ **USE ORIGIN_TIME WITH FALLBACK**\n\n")
            f.write("The origin_time field has moderate reliability. ")
            f.write("Implement fallback to received_time or other fields for invalid entries.\n")
        else:
            f.write("❌ **DO NOT USE ORIGIN_TIME**\n\n")
            f.write("The origin_time field is unreliable with >10% invalid values. ")
            f.write("Alternative chronological ordering strategy required.\n")

    logger.info(f"📝 Report saved to: {report_path}")
    return report_path


def main():
    """Main analysis function."""
    # Find the real data file
    data_file = Path("data/staging/ready/BINANCE_BTC-USDT_trades_20240101_20240107.parquet")

    if not data_file.exists():
        logger.error(f"❌ Data file not found: {data_file}")
        return 3

    # Analyze the data
    results = analyze_origin_time_completeness(data_file)

    # Generate console report
    exit_code = generate_report(results)

    # Save detailed report
    report_path = save_report(results)

    # Update story document note
    print("\n" + "=" * 80)
    print("📋 ACTION REQUIRED")
    print("=" * 80)
    print("Please update the story document at:")
    print("docs/stories/1.1.analyze-origin-time-completeness.md")
    print()
    print("Add the following to the Dev Agent Record > Completion Notes:")
    print(f"- Re-executed with REAL Crypto Lake data ({results['total_rows']:,} records)")
    print(f"- Origin_time invalid percentage: {results['invalid_percentage']:.2f}%")
    print(f"- Recommendation: {['SUCCESS', 'WARNING', 'ERROR'][exit_code]}")
    print("=" * 80)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
