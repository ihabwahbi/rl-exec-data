"""Checkpoint manager for order book state persistence."""

import asyncio
import json
import os
import pickle
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from loguru import logger

from .checkpoint_monitor import CheckpointMonitor
from .checkpoint_trigger import CheckpointTrigger, CheckpointTriggerConfig
from .state_snapshot import PipelineState, StateSnapshot
from .wal_manager import WALManager


class CheckpointManager:
    """Manages checkpoints for order book state recovery."""

    def __init__(
        self,
        checkpoint_dir: Path,
        symbol: str,
        max_checkpoints: int = 3,
        use_pickle: bool = True,
        enable_time_trigger: bool = True,
        time_interval: float = 300.0,  # 5 minutes
        event_interval: int = 1_000_000,  # 1M events
    ):
        """
        Initialize checkpoint manager.

        Args:
            checkpoint_dir: Directory for storing checkpoints
            symbol: Trading symbol for checkpoint naming
            max_checkpoints: Maximum number of checkpoints to keep
            use_pickle: Use pickle format (True) or JSON (False)
            enable_time_trigger: Enable time-based checkpoint triggers
            time_interval: Time interval for checkpoints (seconds)
            event_interval: Event count interval for checkpoints
        """
        self.checkpoint_dir = Path(checkpoint_dir)
        self.symbol = symbol
        self.max_checkpoints = max_checkpoints
        self.use_pickle = use_pickle

        # Create checkpoint directory if needed with secure permissions
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.checkpoint_dir, 0o700)

        # State snapshot manager
        self.state_snapshot = StateSnapshot(checkpoint_dir, symbol)

        # Checkpoint trigger
        trigger_config = CheckpointTriggerConfig(
            time_interval=time_interval,
            event_interval=event_interval,
            enable_time_trigger=enable_time_trigger,
            enable_event_trigger=True,
        )
        self.checkpoint_trigger = CheckpointTrigger(
            config=trigger_config,
            checkpoint_callback=self._async_checkpoint_callback,
        )

        # State provider callback
        self._state_provider: Callable | None = None

        # Format preference
        self.prefer_parquet = True  # Prefer Parquet over pickle/JSON

        # Performance monitoring
        self.checkpoint_monitor = CheckpointMonitor()

        # WAL manager for crash recovery
        self.wal_enabled = True
        self.wal_manager = WALManager(
            wal_dir=checkpoint_dir / "wal",
            symbol=symbol,
            segment_size=10000,  # 10k events per segment
            max_segments=10,
        )

        logger.info(
            f"CheckpointManager initialized for {symbol} at {checkpoint_dir} "
            f"(time_trigger={enable_time_trigger}, interval={time_interval}s, WAL=enabled)"
        )

    def save_checkpoint(
        self,
        state_data: dict[str, Any],
        update_id: int,
    ) -> Path:
        """
        Save checkpoint with atomic write pattern.

        Args:
            state_data: State data to checkpoint
            update_id: Current update ID for naming

        Returns:
            Path to saved checkpoint
        """
        if not state_data:
            raise ValueError("Cannot save empty state data")

        if update_id < 0:
            raise ValueError(f"Invalid update_id: {update_id}")

        # Use Parquet format if preferred
        if self.prefer_parquet:
            return self.save_checkpoint_parquet(state_data, update_id)

        try:
            # Generate checkpoint filename
            timestamp = int(time.time() * 1000)
            checkpoint_name = f"{self.symbol}_checkpoint_{update_id}_{timestamp}"

            if self.use_pickle:
                checkpoint_path = self.checkpoint_dir / f"{checkpoint_name}.pkl"
                temp_path = checkpoint_path.with_suffix(".tmp")

                # Write to temp file first
                with open(temp_path, "wb") as f:
                    pickle.dump(state_data, f, protocol=pickle.HIGHEST_PROTOCOL)
            else:
                checkpoint_path = self.checkpoint_dir / f"{checkpoint_name}.json"
                temp_path = checkpoint_path.with_suffix(".tmp")

                # Write to temp file first
                with open(temp_path, "w") as f:
                    json.dump(state_data, f, indent=2)

            # Set secure permissions
            os.chmod(temp_path, 0o600)

            # Atomic rename
            temp_path.rename(checkpoint_path)

            logger.debug(f"Saved checkpoint: {checkpoint_path}")

            # Clean up old checkpoints
            self._cleanup_old_checkpoints()

            return checkpoint_path

        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            raise

    def load_latest_checkpoint(self) -> dict[str, Any] | None:
        """
        Load the most recent checkpoint.

        Returns:
            State data from checkpoint or None if no checkpoints
        """
        # Try Parquet format first if preferred
        if self.prefer_parquet:
            parquet_data = self.load_latest_checkpoint_parquet()
            if parquet_data:
                return parquet_data

        try:
            checkpoints = self._get_checkpoint_files()
            if not checkpoints:
                logger.info("No checkpoints found")
                return None

            # Sort by timestamp (newest first)
            checkpoints.sort(key=lambda p: p.stat().st_mtime, reverse=True)

            latest = checkpoints[0]
            logger.info(f"Loading checkpoint: {latest}")

            if self.use_pickle:
                with open(latest, "rb") as f:
                    return pickle.load(f)
            else:
                with open(latest) as f:
                    return json.load(f)

        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return None

    def load_checkpoint_by_update_id(
        self,
        target_update_id: int,
    ) -> dict[str, Any] | None:
        """
        Load checkpoint closest to target update ID.

        Args:
            target_update_id: Target update ID

        Returns:
            State data from checkpoint or None
        """
        try:
            checkpoints = self._get_checkpoint_files()
            if not checkpoints:
                return None

            # Find checkpoint with closest update_id <= target
            best_checkpoint = None
            best_update_id = 0

            for checkpoint in checkpoints:
                # Extract update_id from filename
                parts = checkpoint.stem.split("_")
                if len(parts) >= 3:
                    update_id = int(parts[2])
                    if update_id <= target_update_id and update_id > best_update_id:
                        best_update_id = update_id
                        best_checkpoint = checkpoint

            if best_checkpoint:
                logger.info(
                    f"Loading checkpoint for update_id {best_update_id}: {best_checkpoint}"
                )

                if self.use_pickle:
                    with open(best_checkpoint, "rb") as f:
                        return pickle.load(f)
                else:
                    with open(best_checkpoint) as f:
                        return json.load(f)

            return None

        except Exception as e:
            logger.error(f"Failed to load checkpoint by update_id: {e}")
            return None

    def _get_checkpoint_files(self) -> list[Path]:
        """Get all checkpoint files for this symbol."""
        pattern = f"{self.symbol}_checkpoint_*"

        files = []

        # Include Parquet files if preferred
        if self.prefer_parquet:
            files.extend(list(self.checkpoint_dir.glob(f"{pattern}.parquet")))

        # Include legacy formats
        if self.use_pickle:
            files.extend(list(self.checkpoint_dir.glob(f"{pattern}.pkl")))
        else:
            files.extend(list(self.checkpoint_dir.glob(f"{pattern}.json")))

        return files

    def _cleanup_old_checkpoints(self) -> None:
        """Remove old checkpoints keeping only max_checkpoints."""
        try:
            checkpoints = self._get_checkpoint_files()

            if len(checkpoints) <= self.max_checkpoints:
                return

            # Sort by modification time (oldest first)
            checkpoints.sort(key=lambda p: p.stat().st_mtime)

            # Remove oldest checkpoints
            to_remove = len(checkpoints) - self.max_checkpoints
            for checkpoint in checkpoints[:to_remove]:
                checkpoint.unlink()
                logger.debug(f"Removed old checkpoint: {checkpoint}")

        except Exception as e:
            logger.error(f"Failed to cleanup checkpoints: {e}")

    def clear_all_checkpoints(self) -> None:
        """Remove all checkpoints for this symbol."""
        try:
            checkpoints = self._get_checkpoint_files()
            for checkpoint in checkpoints:
                checkpoint.unlink()

            logger.info(f"Cleared {len(checkpoints)} checkpoints")

        except Exception as e:
            logger.error(f"Failed to clear checkpoints: {e}")

    def set_state_provider(self, provider: Any) -> None:
        """Set the state provider for checkpoint data.

        Args:
            provider: Object with get_checkpoint_state() method
        """
        self._state_provider = provider

    async def start(self) -> None:
        """Start the checkpoint manager with time-based triggers."""
        await self.checkpoint_trigger.start()
        logger.info("CheckpointManager started with triggers active")

    async def stop(self) -> None:
        """Stop the checkpoint manager and perform final checkpoint."""
        await self.checkpoint_trigger.stop()

        # Flush WAL
        if self.wal_enabled:
            self.wal_manager.flush()

        # Log performance summary
        self.checkpoint_monitor.log_summary()

        logger.info("CheckpointManager stopped")

    async def record_events(self, event_count: int) -> None:
        """Record processed events for trigger checking.

        Args:
            event_count: Number of events processed
        """
        # Record for performance monitoring
        self.checkpoint_monitor.record_events(event_count)

        # Record for trigger checking
        await self.checkpoint_trigger.record_events(event_count)

    async def _async_checkpoint_callback(self) -> asyncio.Task:
        """Async callback for checkpoint triggers."""
        if not self._state_provider:
            logger.warning("No state provider set, skipping checkpoint")
            return None

        # Create async task for checkpoint
        return asyncio.create_task(self._perform_async_checkpoint())

    async def _perform_async_checkpoint(self) -> None:
        """Perform async checkpoint with COW snapshot."""
        try:
            # Mark checkpoint start for monitoring
            self.checkpoint_monitor.checkpoint_started()

            # Create COW snapshot
            state = await self.state_snapshot.create_snapshot(self._state_provider)

            # Persist snapshot asynchronously
            checkpoint_path = await self._save_parquet_checkpoint(state)

            # Clean up old checkpoints
            self._cleanup_old_checkpoints()

            # Mark checkpoint completion
            self.checkpoint_monitor.checkpoint_completed()

            logger.info(
                f"Async checkpoint completed: {checkpoint_path.name} "
                f"(events: {state.events_processed}, duration: {state.snapshot_duration_ms:.1f}ms)"
            )

        except Exception as e:
            logger.error(f"Failed to perform async checkpoint: {e}")
            self.checkpoint_monitor.checkpoint_completed()  # Mark as completed even on error

    async def _save_parquet_checkpoint(self, state: PipelineState) -> Path:
        """Save checkpoint in Parquet format.

        Args:
            state: Pipeline state to checkpoint

        Returns:
            Path to saved checkpoint file
        """
        try:
            # Use state snapshot manager for Parquet persistence
            checkpoint_path = await self.state_snapshot.persist_snapshot(state)

            return checkpoint_path

        except Exception as e:
            logger.error(f"Failed to save Parquet checkpoint: {e}")
            raise

    def save_checkpoint_parquet(
        self,
        state_data: dict[str, Any],
        update_id: int,
    ) -> Path:
        """Save checkpoint in Parquet format (synchronous version).

        Args:
            state_data: State data to checkpoint
            update_id: Current update ID for naming

        Returns:
            Path to saved checkpoint
        """
        if not state_data:
            raise ValueError("Cannot save empty state data")

        if update_id < 0:
            raise ValueError(f"Invalid update_id: {update_id}")

        try:
            # Convert to PipelineState
            state = PipelineState(
                symbol=self.symbol,
                checkpoint_timestamp=int(time.time() * 1000),
                order_book_state=state_data.get("book_state", {}),
                last_update_id=update_id,
                events_processed=state_data.get("updates_processed", 0),
                gap_statistics=state_data.get("gap_stats", {}),
                drift_metrics=state_data.get("drift_metrics", {}),
            )

            # Generate checkpoint filename
            checkpoint_name = f"{self.symbol}_checkpoint_{update_id}_{state.checkpoint_timestamp}.parquet"
            checkpoint_path = self.checkpoint_dir / checkpoint_name
            temp_path = checkpoint_path.with_suffix(".tmp")

            # Convert to DataFrame and save
            df = pd.DataFrame([state.to_parquet_dict()])
            table = pa.Table.from_pandas(df)

            pq.write_table(
                table,
                temp_path,
                compression="snappy",
                metadata={
                    "symbol": self.symbol,
                    "checkpoint_version": "1.0",
                    "update_id": str(update_id),
                },
            )

            # Set secure permissions and rename
            os.chmod(temp_path, 0o600)
            temp_path.rename(checkpoint_path)

            logger.debug(f"Saved Parquet checkpoint: {checkpoint_path}")

            # Clean up old checkpoints
            self._cleanup_old_checkpoints()

            return checkpoint_path

        except Exception as e:
            logger.error(f"Failed to save Parquet checkpoint: {e}")
            raise

    def load_latest_checkpoint_parquet(self) -> dict[str, Any] | None:
        """Load the most recent Parquet checkpoint.

        Returns:
            State data from checkpoint or None if no checkpoints
        """
        try:
            # Get all Parquet checkpoints
            parquet_files = list(
                self.checkpoint_dir.glob(f"{self.symbol}_checkpoint_*.parquet")
            )
            if not parquet_files:
                logger.info("No Parquet checkpoints found")
                return None

            # Sort by modification time (newest first)
            parquet_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            latest = parquet_files[0]

            logger.info(f"Loading Parquet checkpoint: {latest}")

            # Load using state snapshot
            state = asyncio.run(self.state_snapshot.load_snapshot(latest))
            if not state:
                return None

            # Convert back to legacy format for compatibility
            return {
                "book_state": state.order_book_state,
                "last_update_id": state.last_update_id,
                "gap_stats": state.gap_statistics,
                "updates_processed": state.events_processed,
                "snapshot_count": 0,
                "drift_metrics": state.drift_metrics,
                "current_file": state.current_file,
                "file_offset": state.file_offset,
            }

        except Exception as e:
            logger.error(f"Failed to load Parquet checkpoint: {e}")
            return None

    def log_event_to_wal(self, event_data: dict[str, Any]) -> None:
        """Log an event to the WAL for crash recovery.

        Args:
            event_data: Event data to log
        """
        if self.wal_enabled and self.wal_manager:
            try:
                self.wal_manager.append_event(event_data)
            except Exception as e:
                logger.error(f"Failed to log event to WAL: {e}")

    async def recover_from_wal(self) -> int:
        """Recover events from WAL after checkpoint.

        Returns:
            Number of events recovered from WAL
        """
        if not self.wal_enabled or not self.wal_manager:
            return 0

        try:
            # Get WAL segments
            segments = self.wal_manager.recover_segments()
            if not segments:
                logger.info("No WAL segments to recover")
                return 0

            # Get last checkpoint update_id
            checkpoint_state = self.load_latest_checkpoint()
            last_checkpoint_update_id = (
                checkpoint_state.get("last_update_id", 0) if checkpoint_state else 0
            )

            # Process segments after checkpoint
            total_recovered = 0
            for segment in segments:
                if (
                    segment.last_update_id
                    and segment.last_update_id > last_checkpoint_update_id
                ):
                    # Read events from segment
                    events_df = self.wal_manager.read_segment_events(segment)

                    # Filter events after checkpoint
                    if not events_df.empty and "update_id" in events_df.columns:
                        new_events = events_df[
                            events_df["update_id"] > last_checkpoint_update_id
                        ]
                        total_recovered += len(new_events)

                        logger.info(
                            f"Recovered {len(new_events)} events from WAL segment {segment.segment_id}"
                        )

            return total_recovered

        except Exception as e:
            logger.error(f"Failed to recover from WAL: {e}")
            return 0
