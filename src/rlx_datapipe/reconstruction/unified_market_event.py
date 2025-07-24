"""Unified Market Event data model.

Defines the standardized event format used throughout the pipeline.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, List, Tuple


@dataclass
class UnifiedMarketEvent:
    """Unified Market Event Schema with decimal128(38,18) precision.
    
    This represents the normalized event format output by the ChronologicalEventReplay
    and consumed by the DataSink for Parquet storage.
    
    All price and quantity fields use Decimal type for exact precision.
    Nullable fields are set to None for event types that don't use them.
    """
    
    # Core identifiers (always present)
    event_timestamp: int  # Nanosecond precision timestamp
    event_type: str  # 'TRADE' | 'BOOK_SNAPSHOT' | 'BOOK_DELTA'
    update_id: Optional[int] = None
    
    # Trade-specific fields (null if not TRADE)
    trade_id: Optional[int] = None
    trade_price: Optional[Decimal] = None
    trade_quantity: Optional[Decimal] = None
    trade_side: Optional[str] = None  # 'BUY' | 'SELL'
    
    # Book snapshot fields (null if not BOOK_SNAPSHOT)
    bids: Optional[List[Tuple[Decimal, Decimal]]] = None  # [(price, quantity), ...]
    asks: Optional[List[Tuple[Decimal, Decimal]]] = None  # [(price, quantity), ...]
    is_snapshot: Optional[bool] = None
    
    # Book delta fields (null if not BOOK_DELTA)
    delta_side: Optional[str] = None  # 'BID' | 'ASK'
    delta_price: Optional[Decimal] = None
    delta_quantity: Optional[Decimal] = None
    
    def __post_init__(self):
        """Validate event type and ensure correct fields are populated."""
        valid_types = {'TRADE', 'BOOK_SNAPSHOT', 'BOOK_DELTA'}
        if self.event_type not in valid_types:
            raise ValueError(f"Invalid event_type: {self.event_type}. Must be one of {valid_types}")
        
        # Validate that appropriate fields are set for each event type
        if self.event_type == 'TRADE':
            if self.trade_id is None or self.trade_price is None or self.trade_quantity is None:
                raise ValueError("TRADE events must have trade_id, trade_price, and trade_quantity")
        
        elif self.event_type == 'BOOK_SNAPSHOT':
            if self.bids is None or self.asks is None or self.is_snapshot is None:
                raise ValueError("BOOK_SNAPSHOT events must have bids, asks, and is_snapshot")
        
        elif self.event_type == 'BOOK_DELTA':
            if self.delta_side is None or self.delta_price is None or self.delta_quantity is None:
                raise ValueError("BOOK_DELTA events must have delta_side, delta_price, and delta_quantity")
