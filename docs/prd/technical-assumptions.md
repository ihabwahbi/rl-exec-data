# Technical Assumptions

## Data Assumptions (Critical)

* **Real Data Prerequisite:** ALL development, testing, and validation must be performed using actual Crypto Lake historical data. Synthetic data should only be used for initial development scaffolding and must be replaced with real data before any validation work begins.
* **Data Acquisition Timeline:** Data acquisition from Crypto Lake is the critical path and must be completed before any other Epic 1 work can proceed. This includes account setup, API access, data download, and verification.
* **Data Quality Unknown:** Until actual Crypto Lake data is analyzed, all assumptions about data quality, completeness, and format are preliminary. The pipeline architecture must be flexible enough to adapt to real data characteristics.

## Architecture Assumptions

* **Repository Structure:** A single Monorepo will be used to house all scripts and modules for the data pipeline project.
* **Service Architecture:** The pipeline will be architected as a series of modular, command-line Python scripts, not a long-running service.
* **Core Language:** Python (version 3.10+).
* **Data Handling & Processing:** The primary libraries will be Polars (for its high-performance, memory-efficient data manipulation) and Pandas/NumPy where appropriate.
* **Data Storage:** The final processed data will be stored as partitioned Parquet files with Zstandard (zstd) compression in a local directory structure (`data/spot_lake/...`). No cloud storage or database is required for this POC.
* **Testing Framework:** Unit and integration tests for the pipeline will be written using `pytest`.
* **Hardware Constraint:** All performance requirements and development must consider the target local hardware (Beelink SER9 with 32GB RAM). Memory usage must not exceed 28GB to allow for OS overhead. Delta feed processing for 1 hour of BTC-USDT data (~8M events) must fit within this constraint or implement streaming/chunking.

## WebSocket Stream Assumptions

* **Combined Stream Requirement:** Binance WebSocket connections must use the combined stream endpoint (`/stream?streams=...`) to ensure chronological ordering of events across different data types (trades and depth).
* **Stream Naming Convention:** The depth stream must use the `@depth@100ms` suffix (not just `@depth`) to match the 100ms snapshot frequency of historical data.
* **Timestamp Precision:** All timestamps must be captured with nanosecond precision using `time.perf_counter_ns()` for accurate latency measurements.
* **Order Book Synchronization:** The order book synchronization protocol (REST snapshot + buffered WebSocket updates) must be implemented exactly as specified in Binance documentation to prevent gaps or inconsistencies.

## Validated Performance Metrics

Based on Epic 1 validation with real data:

* **Memory Usage:** 1.67GB peak for 8M events (14x safety margin vs 24GB constraint)
* **Throughput:** 12.97M events/second achieved (130x above 100k requirement)
* **I/O Performance:** 3.07GB/s write, 7.75GB/s read (20x above 150-200 MB/s requirement)
* **Delta Feed Quality:** 0% sequence gaps in 11.15M messages (perfect quality)
* **Processing Speed:** ~336K messages/second for golden sample analysis

## Implementation Learnings

* **Raw Data Preservation:** Golden samples must preserve exact WebSocket message format without transformation
* **Combined Stream Critical:** Must use combined stream endpoint with proper suffixes (@depth@100ms)
* **Validation-First Approach:** Build validation infrastructure before complex features
* **Streaming Architecture:** Essential for handling multi-GB files without memory issues
* **Delta Feed Reliability:** book_delta_v2 data has exceptional quality, enabling FullReconstruction

## Epic 2 Architecture Assumptions (From Research)

**Note**: These assumptions come from deep research synthesis. Each must be validated empirically in Epic 2 implementation.

> [ASSUMPTION][R-CLD-01] Hybrid Delta-Event Sourcing Architecture improves memory efficiency by 40-65%. Validation: Story 2.1b-perf

> [ASSUMPTION][R-GMN-01] Scaled Integer Arithmetic (int64) for hot path provides significant performance boost vs Decimal128. Validation: Story 2.1b-perf

> [ASSUMPTION][R-OAI-01] Pending Queue Pattern ensures atomic updates during snapshots/transactions. Validation: Story 2.2

> [ASSUMPTION][R-ALL-01] Micro-batching (100-1000 events) optimizes Polars vectorization. Validation: Story 2.1b-perf

> [ASSUMPTION][R-CLD-02] Memory-Mapped Processing provides 13x faster I/O, 60% memory reduction. Validation: Story 2.1b-perf

> [ASSUMPTION][R-GMN-02] Single-Process Per Symbol architecture avoids Python GIL contention. Validation: Story 2.4 (new)

> [ASSUMPTION][R-GMN-04] Hybrid Data Structure (contiguous arrays for top-of-book, hash for deep) optimizes access. Validation: Story 2.2

> [ASSUMPTION][R-OAI-03] Copy-on-Write Checkpointing enables non-blocking state persistence. Validation: Story 2.5 (new)

> [ASSUMPTION][R-CLD-04] Manual GC Control reduces pause times by 20-40%. Validation: Story 2.1b-perf

## Epic 3 Validation Assumptions (From Research)

**Note**: These validation metrics represent convergent findings from all three AI research analyses.

> [ASSUMPTION][R-CLD-03] Multi-Level Spread Analysis (L1,L5,L10,L15,L20) captures market microstructure. Validation: Story 3.1

> [ASSUMPTION][R-GMN-03] Power Law Tail validation expects tail index α ∈ [2,5]. Validation: Story 3.1

> [ASSUMPTION][R-OAI-02] GARCH(1,1) model parameters should match within 10% between golden and reconstructed. Validation: Story 3.1

> [ASSUMPTION][R-CLD-05] Order Flow Imbalance (OFI) is key short-term price movement predictor. Validation: Story 3.1

> [ASSUMPTION][R-GMN-05] Two-Sample K-S Tests with p-value > 0.05 confirm distribution match. Validation: Story 3.3 - **Aligned with ValidationFramework implementation**

> [ASSUMPTION][R-OAI-04] Online Metric Computation provides efficiency for streaming validation. Validation: Story 3.1

> [ASSUMPTION][R-CLD-06] Queue Position Feature improves RL agent training effectiveness. Validation: Story 3.4 (new)

## Epic 3 Advanced Validation Assumptions (From New Research)

**Note**: These assumptions represent convergent findings from the deep research on statistical fidelity validation. Each addresses specific limitations of traditional validation approaches.

### Statistical Test Evolution

> [ASSUMPTION][R-GEM-01] **Anderson-Darling Test Superiority**: The Anderson-Darling test is fundamentally superior to Kolmogorov-Smirnov for financial data due to its enhanced sensitivity to tail events where risk concentrates. Validation: Story 3.1b

> [ASSUMPTION][R-OAI-06] **Cramér-von Mises Omnibus Power**: The C-vM test provides better overall distributional comparison than K-S by integrating squared differences across the entire CDF. Validation: Story 3.1b

> [ASSUMPTION][R-CLD-07] **Energy Distance for Multivariate**: Energy distance enables true multivariate distribution validation without dimensionality reduction, critical for joint market state validation. Validation: Story 3.1b

> [ASSUMPTION][R-ALL-04] **MMD with Signature Kernels**: Maximum Mean Discrepancy using signature kernels captures temporal dependencies that static distribution tests miss entirely. Validation: Story 3.1b

### Microstructure Dynamics

> [ASSUMPTION][R-GEM-02] **Cross-Sectional Dependencies**: Bid-ask movements are correlated in complex patterns that must be validated using cross-sectional tests. Validation: Story 3.1a

> [ASSUMPTION][R-OAI-05] **Copula-Based Joint Validation**: Joint distributions of bid/ask queue sizes require copula methods to validate dependence structures independently of marginals. Validation: Story 3.1a

> [ASSUMPTION][R-GEM-03] **Volatility Clustering Validation**: Autocorrelation of squared returns must be preserved to maintain realistic volatility persistence patterns. Validation: Story 3.1c

> [ASSUMPTION][R-CLD-08] **Order Flow Clustering**: Order arrivals exhibit Hawkes process-like clustering that must be validated through inter-arrival time distributions. Validation: Story 3.1c

> [ASSUMPTION][R-OAI-07] **Intraday Pattern Preservation**: U-shaped volume patterns and time-of-day effects must be validated across different time zones. Validation: Story 3.1c

> [ASSUMPTION][R-CLD-09] **Hausman Test for Microstructure Noise**: The Hausman test provides ultra-fast detection of microstructure noise preservation. Validation: Story 3.1c

### Advanced Microstructure Validation

> [ASSUMPTION][R-OAI-08] **Empirical Copula Tests**: Empirical copula goodness-of-fit tests validate complex non-linear dependencies between price and volume. Validation: Story 3.2

> [ASSUMPTION][R-GEM-04] **Pesaran CD Test**: Cross-sectional dependence across order book levels requires specialized tests like Pesaran CD. Validation: Story 3.2

> [ASSUMPTION][R-CLD-10] **OFI Predictive Power**: Order Flow Imbalance must maintain predictive power for price movements with R² > 0.1. Validation: Story 3.2

> [ASSUMPTION][R-GEM-05] **Hidden Liquidity Validation**: Iceberg orders and hidden liquidity manifest through unexpected fill patterns that must be preserved. Validation: Story 3.2

### RL-Specific Metrics

> [ASSUMPTION][R-CLD-11] **State Coverage Requirement**: RL state space coverage must exceed 95% of live market states to prevent policy blind spots. Validation: Story 3.3

> [ASSUMPTION][R-OAI-09] **Reward Distribution Matching**: Reward distributions must match within 5% across all market regimes to ensure consistent learning. Validation: Story 3.3

> [ASSUMPTION][R-GEM-06] **Sim-to-Real Gap Limit**: The sim-to-real performance gap must remain below 5% for production viability. Validation: Story 3.3

> [ASSUMPTION][R-ALL-05] **Multi-Regime Consistency**: RL performance must be consistent across calm, normal, and volatile market conditions. Validation: Story 3.3

### Adversarial Dynamics

> [ASSUMPTION][R-GEM-07] **Spoofing Frequency Preservation**: Spoofing event frequency must match golden samples within ±20% to maintain realistic adversarial dynamics. Validation: Story 3.4

> [ASSUMPTION][R-CLD-12] **Fleeting Liquidity Distribution**: Sub-100ms order lifetimes must match reality to preserve high-frequency dynamics. Validation: Story 3.4

> [ASSUMPTION][R-OAI-10] **Message Burst Patterns**: Quote stuffing and message rate bursts must be preserved for realistic market stress. Validation: Story 3.4

### Performance Architecture

> [ASSUMPTION][R-GEM-08] **Streaming Validation Throughput**: The streaming validation layer must handle 336K+ messages/second without becoming a bottleneck. Validation: Story 3.5

> [ASSUMPTION][R-CLD-13] **GPU Acceleration Benefits**: GPU acceleration should achieve 100x speedup for computationally intensive tests like MMD. Validation: Story 3.5

> [ASSUMPTION][R-OAI-11] **Linear Scaling**: The distributed validation architecture must scale linearly with additional compute resources. Validation: Story 3.5

## Risk Register

* **Synthetic Data Fallback:** ✅ RESOLVED - Real data acquired and validated
* **Performance Validation:** ✅ RESOLVED - All metrics validated with real data
* **Delta Feed Gaps:** ✅ RESOLVED - 0% gaps confirmed across all market regimes
* **[RISK][R-GMN-06] Polars Decimal128 Instability:** Polars marks Decimal type as unstable with history of regressions. Mitigation: Implement int64 scaled arithmetic as primary approach, Decimal128 as fallback only.
* **[RISK][R-VAL-01] K-S Test Inadequacy:** NEW - Kolmogorov-Smirnov tests fundamentally inadequate for financial time series. Mitigation: Replace with Anderson-Darling and advanced test suite.
* **[RISK][R-VAL-02] Computational Overhead:** NEW - Advanced validation tests may impact throughput. Mitigation: Three-tier architecture with appropriate latency budgets.
* **[RISK][R-VAL-03] Sim-to-Real Gap:** NEW - RL agents may still experience performance degradation. Mitigation: Comprehensive RL-specific validation metrics and <5% gap requirement.
