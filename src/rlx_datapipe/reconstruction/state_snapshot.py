"""Copy-on-Write state snapshot mechanism for non-blocking checkpoints."""

import asyncio
import os
import time
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from loguru import logger


@dataclass
class PipelineState:
    """Complete pipeline state for checkpointing."""

    # Order book state
    order_book_state: dict[str, Any] = field(default_factory=dict)
    last_update_id: int | None = None

    # Pipeline progress
    current_file: str | None = None
    file_offset: int = 0
    events_processed: int = 0

    # Performance metrics
    gap_statistics: dict[str, Any] = field(default_factory=dict)
    drift_metrics: dict[str, float] = field(default_factory=dict)
    processing_rate: float = 0.0

    # Metadata
    symbol: str = ""
    checkpoint_timestamp: int = 0
    snapshot_duration_ms: float = 0.0

    def to_parquet_dict(self) -> dict[str, Any]:
        """Convert state to dictionary suitable for Parquet storage."""
        return {
            "symbol": self.symbol,
            "checkpoint_timestamp": self.checkpoint_timestamp,
            "last_update_id": self.last_update_id or 0,
            "current_file": self.current_file or "",
            "file_offset": self.file_offset,
            "events_processed": self.events_processed,
            "processing_rate": self.processing_rate,
            "snapshot_duration_ms": self.snapshot_duration_ms,
            # Serialize complex nested structures as JSON strings
            "order_book_state": str(self.order_book_state),
            "gap_statistics": str(self.gap_statistics),
            "drift_metrics": str(self.drift_metrics),
        }

    @classmethod
    def from_parquet_dict(cls, data: dict[str, Any]) -> "PipelineState":
        """Reconstruct state from Parquet dictionary."""
        import json

        state = cls(
            symbol=data["symbol"],
            checkpoint_timestamp=data["checkpoint_timestamp"],
            last_update_id=data["last_update_id"],
            current_file=data["current_file"] if data["current_file"] else None,
            file_offset=data["file_offset"],
            events_processed=data["events_processed"],
            processing_rate=data["processing_rate"],
            snapshot_duration_ms=data["snapshot_duration_ms"],
        )

        # Deserialize complex structures
        if data.get("order_book_state"):
            state.order_book_state = json.loads(data["order_book_state"])
        if data.get("gap_statistics"):
            state.gap_statistics = json.loads(data["gap_statistics"])
        if data.get("drift_metrics"):
            state.drift_metrics = json.loads(data["drift_metrics"])

        return state


class StateSnapshot:
    """Copy-on-Write state snapshot manager for non-blocking persistence."""

    def __init__(self, checkpoint_dir: Path, symbol: str):
        """Initialize state snapshot manager.

        Args:
            checkpoint_dir: Directory for checkpoint storage
            symbol: Trading symbol for this snapshot manager
        """
        self.checkpoint_dir = Path(checkpoint_dir)
        self.symbol = symbol

        # Ensure checkpoint directory exists with secure permissions
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        # Set directory permissions to 0700 (owner read/write/execute only)
        os.chmod(self.checkpoint_dir, 0o700)

        # Snapshot state
        self._current_state: PipelineState | None = None
        self._snapshot_lock = asyncio.Lock()
        self._snapshot_in_progress = False

        logger.info(f"StateSnapshot initialized for {symbol} at {checkpoint_dir}")

    async def create_snapshot(self, state_provider: Any) -> PipelineState:
        """Create a copy-on-write snapshot of current state.
        
        This method creates a snapshot without blocking the main pipeline.
        The snapshot is created in <100ms using shallow copy techniques.
        
        Args:
            state_provider: Object providing get_checkpoint_state() method
            
        Returns:
            Snapshot of current pipeline state
        """
        start_time = time.time()

        async with self._snapshot_lock:
            try:
                # Get current state from provider (should be quick)
                raw_state = state_provider.get_checkpoint_state()

                # Create COW snapshot using deepcopy for nested structures
                # This is fast for reasonably sized state (<100MB)
                self._current_state = PipelineState(
                    symbol=self.symbol,
                    checkpoint_timestamp=int(time.time() * 1000),
                    order_book_state=deepcopy(raw_state.get("order_book_state", {})),
                    last_update_id=raw_state.get("last_update_id"),
                    current_file=raw_state.get("current_file"),
                    file_offset=raw_state.get("file_offset", 0),
                    events_processed=raw_state.get("events_processed", 0),
                    gap_statistics=deepcopy(raw_state.get("gap_statistics", {})),
                    drift_metrics=deepcopy(raw_state.get("drift_metrics", {})),
                    processing_rate=raw_state.get("processing_rate", 0.0),
                )

                # Record snapshot duration
                snapshot_duration = (time.time() - start_time) * 1000
                self._current_state.snapshot_duration_ms = snapshot_duration

                if snapshot_duration > 100:
                    logger.warning(
                        f"Snapshot creation took {snapshot_duration:.1f}ms "
                        f"(target: <100ms)"
                    )
                else:
                    logger.debug(f"Snapshot created in {snapshot_duration:.1f}ms")

                # Log snapshot size estimate
                state_size_kb = self._estimate_state_size(self._current_state) / 1024
                logger.debug(f"Snapshot size estimate: {state_size_kb:.1f}KB")

                return self._current_state

            except Exception as e:
                logger.error(f"Failed to create snapshot: {e}")
                raise

    async def persist_snapshot(self, state: PipelineState) -> Path:
        """Persist snapshot to disk using Parquet format.
        
        This method runs asynchronously without blocking the pipeline.
        Uses atomic write pattern for crash safety.
        
        Args:
            state: Pipeline state to persist
            
        Returns:
            Path to persisted checkpoint file
        """
        try:
            # Generate checkpoint filename
            checkpoint_name = (
                f"{self.symbol}_checkpoint_{state.last_update_id}_"
                f"{state.checkpoint_timestamp}.parquet"
            )
            checkpoint_path = self.checkpoint_dir / checkpoint_name
            temp_path = checkpoint_path.with_suffix(".tmp")

            # Convert state to Parquet-compatible format
            state_dict = state.to_parquet_dict()
            df = pd.DataFrame([state_dict])

            # Write to temporary file first
            table = pa.Table.from_pandas(df)
            pq.write_table(
                table,
                temp_path,
                compression="snappy",  # Fast compression
                use_dictionary=True,
                # Write metadata for integrity checking
                metadata={
                    "symbol": self.symbol,
                    "checkpoint_version": "1.0",
                    "update_id": str(state.last_update_id),
                }
            )

            # Set secure file permissions before rename
            os.chmod(temp_path, 0o600)  # Owner read/write only

            # Atomic rename
            temp_path.rename(checkpoint_path)

            logger.info(
                f"Persisted checkpoint: {checkpoint_path.name} "
                f"(size: {checkpoint_path.stat().st_size / 1024:.1f}KB)"
            )

            return checkpoint_path

        except Exception as e:
            logger.error(f"Failed to persist snapshot: {e}")
            raise

    async def load_snapshot(self, checkpoint_path: Path) -> PipelineState | None:
        """Load snapshot from checkpoint file.
        
        Args:
            checkpoint_path: Path to checkpoint file
            
        Returns:
            Loaded pipeline state or None if load fails
        """
        try:
            if not checkpoint_path.exists():
                logger.warning(f"Checkpoint file not found: {checkpoint_path}")
                return None

            # Verify file permissions
            stat_info = checkpoint_path.stat()
            if oct(stat_info.st_mode)[-3:] != "600":
                logger.warning(
                    f"Checkpoint has incorrect permissions: "
                    f"{oct(stat_info.st_mode)[-3:]}, expected 600"
                )

            # Read Parquet file
            table = pq.read_table(checkpoint_path)
            df = table.to_pandas()

            if df.empty:
                logger.warning("Empty checkpoint file")
                return None

            # Verify metadata
            metadata = table.schema.metadata
            if metadata:
                stored_symbol = metadata.get(b"symbol", b"").decode()
                if stored_symbol != self.symbol:
                    logger.error(
                        f"Symbol mismatch in checkpoint: "
                        f"expected {self.symbol}, got {stored_symbol}"
                    )
                    return None

            # Reconstruct state
            state_dict = df.iloc[0].to_dict()
            state = PipelineState.from_parquet_dict(state_dict)

            logger.info(
                f"Loaded checkpoint: update_id={state.last_update_id}, "
                f"events_processed={state.events_processed}"
            )

            return state

        except Exception as e:
            logger.error(f"Failed to load snapshot: {e}")
            return None

    def get_latest_snapshot(self) -> PipelineState | None:
        """Get the most recent in-memory snapshot."""
        return self._current_state

    def _estimate_state_size(self, state: PipelineState) -> int:
        """Estimate the size of the state object in bytes.
        
        Args:
            state: Pipeline state to estimate
            
        Returns:
            Estimated size in bytes
        """
        import sys

        # Rough estimation based on object sizes
        size = sys.getsizeof(state)

        # Add sizes of nested structures
        if state.order_book_state:
            size += sys.getsizeof(state.order_book_state)
            # Estimate book data size (bids + asks)
            if isinstance(state.order_book_state, dict):
                for key, value in state.order_book_state.items():
                    size += sys.getsizeof(key) + sys.getsizeof(value)

        if state.gap_statistics:
            size += sys.getsizeof(state.gap_statistics)

        if state.drift_metrics:
            size += sys.getsizeof(state.drift_metrics)

        return size

