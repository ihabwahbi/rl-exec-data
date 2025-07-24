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
| R-CLD-06 | Claude | Epic 3 - Features | [ASSUMPTION] | Story 3.4 (old) | LOW |
| **Queue Position Feature** | | | For RL agent training | Validation: Feature importance analysis |
| R-GMN-06 | Gemini | Risk Register | [RISK] | N/A | HIGH |
| **Polars Decimal128 Instability** | | | API marked unstable, regressions | Mitigation: Int64 fallback ready |

## Epic 3 Advanced Validation Insights (From New Research)

| Insight_ID | Source(s) | Section to Update | Tag | Validation Story/Metric | Priority |
|------------|-----------|-------------------|-----|------------------------|----------|
| R-GEM-01 | Gemini | Epic 3 - Story 3.1b | [ASSUMPTION] | Story 3.1b | CRITICAL |
| **Anderson-Darling Test Superiority** | | | Replaces K-S for tail sensitivity | Validation: Compare p-values on extreme events |
| R-OAI-06 | OpenAI | Epic 3 - Story 3.1b | [ASSUMPTION] | Story 3.1b | HIGH |
| **Cramér-von Mises Omnibus Power** | | | Better overall distribution test | Validation: Benchmark vs K-S power |
| R-CLD-07 | Claude | Epic 3 - Story 3.1b | [ASSUMPTION] | Story 3.1b | CRITICAL |
| **Energy Distance for Multivariate** | | | True multivariate validation | Validation: Joint state vector testing |
| R-ALL-04 | All 3 | Epic 3 - Story 3.1b | [ASSUMPTION] | Story 3.1b | CRITICAL |
| **MMD with Signature Kernels** | | | Captures temporal dependencies | Validation: Volatility clustering detection |
| R-GEM-02 | Gemini | Epic 3 - Story 3.1a | [ASSUMPTION] | Story 3.1a | HIGH |
| **Cross-Sectional Dependencies** | | | Bid-ask correlated movements | Validation: Cross-correlation analysis |
| R-OAI-05 | OpenAI | Epic 3 - Story 3.1a | [ASSUMPTION] | Story 3.1a | HIGH |
| **Copula-Based Joint Validation** | | | Queue size dependencies | Validation: Empirical copula fitting |
| R-GEM-03 | Gemini | Epic 3 - Story 3.1c | [ASSUMPTION] | Story 3.1c | HIGH |
| **Volatility Clustering Validation** | | | Squared return autocorrelation | Validation: ACF comparison |
| R-CLD-08 | Claude | Epic 3 - Story 3.1c | [ASSUMPTION] | Story 3.1c | HIGH |
| **Order Flow Clustering** | | | Hawkes process characteristics | Validation: Inter-arrival distributions |
| R-OAI-07 | OpenAI | Epic 3 - Story 3.1c | [ASSUMPTION] | Story 3.1c | MEDIUM |
| **Intraday Pattern Preservation** | | | U-shaped volume patterns | Validation: Time-of-day analysis |
| R-CLD-09 | Claude | Epic 3 - Story 3.1c | [ASSUMPTION] | Story 3.1c | HIGH |
| **Hausman Test for Noise** | | | Ultra-fast noise detection | Validation: <1μs performance |
| R-OAI-08 | OpenAI | Epic 3 - Story 3.2 | [ASSUMPTION] | Story 3.2 | HIGH |
| **Empirical Copula Tests** | | | Price-volume dependencies | Validation: Goodness-of-fit tests |
| R-GEM-04 | Gemini | Epic 3 - Story 3.2 | [ASSUMPTION] | Story 3.2 | HIGH |
| **Pesaran CD Test** | | | Cross-sectional dependence | Validation: Order book correlations |
| R-CLD-10 | Claude | Epic 3 - Story 3.2 | [ASSUMPTION] | Story 3.2 | CRITICAL |
| **OFI Predictive Power** | | | R² > 0.1 for price prediction | Validation: Regression analysis |
| R-GEM-05 | Gemini | Epic 3 - Story 3.2 | [ASSUMPTION] | Story 3.2 | MEDIUM |
| **Hidden Liquidity Validation** | | | Iceberg order detection | Validation: Fill pattern analysis |
| R-CLD-11 | Claude | Epic 3 - Story 3.3 | [ASSUMPTION] | Story 3.3 | CRITICAL |
| **State Coverage Requirement** | | | >95% coverage of live states | Validation: Energy distance metric |
| R-OAI-09 | OpenAI | Epic 3 - Story 3.3 | [ASSUMPTION] | Story 3.3 | CRITICAL |
| **Reward Distribution Matching** | | | <5% difference across regimes | Validation: P&L distribution tests |
| R-GEM-06 | Gemini | Epic 3 - Story 3.3 | [ASSUMPTION] | Story 3.3 | CRITICAL |
| **Sim-to-Real Gap Limit** | | | <5% performance degradation | Validation: Policy backtesting |
| R-ALL-05 | All 3 | Epic 3 - Story 3.3 | [ASSUMPTION] | Story 3.3 | HIGH |
| **Multi-Regime Consistency** | | | Performance across volatility | Validation: Regime-specific testing |
| R-GEM-07 | Gemini | Epic 3 - Story 3.4 | [ASSUMPTION] | Story 3.4 | HIGH |
| **Spoofing Frequency Preservation** | | | ±20% of golden sample | Validation: ML detection comparison |
| R-CLD-12 | Claude | Epic 3 - Story 3.4 | [ASSUMPTION] | Story 3.4 | HIGH |
| **Fleeting Liquidity Distribution** | | | Sub-100ms order lifetimes | Validation: Lifetime histograms |
| R-OAI-10 | OpenAI | Epic 3 - Story 3.4 | [ASSUMPTION] | Story 3.4 | MEDIUM |
| **Message Burst Patterns** | | | Quote stuffing preservation | Validation: Rate spike detection |
| R-GEM-08 | Gemini | Epic 3 - Story 3.5 | [ASSUMPTION] | Story 3.5 | CRITICAL |
| **Streaming Validation Throughput** | | | 336K+ msg/s capability | Validation: Load testing |
| R-CLD-13 | Claude | Epic 3 - Story 3.5 | [ASSUMPTION] | Story 3.5 | HIGH |
| **GPU Acceleration Benefits** | | | 100x speedup for MMD | Validation: Benchmark vs CPU |
| R-OAI-11 | OpenAI | Epic 3 - Story 3.5 | [ASSUMPTION] | Story 3.5 | HIGH |
| **Linear Scaling** | | | Distributed architecture | Validation: Multi-node testing |

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

### Epic 3 Validation Revolution Summary

#### Critical Paradigm Shifts
1. **K-S Test Replacement**: All three sources emphasize K-S test inadequacy for financial data
   - Anderson-Darling for tail sensitivity (critical for risk)
   - Energy Distance for multivariate validation
   - MMD with signature kernels for temporal patterns

2. **Microstructure Fidelity**: Beyond simple distributions to complex dynamics
   - Copula methods for non-linear dependencies
   - Cross-sectional tests for order book correlations
   - Adversarial pattern preservation (spoofing, fleeting liquidity)

3. **RL-Specific Validation**: New category of metrics entirely
   - State-action coverage requirements (>95%)
   - Reward signal preservation across regimes
   - Sim-to-real gap quantification (<5%)

4. **Performance Architecture**: Three-tier validation system
   - Tier 1: <1μs streaming tests
   - Tier 2: <1ms GPU-accelerated tests
   - Tier 3: <100ms comprehensive analysis

#### Impact on Epic 3
- Story count increased from 5 to 11 stories
- Timeline expanded from ~20 days to ~40-45 days
- Fundamental shift from basic statistical tests to comprehensive validation suite
- Strong emphasis on preventing catastrophic sim-to-real gaps

## Next Actions

1. ✅ Update Epic 3 stories with advanced validation framework
2. ✅ Enhance validation-strategy.md with multi-faceted approach
3. ✅ Add Epic 3 Advanced Validation Assumptions to technical-assumptions.md
4. ✅ Update research-impact-matrix.md with new insights
5. ✅ Add new validation risks to risk register
6. Create changelog entry documenting all updates