#!/usr/bin/env python3
"""CLI script for analyzing origin_time completeness in Crypto Lake data."""

import argparse
import sys
from pathlib import Path

from loguru import logger

from rlx_datapipe.analysis.origin_time_analyzer import OriginTimeAnalyzer


def parse_date_range(date_range_str: str) -> tuple[str, str]:
    """Parse date range string into start and end dates.

    Args:
        date_range_str: Date range in format "YYYY-MM-DD,YYYY-MM-DD"

    Returns:
        Tuple of (start_date, end_date)
    """
    try:
        start_date, end_date = date_range_str.split(",")
        return start_date.strip(), end_date.strip()
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid date range format: {date_range_str}. "
            f"Expected format: YYYY-MM-DD,YYYY-MM-DD"
        ) from None


def collect_files(directory: Path, pattern: str) -> list[Path]:
    """Collect files matching pattern from directory.

    Args:
        directory: Directory to search
        pattern: File pattern to match

    Returns:
        List of matching file paths
    """
    if not directory.exists():
        logger.warning(f"Directory not found: {directory}")
        return []

    files = list(directory.glob(pattern))
    logger.info(f"Found {len(files)} files matching pattern '{pattern}' in {directory}")

    return files


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze origin_time completeness in Crypto Lake data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze trades data
  python analyze_origin_time.py --trades-dir /path/to/trades --trades-pattern "*.csv"

  # Analyze both trades and book data
  python analyze_origin_time.py --trades-dir /path/to/trades --book-dir /path/to/book

  # Analyze with date filter
  python analyze_origin_time.py --trades-dir /path/to/trades \\
    --date-range "2024-01-01,2024-01-14"

  # Analyze different symbol
  python analyze_origin_time.py --trades-dir /path/to/trades --symbol ETH-USDT
        """,
    )

    # Data source arguments
    parser.add_argument(
        "--trades-dir", type=Path, help="Directory containing trades data files"
    )

    parser.add_argument(
        "--trades-pattern",
        type=str,
        default="*.csv",
        help="File pattern for trades data (default: *.csv)",
    )

    parser.add_argument(
        "--book-dir", type=Path, help="Directory containing book data files"
    )

    parser.add_argument(
        "--book-pattern",
        type=str,
        default="*.csv",
        help="File pattern for book data (default: *.csv)",
    )

    # Analysis parameters
    parser.add_argument(
        "--symbol",
        type=str,
        default="BTC-USDT",
        help="Trading symbol to analyze (default: BTC-USDT)",
    )

    parser.add_argument(
        "--date-range",
        type=parse_date_range,
        help="Date range to analyze in format YYYY-MM-DD,YYYY-MM-DD",
    )

    # Output options
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/analysis"),
        help="Output directory for reports (default: data/analysis)",
    )

    parser.add_argument(
        "--no-report", action="store_true", help="Don't save report to file"
    )

    parser.add_argument(
        "--no-summary", action="store_true", help="Don't print summary to console"
    )

    # Logging options
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)",
    )

    parser.add_argument(
        "--log-file", type=Path, help="Log file path (default: console only)"
    )

    # Parse arguments
    args = parser.parse_args()

    # Validate arguments
    if not args.trades_dir and not args.book_dir:
        parser.error("At least one of --trades-dir or --book-dir must be specified")

    # Collect data files
    trades_files = []
    book_files = []

    if args.trades_dir:
        trades_files = collect_files(args.trades_dir, args.trades_pattern)
        if not trades_files:
            logger.warning(f"No trades files found in {args.trades_dir}")

    if args.book_dir:
        book_files = collect_files(args.book_dir, args.book_pattern)
        if not book_files:
            logger.warning(f"No book files found in {args.book_dir}")

    if not trades_files and not book_files:
        logger.error("No data files found. Check directory paths and patterns.")
        sys.exit(1)

    # Initialize analyzer
    analyzer = OriginTimeAnalyzer(
        output_path=args.output_dir, log_level=args.log_level, log_file=args.log_file
    )

    try:
        # Run analysis
        results = analyzer.run_analysis(
            trades_files=trades_files or None,
            book_files=book_files or None,
            symbol=args.symbol,
            date_filter=args.date_range,
            save_report=not args.no_report,
            print_summary=not args.no_summary,
        )

        # Get recommendation
        recommendation = analyzer.get_recommendation(results)

        # Print recommendation
        print("\n" + "=" * 60)
        print("FINAL RECOMMENDATION")
        print("=" * 60)
        print(f"Strategy: {recommendation['strategy']}")
        print(f"Confidence: {recommendation['confidence']}")
        print(f"Reason: {recommendation['reason']}")
        print("=" * 60)

        # Exit with appropriate code
        if recommendation["strategy"] == "origin_time_primary":
            sys.exit(0)  # Success - can use origin_time
        elif recommendation["strategy"] in ["snapshot_anchored", "book_time_primary"]:
            sys.exit(1)  # Warning - alternative strategy needed
        else:
            sys.exit(2)  # Error - significant reliability issues

    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        sys.exit(3)


if __name__ == "__main__":
    main()
