# Data Models

**Last Updated**: 2025-07-31  
**Status**: Updated with validated schemas from Epic 0 and Epic 1 completion

The pipeline handles three primary input schemas from Crypto Lake (validated during Epic 0 implementation) and one unified output schema for the backtesting environment.

## Data Precision Strategy

**Status**: Validated through Epic 1 Story 1.2.5

### Executive Summary

The expert review correctly identified that Polars decimal128 support is experimental and may not meet our performance requirements. This section defines our decimal handling strategy with clear decision criteria and implementation paths.

**Validation Results**: Story 1.2.5 tested both decimal128 and int64 pips approaches. Decimal128 operations completed without errors and are recommended as the primary approach, with int64 pips as a proven fallback strategy.

### The Precision Challenge

#### Requirements
- **No precision loss**: Critical for small-quantity symbols (e.g., SOL-USDT)
- **Performance**: Must sustain 100k events/second
- **Memory efficiency**: Operate within 28GB constraint
- **Determinism**: Identical results across runs

#### The Problem
- Float64 causes rounding errors: `0.123456789` → `0.12345679` 
- Decimal128 in Polars is experimental and may panic on operations
- String storage is memory-inefficient and slow

### Implementation Strategy

**Storage Layer**: All price and quantity fields are stored as `decimal128(38,18)` in Parquet files to prevent any precision loss, especially critical for small-quantity symbols like SOL-USDT.

**Processing Layer**: Internal calculations use Polars decimal types or Python Decimal where appropriate.

**ML Input Layer**: Convert to float32 only at the final step when feeding data to the RL agent, as neural networks require floating-point inputs. Implement a "tensor adapter" that validates max abs(price) and quantity ranges before casting to prevent silent overflow on exotic pairs.

### Primary Approach: Int64 Pips (Fallback Strategy)

If Polars decimal128 operations fail performance requirements, use int64 "pips" representation:

```python
class PipsConverter:
    """Convert decimal prices/quantities to int64 pips."""
    
    # Symbol-specific decimal places
    PRICE_DECIMALS = {
        'BTC-USDT': 2,   # $0.01 precision
        'ETH-USDT': 2,   # $0.01 precision  
        'SOL-USDT': 4,   # $0.0001 precision
        'SHIB-USDT': 8,  # $0.00000001 precision
    }
    
    QUANTITY_DECIMALS = {
        'BTC-USDT': 8,   # 0.00000001 BTC (1 satoshi)
        'ETH-USDT': 8,   # 0.00000001 ETH
        'SOL-USDT': 6,   # 0.000001 SOL
        'SHIB-USDT': 0,  # 1 SHIB (integer only)
    }
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.price_multiplier = 10 ** self.PRICE_DECIMALS.get(symbol, 8)
        self.qty_multiplier = 10 ** self.QUANTITY_DECIMALS.get(symbol, 8)
        
    def price_to_pips(self, price: str) -> int:
        """Convert string price to int64 pips."""
        # Using Decimal for exact conversion
        from decimal import Decimal, ROUND_HALF_UP
        
        decimal_price = Decimal(price)
        pips = decimal_price * self.price_multiplier
        return int(pips.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        
    def pips_to_price(self, pips: int) -> Decimal:
        """Convert pips back to decimal price."""
        return Decimal(pips) / self.price_multiplier
```

#### Advantages of Pips
1. **Performance**: Int64 operations are fastest in Polars
2. **Memory**: 8 bytes per value, highly compressible
3. **Determinism**: Integer math is always exact
4. **Compatibility**: Works with all DataFrame operations

### Decision Tree for Implementation

```
Start: Can we use Polars native decimal128?
  │
  ├─ YES: Performance test passes → Use decimal128 natively
  │
  └─ NO: Does int64 pips meet precision needs?
      │
      ├─ YES: For 99% of use cases → Implement pips strategy
      │
      └─ NO: Exotic requirements → Use PyArrow decimal128
```

### PyArrow Decimal128 Fallback

If pips prove insufficient (e.g., for cross-asset strategies):

```python
import pyarrow as pa
import pyarrow.compute as pc

class ArrowDecimalProcessor:
    """Use PyArrow for decimal operations, bypassing Polars."""
    
    def process_batch(self, batch: pa.RecordBatch) -> pa.RecordBatch:
        # Convert string prices to decimal128
        price_type = pa.decimal128(38, 18)
        prices = pc.cast(batch.column('price'), price_type)
        
        # Perform operations in Arrow
        avg_price = pc.mean(prices)
        sum_qty = pc.sum(pc.cast(batch.column('quantity'), price_type))
        
        # Return processed batch
        return pa.record_batch([
            batch.column('timestamp'),
            prices,
            batch.column('quantity'),
        ], names=['timestamp', 'price_decimal', 'quantity'])
```

### Recommendation

Based on the analysis, **decimal128 is the primary strategy with int64 pips as fallback**:

1. **Decimal128 validated**: Works without errors in Story 1.2.5
2. **Pips as fallback**: Proven approach used by major exchanges
3. **Best performance**: Pips provide 5-10x speed if needed
4. **Future-proof**: Easy to migrate between approaches

## Input Schema 1: Crypto Lake Book Data

Based on Epic 0 validation, the `book` table provides L2 order book snapshots.

**Core Columns** (validated in Epic 0):
- `origin_time`: int64 (nanoseconds) - Exchange timestamp - **100% reliable** (Story 1.1)
- `timestamp`: int64 - Collection timestamp
- `symbol`: string - Trading pair (e.g., "BTC-USDT")
- `exchange`: string - Source exchange ("binance")

**Market Data Columns** (wide format):
- `bid_0_price` through `bid_19_price`: float64 (to be stored as decimal128)
- `bid_0_size` through `bid_19_size`: float64 (to be stored as decimal128)
- `ask_0_price` through `ask_19_price`: float64 (to be stored as decimal128)
- `ask_0_size` through `ask_19_size`: float64 (to be stored as decimal128)

**Data Characteristics** (from Epic 0):
- Available: 2M book snapshots for BTC-USDT
- Update frequency: ~100ms intervals
- All numeric values positive and within expected ranges

## Input Schema 2: Crypto Lake Trades Data

Validated schema from Epic 0 implementation for the `trades` table.

**Required Columns**:
- `origin_time`: int64 (nanoseconds) - Exchange timestamp
- `price`: float64 - Trade price (to be stored as decimal128)
- `quantity`: float64 - Trade amount (to be stored as decimal128)
- `side`: string - Trade side ('buy' or 'sell')

**Optional Columns**:
- `trade_id`: int64 - Unique trade identifier
- `timestamp`: int64 - Collection timestamp
- `symbol`: string - Trading pair
- `exchange`: string - Source exchange

**Data Characteristics** (from Epic 0):
- Successfully validated 2.3M+ trade records
- 8 columns total in downloaded data
- All numeric values positive and within expected ranges
```

## Input Schema 3: Crypto Lake Book Delta v2 Data (VALIDATED)

The `book_delta_v2` table provides differential order book updates - **validated with perfect quality in Story 1.2.5**.

**Validated Schema** (from Epic 1):
- `origin_time`: int64 (nanoseconds) - Exchange timestamp
- `update_id`: int64 - Monotonic sequence number - **0% gaps validated**
- `price`: float64 - Price level (to be stored as decimal128)
- `new_quantity`: float64 - New quantity at level (0 = remove)
- `side`: string - Update side ('bid' or 'ask')

**Optional Columns**:
- `timestamp`: int64 - Collection timestamp
- `symbol`: string - Trading pair
- `exchange`: string - Source exchange
- `side_is_bid`: boolean - Alternative side representation

**Data Quality** (validated in Story 1.2.5):
- 102M rows available for BTC-USDT
- **0% sequence gaps** across all 11.15M golden sample messages
- Perfect update_id monotonicity in all market regimes
- Processing performance: ~336K messages/second
- Enables FullReconstruction strategy for maximum fidelity

**Critical Notes**:
- `update_id` must be processed in monotonic order to maintain book integrity
- Sequence gaps indicate missed updates and require recovery from next snapshot
- `new_quantity` of 0 indicates the price level should be removed from the book
- Multiple deltas can have the same `origin_time` but different `update_id`

## Output Schema: Unified Market Event

This is the target schema for the processed data. The pipeline will transform the raw inputs into this unified, chronologically-ordered stream. This design is directly informed by the research to ensure maximum fidelity.

```typescript
// Conceptual TypeScript representation of the final Parquet schema

interface UnifiedMarketEvent {
  // Core identifiers used for sorting and synchronization
  event_timestamp: number;      // Nanosecond precision, from origin_time
  event_type: 'TRADE' | 'BOOK_SNAPSHOT' | 'BOOK_DELTA';
  update_id?: number;           // For maintaining event ordering within same timestamp

  // Trade-specific data (null if event_type is not 'TRADE')
  trade_id?: number;
  trade_price?: Decimal128;     // Stored as decimal128(38,18) in Parquet
  trade_quantity?: Decimal128;  // Stored as decimal128(38,18) in Parquet
  trade_side?: 'BUY' | 'SELL'; // Aggressor side

  // Book snapshot data (null if event_type is not 'BOOK_SNAPSHOT')
  bids?: Array<[Decimal128, Decimal128]>; // Array of [price, quantity] tuples
  asks?: Array<[Decimal128, Decimal128]>; // Array of [price, quantity] tuples
  is_snapshot?: boolean;        // True for full snapshots used as recovery anchors

  // Book delta data (null if event_type is not 'BOOK_DELTA')
  delta_side?: 'BID' | 'ASK';
  delta_price?: Decimal128;     // Price level being updated
  delta_quantity?: Decimal128;  // New quantity at this level (0 = remove)
}
```

**Memory Optimization Note**: When processing, maintain only top 20 bid/ask levels in memory as bounded dictionaries. Deeper levels can be tracked with lossy counters for volume statistics without storing full detail.
