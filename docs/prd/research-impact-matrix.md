# Research → PRD Impact Matrix

**Generated**: 2025-07-22  
**Sources**: Claude, Gemini, and OpenAI deep research documents

## Overview

This matrix maps valuable insights from the research phase to their impact on the PRD. Each insight is tagged and tracked with validation plans.

## Impact Matrix

| Insight_ID | Source(s) | Section to Update | Tag | Validation Story/Metric | Priority |
|------------|-----------|-------------------|-----|------------------------|----------|
| R-CLD-01 | Claude | Epic 2 - Technical Implementation | [ASSUMPTION] | Story 2.1b-perf | HIGH |
| **Hybrid Delta-Event Sourcing Architecture** | | | Memory efficiency 40-65% reduction claimed | Validation: Memory profiling under Epic 2 Story 2.1b |
| R-GMN-01 | Gemini | Epic 2 - Technical Implementation | [ASSUMPTION] | Story 2.1b-perf | HIGH |
| **Scaled Integer Arithmetic for Hot Path** | | | Performance boost vs Decimal128 in Polars | Validation: Benchmark int64 vs Decimal128 throughput |
| R-OAI-01 | OpenAI | Epic 2 - Technical Implementation | [ASSUMPTION] | Story 2.2 | HIGH |
| **Pending Queue Pattern for Atomicity** | | | Ensures consistent state during snapshots | Validation: Test with synthetic sequence gaps |
| R-ALL-01 | All 3 | Epic 2 - Technical Implementation | [ASSUMPTION] | Story 2.1b-perf | HIGH |
| **Micro-batching for Vectorization** | | | 100-1000 event batches optimize Polars | Validation: Benchmark optimal batch sizes |
| R-CLD-02 | Claude | Epic 2 - Performance | [ASSUMPTION] | Story 2.1b-perf | MEDIUM |
| **Memory-Mapped Processing** | | | 13x faster I/O, 60% memory reduction | Validation: Compare mmap vs standard I/O |
| R-GMN-02 | Gemini | Epic 2 - Architecture | [ASSUMPTION] | Story 2.4 (new) | MEDIUM |
| **Single-Process Per Symbol** | | | Avoids Python GIL contention | Validation: Multi-symbol scaling tests |
| R-CLD-03 | Claude | Epic 3 - Validation | [ASSUMPTION] | Story 3.1 | HIGH |
| **Multi-Level Spread Analysis** | | | Track L1,L5,L10,L15,L20 spreads | Validation: Against golden samples |
| R-GMN-03 | Gemini | Epic 3 - Validation | [ASSUMPTION] | Story 3.1 | HIGH |
| **Power Law Tail Validation** | | | Tail index α ∈ [2,5] expected | Validation: Hill estimator on returns |
| R-OAI-02 | OpenAI | Epic 3 - Validation | [ASSUMPTION] | Story 3.1 | HIGH |
| **GARCH Volatility Clustering** | | | GARCH(1,1) parameters within 10% | Validation: Fit models to golden/reconstructed |
| R-ALL-02 | All 3 | Epic 2 - Edge Cases | [VALIDATED] | Already in PRD | LOW |
| **Sequence Gap Handling** | | | Already addressed (0% gaps found) | No validation needed |
| R-CLD-04 | Claude | Epic 2 - Performance | [ASSUMPTION] | Story 2.1b-perf | MEDIUM |
| **GC Optimization Pattern** | | | 20-40% reduction in pause times | Validation: Profile GC impact |
| R-GMN-04 | Gemini | Epic 2 - Architecture | [ASSUMPTION] | Story 2.2 | MEDIUM |
| **Hybrid Data Structure** | | | O(1) top-of-book, hash for deep | Validation: Profile access patterns |
| R-OAI-03 | OpenAI | Epic 2 - Recovery | [ASSUMPTION] | Story 2.5 (new) | MEDIUM |
| **Copy-on-Write Checkpointing** | | | Non-blocking state persistence | Validation: Checkpoint overhead tests |
| R-CLD-05 | Claude | Epic 3 - Metrics | [ASSUMPTION] | Story 3.1 | HIGH |
| **Order Flow Imbalance (OFI)** | | | Key short-term price predictor | Validation: OFI correlation with price moves |
| R-GMN-05 | Gemini | Epic 3 - Testing | [ASSUMPTION] | Story 3.3 | MEDIUM |
| **Two-Sample K-S Test Suite** | | | p-value > 0.05 for distributions | Validation: Implement and calibrate |
| R-OAI-04 | OpenAI | Epic 3 - Metrics | [ASSUMPTION] | Story 3.1 | HIGH |
| **Online Metric Computation** | | | Streaming calculation efficiency | Validation: Compare vs batch computation |
| R-ALL-03 | All 3 | Technical Assumptions | [ASSUMPTION] | Epic 2 general | HIGH |
| **100k+ events/sec feasible** | | | All cite similar benchmarks | Validation: End-to-end throughput test |
| R-CLD-06 | Claude | Epic 3 - Features | [ASSUMPTION] | Story 3.4 (new) | LOW |
| **Queue Position Feature** | | | For RL agent training | Validation: Feature importance analysis |
| R-GMN-06 | Gemini | Risk Register | [RISK] | N/A | HIGH |
| **Polars Decimal128 Instability** | | | API marked unstable, regressions | Mitigation: Int64 fallback ready |

## Key Insights Summary

### High-Value Convergent Insights (All 3 Sources)
1. **Micro-batching Strategy**: All sources emphasize batching 100-1000 events for Polars vectorization
2. **Sequence Gap Recovery**: All describe similar pending queue patterns (though we have 0% gaps)
3. **100k events/sec Target**: All confirm feasibility with proper optimization

### Architecture Patterns
1. **Claude**: Hybrid Delta-Event Sourcing with memory tiers (hot/warm/cold)
2. **Gemini**: Single-process per symbol to avoid GIL
3. **OpenAI**: Stateful event replayer with atomic updates

### Performance Optimizations
1. **Claude**: Memory-mapped I/O, adaptive batching, GC control
2. **Gemini**: Scaled integers in hot path, contiguous arrays for cache
3. **OpenAI**: Lazy evaluation, zero-copy operations, profiling focus

### Validation Metrics
1. **Claude**: OFI, book pressure, multi-level spreads
2. **Gemini**: Power law tails, K-S tests, confidence intervals
3. **OpenAI**: GARCH models, online computation, visual Q-Q plots

## Rejected/Duplicate Insights

| Insight | Source | Reason for Rejection |
|---------|--------|---------------------|
| AVL/Red-Black Trees | Claude | Over-engineered for our use case |
| Distributed Architecture | Gemini | Premature - single node sufficient |
| Synthetic Data Generation | Multiple | Epic 1 has real data |
| Circuit Breaker Pattern | Claude | Overengineering for offline pipeline |
| Multi-exchange Support | Claude | Out of scope |

## Next Actions

1. Update Epic 2 stories with new performance assumptions
2. Create new Story 2.4 for multi-symbol architecture
3. Create new Story 2.5 for checkpointing mechanism
4. Create new Story 3.4 for RL-specific features
5. Update technical-assumptions.md with all [ASSUMPTION] tags
6. Add Polars Decimal128 risk to risk register