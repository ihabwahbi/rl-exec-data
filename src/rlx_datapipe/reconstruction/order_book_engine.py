"""Order book engine for reconstructing book state from delta updates."""

import gc
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import polars as pl
import pyarrow as pa
from loguru import logger

from rlx_datapipe.common.decimal_utils import scaled_to_decimal128
from rlx_datapipe.reconstruction.checkpoint_manager import CheckpointManager
from rlx_datapipe.reconstruction.order_book_state import OrderBookState


@dataclass
class GapStatistics:
    """Statistics for tracking sequence gaps."""
    
    total_gaps: int = 0
    max_gap_size: int = 0
    last_gap_update_id: Optional[int] = None
    gaps_by_size: Dict[int, int] = field(default_factory=dict)
    
    def record_gap(self, expected: int, actual: int) -> None:
        """Record a sequence gap."""
        gap_size = actual - expected
        self.total_gaps += 1
        self.max_gap_size = max(self.max_gap_size, gap_size)
        self.last_gap_update_id = actual
        
        # Track gap size distribution
        if gap_size in self.gaps_by_size:
            self.gaps_by_size[gap_size] += 1
        else:
            self.gaps_by_size[gap_size] = 1


class OrderBookEngine:
    """Engine for reconstructing order book state from delta updates."""
    
    def __init__(
        self,
        symbol: str,
        max_levels: int = 20,
        checkpoint_dir: Optional[Path] = None,
        gc_interval: int = 100_000,
        enable_drift_tracking: bool = True,
    ):
        """
        Initialize order book engine.
        
        Args:
            symbol: Trading symbol
            max_levels: Maximum number of price levels to track (default 20)
            checkpoint_dir: Directory for state checkpoints
            gc_interval: Number of updates between manual GC calls
            enable_drift_tracking: Enable drift tracking between snapshots
        """
        self.symbol = symbol
        self.max_levels = max_levels
        self.gc_interval = gc_interval
        self.enable_drift_tracking = enable_drift_tracking
        
        # Order book state
        self.book_state = OrderBookState(symbol, max_levels)
        
        # Sequence tracking
        self.last_update_id: Optional[int] = None
        self.gap_stats = GapStatistics()
        
        # Performance counters
        self.updates_processed = 0
        self.last_gc_time = time.time()
        
        # Checkpoint manager
        self.checkpoint_manager = None
        if checkpoint_dir:
            self.checkpoint_manager = CheckpointManager(
                checkpoint_dir=checkpoint_dir,
                symbol=symbol,
                enable_time_trigger=False,  # Will be managed at pipeline level
            )
            # Set this engine as state provider
            self.checkpoint_manager.set_state_provider(self)
        
        # Drift tracking
        self.drift_metrics: Dict[str, float] = {}
        self.snapshot_count = 0
        
        logger.info(
            f"Initialized OrderBookEngine for {symbol} with max_levels={max_levels}"
        )
    
    def process_snapshot(self, snapshot_data: pl.DataFrame) -> None:
        """
        Process a book snapshot to initialize or resync state.
        
        Args:
            snapshot_data: DataFrame with bid/ask price levels
        """
        try:
            # Validate snapshot data
            if snapshot_data.is_empty():
                logger.warning("Empty snapshot received, skipping")
                return
                
            required_cols = {"side", "price", "quantity"}
            if not required_cols.issubset(set(snapshot_data.columns)):
                raise ValueError(f"Snapshot missing required columns: {required_cols}")
                
            # Extract bid and ask data
            bid_data = snapshot_data.filter(pl.col("side") == "BID")
            ask_data = snapshot_data.filter(pl.col("side") == "ASK")
            
            # Initialize book state from snapshot
            self.book_state.initialize_from_snapshot(
                bid_prices=bid_data["price"].to_numpy(),
                bid_quantities=bid_data["quantity"].to_numpy(),
                ask_prices=ask_data["price"].to_numpy(),
                ask_quantities=ask_data["quantity"].to_numpy(),
                update_id=snapshot_data["update_id"][0] if "update_id" in snapshot_data.columns else 0,
            )
            
            # Update last update_id
            if "update_id" in snapshot_data.columns:
                self.last_update_id = int(snapshot_data["update_id"][0])
            
            self.snapshot_count += 1
            logger.debug(f"Processed snapshot #{self.snapshot_count} with update_id={self.last_update_id}")
            
        except Exception as e:
            logger.error(f"Failed to process snapshot: {e}")
            raise
    
    def process_delta_batch(
        self,
        delta_batch: pl.DataFrame,
        validate_sequence: bool = True,
    ) -> pl.DataFrame:
        """
        Process a batch of delta updates.
        
        Args:
            delta_batch: DataFrame with delta updates
            validate_sequence: Whether to validate update_id sequence
            
        Returns:
            DataFrame with enriched delta data including book state
        """
        try:
            # Sort by update_id to ensure correct ordering
            delta_batch = delta_batch.sort("update_id")
            
            # Pre-allocate arrays for enriched data
            num_deltas = len(delta_batch)
            bid_top_prices = np.zeros(num_deltas, dtype=np.int64)
            bid_top_quantities = np.zeros(num_deltas, dtype=np.int64)
            ask_top_prices = np.zeros(num_deltas, dtype=np.int64)
            ask_top_quantities = np.zeros(num_deltas, dtype=np.int64)
            bid_depth = np.zeros(num_deltas, dtype=np.int32)
            ask_depth = np.zeros(num_deltas, dtype=np.int32)
            
            # Process each delta
            for i, row in enumerate(delta_batch.iter_rows(named=True)):
                # Validate sequence if enabled
                if validate_sequence and self.last_update_id is not None:
                    expected_id = self.last_update_id + 1
                    actual_id = row["update_id"]
                    
                    if actual_id != expected_id:
                        self.gap_stats.record_gap(expected_id, actual_id)
                        logger.warning(
                            f"Sequence gap detected: expected {expected_id}, got {actual_id}"
                        )
                        
                        # Signal recovery if gap is too large
                        if actual_id - expected_id > 1000:
                            logger.error(
                                f"Large sequence gap ({actual_id - expected_id}), recovery needed"
                            )
                
                # Apply delta to book state
                self.book_state.apply_delta(
                    price=row["price"],
                    quantity=row["new_quantity"],
                    side=row["side"],
                    update_id=row["update_id"],
                )
                
                # Get current book state for enrichment
                top_bid, top_ask = self.book_state.get_top_of_book()
                
                if top_bid:
                    bid_top_prices[i] = top_bid[0]
                    bid_top_quantities[i] = top_bid[1]
                else:
                    bid_top_prices[i] = 0
                    bid_top_quantities[i] = 0
                
                if top_ask:
                    ask_top_prices[i] = top_ask[0]
                    ask_top_quantities[i] = top_ask[1]
                else:
                    ask_top_prices[i] = 0
                    ask_top_quantities[i] = 0
                
                # Get book depth
                bid_depth[i], ask_depth[i] = self.book_state.get_book_depth()
                
                self.last_update_id = row["update_id"]
                self.updates_processed += 1
                
                # Manual GC control
                if self.updates_processed % self.gc_interval == 0:
                    self._perform_gc()
            
            # Create enriched DataFrame
            enriched_df = delta_batch.with_columns([
                pl.Series("bid_top_price", bid_top_prices),
                pl.Series("bid_top_quantity", bid_top_quantities),
                pl.Series("ask_top_price", ask_top_prices),
                pl.Series("ask_top_quantity", ask_top_quantities),
                pl.Series("bid_depth", bid_depth),
                pl.Series("ask_depth", ask_depth),
            ])
            
            # Record events for checkpoint triggers
            if self.checkpoint_manager:
                asyncio.create_task(
                    self.checkpoint_manager.record_events(len(delta_batch))
                )
            
            return enriched_df
            
        except Exception as e:
            logger.error(f"Failed to process delta batch: {e}")
            raise
    
    def calculate_drift(self, snapshot_data: pl.DataFrame) -> Dict[str, float]:
        """
        Calculate drift between current state and snapshot.
        
        Args:
            snapshot_data: Snapshot to compare against
            
        Returns:
            Dictionary of drift metrics
        """
        if not self.enable_drift_tracking:
            return {}
        
        try:
            # Get current book state
            current_bids, current_asks = self.book_state.get_current_state()
            
            # Extract snapshot data
            snapshot_bids = snapshot_data.filter(pl.col("side") == "BID").sort("price", descending=True)
            snapshot_asks = snapshot_data.filter(pl.col("side") == "ASK").sort("price")
            
            # Calculate bid side drift
            bid_price_diff = 0.0
            bid_quantity_diff = 0.0
            
            for i in range(min(len(current_bids), len(snapshot_bids))):
                bid_price_diff += abs(current_bids[i][0] - snapshot_bids["price"][i])
                bid_quantity_diff += abs(current_bids[i][1] - snapshot_bids["quantity"][i])
            
            # Calculate ask side drift
            ask_price_diff = 0.0
            ask_quantity_diff = 0.0
            
            for i in range(min(len(current_asks), len(snapshot_asks))):
                ask_price_diff += abs(current_asks[i][0] - snapshot_asks["price"][i])
                ask_quantity_diff += abs(current_asks[i][1] - snapshot_asks["quantity"][i])
            
            # Update drift metrics
            self.drift_metrics = {
                "bid_price_drift": bid_price_diff,
                "bid_quantity_drift": bid_quantity_diff,
                "ask_price_drift": ask_price_diff,
                "ask_quantity_drift": ask_quantity_diff,
                "total_drift": bid_price_diff + bid_quantity_diff + ask_price_diff + ask_quantity_diff,
            }
            
            if self.drift_metrics["total_drift"] > 0:
                logger.warning(f"Drift detected: {self.drift_metrics}")
            
            return self.drift_metrics
            
        except Exception as e:
            logger.error(f"Failed to calculate drift: {e}")
            return {}
    
    def get_statistics(self) -> Dict:
        """Get engine statistics."""
        return {
            "updates_processed": self.updates_processed,
            "last_update_id": self.last_update_id,
            "snapshot_count": self.snapshot_count,
            "gap_statistics": {
                "total_gaps": self.gap_stats.total_gaps,
                "max_gap_size": self.gap_stats.max_gap_size,
                "last_gap_update_id": self.gap_stats.last_gap_update_id,
                "gaps_by_size": dict(self.gap_stats.gaps_by_size),
            },
            "drift_metrics": self.drift_metrics,
            "book_depth": self.book_state.get_book_depth(),
        }
    
    def _perform_gc(self) -> None:
        """Perform manual garbage collection."""
        current_time = time.time()
        gc.collect(0)  # Collect youngest generation only
        gc_time = time.time() - current_time
        
        logger.debug(f"Manual GC completed in {gc_time:.3f}s")
        self.last_gc_time = current_time
    
    def _save_checkpoint(self) -> None:
        """Save current state checkpoint."""
        if not self.checkpoint_manager:
            return
        
        try:
            state_data = {
                "book_state": self.book_state.to_dict(),
                "last_update_id": self.last_update_id,
                "gap_stats": self.gap_stats,
                "updates_processed": self.updates_processed,
                "snapshot_count": self.snapshot_count,
                "drift_metrics": self.drift_metrics,
            }
            
            self.checkpoint_manager.save_checkpoint(
                state_data=state_data,
                update_id=self.last_update_id,
            )
            
            logger.info(f"Saved checkpoint at update_id={self.last_update_id}")
            
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
    
    def load_checkpoint(self) -> bool:
        """
        Load state from checkpoint.
        
        Returns:
            True if checkpoint loaded successfully
        """
        if not self.checkpoint_manager:
            return False
        
        try:
            state_data = self.checkpoint_manager.load_latest_checkpoint()
            if not state_data:
                return False
            
            # Restore book state
            self.book_state = OrderBookState.from_dict(state_data["book_state"])
            
            # Restore tracking state
            self.last_update_id = state_data["last_update_id"]
            self.gap_stats = state_data["gap_stats"]
            self.updates_processed = state_data["updates_processed"]
            self.snapshot_count = state_data["snapshot_count"]
            self.drift_metrics = state_data["drift_metrics"]
            
            logger.info(f"Loaded checkpoint at update_id={self.last_update_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return False
    
    def get_checkpoint_state(self) -> Dict[str, Any]:
        """Get current state for checkpointing.
        
        This method is called by the checkpoint manager to capture state.
        Designed to be fast for COW snapshot creation.
        
        Returns:
            Dictionary containing full pipeline state
        """
        return {
            "book_state": self.book_state.to_dict(),
            "last_update_id": self.last_update_id,
            "gap_stats": self.gap_stats.__dict__ if hasattr(self.gap_stats, '__dict__') else self.gap_stats,
            "updates_processed": self.updates_processed,
            "snapshot_count": self.snapshot_count,
            "drift_metrics": self.drift_metrics,
            "processing_rate": self.updates_processed / max(1, time.time() - self.last_gc_time),
        }
