"""Enhanced unified event stream with order book reconstruction."""

import gc
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Generator, Optional, Tuple

import numpy as np
import polars as pl
from loguru import logger

from rlx_datapipe.common.decimal_utils import float_to_scaled_int64
from rlx_datapipe.reconstruction.delta_feed_processor import DeltaFeedProcessor
from rlx_datapipe.reconstruction.memory_mapped_processor import MemoryMappedProcessor
from rlx_datapipe.reconstruction.order_book_engine import OrderBookEngine
from rlx_datapipe.reconstruction.unification import UnifiedEventStream, UnificationConfig


@dataclass
class EnhancedUnificationConfig(UnificationConfig):
    """Enhanced configuration with order book settings."""
    
    enable_order_book: bool = True
    max_book_levels: int = 20
    checkpoint_dir: Optional[Path] = None
    gc_interval: int = 100_000
    enable_drift_tracking: bool = True
    pending_queue_size: int = 1000
    
    # Memory-mapped processing
    use_memory_mapping: bool = True
    mmap_chunk_size: int = 100_000


@dataclass 
class DriftMetrics:
    """Drift tracking between snapshots and reconstructed state."""
    
    total_snapshots: int = 0
    snapshots_with_drift: int = 0
    max_price_drift: float = 0.0
    max_quantity_drift: float = 0.0
    cumulative_drift: float = 0.0
    drift_history: list = field(default_factory=list)


class UnifiedEventStreamEnhanced(UnifiedEventStream):
    """Enhanced unified stream with order book reconstruction."""
    
    def __init__(
        self,
        symbol: str,
        config: Optional[EnhancedUnificationConfig] = None,
    ):
        """
        Initialize enhanced unified stream.
        
        Args:
            symbol: Trading symbol
            config: Enhanced configuration
        """
        self.symbol = symbol
        self.config = config or EnhancedUnificationConfig()
        super().__init__(self.config)
        
        # Order book components
        self.order_book_engine = None
        self.delta_processor = None
        self.mmap_processor = None
        
        if self.config.enable_order_book:
            self._initialize_order_book_components()
        
        # Drift tracking
        self.drift_metrics = DriftMetrics()
        
        # Pending queue for atomic updates
        self.pending_queue = deque(maxlen=self.config.pending_queue_size)
        
        logger.info(
            f"UnifiedEventStreamEnhanced initialized for {symbol} "
            f"with order_book={'enabled' if self.config.enable_order_book else 'disabled'}"
        )
    
    def _initialize_order_book_components(self) -> None:
        """Initialize order book related components."""
        self.order_book_engine = OrderBookEngine(
            symbol=self.symbol,
            max_levels=self.config.max_book_levels,
            checkpoint_dir=self.config.checkpoint_dir,
            gc_interval=self.config.gc_interval,
            enable_drift_tracking=self.config.enable_drift_tracking,
        )
        
        self.delta_processor = DeltaFeedProcessor(
            gap_threshold=1000,
            store_gap_history=True,
        )
        
        if self.config.use_memory_mapping:
            self.mmap_processor = MemoryMappedProcessor(
                chunk_size=self.config.mmap_chunk_size,
                max_memory_mb=int(self.config.memory_limit_gb * 1024),
            )
    
    def process_with_order_book(
        self,
        trades_path: Optional[Path] = None,
        book_snapshots_path: Optional[Path] = None,
        book_deltas_path: Optional[Path] = None,
        output_path: Optional[Path] = None,
    ) -> Dict:
        """
        Process unified stream with order book reconstruction.
        
        Args:
            trades_path: Path to trades data
            book_snapshots_path: Path to book snapshots
            book_deltas_path: Path to book deltas
            output_path: Optional output path for enriched data
            
        Returns:
            Processing statistics
        """
        if not self.config.enable_order_book:
            raise ValueError("Order book processing not enabled in config")
        
        start_time = time.time()
        stats = {
            "total_events": 0,
            "trades_processed": 0,
            "snapshots_processed": 0,
            "deltas_processed": 0,
            "processing_time": 0.0,
            "throughput": 0.0,
        }
        
        try:
            # Try to load checkpoint
            if self.order_book_engine.load_checkpoint():
                logger.info("Resumed from checkpoint")
            
            # Process in streaming mode if enabled
            if self.config.enable_streaming and self.config.use_memory_mapping:
                stats = self._process_streaming_mmap(
                    trades_path,
                    book_snapshots_path, 
                    book_deltas_path,
                    output_path,
                )
            else:
                stats = self._process_batch_mode(
                    trades_path,
                    book_snapshots_path,
                    book_deltas_path,
                    output_path,
                )
            
            # Calculate final statistics
            stats["processing_time"] = time.time() - start_time
            stats["throughput"] = stats["total_events"] / stats["processing_time"]
            
            # Add order book statistics
            stats["order_book_stats"] = self.order_book_engine.get_statistics()
            stats["delta_processor_stats"] = self.delta_processor.get_statistics()
            stats["drift_metrics"] = {
                "total_snapshots": self.drift_metrics.total_snapshots,
                "snapshots_with_drift": self.drift_metrics.snapshots_with_drift,
                "max_price_drift": self.drift_metrics.max_price_drift,
                "max_quantity_drift": self.drift_metrics.max_quantity_drift,
            }
            
            logger.info(
                f"Processing completed: {stats['total_events']:,} events in "
                f"{stats['processing_time']:.1f}s ({stats['throughput']:.0f} events/s)"
            )
            
        except Exception as e:
            logger.error(f"Processing failed: {e}")
            raise
        
        return stats
    
    def _process_streaming_mmap(
        self,
        trades_path: Optional[Path],
        book_snapshots_path: Optional[Path],
        book_deltas_path: Optional[Path],
        output_path: Optional[Path],
    ) -> Dict:
        """Process data using memory-mapped streaming."""
        stats = {
            "total_events": 0,
            "trades_processed": 0,
            "snapshots_processed": 0,
            "deltas_processed": 0,
        }
        
        # Process book deltas with order book reconstruction
        if book_deltas_path:
            def process_delta_chunk(chunk: pl.DataFrame) -> pl.DataFrame:
                # Convert prices/quantities to scaled int64
                chunk = chunk.with_columns([
                    chunk["price"].map_elements(
                        lambda x: float_to_scaled_int64(x),
                        return_dtype=pl.Int64,
                    ).alias("price_scaled"),
                    chunk["new_quantity"].map_elements(
                        lambda x: float_to_scaled_int64(x),
                        return_dtype=pl.Int64,
                    ).alias("quantity_scaled"),
                ])
                
                # Process with delta processor
                sorted_chunk, recovery_needed = self.delta_processor.process_batch(chunk)
                
                if recovery_needed:
                    logger.warning("Recovery needed due to large sequence gap")
                
                # Enrich with order book state
                enriched = self.order_book_engine.process_delta_batch(
                    sorted_chunk,
                    validate_sequence=True,
                )
                
                stats["deltas_processed"] += len(enriched)
                stats["total_events"] += len(enriched)
                
                return enriched
            
            if output_path:
                delta_stats = self.mmap_processor.process_with_mmap(
                    book_deltas_path,
                    output_path / "enriched_deltas.parquet",
                    process_delta_chunk,
                )
                logger.info(f"Processed {delta_stats['total_rows']:,} delta events")
        
        # Process snapshots for drift tracking
        if book_snapshots_path:
            for chunk in self.mmap_processor.read_parquet_mmap(book_snapshots_path):
                self._process_snapshot_chunk(chunk)
                stats["snapshots_processed"] += len(chunk)
                stats["total_events"] += len(chunk)
        
        return stats
    
    def _process_batch_mode(
        self,
        trades_path: Optional[Path],
        book_snapshots_path: Optional[Path],
        book_deltas_path: Optional[Path],
        output_path: Optional[Path],
    ) -> Dict:
        """Process data in batch mode (non-streaming)."""
        # Use parent class merge_streams for initial unification
        unified_df = self.merge_streams(
            trades_path=trades_path,
            book_snapshots_path=book_snapshots_path,
            book_deltas_path=book_deltas_path,
        )
        
        stats = {
            "total_events": len(unified_df),
            "trades_processed": 0,
            "snapshots_processed": 0,
            "deltas_processed": 0,
        }
        
        # Process events in chronological order
        for event_type in unified_df["event_type"].unique():
            event_df = unified_df.filter(pl.col("event_type") == event_type)
            
            if event_type == "BOOK_SNAPSHOT":
                self._process_snapshots_batch(event_df)
                stats["snapshots_processed"] = len(event_df)
                
            elif event_type == "BOOK_DELTA":
                enriched_df = self._process_deltas_batch(event_df)
                stats["deltas_processed"] = len(enriched_df)
                
                if output_path:
                    output_path.mkdir(parents=True, exist_ok=True)
                    enriched_df.write_parquet(
                        output_path / "enriched_deltas.parquet"
                    )
            
            elif event_type == "TRADE":
                stats["trades_processed"] = len(event_df)
        
        return stats
    
    def _process_snapshot_chunk(self, snapshot_df: pl.DataFrame) -> None:
        """Process snapshot chunk for initialization and drift tracking."""
        for symbol in snapshot_df["symbol"].unique():
            symbol_snapshots = snapshot_df.filter(pl.col("symbol") == symbol)
            
            for snapshot_time in symbol_snapshots["origin_time"].unique():
                snapshot = symbol_snapshots.filter(
                    pl.col("origin_time") == snapshot_time
                )
                
                # Initialize or check drift
                if self.order_book_engine.last_update_id == 0:
                    # First snapshot - initialize
                    self.order_book_engine.process_snapshot(snapshot)
                    logger.info(f"Initialized order book from snapshot at {snapshot_time}")
                else:
                    # Calculate drift
                    drift = self.order_book_engine.calculate_drift(snapshot)
                    self._update_drift_metrics(drift)
                    
                    # Resync if drift is too high
                    if drift.get("total_drift", 0) > 1000000:  # Threshold in scaled units
                        logger.warning(f"High drift detected, resyncing from snapshot")
                        self.order_book_engine.process_snapshot(snapshot)
    
    def _process_deltas_batch(self, deltas_df: pl.DataFrame) -> pl.DataFrame:
        """Process delta batch with order book enrichment."""
        # Convert to scaled int64
        deltas_df = deltas_df.with_columns([
            deltas_df["price"].map_elements(
                lambda x: float_to_scaled_int64(x),
                return_dtype=pl.Int64,
            ).alias("price_scaled"),
            deltas_df["new_quantity"].map_elements(
                lambda x: float_to_scaled_int64(x),
                return_dtype=pl.Int64,
            ).alias("quantity_scaled"),
        ])
        
        # Process with delta processor
        sorted_df, recovery_needed = self.delta_processor.process_batch(deltas_df)
        
        # Enrich with order book state
        enriched_df = self.order_book_engine.process_delta_batch(
            sorted_df,
            validate_sequence=True,
        )
        
        return enriched_df
    
    def _process_snapshots_batch(self, snapshots_df: pl.DataFrame) -> None:
        """Process snapshots batch."""
        self.drift_metrics.total_snapshots += len(snapshots_df["origin_time"].unique())
        
        for idx, snapshot_time in enumerate(snapshots_df["origin_time"].unique()):
            snapshot = snapshots_df.filter(pl.col("origin_time") == snapshot_time)
            
            if idx == 0 and self.order_book_engine.last_update_id == 0:
                # Initialize from first snapshot
                self.order_book_engine.process_snapshot(snapshot)
            else:
                # Track drift
                drift = self.order_book_engine.calculate_drift(snapshot)
                self._update_drift_metrics(drift)
    
    def _update_drift_metrics(self, drift: Dict[str, float]) -> None:
        """Update drift metrics."""
        if drift.get("total_drift", 0) > 0:
            self.drift_metrics.snapshots_with_drift += 1
            self.drift_metrics.max_price_drift = max(
                self.drift_metrics.max_price_drift,
                drift.get("bid_price_drift", 0) + drift.get("ask_price_drift", 0)
            )
            self.drift_metrics.max_quantity_drift = max(
                self.drift_metrics.max_quantity_drift,
                drift.get("bid_quantity_drift", 0) + drift.get("ask_quantity_drift", 0)
            )
            self.drift_metrics.cumulative_drift += drift.get("total_drift", 0)
            
            # Keep limited history
            if len(self.drift_metrics.drift_history) < 100:
                self.drift_metrics.drift_history.append({
                    "timestamp": time.time(),
                    "drift": drift,
                })
    
    def get_pending_queue_stats(self) -> Dict:
        """Get pending queue statistics."""
        return {
            "queue_size": len(self.pending_queue),
            "max_size": self.pending_queue.maxlen,
            "usage_percent": (len(self.pending_queue) / self.pending_queue.maxlen) * 100,
        }