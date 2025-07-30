"""Write-Ahead Log (WAL) manager for crash-resistant event persistence."""

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from loguru import logger


@dataclass
class WALSegment:
    """Represents a WAL segment file."""

    segment_id: int
    file_path: Path
    events_count: int = 0
    is_complete: bool = False
    start_time: float = 0.0
    end_time: float = 0.0
    first_update_id: int | None = None
    last_update_id: int | None = None


class WALManager:
    """Manages Write-Ahead Log for crash recovery."""

    def __init__(
        self,
        wal_dir: Path,
        symbol: str,
        segment_size: int = 10000,  # Events per segment
        max_segments: int = 10,  # Keep last N segments
    ):
        """Initialize WAL manager.

        Args:
            wal_dir: Directory for WAL segments
            symbol: Trading symbol
            segment_size: Maximum events per segment
            max_segments: Maximum number of segments to retain
        """
        self.wal_dir = Path(wal_dir)
        self.symbol = symbol
        self.segment_size = segment_size
        self.max_segments = max_segments

        # Create WAL directory with secure permissions
        self.wal_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.wal_dir, 0o700)

        # Current segment
        self.current_segment: WALSegment | None = None
        self.segment_buffer: list[dict[str, Any]] = []
        self.next_segment_id = self._find_next_segment_id()

        logger.info(
            f"WALManager initialized for {symbol} at {wal_dir} "
            f"(segment_size={segment_size})"
        )

    def _find_next_segment_id(self) -> int:
        """Find the next segment ID to use."""
        # List existing WAL segments
        segments = list(self.wal_dir.glob(f"{self.symbol}_wal_*.parquet"))

        if not segments:
            return 1

        # Extract segment IDs and find max
        max_id = 0
        for segment_path in segments:
            try:
                # Format: symbol_wal_SEGMENTID_timestamp.parquet
                parts = segment_path.stem.split("_")
                if len(parts) >= 3:
                    segment_id = int(parts[2])
                    max_id = max(max_id, segment_id)
            except (ValueError, IndexError):
                continue

        return max_id + 1

    def append_event(self, event_data: dict[str, Any]) -> None:
        """Append an event to the WAL.

        Args:
            event_data: Event data to append
        """
        # Add WAL metadata
        wal_event = {
            **event_data,
            "wal_timestamp": int(time.time() * 1000),
            "wal_segment_id": self.next_segment_id,
        }

        # Add to buffer
        self.segment_buffer.append(wal_event)

        # Track update IDs if present
        update_id = event_data.get("update_id")
        if update_id is not None:
            if self.current_segment is None:
                self._start_new_segment(update_id)

            self.current_segment.last_update_id = update_id
            self.current_segment.events_count += 1

        # Check if segment is full
        if len(self.segment_buffer) >= self.segment_size:
            self._flush_segment()

    def _start_new_segment(self, first_update_id: int) -> None:
        """Start a new WAL segment."""
        timestamp = int(time.time() * 1000)
        segment_name = f"{self.symbol}_wal_{self.next_segment_id}_{timestamp}.parquet"
        segment_path = self.wal_dir / segment_name

        self.current_segment = WALSegment(
            segment_id=self.next_segment_id,
            file_path=segment_path,
            start_time=time.time(),
            first_update_id=first_update_id,
        )

        logger.debug(f"Started new WAL segment: {segment_name}")

    def _flush_segment(self) -> None:
        """Flush current segment to disk."""
        if not self.segment_buffer or not self.current_segment:
            return

        try:
            # Convert buffer to DataFrame
            df = pd.DataFrame(self.segment_buffer)

            # Write to temporary file first
            temp_path = self.current_segment.file_path.with_suffix(".tmp")

            # Convert to Parquet with metadata
            table = pa.Table.from_pandas(df)

            # Add segment metadata
            metadata = {
                "segment_id": str(self.current_segment.segment_id),
                "symbol": self.symbol,
                "first_update_id": str(self.current_segment.first_update_id or 0),
                "last_update_id": str(self.current_segment.last_update_id or 0),
                "events_count": str(self.current_segment.events_count),
                "complete": "false",  # Will be marked true after rename
            }

            # Write with metadata
            pq.write_table(
                table,
                temp_path,
                compression="snappy",
                metadata=metadata,
            )

            # Set secure permissions
            os.chmod(temp_path, 0o600)

            # Atomic rename to mark as complete
            temp_path.rename(self.current_segment.file_path)

            # Create DONE marker
            self._create_done_marker(self.current_segment)

            logger.info(
                f"Flushed WAL segment {self.current_segment.segment_id} "
                f"with {len(self.segment_buffer)} events"
            )

            # Update segment state
            self.current_segment.is_complete = True
            self.current_segment.end_time = time.time()

            # Clear buffer and prepare for next segment
            self.segment_buffer.clear()
            self.next_segment_id += 1
            self.current_segment = None

            # Clean up old segments
            self._cleanup_old_segments()

        except Exception as e:
            logger.error(f"Failed to flush WAL segment: {e}")
            raise

    def _create_done_marker(self, segment: WALSegment) -> None:
        """Create atomic DONE marker for segment.

        Args:
            segment: WAL segment that was completed
        """
        done_path = segment.file_path.with_suffix(".done")

        # Write segment completion info
        done_info = {
            "segment_id": segment.segment_id,
            "completed_at": int(time.time() * 1000),
            "events_count": segment.events_count,
            "first_update_id": segment.first_update_id,
            "last_update_id": segment.last_update_id,
        }

        # Write atomically
        temp_done = done_path.with_suffix(".tmp")
        pd.DataFrame([done_info]).to_json(temp_done, orient="records", lines=True)
        os.chmod(temp_done, 0o600)
        temp_done.rename(done_path)

        logger.debug(f"Created DONE marker for segment {segment.segment_id}")

    def flush(self) -> None:
        """Flush any pending events."""
        if self.segment_buffer:
            self._flush_segment()

    def _cleanup_old_segments(self) -> None:
        """Remove old WAL segments keeping only max_segments."""
        # Find all complete segments
        segments = []
        for parquet_file in self.wal_dir.glob(f"{self.symbol}_wal_*.parquet"):
            done_file = parquet_file.with_suffix(".done")
            if done_file.exists():
                segments.append((parquet_file, done_file))

        # Sort by modification time
        segments.sort(key=lambda x: x[0].stat().st_mtime)

        # Remove oldest segments if over limit
        while len(segments) > self.max_segments:
            parquet_file, done_file = segments.pop(0)

            parquet_file.unlink()
            done_file.unlink()

            logger.debug(f"Removed old WAL segment: {parquet_file.name}")

    def recover_segments(self) -> list[WALSegment]:
        """Recover all valid WAL segments.

        Returns:
            List of valid WAL segments in order
        """
        recovered_segments = []

        # Find all WAL segments with DONE markers
        for parquet_file in sorted(self.wal_dir.glob(f"{self.symbol}_wal_*.parquet")):
            done_file = parquet_file.with_suffix(".done")

            if not done_file.exists():
                logger.warning(
                    f"WAL segment {parquet_file.name} incomplete (no DONE marker)"
                )
                continue

            try:
                # Read segment metadata
                table = pq.read_table(parquet_file)
                metadata = table.schema.metadata

                if metadata:
                    segment = WALSegment(
                        segment_id=int(metadata.get(b"segment_id", b"0")),
                        file_path=parquet_file,
                        events_count=int(metadata.get(b"events_count", b"0")),
                        is_complete=True,
                        first_update_id=int(metadata.get(b"first_update_id", b"0")),
                        last_update_id=int(metadata.get(b"last_update_id", b"0")),
                    )

                    recovered_segments.append(segment)

            except Exception as e:
                logger.error(f"Failed to recover WAL segment {parquet_file.name}: {e}")
                continue

        # Sort by segment ID
        recovered_segments.sort(key=lambda s: s.segment_id)

        logger.info(f"Recovered {len(recovered_segments)} WAL segments")

        return recovered_segments

    def read_segment_events(self, segment: WALSegment) -> pd.DataFrame:
        """Read events from a WAL segment.

        Args:
            segment: WAL segment to read

        Returns:
            DataFrame of events
        """
        try:
            return pd.read_parquet(segment.file_path)
        except Exception as e:
            logger.error(f"Failed to read WAL segment {segment.file_path}: {e}")
            return pd.DataFrame()

    def get_stats(self) -> dict[str, Any]:
        """Get WAL statistics.

        Returns:
            Dictionary of WAL statistics
        """
        segments = self.recover_segments()

        total_events = sum(s.events_count for s in segments)

        return {
            "total_segments": len(segments),
            "total_events": total_events,
            "current_buffer_size": len(self.segment_buffer),
            "next_segment_id": self.next_segment_id,
            "oldest_segment_id": segments[0].segment_id if segments else None,
            "newest_segment_id": segments[-1].segment_id if segments else None,
        }
