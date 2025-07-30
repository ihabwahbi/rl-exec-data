"""Base classes for validation framework."""

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class ValidationResult:
    """Result from a single validator."""

    validator_name: str
    passed: bool
    metrics: dict[str, Any]
    duration_seconds: float
    error_message: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "validator": self.validator_name,
            "passed": self.passed,
            "metrics": self.metrics,
            "duration": self.duration_seconds,
            "error": self.error_message,
        }


@dataclass
class ValidationReport:
    """Complete validation report containing all results."""

    golden_sample_path: str
    comparison_path: str
    results: list[ValidationResult]
    total_duration: float
    peak_memory_mb: float
    overall_passed: bool
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "validation_run": {
                "timestamp": self.timestamp,
                "golden_sample_path": self.golden_sample_path,
                "comparison_path": self.comparison_path,
                "duration_seconds": self.total_duration,
                "peak_memory_mb": self.peak_memory_mb,
            },
            "results": [r.to_dict() for r in self.results],
            "overall_passed": self.overall_passed,
        }

    def to_json(self, filepath: Path) -> None:
        """Save report as JSON."""
        with open(filepath, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    def to_markdown(self, filepath: Path) -> None:
        """Save report as markdown."""
        with open(filepath, "w") as f:
            f.write("# Validation Report\n\n")
            f.write(f"**Generated**: {self.timestamp}\n\n")
            f.write("## Summary\n\n")
            f.write(
                f"- **Status**: {'✅ PASSED' if self.overall_passed else '❌ FAILED'}\n"
            )
            f.write(f"- **Golden Sample**: `{self.golden_sample_path}`\n")
            f.write(f"- **Comparison Data**: `{self.comparison_path}`\n")
            f.write(f"- **Duration**: {self.total_duration:.2f} seconds\n")
            f.write(f"- **Peak Memory**: {self.peak_memory_mb:.2f} MB\n\n")

            f.write("## Validation Results\n\n")
            f.write("| Validator | Status | Duration | Key Metrics |\n")
            f.write("|-----------|--------|----------|-------------|\n")

            for result in self.results:
                status = "✅ Pass" if result.passed else "❌ Fail"
                duration = f"{result.duration_seconds:.2f}s"

                # Format key metrics
                key_metrics = []
                if result.error_message:
                    key_metrics.append(f"Error: {result.error_message}")
                else:
                    # Show up to 3 key metrics
                    for k, v in list(result.metrics.items())[:3]:
                        if isinstance(v, float):
                            key_metrics.append(f"{k}: {v:.4f}")
                        else:
                            key_metrics.append(f"{k}: {v}")

                metrics_str = "<br>".join(key_metrics)
                f.write(
                    f"| {result.validator_name} | {status} | {duration} | {metrics_str} |\n"
                )

            f.write("\n## Detailed Metrics\n\n")
            for result in self.results:
                f.write(f"### {result.validator_name}\n\n")
                if result.error_message:
                    f.write(f"**Error**: {result.error_message}\n\n")
                else:
                    f.write("```json\n")
                    f.write(json.dumps(result.metrics, indent=2))
                    f.write("\n```\n\n")


class BaseValidator(ABC):
    """Base class for all validators."""

    def __init__(self, name: str, **config):
        self.name = name
        self.config = config

    @abstractmethod
    def _validate(self, data1: Any, data2: Any) -> tuple[bool, dict]:
        """Implement validation logic.

        Args:
            data1: First dataset (usually golden sample)
            data2: Second dataset (usually reconstructed data)

        Returns:
            Tuple of (passed, metrics)
        """

    def validate(self, data1: Any, data2: Any) -> ValidationResult:
        """Run validation with timing and error handling."""
        start_time = time.perf_counter()

        try:
            passed, metrics = self._validate(data1, data2)
            duration = time.perf_counter() - start_time

            return ValidationResult(
                validator_name=self.name,
                passed=passed,
                metrics=metrics,
                duration_seconds=duration,
            )
        except Exception as e:
            duration = time.perf_counter() - start_time
            return ValidationResult(
                validator_name=self.name,
                passed=False,
                metrics={},
                duration_seconds=duration,
                error_message=str(e),
            )
