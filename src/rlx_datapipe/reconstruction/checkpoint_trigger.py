"""Checkpoint trigger mechanism for time-based and event-based checkpointing."""

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from loguru import logger


class TriggerType(Enum):
    """Types of checkpoint triggers."""
    TIME_BASED = "time_based"
    EVENT_BASED = "event_based"
    MANUAL = "manual"
    SHUTDOWN = "shutdown"


@dataclass
class CheckpointTriggerConfig:
    """Configuration for checkpoint triggers."""

    # Time-based trigger (seconds)
    time_interval: float = 300.0  # 5 minutes

    # Event-based trigger (number of events)
    event_interval: int = 1_000_000  # 1M events

    # Enable/disable specific triggers
    enable_time_trigger: bool = True
    enable_event_trigger: bool = True

    # Grace period to avoid too frequent checkpoints (seconds)
    min_checkpoint_interval: float = 30.0


class CheckpointTrigger:
    """Manages checkpoint triggering based on time and event counts."""

    def __init__(
        self,
        config: CheckpointTriggerConfig,
        checkpoint_callback: Callable[[], asyncio.Task],
    ):
        """Initialize checkpoint trigger.
        
        Args:
            config: Trigger configuration
            checkpoint_callback: Async callback to invoke for checkpointing
        """
        self.config = config
        self.checkpoint_callback = checkpoint_callback

        # Tracking state
        self.last_checkpoint_time = time.time()
        self.last_checkpoint_event_count = 0
        self.total_events_processed = 0

        # Timer task
        self._timer_task: asyncio.Task | None = None
        self._running = False

        logger.info(
            f"CheckpointTrigger initialized: "
            f"time_interval={config.time_interval}s, "
            f"event_interval={config.event_interval}"
        )

    async def start(self) -> None:
        """Start the checkpoint trigger."""
        if self._running:
            logger.warning("CheckpointTrigger already running")
            return

        self._running = True

        # Start time-based trigger if enabled
        if self.config.enable_time_trigger:
            self._timer_task = asyncio.create_task(self._time_trigger_loop())
            logger.info(f"Started time-based trigger (interval: {self.config.time_interval}s)")

    async def stop(self) -> None:
        """Stop the checkpoint trigger."""
        self._running = False

        # Cancel timer task
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
            try:
                await self._timer_task
            except asyncio.CancelledError:
                pass

        # Trigger final checkpoint on shutdown
        await self._trigger_checkpoint(TriggerType.SHUTDOWN)

        logger.info("CheckpointTrigger stopped")

    async def record_events(self, event_count: int) -> None:
        """Record processed events and check for event-based trigger.
        
        Args:
            event_count: Number of events processed
        """
        if not self.config.enable_event_trigger:
            return

        self.total_events_processed += event_count

        # Check if we've crossed the event threshold
        events_since_checkpoint = (
            self.total_events_processed - self.last_checkpoint_event_count
        )

        if events_since_checkpoint >= self.config.event_interval:
            await self._trigger_checkpoint(TriggerType.EVENT_BASED)

    async def trigger_manual_checkpoint(self) -> bool:
        """Manually trigger a checkpoint.
        
        Returns:
            True if checkpoint was triggered, False if skipped due to grace period
        """
        return await self._trigger_checkpoint(TriggerType.MANUAL)

    async def _time_trigger_loop(self) -> None:
        """Background loop for time-based triggers."""
        try:
            while self._running:
                # Wait for the configured interval
                await asyncio.sleep(self.config.time_interval)

                if self._running:
                    await self._trigger_checkpoint(TriggerType.TIME_BASED)

        except asyncio.CancelledError:
            logger.debug("Time trigger loop cancelled")
        except Exception as e:
            logger.error(f"Error in time trigger loop: {e}")

    async def _trigger_checkpoint(self, trigger_type: TriggerType) -> bool:
        """Trigger a checkpoint if grace period allows.
        
        Args:
            trigger_type: Type of trigger causing the checkpoint
            
        Returns:
            True if checkpoint was triggered, False if skipped
        """
        current_time = time.time()
        time_since_last = current_time - self.last_checkpoint_time

        # Check grace period (except for shutdown triggers)
        if (trigger_type != TriggerType.SHUTDOWN and
            time_since_last < self.config.min_checkpoint_interval):
            logger.debug(
                f"Skipping {trigger_type.value} checkpoint: "
                f"only {time_since_last:.1f}s since last checkpoint "
                f"(min interval: {self.config.min_checkpoint_interval}s)"
            )
            return False

        try:
            logger.info(
                f"Triggering {trigger_type.value} checkpoint "
                f"(events since last: {self.total_events_processed - self.last_checkpoint_event_count})"
            )

            # Invoke the checkpoint callback
            checkpoint_task = await self.checkpoint_callback()

            # Update tracking state
            self.last_checkpoint_time = current_time
            self.last_checkpoint_event_count = self.total_events_processed

            # Wait for checkpoint to complete if it's a shutdown trigger
            if trigger_type == TriggerType.SHUTDOWN and checkpoint_task:
                await checkpoint_task

            return True

        except Exception as e:
            logger.error(f"Failed to trigger checkpoint: {e}")
            return False

    def get_stats(self) -> dict:
        """Get trigger statistics."""
        return {
            "total_events_processed": self.total_events_processed,
            "last_checkpoint_time": self.last_checkpoint_time,
            "last_checkpoint_event_count": self.last_checkpoint_event_count,
            "time_since_last_checkpoint": time.time() - self.last_checkpoint_time,
            "events_since_last_checkpoint": (
                self.total_events_processed - self.last_checkpoint_event_count
            ),
        }

