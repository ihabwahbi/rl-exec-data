#!/usr/bin/env python3
"""
Golden Sample Delta Feed Validation Script

Validates delta feed quality from production golden samples captured in Story 1.2.1.
Analyzes sequence gaps and data quality across different market regimes to support
GO/NO-GO decision for Epic 2 reconstruction strategy.
"""

import argparse
import gzip
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add src to path to import our modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from loguru import logger

from rlx_datapipe.common.logging import setup_logging


class GoldenSampleDeltaValidator:
    """Validates delta feed quality from golden sample captures."""

    def __init__(self) -> None:
        """Initialize validator."""
        self.results: Dict[str, Any] = {
            "validation_timestamp": time.time(),
            "market_regimes": {},
            "overall_summary": {
                "go_decision": None,
                "reasons": [],
                "recommendations": []
            }
        }

    def validate_regime(self, regime_name: str, regime_path: Path) -> dict[str, Any]:
        """
        Validate delta feed quality for a specific market regime.

        Args:
            regime_name: Name of the market regime (e.g. high_volume)
            regime_path: Path to the regime directory with JSONL.gz files

        Returns:
            Dictionary containing validation results for the regime
        """
        logger.info(f"Validating {regime_name} regime from {regime_path}")

        regime_results = {
            "regime": regime_name,
            "files_analyzed": 0,
            "total_messages": 0,
            "depth_updates": 0,
            "sequence_gaps": {
                "count": 0,
                "max_gap": 0,
                "gaps_by_size": {},
                "gap_ratio_percent": 0.0
            },
            "data_quality": {
                "valid_updates": 0,
                "invalid_updates": 0,
                "out_of_order": 0
            },
            "performance": {
                "processing_time_seconds": 0.0,
                "messages_per_second": 0.0
            }
        }

        start_time = time.time()

        # Get all JSONL.gz files in the regime directory
        jsonl_files = sorted(regime_path.glob("*.jsonl.gz"))
        if not jsonl_files:
            logger.warning(f"No JSONL.gz files found in {regime_path}")
            return regime_results

        logger.info(f"Found {len(jsonl_files)} files to analyze")

        # Track sequence IDs per symbol
        symbol_sequences: Dict[str, Dict[str, Any]] = {}

        # Process each file
        for file_path in jsonl_files:
            skip_file = (
                file_path.name == "checksums.txt" or
                file_path.name.endswith(".incomplete")
            )
            if skip_file:
                continue

            logger.debug(f"Processing {file_path.name}")
            regime_results["files_analyzed"] += 1

            try:
                with gzip.open(file_path, "rt", encoding="utf-8") as f:
                    for line_num, line in enumerate(f):
                        # Process in batches to control memory usage
                        if line_num > 0 and line_num % 100000 == 0:
                            logger.debug(f"Processed {line_num:,} lines from {file_path.name}")
                        try:
                            msg = json.loads(line.strip())
                            regime_results["total_messages"] += 1

                            # Extract stream type and data
                            stream = msg.get("stream", "")
                            data = msg.get("data", {})

                            # We're interested in depth updates for delta feed analysis
                            if "@depth" in stream:
                                regime_results["depth_updates"] += 1

                                # Extract symbol from stream
                                symbol = stream.split("@")[0]

                                # Get update IDs
                                first_update_id = data.get("U")
                                final_update_id = data.get("u")

                                if first_update_id is None or final_update_id is None:
                                    regime_results["data_quality"]["invalid_updates"] += 1
                                    continue

                                regime_results["data_quality"]["valid_updates"] += 1

                                # Initialize symbol tracking if needed
                                if symbol not in symbol_sequences:
                                    symbol_sequences[symbol] = {
                                        "last_update_id": None,
                                        "gaps": []
                                    }

                                # Check for sequence gaps
                                last_id = symbol_sequences[symbol]["last_update_id"]
                                if last_id is not None:
                                    expected_id = last_id + 1

                                    # Check if there's a gap
                                    if first_update_id > expected_id:
                                        gap_size = first_update_id - expected_id
                                        symbol_sequences[symbol]["gaps"].append(gap_size)
                                        regime_results["sequence_gaps"]["count"] += 1
                                        regime_results["sequence_gaps"]["max_gap"] = max(
                                            regime_results["sequence_gaps"]["max_gap"],
                                            gap_size
                                        )

                                        # Categorize gap size
                                        gap_bucket = self._get_gap_size_bucket(gap_size)
                                        gaps_by_size = regime_results["sequence_gaps"]["gaps_by_size"]
                                        gaps_by_size[gap_bucket] = gaps_by_size.get(gap_bucket, 0) + 1

                                    elif first_update_id < expected_id:
                                        # Out of order update
                                        regime_results["data_quality"]["out_of_order"] += 1

                                # Update last seen ID
                                symbol_sequences[symbol]["last_update_id"] = final_update_id

                        except json.JSONDecodeError as e:
                            logger.warning(f"Invalid JSON at line {line_num}: {e}")
                        except Exception as e:
                            logger.warning(f"Error processing message at line {line_num}: {e}")

            except Exception as e:
                logger.error(f"Error processing file {file_path}: {e}")

        # Calculate gap ratio
        total_gap_count = 0
        total_range = 0

        for symbol, seq_data in symbol_sequences.items():
            if seq_data["gaps"]:
                total_gap_count += sum(seq_data["gaps"])

            if seq_data["last_update_id"] is not None:
                # Estimate the total range
                total_range += seq_data["last_update_id"]

        if total_range > 0:
            regime_results["sequence_gaps"]["gap_ratio_percent"] = (total_gap_count / total_range) * 100

        # Calculate performance metrics
        end_time = time.time()
        regime_results["performance"]["processing_time_seconds"] = end_time - start_time

        if regime_results["performance"]["processing_time_seconds"] > 0:
            total_msgs = regime_results["total_messages"]
            proc_time = regime_results["performance"]["processing_time_seconds"]
            regime_results["performance"]["messages_per_second"] = total_msgs / proc_time

        return regime_results

    def _get_gap_size_bucket(self, gap: int) -> str:
        """Categorize gaps by size.
        
        Args:
            gap: The gap size to categorize
            
        Returns:
            String representation of the gap size bucket
        """
        if gap <= 10:
            return "1-10"
        if gap <= 100:
            return "11-100"
        if gap <= 1000:
            return "101-1000"
        return "1000+"

    def validate_all_regimes(self, golden_samples_path: Path) -> None:
        """
        Validate delta feed quality across all market regimes.

        Args:
            golden_samples_path: Path to golden_samples directory
        """
        regimes = ["high_volume", "low_volume", "special_event"]

        for regime in regimes:
            regime_path = golden_samples_path / regime
            if regime_path.exists():
                self.results["market_regimes"][regime] = self.validate_regime(regime, regime_path)
            else:
                logger.warning(f"Regime directory not found: {regime_path}")

        # Generate overall summary
        self._generate_summary()

    def _generate_summary(self) -> None:
        """Generate overall summary and GO/NO-GO decision."""
        all_passed = True
        reasons = []
        recommendations = []

        logger.info("\n=== VALIDATION RESULTS BY REGIME ===")

        for regime_name, regime_data in self.results["market_regimes"].items():
            logger.info(f"\n{regime_name.upper()} REGIME:")
            logger.info(f"  Files analyzed: {regime_data['files_analyzed']}")
            logger.info(f"  Total messages: {regime_data['total_messages']:,}")
            logger.info(f"  Depth updates: {regime_data['depth_updates']:,}")
            logger.info(f"  Sequence gaps: {regime_data['sequence_gaps']['count']:,}")
            logger.info(f"  Max gap size: {regime_data['sequence_gaps']['max_gap']:,}")
            logger.info(f"  Gap ratio: {regime_data['sequence_gaps']['gap_ratio_percent']:.4f}%")

            # Check if gap ratio meets threshold
            gap_ratio = regime_data["sequence_gaps"]["gap_ratio_percent"]
            if gap_ratio < 0.1:
                logger.info(f"  ✅ Gap ratio {gap_ratio:.4f}% < 0.1% threshold")
            else:
                logger.error(f"  ❌ Gap ratio {gap_ratio:.4f}% >= 0.1% threshold")
                all_passed = False
                msg = f"{regime_name} regime gap ratio {gap_ratio:.4f}% exceeds 0.1% threshold"
                reasons.append(msg)

        # Overall decision
        logger.info("\n=== OVERALL GO/NO-GO DECISION ===")

        if all_passed:
            self.results["overall_summary"]["go_decision"] = "GO"
            logger.info("✅ GO - All regimes pass delta feed quality criteria")
            reasons.append("All market regimes show sequence gap ratios < 0.1%")
            reasons.append("Delta feed quality is sufficient for Epic 2 reconstruction")

            recommendations.extend([
                "Proceed with FullReconstruction strategy as primary approach",
                "SnapshotAnchoredStrategy can be used as fallback if needed",
                "Implement sequence gap detection and recovery in production"
            ])
        else:
            self.results["overall_summary"]["go_decision"] = "NO-GO"
            logger.error("❌ NO-GO - Delta feed quality issues detected")

            recommendations.extend([
                "Consider SnapshotAnchoredStrategy as primary approach",
                "Investigate root cause of sequence gaps in affected regimes",
                "May need to adjust -5bp VWAP target based on data quality"
            ])

        # Add regime-specific patterns
        if self.results["market_regimes"]:
            # Compare gap patterns across regimes
            gap_patterns = []
            for regime_name, regime_data in self.results["market_regimes"].items():
                gap_ratio = regime_data["sequence_gaps"]["gap_ratio_percent"]
                gap_patterns.append((regime_name, gap_ratio))

            gap_patterns.sort(key=lambda x: x[1], reverse=True)

            if gap_patterns[0][1] > gap_patterns[-1][1] * 2:
                recommendations.append(
                    f"Note: {gap_patterns[0][0]} shows significantly higher gap ratio "
                    f"({gap_patterns[0][1]:.4f}%) compared to {gap_patterns[-1][0]} "
                    f"({gap_patterns[-1][1]:.4f}%). Consider regime-specific handling."
                )

        self.results["overall_summary"]["reasons"] = reasons
        self.results["overall_summary"]["recommendations"] = recommendations

        # Print summary
        logger.info("\nREASONS:")
        for reason in reasons:
            logger.info(f"  - {reason}")

        logger.info("\nRECOMMENDATIONS:")
        for rec in recommendations:
            logger.info(f"  - {rec}")

    def save_results(self, output_path: Path) -> None:
        """Save validation results to JSON file."""
        with output_path.open("w") as f:
            json.dump(self.results, f, indent=2)
        logger.info(f"Results saved to {output_path}")


def main() -> None:
    """Main function to run golden sample delta validation."""
    parser = argparse.ArgumentParser(
        description="Validate delta feed quality from production golden samples"
    )
    parser.add_argument(
        "--golden-samples-dir",
        type=Path,
        default=Path("data/golden_samples"),
        help="Path to golden samples directory (default: data/golden_samples)"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("data/golden_samples/delta_validation_results.json"),
        help="Output JSON file path"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(log_level=log_level)

    # Validate input path
    if not args.golden_samples_dir.exists():
        logger.error(f"Golden samples directory not found: {args.golden_samples_dir}")
        sys.exit(1)

    # Initialize validator
    validator = GoldenSampleDeltaValidator()

    # Run validation
    try:
        validator.validate_all_regimes(args.golden_samples_dir)
        validator.save_results(args.output)
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
