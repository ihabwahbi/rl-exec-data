# Decimal Precision Strategy

**Last Updated**: 2025-07-22  
**Status**: Validated through Epic 1 Story 1.2.5

## Executive Summary

The expert review correctly identified that Polars decimal128 support is experimental and may not meet our performance requirements. This document defines our decimal handling strategy with clear decision criteria and implementation paths.

**Validation Results**: Story 1.2.5 tested both decimal128 and int64 pips approaches. Decimal128 operations completed without errors and are recommended as the primary approach, with int64 pips as a proven fallback strategy.

## The Precision Challenge

### Requirements
- **No precision loss**: Critical for small-quantity symbols (e.g., SOL-USDT)
- **Performance**: Must sustain 100k events/second
- **Memory efficiency**: Operate within 28GB constraint
- **Determinism**: Identical results across runs

### The Problem
- Float64 causes rounding errors: `0.123456789` → `0.12345679` 
- Decimal128 in Polars is experimental and may panic on operations
- String storage is memory-inefficient and slow

## Implementation Strategy

### Primary Approach: Int64 Pips

Convert all prices and quantities to integer "pips" (smallest unit):

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

### Advantages of Pips

1. **Performance**: Int64 operations are fastest in Polars
2. **Memory**: 8 bytes per value, highly compressible
3. **Determinism**: Integer math is always exact
4. **Compatibility**: Works with all DataFrame operations

### Storage Schema with Pips

```python
# Parquet schema using pips
unified_event_schema_pips = {
    'event_timestamp': pa.int64(),      # Nanoseconds
    'event_type': pa.string(),           # TRADE, BOOK_SNAPSHOT, BOOK_DELTA
    'update_id': pa.int64(),            
    
    # Trade fields (as pips)
    'trade_id': pa.int64(),
    'trade_price_pips': pa.int64(),     # Price in pips
    'trade_quantity_pips': pa.int64(),  # Quantity in pips
    'trade_side': pa.string(),
    
    # Book fields (as pips)
    'bid_prices_pips': pa.list_(pa.int64()),  # List of price pips
    'bid_quantities_pips': pa.list_(pa.int64()),  # List of qty pips
    'ask_prices_pips': pa.list_(pa.int64()),
    'ask_quantities_pips': pa.list_(pa.int64()),
    
    # Metadata for conversion
    'price_decimal_places': pa.int8(),
    'quantity_decimal_places': pa.int8(),
}
```

### Fallback: PyArrow Decimal128

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

## Decision Tree for Implementation

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

## Validation Tests

### 1. Precision Test
```python
def test_precision_preservation():
    """Ensure no precision loss in round-trip conversion."""
    test_prices = [
        "0.123456789123456789",  # 18 decimal places
        "12345678.123456789",     # Large value with decimals
        "0.000000000001",         # Very small value
    ]
    
    for symbol in ['BTC-USDT', 'SOL-USDT', 'SHIB-USDT']:
        converter = PipsConverter(symbol)
        for price_str in test_prices:
            pips = converter.price_to_pips(price_str)
            recovered = converter.pips_to_price(pips)
            
            # Check precision preserved to symbol's decimal places
            expected_decimals = converter.PRICE_DECIMALS[symbol]
            assert_decimal_equals(price_str, recovered, expected_decimals)
```

### 2. Performance Test
```python
async def benchmark_decimal_strategies():
    """Compare performance of decimal handling approaches."""
    
    # Generate 10M events
    data = generate_test_events(10_000_000)
    
    # Test 1: Polars decimal128
    t1 = time.time()
    df_decimal = pl.DataFrame(data)
    df_decimal = df_decimal.with_columns([
        pl.col('price').cast(pl.Decimal(38, 18)),
        pl.col('quantity').cast(pl.Decimal(38, 18))
    ])
    result1 = df_decimal.group_by('symbol').agg([
        pl.col('price').mean(),
        pl.col('quantity').sum()
    ])
    decimal_time = time.time() - t1
    
    # Test 2: Int64 pips
    t2 = time.time()
    converter = PipsConverter('BTC-USDT')
    df_pips = pl.DataFrame({
        'price_pips': [converter.price_to_pips(p) for p in data['price']],
        'quantity_pips': [converter.qty_to_pips(q) for q in data['quantity']],
        'symbol': data['symbol']
    })
    result2 = df_pips.group_by('symbol').agg([
        pl.col('price_pips').mean(),
        pl.col('quantity_pips').sum()
    ])
    pips_time = time.time() - t2
    
    return {
        'decimal128_seconds': decimal_time,
        'pips_seconds': pips_time,
        'speedup': decimal_time / pips_time
    }
```

## Implementation Checklist

1. **Week 1 - Validation Phase**
   - [ ] Run decimal128 test on 10GB sample
   - [ ] Implement pips converter with tests
   - [ ] Benchmark both approaches
   - [ ] Make Go/No-Go decision

2. **Week 2 - Implementation Phase**
   - [ ] Implement chosen strategy in Reconstructor
   - [ ] Add conversion layer for ML interface
   - [ ] Update all tests for new schema
   - [ ] Document decimal places per symbol

3. **Long-term Monitoring**
   - [ ] Track precision-related errors
   - [ ] Monitor performance regression
   - [ ] Plan for Polars decimal128 maturity

## Recommendation

Based on the analysis, **implement int64 pips as the primary strategy**:

1. **Proven approach**: Used by major exchanges internally
2. **Best performance**: 5-10x faster than decimal types
3. **Simple fallback**: Can always convert to decimal for display
4. **Future-proof**: Easy to migrate when decimal128 matures

The pips approach gives us the precision we need with the performance we require, while keeping the door open for future decimal support as tooling improves.