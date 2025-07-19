"""Main analysis orchestrator for origin_time completeness analysis."""

from pathlib import Path

from loguru import logger

from rlx_datapipe.analysis.data_loader import (
    load_book_data,
    load_multiple_files,
    load_trades_data,
)
from rlx_datapipe.analysis.origin_time_validator import OriginTimeValidator
from rlx_datapipe.analysis.report_generator import OriginTimeReportGenerator
from rlx_datapipe.common.logging import setup_logging


class OriginTimeAnalyzer:
    """Orchestrates the complete origin_time analysis workflow."""

    def __init__(
        self,
        output_path: Path | None = None,
        log_level: str = "INFO",
        log_file: Path | None = None,
    ):
        """Initialize the analyzer.

        Args:
            output_path: Path to save analysis results
            log_level: Logging level
            log_file: Optional log file path
        """
        # Set up logging
        setup_logging(log_level=log_level, log_file=log_file)

        # Initialize components
        self.validator = OriginTimeValidator()
        self.report_generator = OriginTimeReportGenerator(output_path=output_path)

        logger.info("OriginTimeAnalyzer initialized")

    def analyze_single_file(
        self,
        file_path: Path,
        data_type: str,
        symbol: str = "BTC-USDT",
        date_filter: tuple[str, str] | None = None,
    ) -> dict:
        """Analyze a single data file.

        Args:
            file_path: Path to the data file
            data_type: Type of data ('trades' or 'book')
            symbol: Trading symbol to filter for
            date_filter: Optional date range filter

        Returns:
            Validation results dictionary
        """
        logger.info(f"Analyzing single file: {file_path} ({data_type})")

        # Load data
        if data_type == "trades":
            df = load_trades_data(file_path, symbol=symbol, date_filter=date_filter)
        elif data_type == "book":
            df = load_book_data(file_path, symbol=symbol, date_filter=date_filter)
        else:
            raise ValueError(
                f"Invalid data_type: {data_type}. Must be 'trades' or 'book'"
            )

        # Validate origin_time
        validation_results = self.validator.validate_origin_time(df, data_type)

        logger.info(f"Analysis complete for {file_path}")
        return validation_results

    def analyze_multiple_files(
        self,
        trades_files: list[Path],
        book_files: list[Path],
        symbol: str = "BTC-USDT",
        date_filter: tuple[str, str] | None = None,
    ) -> list[dict]:
        """Analyze multiple data files.

        Args:
            trades_files: List of trades data files
            book_files: List of book data files
            symbol: Trading symbol to filter for
            date_filter: Optional date range filter

        Returns:
            List of validation results
        """
        logger.info(
            f"Analyzing {len(trades_files)} trades files and "
            f"{len(book_files)} book files"
        )

        results = []

        # Analyze trades files
        if trades_files:
            try:
                trades_df = load_multiple_files(
                    trades_files, "trades", symbol=symbol, date_filter=date_filter
                )
                trades_results = self.validator.validate_origin_time(
                    trades_df, "trades"
                )
                results.append(trades_results)
            except Exception as e:
                logger.error(f"Failed to analyze trades files: {e}")

        # Analyze book files
        if book_files:
            try:
                book_df = load_multiple_files(
                    book_files, "book", symbol=symbol, date_filter=date_filter
                )
                book_results = self.validator.validate_origin_time(book_df, "book")
                results.append(book_results)
            except Exception as e:
                logger.error(f"Failed to analyze book files: {e}")

        logger.info(f"Analysis complete for {len(results)} datasets")
        return results

    def run_analysis(
        self,
        trades_files: list[Path] | None = None,
        book_files: list[Path] | None = None,
        symbol: str = "BTC-USDT",
        date_filter: tuple[str, str] | None = None,
        save_report: bool = True,
        print_summary: bool = True,
    ) -> list[dict]:
        """Run complete origin_time analysis workflow.

        Args:
            trades_files: List of trades data files
            book_files: List of book data files
            symbol: Trading symbol to filter for
            date_filter: Optional date range filter
            save_report: Whether to save the report to file
            print_summary: Whether to print summary to console

        Returns:
            List of validation results
        """
        logger.info("Starting complete origin_time analysis")

        if not trades_files and not book_files:
            raise ValueError(
                "At least one of trades_files or book_files must be provided"
            )

        # Convert to lists if None
        trades_files = trades_files or []
        book_files = book_files or []

        # Run analysis
        results = self.analyze_multiple_files(
            trades_files=trades_files,
            book_files=book_files,
            symbol=symbol,
            date_filter=date_filter,
        )

        if not results:
            logger.warning("No validation results generated")
            return []

        # Generate and save report
        if save_report:
            report_path = self.report_generator.save_report(results)
            logger.info(f"Report saved to: {report_path}")

        # Print summary
        if print_summary:
            self.report_generator.print_summary(results)

        logger.info("Origin_time analysis complete")
        return results

    def get_recommendation(self, validation_results: list[dict]) -> dict:
        """Get chronological unification recommendation.

        Args:
            validation_results: Validation results from analysis

        Returns:
            Recommendation dictionary
        """
        return self.report_generator.generate_chronological_recommendation(
            validation_results
        )
