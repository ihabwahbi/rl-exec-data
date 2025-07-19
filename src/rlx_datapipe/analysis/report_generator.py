"""Report generation for origin_time analysis."""

from datetime import datetime
from pathlib import Path

from loguru import logger


class OriginTimeReportGenerator:
    """Generates analysis reports for origin_time completeness."""

    def __init__(self, output_path: Path | None = None):
        """Initialize report generator.

        Args:
            output_path: Path to save reports (default: data/analysis/)
        """
        self.output_path = output_path or Path("data/analysis")
        self.output_path.mkdir(parents=True, exist_ok=True)
        logger.info(
            f"Report generator initialized with output path: {self.output_path}"
        )

    def generate_summary_statistics(self, validation_results: list[dict]) -> dict:
        """Generate summary statistics from validation results.

        Args:
            validation_results: List of validation results from OriginTimeValidator

        Returns:
            Dictionary with summary statistics
        """
        if not validation_results:
            return {}

        total_rows = sum(result["total_rows"] for result in validation_results)
        total_valid = sum(result["valid_count"] for result in validation_results)

        summary = {
            "total_datasets": len(validation_results),
            "total_rows_analyzed": total_rows,
            "total_valid_rows": total_valid,
            "overall_validity_percentage": (
                (total_valid / total_rows * 100) if total_rows > 0 else 0
            ),
            "datasets": [],
        }

        for result in validation_results:
            dataset_summary = {
                "data_type": result["data_type"],
                "total_rows": result["total_rows"],
                "valid_count": result["valid_count"],
                "valid_percentage": result["valid_percentage"],
                "reliability_score": result["valid_percentage"],
            }
            summary["datasets"].append(dataset_summary)

        return summary

    def generate_chronological_recommendation(
        self, validation_results: list[dict]
    ) -> dict:
        """Generate recommendation for chronological unification strategy.

        Args:
            validation_results: List of validation results from OriginTimeValidator

        Returns:
            Dictionary with recommendation details
        """
        if not validation_results:
            return {"strategy": "unknown", "reason": "No validation results provided"}

        # Find trades and book results
        trades_result = next(
            (r for r in validation_results if r["data_type"] == "trades"), None
        )
        book_result = next(
            (r for r in validation_results if r["data_type"] == "book"), None
        )

        reliability_threshold = 95.0

        recommendation = {
            "strategy": "unknown",
            "reason": "",
            "details": {},
            "confidence": "low",
        }

        if trades_result and book_result:
            trades_reliable = trades_result["valid_percentage"] >= reliability_threshold
            book_reliable = book_result["valid_percentage"] >= reliability_threshold

            if trades_reliable and book_reliable:
                recommendation.update(
                    {
                        "strategy": "origin_time_primary",
                        "reason": "Both trades and book data have high origin_time "
                        "reliability (>95%)",
                        "confidence": "high",
                        "details": {
                            "trades_reliability": trades_result["valid_percentage"],
                            "book_reliability": book_result["valid_percentage"],
                            "can_use_origin_time": True,
                        },
                    }
                )
            elif trades_reliable and not book_reliable:
                recommendation.update(
                    {
                        "strategy": "snapshot_anchored",
                        "reason": "Trades data is reliable but book snapshots are not. "
                        "Use snapshot timestamps as primary clock.",
                        "confidence": "medium",
                        "details": {
                            "trades_reliability": trades_result["valid_percentage"],
                            "book_reliability": book_result["valid_percentage"],
                            "can_use_origin_time": False,
                        },
                    }
                )
            elif not trades_reliable and book_reliable:
                recommendation.update(
                    {
                        "strategy": "book_time_primary",
                        "reason": "Book data is reliable but trades are not. "
                        "Use book timestamps as primary clock.",
                        "confidence": "medium",
                        "details": {
                            "trades_reliability": trades_result["valid_percentage"],
                            "book_reliability": book_result["valid_percentage"],
                            "can_use_origin_time": False,
                        },
                    }
                )
            else:
                recommendation.update(
                    {
                        "strategy": "alternative_timestamp",
                        "reason": "Both trades and book data have unreliable "
                        "origin_time. Consider using exchange_time or implementing "
                        "custom synchronization.",
                        "confidence": "low",
                        "details": {
                            "trades_reliability": trades_result["valid_percentage"],
                            "book_reliability": book_result["valid_percentage"],
                            "can_use_origin_time": False,
                        },
                    }
                )

        return recommendation

    def generate_detailed_validation_report(
        self, validation_results: list[dict]
    ) -> str:
        """Generate detailed validation report in markdown format.

        Args:
            validation_results: List of validation results from OriginTimeValidator

        Returns:
            Markdown-formatted report string
        """
        if not validation_results:
            return (
                "# Origin Time Completeness Report\n\nNo validation results provided.\n"
            )

        report_lines = []
        report_lines.append("# Origin Time Completeness Report")
        report_lines.append("")
        report_lines.append(
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        report_lines.append("")

        # Summary statistics
        summary = self.generate_summary_statistics(validation_results)
        report_lines.append("## Summary Statistics")
        report_lines.append("")
        report_lines.append(
            f"- **Total Datasets Analyzed:** {summary['total_datasets']}"
        )
        report_lines.append(
            f"- **Total Rows Analyzed:** {summary['total_rows_analyzed']:,}"
        )
        report_lines.append(f"- **Total Valid Rows:** {summary['total_valid_rows']:,}")
        report_lines.append(
            f"- **Overall Validity:** {summary['overall_validity_percentage']:.2f}%"
        )
        report_lines.append("")

        # Dataset details
        report_lines.append("## Dataset Details")
        report_lines.append("")

        for result in validation_results:
            report_lines.append(f"### {result['data_type'].title()} Data")
            report_lines.append("")
            report_lines.append(f"- **Total Rows:** {result['total_rows']:,}")
            report_lines.append(f"- **Valid Rows:** {result['valid_count']:,}")
            report_lines.append(
                f"- **Validity Rate:** {result['valid_percentage']:.2f}%"
            )
            report_lines.append("")

            # Validation details
            details = result["validation_details"]
            report_lines.append("#### Validation Breakdown")
            report_lines.append("")
            report_lines.append("| Issue Type | Count | Percentage |")
            report_lines.append("|------------|-------|------------|")

            for issue_type, issue_data in details.items():
                issue_name = issue_type.replace("_", " ").title()
                report_lines.append(
                    f"| {issue_name} | {issue_data['count']:,} | "
                    f"{issue_data['percentage']:.2f}% |"
                )

            report_lines.append("")

        # Recommendation
        recommendation = self.generate_chronological_recommendation(validation_results)
        report_lines.append("## Chronological Unification Recommendation")
        report_lines.append("")
        report_lines.append(f"**Recommended Strategy:** `{recommendation['strategy']}`")
        report_lines.append("")
        report_lines.append(f"**Reason:** {recommendation['reason']}")
        report_lines.append("")
        report_lines.append(f"**Confidence:** {recommendation['confidence'].title()}")
        report_lines.append("")

        if recommendation["details"]:
            report_lines.append("### Details")
            report_lines.append("")
            for key, value in recommendation["details"].items():
                formatted_key = key.replace("_", " ").title()
                if isinstance(value, float):
                    report_lines.append(f"- **{formatted_key}:** {value:.2f}%")
                else:
                    report_lines.append(f"- **{formatted_key}:** {value}")
            report_lines.append("")

        # Conclusion
        report_lines.append("## Conclusion")
        report_lines.append("")

        if recommendation["strategy"] == "origin_time_primary":
            report_lines.append(
                "The `origin_time` field is sufficiently reliable for chronological "
                "unification. The pipeline can use `origin_time` as the primary sort "
                "key for merging trades and book data."
            )
        elif recommendation["strategy"] == "snapshot_anchored":
            report_lines.append(
                "The `origin_time` field is not reliable for book snapshots. "
                "The pipeline should use the snapshot-anchored method, using snapshot "
                "timestamps as the primary clock and injecting trades into their "
                "respective 100ms windows."
            )
        else:
            report_lines.append(
                "The `origin_time` field has significant reliability issues. "
                "Alternative synchronization methods should be considered."
            )

        return "\n".join(report_lines)

    def save_report(
        self,
        validation_results: list[dict],
        filename: str = "origin_time_completeness_report.md",
    ) -> Path:
        """Save the analysis report to a file.

        Args:
            validation_results: List of validation results from OriginTimeValidator
            filename: Output filename (default: origin_time_completeness_report.md)

        Returns:
            Path to the saved report file
        """
        report_content = self.generate_detailed_validation_report(validation_results)

        report_path = self.output_path / filename
        report_path.write_text(report_content)

        logger.info(f"Report saved to: {report_path}")

        return report_path

    def print_summary(self, validation_results: list[dict]) -> None:
        """Print a summary of the validation results to console.

        Args:
            validation_results: List of validation results from OriginTimeValidator
        """
        if not validation_results:
            print("No validation results to display.")
            return

        print("\n" + "=" * 60)
        print("ORIGIN TIME COMPLETENESS ANALYSIS SUMMARY")
        print("=" * 60)

        summary = self.generate_summary_statistics(validation_results)

        print(f"Total Datasets: {summary['total_datasets']}")
        print(f"Total Rows: {summary['total_rows_analyzed']:,}")
        print(f"Overall Validity: {summary['overall_validity_percentage']:.2f}%")
        print()

        for dataset in summary["datasets"]:
            print(f"{dataset['data_type'].upper()} DATA:")
            print(f"  Rows: {dataset['total_rows']:,}")
            print(
                f"  Valid: {dataset['valid_count']:,} "
                f"({dataset['valid_percentage']:.2f}%)"
            )
            print()

        recommendation = self.generate_chronological_recommendation(validation_results)
        print(f"RECOMMENDATION: {recommendation['strategy']}")
        print(f"REASON: {recommendation['reason']}")
        print(f"CONFIDENCE: {recommendation['confidence'].upper()}")
        print("=" * 60)
