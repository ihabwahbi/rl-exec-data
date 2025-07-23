"""Chronological event replay with stateful order book maintenance.

This module implements the ChronologicalEventReplay algorithm that processes
events in strict origin_time order while maintaining accurate market state.
"""

from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
import polars as pl
from loguru import logger

from .order_book_state import OrderBookState
from .schema_normalizer import SchemaNormalizer
from .drift_tracker import DriftTracker


class ChronologicalEventReplay:
    """Processes events chronologically while maintaining order book state.
    
    Implements the core replay algorithm that:
    - Sorts events by origin_time and update_id
    - Maintains full L2 book state with bounded memory
    - Tracks drift between snapshots and reconstructed state
    - Enriches events with current book state
    """
    
    def __init__(
        self,
        drift_threshold: float = 0.001,
        max_levels: int = 20,
        resync_on_drift: bool = True
    ):
        """Initialize the event replayer.
        
        Args:
            drift_threshold: RMS error threshold for triggering resync
            max_levels: Maximum number of price levels to maintain
            resync_on_drift: Whether to resync on drift threshold breach
        """
        self.drift_threshold = drift_threshold
        self.max_levels = max_levels
        self.resync_on_drift = resync_on_drift
        self.normalizer = SchemaNormalizer()
        self.drift_tracker = DriftTracker(drift_threshold)
        
    def execute(self, events_df: pl.DataFrame) -> pl.DataFrame:
        """Execute chronological event replay with stateful processing.
        
        Args:
            events_df: DataFrame with events to process
            
        Returns:
            DataFrame with events enriched with book state and drift metrics
        """
        logger.info(f"Starting chronological event replay for {len(events_df)} events")
        
        # Step 1: Stable sort by origin_time and update_id
        sorted_events = self._sort_events(events_df)
        
        # Step 2: Add event type labels if not present
        labeled_events = self._label_event_types(sorted_events)
        
        # Step 3: Normalize to unified schema
        normalized_events = self.normalizer.normalize_events(labeled_events)
        
        # Step 4: Stateful replay with book maintenance
        replayed_events = self._stateful_replay(normalized_events)
        
        logger.info(f"Completed replay of {len(replayed_events)} events")
        return replayed_events
    
    def _sort_events(self, events_df: pl.DataFrame) -> pl.DataFrame:
        """Stable sort events by origin_time and update_id.
        
        Args:
            events_df: Events to sort
            
        Returns:
            Sorted DataFrame maintaining causality
        """
        # Check if update_id exists, add if missing
        if "update_id" not in events_df.columns:
            events_df = events_df.with_columns(
                pl.lit(0).alias("update_id")
            )
        
        # Stable sort maintaining original order for equal timestamps
        sorted_df = events_df.sort(
            ["origin_time", "update_id"],
            descending=[False, False],
            maintain_order=True
        )
        
        logger.debug(f"Sorted {len(events_df)} events by origin_time and update_id")
        return sorted_df
    
    def _label_event_types(self, events_df: pl.DataFrame) -> pl.DataFrame:
        """Add event type labels if not present.
        
        Args:
            events_df: Events to label
            
        Returns:
            DataFrame with event_type column
        """
        if "event_type" in events_df.columns:
            return events_df
            
        # Infer event types based on column presence
        conditions = []
        
        # Trade events have trade_id
        if "trade_id" in events_df.columns:
            conditions.append(
                pl.when(pl.col("trade_id").is_not_null())
                .then(pl.lit("TRADE"))
            )
        
        # Snapshot events have is_snapshot flag or both bids and asks
        if "is_snapshot" in events_df.columns:
            conditions.append(
                pl.when(pl.col("is_snapshot") == True)
                .then(pl.lit("BOOK_SNAPSHOT"))
            )
        elif "bids" in events_df.columns and "asks" in events_df.columns:
            conditions.append(
                pl.when(
                    pl.col("bids").is_not_null() & 
                    pl.col("asks").is_not_null()
                )
                .then(pl.lit("BOOK_SNAPSHOT"))
            )
        
        # Default to BOOK_DELTA
        expr = pl.lit("BOOK_DELTA")
        for condition in conditions:
            expr = condition.otherwise(expr)
        
        return events_df.with_columns(
            expr.alias("event_type")
        )
    
    def _stateful_replay(self, events_df: pl.DataFrame) -> pl.DataFrame:
        """Replay events while maintaining order book state.
        
        Args:
            events_df: Normalized events to replay
            
        Returns:
            Events enriched with book state and drift metrics
        """
        order_book = OrderBookState(max_levels=self.max_levels)
        
        output_rows = []
        
        # Process events sequentially
        for row in events_df.iter_rows(named=True):
            event = dict(row)
            
            if event["event_type"] == "BOOK_SNAPSHOT":
                drift_metrics = self._process_snapshot(
                    event, order_book
                )
                event["drift_metrics"] = drift_metrics
                
            elif event["event_type"] == "TRADE":
                self._process_trade(event, order_book)
                
            elif event["event_type"] == "BOOK_DELTA":
                self._process_delta(event, order_book)
            
            # Enrich with current book state
            event["book_state"] = order_book.get_current_state()
            event["top_bid"] = order_book.get_best_bid()
            event["top_ask"] = order_book.get_best_ask()
            event["spread"] = order_book.get_spread()
            
            output_rows.append(event)
        
        # Convert back to DataFrame
        return pl.DataFrame(output_rows)
    
    def _process_snapshot(
        self,
        event: Dict[str, Any],
        order_book: OrderBookState
    ) -> Optional[Dict[str, float]]:
        """Process snapshot event with drift tracking.
        
        Args:
            event: Snapshot event
            order_book: Current book state
            
        Returns:
            Drift metrics if book was already initialized
        """
        drift_metrics = None
        
        if not order_book.initialized:
            # First snapshot - initialize book
            order_book.initialize_from_snapshot({
                "bids": event.get("bids", []),
                "asks": event.get("asks", [])
            })
            logger.info("Initialized order book from first snapshot")
        else:
            # Calculate drift before resync
            drift_metrics = self.drift_tracker.calculate_drift(
                order_book, event
            )
            
            if self.resync_on_drift and drift_metrics["rms_error"] > self.drift_threshold:
                logger.warning(
                    f"Drift threshold exceeded: {drift_metrics['rms_error']:.4f} > "
                    f"{self.drift_threshold}, resyncing"
                )
                order_book.resynchronize(event)
        
        return drift_metrics
    
    def _process_trade(
        self,
        event: Dict[str, Any],
        order_book: OrderBookState
    ) -> None:
        """Process trade event with liquidity consumption.
        
        Args:
            event: Trade event
            order_book: Current book state
        """
        if not order_book.initialized:
            logger.warning("Skipping trade - order book not initialized")
            return
        
        # Apply trade to book (liquidity consumption modeling)
        trade_price = event.get("trade_price")
        trade_quantity = event.get("trade_quantity")
        trade_side = event.get("trade_side")
        
        if all([trade_price, trade_quantity, trade_side]):
            order_book.apply_trade({
                "price": trade_price,
                "quantity": trade_quantity,
                "side": trade_side
            })
    
    def _process_delta(
        self,
        event: Dict[str, Any],
        order_book: OrderBookState
    ) -> None:
        """Process book delta event.
        
        Args:
            event: Delta event
            order_book: Current book state
        """
        if not order_book.initialized:
            logger.warning("Skipping delta - order book not initialized")
            return
        
        # Apply delta directly to order book
        delta_side = event.get("delta_side")
        delta_price = event.get("delta_price")
        delta_quantity = event.get("delta_quantity")
        
        if all([delta_side is not None, delta_price is not None, delta_quantity is not None]):
            # Convert price and quantity to scaled int
            price_int = int(float(delta_price) * 1e8)
            quantity_int = int(float(delta_quantity) * 1e8)
            
            # Apply delta
            order_book.apply_delta(
                price=price_int,
                quantity=quantity_int,
                side=delta_side,
                update_id=event.get("update_id", 0)
            )