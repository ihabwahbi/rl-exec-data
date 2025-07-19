# ADR-002: Raw Data Preservation for Golden Samples

## Status
Accepted

## Context
The original Story 1.2 implementation transformed WebSocket data into a processed format, losing the original message structure. This prevents accurate validation because we can't compare the exact format that would be received in production.

## Decision
Golden samples must preserve WebSocket messages exactly as received from Binance, with only minimal metadata addition for capture timestamp and stream identification.

## Rationale
1. **Ground Truth Requirement**: Validation requires comparing exact formats
2. **Future Compatibility**: Exchange formats may change; raw data preserves options
3. **Debugging Capability**: Can replay exact scenarios
4. **Research Validation**: Can test claims about message structure

## Implementation
```json
{
  "capture_ns": 1234567890123456789,
  "stream": "btcusdt@trade",
  "data": {
    // Original message exactly as received
    "e": "trade",
    "E": 1234567890123,
    "s": "BTCUSDT",
    "t": 12345,
    "p": "50000.00",
    "q": "0.001",
    "T": 1234567890123,
    "m": true,
    "M": true
  }
}
```

## Consequences

### Positive
- Enables accurate validation
- Preserves all information
- Allows format evolution
- Simplifies capture implementation

### Negative
- Larger storage requirements
- Requires parsing during analysis
- May capture unnecessary fields

### Neutral
- Different from processed format used later
- Requires clear documentation

## Alternatives Considered
1. **Normalized format**: Loses original structure needed for validation
2. **Selective preservation**: Risk losing important fields
3. **Binary format**: Harder to debug and analyze

## Migration
- Fix existing capture implementation
- Re-capture golden samples
- Archive previous captures