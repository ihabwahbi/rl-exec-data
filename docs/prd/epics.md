# Epics

> **📌 MASTER DOCUMENT**: This is the definitive source of truth for project scope and sequencing. All other PRD documents must align with the plan detailed here.

**CURRENT STATUS**: Epics 0-2 are COMPLETE. Epic 3 (Automated Fidelity Validation & Reporting) is the current primary focus, aligned with our primary goal of achieving high-fidelity validation.

The work is structured into four logical epics, progressing from data acquisition through validation:

## **Epic 0: Data Acquisition** ✅ **COMPLETE**

*Goal: To establish access to actual Crypto Lake historical data and build a robust acquisition pipeline.*

**Status**: Successfully completed. Pipeline implemented with lakeapi integration, comprehensive testing (49% coverage), and real data validation.

**Completed Story 0.1: Implement Data Acquisition Pipeline**
- ✅ Crypto Lake API authentication working with lakeapi package
- ✅ Downloaded and validated 2.3M+ trade records  
- ✅ CLI interface with 6 commands (test-connection, list-inventory, download, validate, status, certify)
- ✅ Comprehensive test suite with 44/45 tests passing
- ✅ End-to-end pipeline tested and production-ready

**Key Achievements**:
- Connection verified: 946,485+ trade rows accessible
- Data availability confirmed: 3.3M trades, 2M book, 102M book_delta_v2 rows
- Download performance: 34.3 MB/s
- Schema validation: Proper 8-column structure with realistic BTC-USDT data

## **Epic 1: Foundational Analysis** ✅ **COMPLETE**

*Goal: To analyze actual Crypto Lake data characteristics and validate technical assumptions before building the reconstruction pipeline.*

**Status**: All 5 stories complete with exceptional results. Ready for Epic 2.
* **Story 1.1: Analyze `origin_time` Completeness:** ✅ **COMPLETE** - Validated with 2.3M real records showing 0% invalid origin_time values. Origin time is 100% reliable for chronological ordering.
* **Story 1.2: Implement Live Data Capture Utility:** ✅ **COMPLETE** - Fixed critical issues and now operational, capturing ~969 messages/minute with proper raw data preservation and @100ms depth stream.
* **Story 1.2.1: Capture Production Golden Samples:** ✅ **COMPLETE** - Successfully captured 11.15M messages across three market regimes (high volume: 5.5M, low volume: 2.8M, special event: 2.8M) with <0.01% gaps.
* **Story 1.3: Implement Core Validation Framework:** ✅ **COMPLETE** - Built comprehensive validation framework with 91% test coverage, streaming support for large files, and statistical validators (K-S tests, power law, sequence gaps).
* **Story 1.2.5: Delta Feed & Technical Viability Validation:** ✅ **COMPLETE** - Comprehensive technical validation spike confirmed all assumptions:
    * ✅ **Critical Discovery**: Delta feed has **0% sequence gaps** in all 11.15M golden sample messages
    * ✅ Memory profiling: 1.67GB peak for 8M events (14x safety margin vs 24GB limit)
    * ✅ Throughput testing: 12.97M events/sec achieved (130x above 100k requirement)
    * ✅ Decimal128 pipeline: Validated as primary approach, int64 pips as fallback
    * ✅ I/O analysis: 3.07GB/s write, 7.75GB/s read (20x above requirements)
    * ✅ Performance baseline: Created with OpenTelemetry metrics export
    * ✅ Processing performance: ~336K messages/second for golden sample analysis
    * ✅ **GO Decision**: Perfect delta quality enables FullReconstruction strategy

**Epic 1 Key Achievements:**
- Origin time 100% reliable (0% invalid) - enables chronological ordering
- Golden samples: 11.15M messages captured with exceptional quality
- Validation framework: 91% test coverage, production-ready
- Performance: 13M events/sec throughput (130x requirement)
- Memory: 1.67GB for 8M events (14x safety margin)
- **Perfect delta feed quality: 0% sequence gaps** - enables maximum fidelity reconstruction

## **Epic 2: Core Data Reconstruction Pipeline** ✅ **COMPLETE**

*Goal: To build the main ETL pipeline that transforms raw historical data into a high-fidelity, unified event stream, based on the findings from Epic 1.*

**Status**: Successfully completed. All 6 stories implemented with comprehensive testing and QA approval.

**Strategy Implementation**: The **FullReconstruction strategy** has been successfully implemented using the `book_delta_v2` data with 0% sequence gaps. The pipeline achieves 336-345K messages/second throughput with bounded memory usage and comprehensive checkpointing.

**Key Achievements**:
- Data ingestion handles trades, book snapshots, and deltas with micro-batching
- Order book engine maintains L2 state with sequence validation
- ChronologicalEventReplay algorithm working with drift tracking
- Parquet output with decimal128(38,18) precision
- Multi-symbol processing with linear scaling
- Copy-on-write checkpointing ensures crash recovery

* ✅ **Story 2.1: Implement Data Ingestion & Unification:** Successfully implemented with 336K+ msg/s throughput. Micro-batching with 1GB memory limits working correctly.
    * ✅ [ASSUMPTION][R-ALL-01] Micro-batching validated with 100-1000 event batches
* ✅ **Story 2.1b: Implement Delta Feed Parser & Order Book Engine:** Fully implemented achieving 345K+ msg/s. L2 order book state maintenance with 0% sequence gaps.
    * ✅ [ASSUMPTION][R-CLD-01] Hybrid architecture implemented (actual efficiency gains to be measured)
    * ✅ [ASSUMPTION][R-GMN-01] Scaled int64 arithmetic implemented for performance
    * ✅ [ASSUMPTION][R-CLD-02] Memory-mapped processing achieved 13x improvement
    * ✅ [ASSUMPTION][R-CLD-04] Manual GC control implemented with configurable intervals
* ✅ **Story 2.2: Implement Stateful Event Replayer & Schema Normalization:** ChronologicalEventReplay algorithm fully operational with drift tracking.
    * ✅ [ASSUMPTION][R-OAI-01] Pending queue pattern implemented
    * ✅ [ASSUMPTION][R-GMN-04] Hybrid data structure in use (arrays + hash maps)
    * ✅ All event types handled with proper schema normalization
    * ✅ Drift tracking with RMS error threshold of 0.001
* ✅ **Story 2.3: Implement Data Sink:** Parquet writer with atomic operations and manifest tracking complete.
    * ✅ Decimal128(38,18) precision maintained throughout
    * ✅ Hourly partitioning with 100-500MB file sizes
* ✅ **Story 2.4: Multi-Symbol Architecture:** Process-per-symbol architecture working with linear scaling.
    * ✅ [ASSUMPTION][R-GMN-02] GIL avoidance validated with process isolation
* ✅ **Story 2.5: Checkpointing & Recovery:** COW checkpointing operational with <100ms snapshots.
    * ✅ [ASSUMPTION][R-OAI-03] Non-blocking persistence validated with <1% performance impact

## **Epic 3: Automated Fidelity Validation & Reporting** 🔴 **CURRENT PRIORITY - IN PROGRESS**

*Goal: To build the automated quality assurance framework that proves the backtesting data is a faithful replica of the live market. This is the critical deliverable for achieving our primary goal of high-fidelity validation.*

**PREREQUISITE**: ✅ Epic 2 pipeline complete. The ValidationFramework from Story 1.3 provides a strong foundation with K-S tests, power law validation, and streaming support that can be extended for comprehensive fidelity reporting.

**CRITICAL CONTEXT**: Epic 2 review revealed FidelityReporter component needs to be built from scratch. The validation framework foundation from Epic 1 provides a strong starting point, but full implementation is required. This epic represents the core value delivery for the project.

### Updated Story List

* **Story 3.0: FidelityReporter Foundation [BLOCKING - FIRST PRIORITY]:** Implement the base FidelityReporter component that forms the foundation for all validation:
    * Build pluggable metric architecture  
    * Create streaming and batch computation support
    * Implement report generation framework (HTML/PDF/Dashboard)
    * Integrate with existing pipeline components
    * Performance target: <5% overhead when enabled
    * Estimated effort: 5 days

* **Story 3.1a: Core Microstructure Metrics [REPLACES PART OF 3.1]:** Implement essential market microstructure metrics:
    * **Order Flow Dynamics**: Trade size distributions, inter-event time distributions
    * > [ASSUMPTION][R-CLD-05] Implement Order Flow Imbalance (OFI) as key price movement predictor
    * > [ASSUMPTION][R-GEM-02] Validate cross-sectional dependencies including bid-ask correlated movements
    * **Market State Properties**: Bid-ask spread distributions, top-of-book depth distributions, order book imbalance metrics
    * > [ASSUMPTION][R-CLD-03] Implement multi-level spread analysis (L1,L5,L10,L15,L20)
    * > [ASSUMPTION][R-OAI-05] Validate joint distributions of bid/ask queue sizes using copula methods
    * **Kyle's Lambda**: Price impact coefficient for execution cost modeling
    * **Queue Position Dynamics**: Validate inferred queue position accuracy and fill time distributions
    * **Basic Distributions**: Inter-arrival times, trade size distributions
    * Estimated effort: 4 days

* **Story 3.1b: Advanced Statistical Tests [ENHANCED]:** Replace K-S test with superior alternatives:
    * **Anderson-Darling Test**: Primary test for tail-sensitive distribution validation
    * > [ASSUMPTION][R-GEM-01] Anderson-Darling test superior to K-S for tail events, critical for risk management
    * **Cramér-von Mises Test**: For balanced overall distribution validation
    * > [ASSUMPTION][R-OAI-06] C-vM test provides better omnibus power than K-S
    * **Energy Distance**: For multivariate state vector validation
    * > [ASSUMPTION][R-CLD-07] Energy distance validates joint distributions without dimension reduction
    * **Maximum Mean Discrepancy (MMD)**: For detecting any distributional differences
    * > [ASSUMPTION][R-ALL-04] MMD with signature kernels captures temporal dependencies
    * Calculate p-values and establish pass/fail thresholds appropriate to each test
    * Estimated effort: 5 days

* **Story 3.1c: Temporal Dynamics & Stylized Facts [NEW]:** Validate critical temporal patterns:
    * **Volatility Clustering**: Validate autocorrelation of squared returns
    * > [ASSUMPTION][R-GEM-03] Implement autocorrelation tests for volatility persistence patterns
    * **Order Flow Clustering**: Validate bursty behavior and Hawkes process characteristics
    * > [ASSUMPTION][R-CLD-08] Validate order arrival clustering via inter-arrival time distributions
    * **Multi-Scale Intensity Peaks**: Ensure the reconstruction preserves multi-scale intensity peaks (~10µs, 1-5ms) characteristic of Hawkes processes in crypto markets
    * **Intraday Seasonality**: U-shaped volume patterns, spread variations
    * > [ASSUMPTION][R-OAI-07] Implement intraday pattern validation across time zones
    * **Microstructure Noise**: Implement Hausman test for noise detection
    * > [ASSUMPTION][R-CLD-09] Use Hausman test to validate microstructure noise preservation
    * **Order Book Resilience**: Measure book recovery after large trades
    * Estimated effort: 4 days

* **Story 3.2: Multi-Dimensional Microstructure Validation [NEW]:** Implement validation of complex market dynamics:
    * **Copula-Based Tests**: Validate dependence structures between price and volume
    * > [ASSUMPTION][R-OAI-08] Implement empirical copula goodness-of-fit tests
    * **Cross-Sectional Dependencies**: Validate correlations across order book levels
    * > [ASSUMPTION][R-GEM-04] Use Pesaran CD test for cross-sectional dependence
    * **Deep Book Imbalance Analysis**: Validate that deep-book imbalances retain their predictive power for short-term price movements
    * **Order Book Imbalance Predictive Power**: Validate OFI regression coefficients
    * > [ASSUMPTION][R-CLD-10] OFI should predict short-term price movements with R² > 0.1
    * **Hidden Liquidity Detection**: Validate iceberg order effects through slippage analysis
    * > [ASSUMPTION][R-GEM-05] Validate hidden liquidity via unexpected fill patterns
    * Estimated effort: 5 days

* **Story 3.3: RL-Specific Fidelity Metrics [NEW]:** Validate sim-to-real transfer for RL agents:
    * **State-Action Coverage**: Compare state visitation frequencies using energy distance
    * > [ASSUMPTION][R-CLD-11] State space coverage must exceed 95% of live states
    * **Reward Signal Preservation**: Validate P&L distributions across market regimes
    * > [ASSUMPTION][R-OAI-09] Reward distributions must match within 5% across regimes
    * **Sim-to-Real Gap Quantification**: Measure policy performance degradation
    * > [ASSUMPTION][R-GEM-06] Sim-to-real performance gap must be < 5%
    * **Multi-Regime Validation**: Test across calm, normal, and volatile market conditions
    * > [ASSUMPTION][R-ALL-05] Performance consistency required across all market regimes
    * Estimated effort: 5 days

* **Story 3.4: Adversarial Dynamics Detection [NEW]:** Validate preservation of adversarial patterns:
    * **Spoofing Detection**: Identify rapid order placement/cancellation patterns
    * > [ASSUMPTION][R-GEM-07] Spoofing frequency must match golden sample ±20%
    * **Fleeting Liquidity**: Validate sub-100ms order lifetime distributions
    * > [ASSUMPTION][R-CLD-12] Fleeting order percentage must match reality
    * **Fleeting Quotes Validation**: Confirm the presence of fleeting quotes with sub-100ms lifetimes and realistic order-to-trade ratios during simulated quote stuffing events
    * **Quote Stuffing**: Detect message rate bursts and volatility spikes
    * > [ASSUMPTION][R-OAI-10] Message burst patterns must be preserved
    * **Market Manipulation Patterns**: Validate layering and momentum ignition
    * Estimated effort: 4 days

* **Story 3.5: High-Performance Validation Architecture [NEW]:** Implement scalable validation pipeline:
    * **Tier 1 Streaming Tests**: <1μs latency tests (Hausman, basic filters)
    * > [ASSUMPTION][R-GEM-08] Streaming layer must handle 336K+ msg/s
    * **Tier 2 GPU-Accelerated Tests**: <1ms tests (Anderson-Darling, Energy Distance)
    * > [ASSUMPTION][R-CLD-13] GPU acceleration achieves 100x speedup for MMD
    * **Tier 3 Comprehensive Tests**: <100ms tests (signature MMD, copulas)
    * > [ASSUMPTION][R-OAI-11] Distributed architecture scales linearly
    * **Real-time Dashboard**: Live fidelity monitoring and alerting
    * Estimated effort: 6 days

* **Story 3.6: Generate Comprehensive Fidelity Report [ENHANCED]:** Create sophisticated reporting:
    * Use metrics from all validation stories (3.1a-3.5)
    * Generate multi-dimensional visualizations (heatmaps, Q-Q plots, correlation matrices)
    * Produce executive summary with pass/fail recommendations
    * Include detailed technical appendix with all test results
    * Support HTML, PDF, and real-time dashboard formats
    * Estimated effort: 3 days

* **Story 3.7: Integrate Validation Pipeline [ENHANCED]:** Full integration with main pipeline:
    * Implement circuit breaker to halt processing on validation failure
    * Add configurable validation levels (light, standard, comprehensive)
    * Support both streaming and batch validation modes
    * Integrate with existing monitoring and alerting systems
    * Performance target: <5% overhead in standard mode
    * Estimated effort: 4 days

* **Story 3.8: Research Validation Suite [ORIGINAL]:** Validate all research assumptions and measure actual vs. claimed benefits:
    * Measure statistical test improvements over K-S baseline
    * Validate GPU acceleration performance gains
    * Document effectiveness of each new validation metric
    * Generate comprehensive research validation report
    * Estimated effort: 3 days

### Epic 3 Summary

**Original Estimate**: ~10-15 days  
**Initial Revision**: ~20-25 days (2x increase)  
**Deep Research Revision**: ~40-45 days (4x original)  
**Critical Path**: Story 3.0 → Stories 3.1a/b/c → Story 3.2 → Story 3.3 → Story 3.5 → Stories 3.6/3.7  
**Parallel Work**: Stories 3.4 and 3.8 can run in parallel after core metrics complete

**Key Enhancements from Research**:
- Replacing K-S tests with Anderson-Darling, Energy Distance, and MMD
- Adding comprehensive microstructure validation including copulas and cross-sectional tests
- RL-specific metrics to prevent sim-to-real gaps
- Adversarial pattern detection to ensure realistic market dynamics
- High-performance architecture with GPU acceleration and streaming tiers
- Sophisticated multi-dimensional reporting and visualization
