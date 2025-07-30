"""Timing and sequence validators."""

from pathlib import Path

from loguru import logger

from ..base import BaseValidator
from ..loaders import GoldenSampleLoader


class ChronologicalOrderValidator(BaseValidator):
    """Validate that messages are in chronological order."""

    def __init__(self):
        """Initialize chronological order validator."""
        super().__init__(name="Chronological Order Check")

    def _validate(self, filepath1: Path, filepath2: Path) -> tuple[bool, dict]:
        """Check chronological ordering in both files.

        Args:
            filepath1: Path to first file
            filepath2: Path to second file

        Returns:
            Tuple of (passed, metrics)
        """
        results = {}
        passed = True

        for idx, filepath in enumerate([filepath1, filepath2], 1):
            loader = GoldenSampleLoader()

            out_of_order = 0
            total_messages = 0
            last_timestamp = 0
            max_backwards_jump = 0

            for msg in loader.load_messages(filepath, show_progress=False):
                total_messages += 1

                if "capture_ns" in msg:
                    timestamp = msg["capture_ns"]

                    if timestamp < last_timestamp:
                        out_of_order += 1
                        backwards_jump = last_timestamp - timestamp
                        max_backwards_jump = max(max_backwards_jump, backwards_jump)

                    last_timestamp = timestamp

            file_result = {
                "total_messages": total_messages,
                "out_of_order": out_of_order,
                "out_of_order_ratio": out_of_order / max(total_messages, 1),
                "max_backwards_jump_ns": max_backwards_jump,
                "chronologically_ordered": out_of_order == 0,
            }

            results[f"file{idx}"] = file_result
            passed &= out_of_order == 0

            logger.info(f"File {idx}: {out_of_order}/{total_messages} out of order")

        metrics = {
            **results,
            "both_ordered": passed,
            "interpretation": (
                "Both files are chronologically ordered"
                if passed
                else "Chronological ordering violations detected"
            ),
        }

        return passed, metrics


class SequenceGapValidator(BaseValidator):
    """Validate sequence gaps in orderbook updates."""

    def __init__(self, max_gap_ratio: float = 0.0001):
        """Initialize sequence gap validator.

        Args:
            max_gap_ratio: Maximum acceptable gap ratio (default 0.01%)
        """
        super().__init__(name="Sequence Gap Detection", max_gap_ratio=max_gap_ratio)

    def _validate(self, filepath1: Path, filepath2: Path) -> tuple[bool, dict]:
        """Check for sequence gaps in orderbook updates.

        Args:
            filepath1: Path to first file
            filepath2: Path to second file

        Returns:
            Tuple of (passed, metrics)
        """
        results = {}
        passed = True

        for idx, filepath in enumerate([filepath1, filepath2], 1):
            loader = GoldenSampleLoader()

            total_updates = 0
            gaps_detected = 0
            max_gap_size = 0
            last_update_id = {}  # Per symbol

            for msg in loader.extract_orderbook_updates(filepath):
                if "data" in msg and "U" in msg["data"] and "u" in msg["data"]:
                    total_updates += 1

                    # Extract symbol from stream
                    symbol = msg["stream"].split("@")[0]
                    first_update_id = msg["data"]["U"]
                    last_update_id_msg = msg["data"]["u"]

                    # Check for gap
                    if symbol in last_update_id:
                        expected_start = last_update_id[symbol] + 1
                        if first_update_id != expected_start:
                            gaps_detected += 1
                            gap_size = first_update_id - expected_start
                            max_gap_size = max(max_gap_size, abs(gap_size))

                    last_update_id[symbol] = last_update_id_msg

            gap_ratio = gaps_detected / max(total_updates, 1)

            file_result = {
                "total_updates": total_updates,
                "gaps_detected": gaps_detected,
                "gap_ratio": gap_ratio,
                "max_gap_size": max_gap_size,
                "symbols_tracked": len(last_update_id),
            }

            results[f"file{idx}"] = file_result
            passed &= gap_ratio <= self.config["max_gap_ratio"]

            logger.info(
                f"File {idx}: {gaps_detected}/{total_updates} gaps "
                f"(ratio: {gap_ratio:.6f})"
            )

        metrics = {
            **results,
            "max_gap_ratio": self.config["max_gap_ratio"],
            "both_within_threshold": passed,
            "interpretation": (
                f"Sequence gaps within threshold ({self.config['max_gap_ratio']:.4%})"
                if passed
                else f"Sequence gaps exceed threshold ({self.config['max_gap_ratio']:.4%})"
            ),
        }

        return passed, metrics
