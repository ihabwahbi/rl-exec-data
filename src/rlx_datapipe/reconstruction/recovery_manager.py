"""Recovery manager for restoring pipeline state from checkpoints."""

from pathlib import Path
from typing import Any

from loguru import logger

from .checkpoint_manager import CheckpointManager


class RecoveryManager:
    """Manages pipeline recovery from checkpoints."""

    def __init__(
        self,
        checkpoint_dir: Path,
        symbol: str,
    ):
        """Initialize recovery manager.
        
        Args:
            checkpoint_dir: Directory containing checkpoints
            symbol: Trading symbol for recovery
        """
        self.checkpoint_dir = Path(checkpoint_dir)
        self.symbol = symbol

        # Checkpoint manager for loading
        self.checkpoint_manager = CheckpointManager(
            checkpoint_dir=checkpoint_dir,
            symbol=symbol,
            enable_time_trigger=False,  # No triggers needed for recovery
        )

        # Recovery state
        self.recovered_state: dict[str, Any] | None = None
        self.recovery_successful = False

        logger.info(f"RecoveryManager initialized for {symbol}")

    async def attempt_recovery(self) -> bool:
        """Attempt to recover from latest checkpoint.
        
        Returns:
            True if recovery successful, False otherwise
        """
        try:
            logger.info(f"Attempting recovery for {self.symbol}...")

            # Find and load latest checkpoint
            self.recovered_state = await self._find_latest_valid_checkpoint()

            if not self.recovered_state:
                logger.info("No valid checkpoint found for recovery")
                return False

            # Validate checkpoint integrity
            if not self._validate_checkpoint(self.recovered_state):
                logger.error("Checkpoint validation failed")
                return False

            self.recovery_successful = True

            logger.info(
                f"Recovery successful from checkpoint: "
                f"update_id={self.recovered_state.get('last_update_id')}, "
                f"events={self.recovered_state.get('events_processed')}"
            )

            return True

        except Exception as e:
            logger.error(f"Recovery failed: {e}")
            return False

    async def _find_latest_valid_checkpoint(self) -> dict[str, Any] | None:
        """Find and load the latest valid checkpoint.
        
        Returns:
            Checkpoint state or None if no valid checkpoint found
        """
        try:
            # Try to load latest Parquet checkpoint first
            state = self.checkpoint_manager.load_latest_checkpoint_parquet()

            if not state:
                # Fall back to legacy formats
                state = self.checkpoint_manager.load_latest_checkpoint()

            return state

        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return None

    def _validate_checkpoint(self, state: dict[str, Any]) -> bool:
        """Validate checkpoint integrity.
        
        Args:
            state: Checkpoint state to validate
            
        Returns:
            True if checkpoint is valid
        """
        # Check required fields
        required_fields = [
            "last_update_id",
            "events_processed",
            "order_book_state",
        ]

        for field in required_fields:
            if field not in state:
                logger.error(f"Checkpoint missing required field: {field}")
                return False

        # Validate update_id
        if state["last_update_id"] is None or state["last_update_id"] < 0:
            logger.error(f"Invalid update_id: {state['last_update_id']}")
            return False

        # Validate event count
        if state["events_processed"] < 0:
            logger.error(f"Invalid events_processed: {state['events_processed']}")
            return False

        logger.debug("Checkpoint validation passed")
        return True

    def get_recovery_state(self) -> dict[str, Any] | None:
        """Get recovered state.
        
        Returns:
            Recovered checkpoint state or None
        """
        return self.recovered_state

    def get_resume_position(self) -> tuple[str | None, int]:
        """Get file and offset to resume from.
        
        Returns:
            Tuple of (filename, offset) or (None, 0)
        """
        if not self.recovered_state:
            return None, 0

        filename = self.recovered_state.get("current_file")
        offset = self.recovered_state.get("file_offset", 0)

        return filename, offset

    def get_last_update_id(self) -> int | None:
        """Get last processed update ID.
        
        Returns:
            Last update ID or None
        """
        if not self.recovered_state:
            return None

        return self.recovered_state.get("last_update_id")

    async def validate_continuity(
        self,
        first_update_id: int,
        first_event_time: int,
    ) -> bool:
        """Validate data continuity after recovery.
        
        Args:
            first_update_id: First update ID after recovery
            first_event_time: First event timestamp after recovery
            
        Returns:
            True if continuity is valid
        """
        if not self.recovered_state:
            return True  # No checkpoint, so no continuity to check

        last_update_id = self.recovered_state.get("last_update_id", 0)

        # Check for gaps in update_id sequence
        if first_update_id > last_update_id + 1:
            gap_size = first_update_id - last_update_id - 1
            logger.warning(
                f"Gap detected after recovery: {gap_size} updates missing "
                f"(last: {last_update_id}, first: {first_update_id})"
            )

            # Allow small gaps (could be from normal market gaps)
            if gap_size > 1000:
                logger.error("Gap too large, recovery may be incomplete")
                return False

        # Check for duplicate processing
        if first_update_id <= last_update_id:
            logger.warning(
                f"Potential duplicate processing detected: "
                f"first_update_id ({first_update_id}) <= "
                f"last_checkpoint_update_id ({last_update_id})"
            )

        logger.info("Data continuity validation passed")
        return True

    def log_recovery_summary(self) -> None:
        """Log a summary of the recovery process."""
        if not self.recovered_state:
            logger.info("No recovery performed (no checkpoint found)")
            return

        logger.info(
            f"Recovery Summary:\n"
            f"  Symbol: {self.symbol}\n"
            f"  Last Update ID: {self.recovered_state.get('last_update_id')}\n"
            f"  Events Processed: {self.recovered_state.get('events_processed')}\n"
            f"  Resume File: {self.recovered_state.get('current_file', 'N/A')}\n"
            f"  Resume Offset: {self.recovered_state.get('file_offset', 0)}\n"
            f"  Snapshot Count: {self.recovered_state.get('snapshot_count', 0)}"
        )

