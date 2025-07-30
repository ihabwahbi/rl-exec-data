"""Validation pipeline for orchestrating multiple validators."""

import asyncio
import json
import time
from pathlib import Path

import psutil
from loguru import logger

from .base import BaseValidator, ValidationReport, ValidationResult
from .loaders import GoldenSampleLoader


class ValidationPipeline:
    """Orchestrate validation comparing golden samples to other data."""

    def __init__(self, max_workers: int | None = None):
        """Initialize validation pipeline.

        Args:
            max_workers: Maximum number of parallel workers
        """
        self.validators: list[BaseValidator] = []
        self.max_workers = max_workers or min(4, psutil.cpu_count())
        self._checkpoints: dict[str, dict] = {}
        self._peak_memory = 0

    def add_validator(self, validator: BaseValidator) -> "ValidationPipeline":
        """Add a validator to the pipeline.

        Args:
            validator: Validator instance to add

        Returns:
            Self for method chaining
        """
        self.validators.append(validator)
        logger.info(f"Added validator: {validator.name}")
        return self

    def run(
        self,
        golden_sample_path: Path,
        comparison_path: Path,
        checkpoint_file: Path | None = None,
    ) -> ValidationReport:
        """Run validation pipeline synchronously.

        Args:
            golden_sample_path: Path to golden sample file
            comparison_path: Path to comparison data file
            checkpoint_file: Optional checkpoint file for resume capability

        Returns:
            ValidationReport with all results
        """
        # Convert to Path objects
        golden_sample_path = Path(golden_sample_path)
        comparison_path = Path(comparison_path)

        # Validate inputs
        if not golden_sample_path.exists():
            raise FileNotFoundError(f"Golden sample not found: {golden_sample_path}")
        if not comparison_path.exists():
            raise FileNotFoundError(f"Comparison file not found: {comparison_path}")

        logger.info("Starting validation pipeline")
        logger.info(f"  Golden sample: {golden_sample_path}")
        logger.info(f"  Comparison: {comparison_path}")

        # Load checkpoint if exists
        if checkpoint_file and checkpoint_file.exists():
            try:
                with open(checkpoint_file) as f:
                    content = f.read().strip()
                    if content:
                        self._checkpoints = json.loads(content)
                    else:
                        self._checkpoints = {}
                logger.info(
                    f"Loaded checkpoint with {len(self._checkpoints)} completed validators"
                )
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"Failed to load checkpoint: {e}. Starting fresh.")
                self._checkpoints = {}

        # Track metrics
        start_time = time.perf_counter()
        results = []

        # Monitor memory
        process = psutil.Process()
        self._peak_memory = process.memory_info().rss

        # Create data loaders
        golden_loader = GoldenSampleLoader()
        comparison_loader = GoldenSampleLoader()

        # Run each validator
        for validator in self.validators:
            # Skip if already completed in checkpoint
            if validator.name in self._checkpoints:
                logger.info(f"Skipping {validator.name} (found in checkpoint)")
                checkpoint_data = self._checkpoints[validator.name]
                # Convert from to_dict format back to ValidationResult
                result = ValidationResult(
                    validator_name=checkpoint_data["validator"],
                    passed=checkpoint_data["passed"],
                    metrics=checkpoint_data["metrics"],
                    duration_seconds=checkpoint_data["duration"],
                    error_message=checkpoint_data.get("error"),
                )
                results.append(result)
                continue

            logger.info(f"Running validator: {validator.name}")

            try:
                # Load data based on validator requirements
                if (
                    hasattr(validator, "_requires_full_data")
                    and validator._requires_full_data
                ):
                    # Load full datasets for validators that need them
                    logger.info("  Loading full datasets...")
                    if (
                        "trade" in validator.name.lower()
                        or "power" in validator.name.lower()
                    ):
                        golden_data = golden_loader.load_all_trades(golden_sample_path)
                        comparison_data = comparison_loader.load_all_trades(
                            comparison_path
                        )
                    else:
                        golden_data = golden_loader.load_all_prices(golden_sample_path)
                        comparison_data = comparison_loader.load_all_prices(
                            comparison_path
                        )
                else:
                    # For streaming validators, pass file paths
                    golden_data = golden_sample_path
                    comparison_data = comparison_path

                # Run validation
                result = validator.validate(golden_data, comparison_data)
                results.append(result)

                # Save checkpoint after each validator
                if checkpoint_file:
                    self._checkpoints[validator.name] = result.to_dict()
                    self._save_checkpoint(checkpoint_file)

                # Update peak memory
                current_memory = process.memory_info().rss
                self._peak_memory = max(self._peak_memory, current_memory)

                logger.info(
                    f"  Result: {'PASSED' if result.passed else 'FAILED'} "
                    f"(duration: {result.duration_seconds:.2f}s)"
                )

            except Exception as e:
                logger.error(f"Error in validator {validator.name}: {e}")
                result = ValidationResult(
                    validator_name=validator.name,
                    passed=False,
                    metrics={},
                    duration_seconds=0,
                    error_message=str(e),
                )
                results.append(result)

        # Calculate total duration
        total_duration = time.perf_counter() - start_time

        # Create report
        report = ValidationReport(
            golden_sample_path=str(golden_sample_path),
            comparison_path=str(comparison_path),
            results=results,
            total_duration=total_duration,
            peak_memory_mb=self._peak_memory / (1024 * 1024),
            overall_passed=all(r.passed for r in results),
        )

        logger.info(
            f"Validation complete: {'PASSED' if report.overall_passed else 'FAILED'}"
        )
        logger.info(f"Total duration: {total_duration:.2f}s")
        logger.info(f"Peak memory: {report.peak_memory_mb:.2f}MB")

        return report

    async def run_async(
        self,
        golden_sample_path: Path,
        comparison_path: Path,
        checkpoint_file: Path | None = None,
    ) -> ValidationReport:
        """Run validation pipeline asynchronously.

        Args:
            golden_sample_path: Path to golden sample file
            comparison_path: Path to comparison data file
            checkpoint_file: Optional checkpoint file

        Returns:
            ValidationReport with all results
        """
        # For now, wrap synchronous execution
        # Full async implementation would require async validators
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.run, golden_sample_path, comparison_path, checkpoint_file
        )

    def _save_checkpoint(self, checkpoint_file: Path) -> None:
        """Save checkpoint to file."""
        with open(checkpoint_file, "w") as f:
            json.dump(self._checkpoints, f, indent=2)

    def clear_validators(self) -> None:
        """Clear all validators from pipeline."""
        self.validators = []
        logger.info("Cleared all validators")

    def get_validator_names(self) -> list[str]:
        """Get list of validator names in pipeline."""
        return [v.name for v in self.validators]
