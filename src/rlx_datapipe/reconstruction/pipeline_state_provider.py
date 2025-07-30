"""Pipeline state provider for unified checkpoint management."""

import time
from typing import Any

from loguru import logger


class PipelineStateProvider:
    """Aggregates state from all pipeline components for checkpointing."""

    def __init__(self, symbol: str):
        """Initialize pipeline state provider.

        Args:
            symbol: Trading symbol for this pipeline
        """
        self.symbol = symbol

        # Component references
        self.order_book_engine = None
        self.file_reader = None
        self.data_sink = None

        # Pipeline progress tracking
        self.current_file: str | None = None
        self.file_offset: int = 0
        self.events_processed: int = 0
        self.pipeline_start_time = time.time()

        logger.info(f"PipelineStateProvider initialized for {symbol}")

    def set_order_book_engine(self, engine: Any) -> None:
        """Set reference to order book engine."""
        self.order_book_engine = engine

    def set_file_reader(self, reader: Any) -> None:
        """Set reference to file reader."""
        self.file_reader = reader

    def set_data_sink(self, sink: Any) -> None:
        """Set reference to data sink."""
        self.data_sink = sink

    def update_file_progress(self, filename: str, offset: int) -> None:
        """Update current file and offset.

        Args:
            filename: Current file being processed
            offset: Current offset in file
        """
        self.current_file = filename
        self.file_offset = offset

    def increment_events_processed(self, count: int = 1) -> None:
        """Increment events processed counter.

        Args:
            count: Number of events to add
        """
        self.events_processed += count

    def get_checkpoint_state(self) -> dict[str, Any]:
        """Get complete pipeline state for checkpointing.

        This method aggregates state from all components into a unified
        checkpoint state. Designed to be fast for COW snapshot creation.

        Returns:
            Dictionary containing full pipeline state
        """
        state = {
            "symbol": self.symbol,
            "events_processed": self.events_processed,
            "current_file": self.current_file,
            "file_offset": self.file_offset,
            "processing_rate": self._calculate_processing_rate(),
        }

        # Get order book state if available
        if self.order_book_engine:
            engine_state = self.order_book_engine.get_checkpoint_state()
            state.update(
                {
                    "order_book_state": engine_state.get("book_state", {}),
                    "last_update_id": engine_state.get("last_update_id"),
                    "gap_statistics": engine_state.get("gap_stats", {}),
                    "drift_metrics": engine_state.get("drift_metrics", {}),
                    "updates_processed": engine_state.get("updates_processed", 0),
                }
            )

        # Get file reader state if available
        if self.file_reader and hasattr(self.file_reader, "get_position"):
            reader_state = self.file_reader.get_position()
            if reader_state:
                state["current_file"] = reader_state.get("file", self.current_file)
                state["file_offset"] = reader_state.get("offset", self.file_offset)

        # Get data sink metrics if available
        if self.data_sink and hasattr(self.data_sink, "get_stats"):
            sink_stats = self.data_sink.get_stats()
            state["output_stats"] = {
                "events_written": sink_stats.get("total_events_written", 0),
                "partitions_written": sink_stats.get("total_partitions_written", 0),
            }

        return state

    def restore_from_checkpoint(self, state: dict[str, Any]) -> None:
        """Restore pipeline state from checkpoint.

        Args:
            state: Checkpoint state to restore
        """
        # Restore local state
        self.symbol = state.get("symbol", self.symbol)
        self.events_processed = state.get("events_processed", 0)
        self.current_file = state.get("current_file")
        self.file_offset = state.get("file_offset", 0)

        # Components will restore their own state separately
        logger.info(
            f"Restored pipeline state: file={self.current_file}, "
            f"offset={self.file_offset}, events={self.events_processed}"
        )

    def _calculate_processing_rate(self) -> float:
        """Calculate current processing rate."""
        elapsed = max(1, time.time() - self.pipeline_start_time)
        return self.events_processed / elapsed
