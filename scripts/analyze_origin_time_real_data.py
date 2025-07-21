#!/usr/bin/env python3
"""CLI script for analyzing origin_time completeness in REAL Crypto Lake data from Epic 0."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger

from rlx_datapipe.analysis.origin_time_analyzer import OriginTimeAnalyzer


def main():
    """Main entry point for real data analysis."""
    logger.info("🎯 Starting origin_time analysis with REAL Crypto Lake data")

    # Define paths to real data from Epic 0
    staging_dir = project_root / "data" / "staging"
    raw_dir = staging_dir / "raw"
    output_dir = project_root / "data" / "analysis"

    # Find available files
    trades_files = list(raw_dir.glob("*trades*.parquet"))
    book_files = list(raw_dir.glob("*book*.parquet"))

    logger.info(f"📁 Found {len(trades_files)} trades files and {len(book_files)} book files")

    if trades_files:
        logger.info(f"📊 Trades data: {trades_files[0].name}")

    # Initialize analyzer
    analyzer = OriginTimeAnalyzer(
        output_path=output_dir,
        log_level="INFO"
    )

    try:
        # Run analysis with real data
        logger.info("🔍 Analyzing REAL Crypto Lake data...")
        results = analyzer.run_analysis(
            trades_files=trades_files if trades_files else None,
            book_files=book_files if book_files else None,
            symbol="BTC-USDT",
            save_report=True,
            print_summary=True
        )

        # Get recommendation
        recommendation = analyzer.get_recommendation(results)

        # Print results with emphasis on REAL DATA
        print("\n" + "=" * 80)
        print("ORIGIN_TIME ANALYSIS - REAL DATA RESULTS")
        print("=" * 80)
        print("Dataset: Crypto Lake BTC-USDT (REAL production data from Epic 0)")
        print(f"Files analyzed: {len(trades_files)} trades, {len(book_files)} book")

        if results:
            for result in results:
                data_type = result.get("data_type", "unknown")
                total_rows = result.get("total_rows", 0)
                invalid_pct = result.get("invalid_percentage", 0)

                print(f"\n{data_type.upper()} TABLE:")
                print(f"- Total rows: {total_rows:,}")
                print(f"- Origin_time invalid: {invalid_pct:.2f}%")

                # Show breakdown
                null_pct = result.get("null_percentage", 0)
                zero_pct = result.get("zero_percentage", 0)
                future_pct = result.get("future_percentage", 0)

                if null_pct > 0:
                    print(f"  - Null values: {null_pct:.2f}%")
                if zero_pct > 0:
                    print(f"  - Zero values: {zero_pct:.2f}%")
                if future_pct > 0:
                    print(f"  - Future timestamps: {future_pct:.2f}%")

        print("\n" + "=" * 80)
        print("FINAL RECOMMENDATION (Based on REAL DATA)")
        print("=" * 80)
        print(f"Strategy: {recommendation['strategy']}")
        print(f"Confidence: {recommendation['confidence']}")
        print(f"Reason: {recommendation['reason']}")
        print("=" * 80)

        # Update story document with results
        story_path = project_root / "docs" / "stories" / "1.1.analyze-origin-time-completeness.md"
        logger.info(f"📝 Results saved to: {output_dir / 'origin_time_completeness_report.md'}")
        logger.info(f"📋 Please update story at: {story_path}")

        # Return appropriate exit code
        if recommendation["strategy"] == "origin_time_primary":
            logger.success("✅ SUCCESS: origin_time can be used as primary chronological key!")
            return 0
        if recommendation["strategy"] in ["snapshot_anchored", "book_time_primary"]:
            logger.warning("⚠️ WARNING: Alternative strategy needed for chronological ordering")
            return 1
        logger.error("❌ ERROR: Significant reliability issues with origin_time")
        return 2

    except Exception as e:
        logger.error(f"❌ Analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return 3


if __name__ == "__main__":
    sys.exit(main())
