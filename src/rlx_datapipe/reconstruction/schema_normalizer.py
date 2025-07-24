"""Schema normalization for unified market event format.

Transforms events from various sources into the Unified Market Event Schema
with proper nullable field handling and decimal precision.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional, Union
import polars as pl
from loguru import logger

from .decimal_utils import ensure_decimal128


class SchemaNormalizer:
    """Normalizes events to the Unified Market Event Schema.
    
    Handles transformation of events from different sources into a unified
    format with consistent field names, types, and precision.
    """
    
    def __init__(self):
        """Initialize the schema normalizer."""
        self.pending_queue: List[Dict[str, Any]] = []
        
    def normalize_events(self, events_df: pl.DataFrame) -> pl.DataFrame:
        """Normalize entire DataFrame to unified schema.
        
        Args:
            events_df: Events to normalize
            
        Returns:
            DataFrame with unified schema
        """
        logger.info(f"Normalizing {len(events_df)} events to unified schema")
        
        # Apply normalization row by row for complex transformations
        normalized_rows = []
        
        for row in events_df.iter_rows(named=True):
            normalized = self.normalize_to_unified_schema(dict(row))
            normalized_rows.append(normalized)
        
        # Create DataFrame with proper schema
        result_df = self._create_unified_dataframe(normalized_rows)
        
        logger.info(f"Normalized {len(result_df)} events successfully")
        return result_df
    
    def normalize_to_unified_schema(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Transform single event to Unified Market Event Schema.
        
        Args:
            event: Raw event data
            
        Returns:
            Event conforming to unified schema with nullable fields
        """
        event_type = event.get("event_type", "UNKNOWN")
        
        # Core identifiers - always present
        unified = {
            "event_timestamp": self._get_timestamp(event),
            "event_type": event_type,
            "update_id": event.get("update_id"),
        }
        
        # Add type-specific fields based on event type
        if event_type == "TRADE":
            self._add_trade_fields(unified, event)
        elif event_type == "BOOK_SNAPSHOT":
            self._add_snapshot_fields(unified, event)
        elif event_type == "BOOK_DELTA":
            self._add_delta_fields(unified, event)
        
        # Ensure all nullable fields exist
        self._ensure_nullable_fields(unified)
        
        # Handle pending queue pattern for atomic updates
        if self.pending_queue and event_type == "BOOK_SNAPSHOT":
            # Apply pending updates atomically after snapshot
            self._apply_pending_updates(unified)
            self.pending_queue.clear()
        
        return unified
    
    def _get_timestamp(self, event: Dict[str, Any]) -> int:
        """Extract timestamp in nanosecond precision.
        
        Args:
            event: Event data
            
        Returns:
            Timestamp in nanoseconds
        """
        # Try multiple timestamp fields
        for field in ["origin_time", "event_timestamp", "timestamp"]:
            if field in event and event[field] is not None:
                ts = event[field]
                # Convert to nanoseconds if needed
                if isinstance(ts, (int, float)):
                    # Assume microseconds if < 1e12, otherwise nanoseconds
                    if ts < 1e12:
                        return int(ts * 1e6)
                    else:
                        return int(ts)
        
        # Fallback to current time if no timestamp found
        import time
        return int(time.time() * 1e9)
    
    def _add_trade_fields(self, unified: Dict[str, Any], event: Dict[str, Any]) -> None:
        """Add trade-specific fields to unified event.
        
        Args:
            unified: Unified event being built
            event: Source event data
        """
        # Map common trade field names
        price_fields = ["trade_price", "price", "exec_price"]
        quantity_fields = ["trade_quantity", "quantity", "exec_quantity", "amount"]
        side_fields = ["trade_side", "side", "exec_side"]
        id_fields = ["trade_id", "id", "exec_id"]
        
        # Extract trade price
        for field in price_fields:
            if field in event and event[field] is not None:
                unified["trade_price"] = ensure_decimal128(event[field])
                break
        
        # Extract trade quantity
        for field in quantity_fields:
            if field in event and event[field] is not None:
                unified["trade_quantity"] = ensure_decimal128(event[field])
                break
        
        # Extract trade side
        for field in side_fields:
            if field in event and event[field] is not None:
                side = str(event[field]).upper()
                # Normalize side values
                if side in ["BUY", "B", "BID"]:
                    unified["trade_side"] = "BUY"
                elif side in ["SELL", "S", "ASK", "OFFER"]:
                    unified["trade_side"] = "SELL"
                break
        
        # Extract trade ID
        for field in id_fields:
            if field in event and event[field] is not None:
                unified["trade_id"] = int(event[field])
                break
    
    def _add_snapshot_fields(self, unified: Dict[str, Any], event: Dict[str, Any]) -> None:
        """Add snapshot-specific fields to unified event.
        
        Args:
            unified: Unified event being built
            event: Source event data
        """
        # Extract bids and asks
        bids = event.get("bids", [])
        asks = event.get("asks", [])
        
        # Ensure proper format: list of [price, quantity] pairs
        unified["bids"] = self._normalize_book_levels(bids)
        unified["asks"] = self._normalize_book_levels(asks)
        unified["is_snapshot"] = True
    
    def _add_delta_fields(self, unified: Dict[str, Any], event: Dict[str, Any]) -> None:
        """Add delta-specific fields to unified event.
        
        Args:
            unified: Unified event being built
            event: Source event data
        """
        # Map delta fields
        side = event.get("delta_side", event.get("side", "")).upper()
        price = event.get("delta_price", event.get("price"))
        quantity = event.get("delta_quantity", event.get("quantity"))
        
        if side in ["BID", "B"]:
            unified["delta_side"] = "BID"
        elif side in ["ASK", "A", "OFFER"]:
            unified["delta_side"] = "ASK"
        
        if price is not None:
            unified["delta_price"] = ensure_decimal128(price)
        
        if quantity is not None:
            unified["delta_quantity"] = ensure_decimal128(quantity)
    
    def _normalize_book_levels(
        self, 
        levels: Union[List[List[Any]], List[Dict[str, Any]]]
    ) -> List[List[Decimal]]:
        """Normalize book levels to [price, quantity] format.
        
        Args:
            levels: Raw book levels in various formats
            
        Returns:
            Normalized levels as list of [Decimal, Decimal]
        """
        normalized = []
        
        for level in levels:
            if isinstance(level, list) and len(level) >= 2:
                # Already in [price, quantity] format
                price = ensure_decimal128(level[0])
                quantity = ensure_decimal128(level[1])
                normalized.append([price, quantity])
            elif isinstance(level, dict):
                # Dict format with price/quantity keys
                price = ensure_decimal128(
                    level.get("price", level.get("p", 0))
                )
                quantity = ensure_decimal128(
                    level.get("quantity", level.get("q", level.get("size", 0)))
                )
                normalized.append([price, quantity])
        
        return normalized
    
    def _ensure_nullable_fields(self, unified: Dict[str, Any]) -> None:
        """Ensure all nullable fields exist in unified event.
        
        Args:
            unified: Unified event to complete
        """
        # Trade fields
        trade_fields = ["trade_id", "trade_price", "trade_quantity", "trade_side"]
        for field in trade_fields:
            if field not in unified:
                unified[field] = None
        
        # Snapshot fields
        snapshot_fields = ["bids", "asks", "is_snapshot"]
        for field in snapshot_fields:
            if field not in unified:
                unified[field] = None
        
        # Delta fields
        delta_fields = ["delta_side", "delta_price", "delta_quantity"]
        for field in delta_fields:
            if field not in unified:
                unified[field] = None
    
    def _apply_pending_updates(self, unified: Dict[str, Any]) -> None:
        """Apply pending updates atomically after snapshot.
        
        Args:
            unified: Snapshot event to update
        """
        if not self.pending_queue:
            return
        
        logger.debug(f"Applying {len(self.pending_queue)} pending updates")
        
        # Group updates by side
        bid_updates = []
        ask_updates = []
        
        for update in self.pending_queue:
            if update.get("delta_side") == "BID":
                bid_updates.append({
                    "price": update["delta_price"],
                    "quantity": update["delta_quantity"]
                })
            elif update.get("delta_side") == "ASK":
                ask_updates.append({
                    "price": update["delta_price"],
                    "quantity": update["delta_quantity"]
                })
        
        # Apply updates to snapshot
        if bid_updates:
            unified["bids"] = self._apply_updates_to_levels(
                unified.get("bids", []), bid_updates
            )
        if ask_updates:
            unified["asks"] = self._apply_updates_to_levels(
                unified.get("asks", []), ask_updates
            )
    
    def _apply_updates_to_levels(
        self,
        levels: List[List[Decimal]],
        updates: List[Dict[str, Decimal]]
    ) -> List[List[Decimal]]:
        """Apply delta updates to book levels.
        
        Args:
            levels: Current book levels
            updates: Updates to apply
            
        Returns:
            Updated levels
        """
        # Convert to dict for easier manipulation
        level_dict = {level[0]: level[1] for level in levels}
        
        # Apply updates
        for update in updates:
            price = update["price"]
            quantity = update["quantity"]
            
            if quantity == 0:
                # Remove level
                level_dict.pop(price, None)
            else:
                # Add/update level
                level_dict[price] = quantity
        
        # Convert back to sorted list
        sorted_levels = sorted(level_dict.items(), key=lambda x: x[0])
        return [[price, qty] for price, qty in sorted_levels]
    
    def _create_unified_dataframe(self, rows: List[Dict[str, Any]]) -> pl.DataFrame:
        """Create DataFrame with proper unified schema.
        
        Args:
            rows: Normalized event rows
            
        Returns:
            DataFrame with unified schema and proper types
        """
        # Convert Decimal values to floats to avoid schema issues
        converted_rows = []
        for row in rows:
            converted_row = {}
            for key, value in row.items():
                if isinstance(value, Decimal):
                    converted_row[key] = float(value)
                elif isinstance(value, list) and value and isinstance(value[0], list):
                    # Handle bid/ask lists
                    converted_list = []
                    for level in value:
                        if isinstance(level, list) and len(level) >= 2:
                            converted_level = []
                            for item in level:
                                if isinstance(item, Decimal):
                                    converted_level.append(float(item))
                                else:
                                    converted_level.append(item)
                            converted_list.append(converted_level)
                        else:
                            converted_list.append(level)
                    converted_row[key] = converted_list
                else:
                    converted_row[key] = value
            converted_rows.append(converted_row)
        
        # Create DataFrame
        df = pl.DataFrame(converted_rows)
        
        # Cast numeric columns to proper types
        numeric_cols = ["event_timestamp", "update_id", "trade_id"]
        for col in numeric_cols:
            if col in df.columns:
                df = df.with_columns(pl.col(col).cast(pl.Int64))
        
        return df
