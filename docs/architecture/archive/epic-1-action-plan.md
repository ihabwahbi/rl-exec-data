# Epic 1: Analysis & Validation - Engineering Action Plan

**Status**: Ready to Execute  
**Timeline**: Week 2-3  
**Prerequisites**: ✅ Epic 0 Complete - Real data available

## Overview

Epic 1 validates our technical assumptions using real Crypto Lake data. This epic determines the feasibility of achieving our -5bp VWAP improvement target and validates critical architectural decisions.

## Story Breakdown

### Story 1.1: Analyze Origin Time Completeness ⏳

**Purpose**: Validate our core assumption that `origin_time` can serve as the universal clock.

**Technical Tasks**:
1. **Load Real Data** (2 hours)
   ```python
   # Use existing DataDownloader from Epic 0
   downloader = DataDownloader(staging_area)
   trades_df = downloader.load_parquet_files('trades')
   book_df = downloader.load_parquet_files('book')
   ```

2. **Analyze Origin Time** (3 hours)
   - Calculate null/zero percentages
   - Check timestamp ranges and continuity
   - Compare origin_time vs timestamp skew
   - Generate distribution plots

3. **Document Findings** (1 hour)
   - Update architecture if >5% missing
   - Propose fallback strategies if needed

**Success Criteria**:
- [ ] <5% origin_time missing/invalid
- [ ] Clock skew <100ms for 95th percentile
- [ ] Clear recommendation on timestamp strategy

### Story 1.2: Implement Live Data Capture ⏳

**Purpose**: Capture golden samples from Binance for fidelity comparison.

**Technical Tasks**:

1. **WebSocket Client Implementation** (4 hours)
   ```python
   class BinanceLiveCapture:
       def __init__(self):
           # CRITICAL: Use combined stream per Gemini research
           self.stream_url = "wss://stream.binance.com:9443/stream?streams=btcusdt@trade/btcusdt@depth@100ms"
   ```

2. **Order Book Initialization** (3 hours)
   - REST snapshot fetch
   - WebSocket buffering during fetch
   - Synchronization validation (U <= lastUpdateId+1)
   - State management implementation

3. **Data Capture Logic** (3 hours)
   - Nanosecond timestamp precision
   - Chronological event ordering
   - Raw JSON persistence
   - Progress monitoring

4. **Market Regime Capture** (2 hours)
   - High volume period (US open)
   - Low volume period (weekend)
   - Special event (if available)

**Success Criteria**:
- [ ] 3x 24-hour captures complete
- [ ] Zero sequence gaps in capture
- [ ] Order book state validated

### Story 1.2.5: Technical Validation Spike 🚨 CRITICAL

**Purpose**: Validate technical feasibility before Epic 2 commitment.

**Technical Tasks**:

1. **Delta Feed Analysis** (4 hours)
   ```python
   # Load book_delta_v2 data
   deltas = load_book_deltas('2024-01-01', '2024-01-02')
   
   # Analyze sequence gaps
   gap_analysis = analyze_update_id_gaps(deltas)
   assert gap_analysis.gap_ratio < 0.001  # <0.1%
   ```

2. **Memory Profiling** (4 hours)
   - Load 1 hour of data (8M events)
   - Monitor memory usage patterns
   - Test on Beelink S12 Pro hardware
   - Implement memory pressure simulation

3. **Throughput Testing** (3 hours)
   ```python
   # Target: 100k events/second
   async def throughput_test():
       events_processed = 0
       start = time.time()
       
       async for event in stream_events():
           await process_event(event)
           events_processed += 1
           
       rate = events_processed / (time.time() - start)
       assert rate >= 100_000
   ```

4. **Decimal128 Validation** (3 hours)
   - Test Polars decimal operations
   - Benchmark vs int64 pips
   - Validate precision preservation
   - Test edge cases (SOL-USDT)

5. **I/O Performance** (2 hours)
   - Measure Parquet read/write speeds
   - Test streaming vs batch loading
   - Validate 220GB monthly processing

**Go/No-Go Decision Criteria**:
- [ ] Delta gap ratio <0.1%
- [ ] Memory usage <24GB P95
- [ ] Throughput ≥100k events/sec
- [ ] Decimal128 working or int64 fallback ready
- [ ] I/O supports 220GB/month

## Architecture Integration Points

### From Epic 0
- Reuse `CryptoLakeAPIClient` for data access
- Leverage `DataDownloader` patterns
- Apply error handling strategies
- Use established test patterns

### For Epic 2
- Validate streaming architecture assumptions
- Confirm memory management approach
- Finalize decimal precision strategy
- Establish performance baselines

## Risk Mitigation

| Risk | Mitigation | Fallback |
|------|------------|----------|
| Origin time >5% missing | Use timestamp field | Vendor clock sync |
| Delta gaps >0.1% | Snapshot reconstruction | Lower fidelity target |
| Memory >24GB | Streaming windows | Larger hardware |
| Throughput <100k/s | Optimize critical path | Batch processing |

## Tooling Requirements

1. **Analysis Tools**
   - Jupyter notebooks for exploration
   - Polars for data processing
   - Matplotlib for visualization

2. **Live Capture**
   - `websockets` library
   - `aiohttp` for REST calls
   - High-precision timing (`time.perf_counter_ns`)

3. **Profiling**
   - `memory_profiler` for memory analysis
   - `py-spy` for performance profiling
   - `pytest-benchmark` for throughput tests

## Testing Strategy

```python
# tests/epic1/
├── test_origin_time_analysis.py
├── test_live_capture.py
├── test_websocket_sync.py
├── test_memory_profiling.py
├── test_throughput.py
└── test_decimal_precision.py
```

## Success Metrics

### Story-Level
- 1.1: Timestamp strategy validated
- 1.2: Golden samples captured
- 1.2.5: Technical feasibility confirmed

### Epic-Level
- All technical risks validated
- Clear Go/No-Go decision
- Architecture updated with findings
- Performance baselines established

## Next Steps

After Epic 1 completion:
1. Update architecture with validated patterns
2. Create Epic 2 detailed design
3. Establish CI/CD for streaming pipeline
4. Plan production deployment strategy

---

**Note**: This action plan incorporates lessons from Epic 0 and insights from the Gemini research on market microstructure. The focus is on validating assumptions with real data before committing to the full reconstruction pipeline.