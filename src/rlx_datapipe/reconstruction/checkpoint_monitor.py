"""Performance monitoring for checkpoint impact."""

import time
from dataclasses import dataclass, field

from loguru import logger


@dataclass
class CheckpointMetrics:
    """Metrics for checkpoint performance monitoring."""

    # Timing metrics
    checkpoint_count: int = 0
    total_checkpoint_time_ms: float = 0.0
    max_checkpoint_time_ms: float = 0.0
    min_checkpoint_time_ms: float = float("inf")

    # Throughput metrics
    events_before_checkpoint: int = 0
    events_after_checkpoint: int = 0
    throughput_samples: list[float] = field(default_factory=list)

    # Impact metrics
    throughput_degradation_percent: float = 0.0
    average_checkpoint_interval_sec: float = 0.0

    # Checkpoint timestamps
    checkpoint_timestamps: list[float] = field(default_factory=list)


class CheckpointMonitor:
    """Monitor checkpoint performance impact on pipeline throughput."""

    def __init__(self, sample_window_sec: float = 10.0):
        """Initialize checkpoint monitor.
        
        Args:
            sample_window_sec: Window size for throughput sampling
        """
        self.sample_window_sec = sample_window_sec
        self.metrics = CheckpointMetrics()

        # Throughput tracking
        self.events_in_window = 0
        self.window_start_time = time.time()
        self.baseline_throughput: float = 0.0
        self.current_throughput: float = 0.0

        # Checkpoint tracking
        self.checkpoint_in_progress = False
        self.checkpoint_start_time: float = 0.0

    def record_events(self, event_count: int) -> None:
        """Record processed events for throughput calculation.
        
        Args:
            event_count: Number of events processed
        """
        self.events_in_window += event_count
        self.metrics.events_after_checkpoint += event_count

        # Check if sample window has elapsed
        current_time = time.time()
        window_duration = current_time - self.window_start_time

        if window_duration >= self.sample_window_sec:
            # Calculate throughput
            self.current_throughput = self.events_in_window / window_duration
            self.metrics.throughput_samples.append(self.current_throughput)

            # Update baseline if no checkpoint in progress
            if not self.checkpoint_in_progress and self.baseline_throughput == 0:
                self.baseline_throughput = self.current_throughput

            # Reset window
            self.events_in_window = 0
            self.window_start_time = current_time

    def checkpoint_started(self) -> None:
        """Mark the start of a checkpoint operation."""
        self.checkpoint_in_progress = True
        self.checkpoint_start_time = time.time()
        self.metrics.events_before_checkpoint = self.metrics.events_after_checkpoint

        logger.debug(f"Checkpoint started at throughput: {self.current_throughput:.0f} events/sec")

    def checkpoint_completed(self) -> None:
        """Mark the completion of a checkpoint operation."""
        if not self.checkpoint_in_progress:
            return

        checkpoint_duration_ms = (time.time() - self.checkpoint_start_time) * 1000

        # Update metrics
        self.metrics.checkpoint_count += 1
        self.metrics.total_checkpoint_time_ms += checkpoint_duration_ms
        self.metrics.max_checkpoint_time_ms = max(
            self.metrics.max_checkpoint_time_ms,
            checkpoint_duration_ms
        )
        self.metrics.min_checkpoint_time_ms = min(
            self.metrics.min_checkpoint_time_ms,
            checkpoint_duration_ms
        )

        # Record timestamp
        self.metrics.checkpoint_timestamps.append(time.time())

        # Calculate average interval
        if len(self.metrics.checkpoint_timestamps) > 1:
            intervals = [
                self.metrics.checkpoint_timestamps[i] - self.metrics.checkpoint_timestamps[i-1]
                for i in range(1, len(self.metrics.checkpoint_timestamps))
            ]
            self.metrics.average_checkpoint_interval_sec = sum(intervals) / len(intervals)

        # Calculate throughput impact
        if self.baseline_throughput > 0 and self.current_throughput > 0:
            degradation = (
                (self.baseline_throughput - self.current_throughput) /
                self.baseline_throughput * 100
            )
            self.metrics.throughput_degradation_percent = max(0, degradation)

        self.checkpoint_in_progress = False

        logger.info(
            f"Checkpoint completed in {checkpoint_duration_ms:.1f}ms "
            f"(throughput impact: {self.metrics.throughput_degradation_percent:.1f}%)"
        )

    def get_metrics(self) -> dict[str, any]:
        """Get checkpoint performance metrics.
        
        Returns:
            Dictionary of performance metrics
        """
        avg_checkpoint_time = (
            self.metrics.total_checkpoint_time_ms / max(1, self.metrics.checkpoint_count)
        )

        avg_throughput = (
            sum(self.metrics.throughput_samples) / max(1, len(self.metrics.throughput_samples))
        )

        return {
            "checkpoint_count": self.metrics.checkpoint_count,
            "avg_checkpoint_time_ms": avg_checkpoint_time,
            "max_checkpoint_time_ms": self.metrics.max_checkpoint_time_ms,
            "min_checkpoint_time_ms": (
                self.metrics.min_checkpoint_time_ms
                if self.metrics.min_checkpoint_time_ms != float("inf")
                else 0
            ),
            "throughput_degradation_percent": self.metrics.throughput_degradation_percent,
            "avg_checkpoint_interval_sec": self.metrics.average_checkpoint_interval_sec,
            "baseline_throughput": self.baseline_throughput,
            "current_throughput": self.current_throughput,
            "avg_throughput": avg_throughput,
            "events_processed": self.metrics.events_after_checkpoint,
        }

    def log_summary(self) -> None:
        """Log a summary of checkpoint performance metrics."""
        metrics = self.get_metrics()

        logger.info(
            f"Checkpoint Performance Summary:\n"
            f"  Checkpoints: {metrics['checkpoint_count']}\n"
            f"  Avg Duration: {metrics['avg_checkpoint_time_ms']:.1f}ms\n"
            f"  Max Duration: {metrics['max_checkpoint_time_ms']:.1f}ms\n"
            f"  Throughput Impact: {metrics['throughput_degradation_percent']:.1f}%\n"
            f"  Avg Interval: {metrics['avg_checkpoint_interval_sec']:.0f}s\n"
            f"  Avg Throughput: {metrics['avg_throughput']:.0f} events/sec"
        )

