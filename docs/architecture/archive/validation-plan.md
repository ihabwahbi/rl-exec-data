# Technical Validation Plan - Story 1.2.5

## Executive Summary

This document outlines the comprehensive validation spike required before proceeding to Epic 2. Based on expert review, we must validate two critical assumptions that could cause project failure if incorrect:

1. **Delta feed integrity and throughput capability**
2. **Decimal128 toolchain maturity in Polars**

## Go/No-Go Criteria

**Proceed to Epic 2 only if ALL criteria pass:**

### Delta Feed Validation
- ✅ Sequence gap ratio < 0.1% over 1-hour sample
- ✅ P95 memory usage < 24GB when processing 8M events
- ✅ Sustained throughput ≥ 100,000 events/second
- ✅ Disk I/O can sustain 150-200 MB/s for 24 hours

### Decimal128 Pipeline
- ✅ Polars decimal operations work without fallback to object dtype, OR
- ✅ Int64 pips implementation validated as performant alternative

### If Any Criteria Fail
- Reassess feasibility of -5bp VWAP target
- Consider fallback to SnapshotAnchoredStrategy
- Re-estimate project timeline with architectural changes

## Validation Tasks

### 1. Delta Feed Analysis Script
```python
# scripts/run_delta_spike.py
# Analyzes book_delta_v2 data for specified period
# Output: JSON report with metrics
{
    "total_events": 8234567,
    "sequence_gaps": {
        "count": 42,
        "max_gap": 156,
        "mean_gap": 23.4,
        "gap_ratio_percent": 0.067
    },
    "memory_usage": {
        "peak_gb": 18.3,
        "p95_gb": 16.2,
        "events_per_gb": 506234
    },
    "throughput": {
        "events_per_second": 125000,
        "mb_per_second": 187
    }
}
```

### 2. Decimal128 Pipeline PoC
```python
# notebooks/decimal_pipeline_test.ipynb
# Test operations:
# 1. Load 10GB sample of wide-format snapshots
# 2. Melt to long format with decimal128 columns
# 3. Perform group_by operations
# 4. Join with trades data
# 5. Write and read back from Parquet
# 6. Measure memory usage and performance

# Fallback implementation if decimals fail:
# - Convert to int64 pips (price * 10^8)
# - Benchmark same operations
# - Compare memory and speed
```

### 3. Performance Baseline Harness
```python
# scripts/bench_replay.py
# Usage: poetry run python scripts/bench_replay.py --events 5000000
# Measures:
# - Parse rate (events/sec)
# - Order book update rate
# - Memory allocation pattern
# - GC pressure
# - Disk write throughput
```

### 4. I/O Endurance Analysis
```python
# scripts/analyze_io_requirements.py
# Calculate for 12-month processing:
# - Total read volume: ~6.5TB compressed, ~22TB uncompressed
# - Total write volume: ~8TB unified events
# - Required IOPS for random seeks
# - SSD wear calculation (TBW)
```

### 5. Multi-Regime Golden Sample Plan
Configure LiveCapture for 3 distinct periods:
1. **High Volume**: 2024-03-15 14:30-16:00 UTC (US CPI release)
2. **Low Volume**: 2024-03-17 02:00-06:00 UTC (Sunday Asia)
3. **Special Event**: 2024-03-20 18:00-19:00 UTC (FOMC decision)

Each capture should validate:
- P95 latency < 100ms
- No dropped messages
- Successful encryption and rotation

## Implementation Timeline

### Week 1 (Priority: Delta Validation)
- Day 1-2: Implement delta analysis script
- Day 3: Run on Beelink hardware, analyze results
- Day 4-5: Implement decimal PoC or pips fallback

### Week 2 (Priority: Performance & Decision)
- Day 1-2: Performance harness and I/O analysis
- Day 3: Multi-regime capture setup
- Day 4: Compile results, make Go/No-Go decision
- Day 5: Update architecture based on findings

## Risk Mitigation Strategies

### If Delta Feeds Fail
1. Implement hybrid approach: Use deltas where available, snapshots for gaps
2. Increase snapshot frequency capture to 50ms if vendor supports
3. Adjust -5bp target to -3bp with transparency to stakeholders

### If Decimal128 Fails
1. Implement int64 pips immediately (well-understood pattern)
2. Consider PyArrow compute functions for decimal operations
3. Evaluate DuckDB as alternative processing engine

### If Performance Fails
1. Implement proper streaming with backpressure
2. Consider partitioning by symbol for parallel processing
3. Evaluate Rust implementation for critical path

## Success Metrics

The validation is successful if we can confidently answer:
1. Can we capture complete market microstructure with <0.1% data loss?
2. Can we process 1 month of data in 24 hours on target hardware?
3. Can we maintain decimal precision without performance penalties?
4. Is our architecture resilient to the discovered edge cases?

## Next Steps After Validation

### If Successful
1. Update Story 1.2 to implement validated golden sample approach
2. Begin Epic 2 with FullEventReplayStrategy
3. Set up nightly performance regression tests

### If Partially Successful
1. Document specific constraints discovered
2. Adjust architecture to work within limits
3. Revise project timeline and expectations

### If Failed
1. Emergency architecture review with team
2. Consider alternative data vendors
3. Reassess entire project approach

---

**Remember**: These 2 days of validation can save 2 months of rework. Be thorough, be honest about results, and make data-driven decisions.