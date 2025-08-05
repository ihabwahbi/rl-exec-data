# Requirements

## Functional Requirements (FR)


* **FR0: Data Acquisition [COMPLETED ✅]:** Successfully established and maintain access to actual Crypto Lake historical data. This included:
    * Secure API access and authentication to Crypto Lake ✅
    * Successful download and verification of multiple weeks of BTC-USDT `trades` and `book` data ✅
    * Data integrity validation and completeness checks ✅
    * Established procedures for data refresh and updates ✅
    * **STATUS**: COMPLETED - Project has full access to actual historical data
* **FR1: Assumption Validation [COMPLETED ✅]:** The pipeline has performed initial analysis on the **actual** Crypto Lake data to determine the completeness and reliability of the `origin_time` field for both `trades` and `book` data types for BTC-USDT. Reports have been generated detailing data patterns and validation results.
* **FR2: Data Ingestion:** The pipeline must be able to ingest actual historical `trades` and `book` (L2 snapshot) data for a specified symbol (e.g., BTC-USDT) and date range from the Crypto Lake source. **PREREQUISITE**: FR0 must be completed before FR2 implementation begins.
* **FR3: Live Data Capture (Golden Sample):** A separate utility must be created to capture and store "golden samples" of raw, unmodified live market data from the Binance combined WebSocket stream. **CRITICAL**: This must preserve the exact raw message format for validation purposes. Requirements:
    * **Endpoint**: Must use combined stream `/stream?streams=btcusdt@trade/btcusdt@depth@100ms` for guaranteed chronological ordering
    * **Format**: Each captured event must be stored as: `{"capture_ns": <nanosecond_timestamp>, "stream": "<stream_name>", "data": {<original_raw_message>}}`
    * **No Transformation**: Raw WebSocket messages must be preserved exactly as received - no parsing, no field extraction, no reformatting
    * **Market Regimes**: Must capture at least 3 distinct 24-48 hour windows:
        * High volume period (e.g., US market open 14:30-21:00 UTC, major news events)
        * Low volume period (e.g., Asian overnight 02:00-06:00 UTC, weekend)
        * Special event period (e.g., Fed announcement, options expiry, or maintenance window)
* **FR4: Chronological Unification:** Based on the finding in FR1 using actual Crypto Lake data, the pipeline must merge the historical trades and book data into a single, unified event stream, sorted chronologically. **PREREQUISITE**: FR1 must be completed with actual data before unification strategy can be determined.
    * *If delta feed is available (preferred):* Use actual `book_delta_v2` data with full event replay to capture all market microstructure changes. Process deltas in monotonic update_id order, maintaining full order book state.
    * *If `origin_time` is reliable for all events and deltas unavailable:* The primary sort key will be `origin_time`.
    * *If `origin_time` is unreliable for book snapshots:* The pipeline will use the "snapshot-anchored" method, using snapshot timestamps as the primary clock and injecting trades into their respective 100ms windows.
* **FR5: Schema Conformation:** The pipeline's final output must conform to the agreed-upon **Unified Market Event Schema**, which includes event type, timestamp, and event-specific data fields (trade price/qty or book state).
* **FR6: Automated Fidelity Reporting [IN PROGRESS - CURRENT PRIORITY]:** The pipeline must generate a comprehensive "Fidelity Report" using advanced statistical validation methods that go beyond traditional K-S tests. **STATUS**: Validation framework exists, implementation in progress as primary focus. 
    
    **IMPLEMENTATION**: This requirement is fully implemented through the FidelityReporter component, which is responsible for testing all the advanced HFT phenomena detailed in NFR1 and validation-strategy.md. The complete implementation is executed via Epic 3 stories (3.0 through 3.8), which define the specific validation metrics and their implementation approach.
    
    The FidelityReporter validation must use a multi-faceted approach including:
    * **Advanced Statistical Tests** (replacing K-S as primary method):
        * Anderson-Darling tests for tail-sensitive distribution validation (primary test)
        * Cramér-von Mises tests for balanced overall distribution validation
        * Energy Distance for multivariate distribution comparison without dimension reduction
        * Maximum Mean Discrepancy (MMD) with signature kernels for temporal dependencies
        * Power law validation for trade sizes (exponent 2.4±0.1)
        * > [ASSUMPTION][R-GMN-03] Power law tail validation for returns with α ∈ [2,5]
    * **Microstructure Metrics**:
        * Sequence gap detection and count in order book updates
        * Best bid/ask price RMSE vs golden sample
        * Order book depth correlation at each price level (target > 0.99)
        * Spread dynamics and mean reversion characteristics
        * Queue position dynamics and fill time distributions
        * Order Flow Imbalance (OFI) predictive power (R² > 0.1)
        * > [ASSUMPTION][R-CLD-03] Multi-level spread analysis (L1,L5,L10,L15,L20)
        * > [ASSUMPTION][R-CLD-05] Order Flow Imbalance (OFI) distribution validation
        * > [ASSUMPTION][R-OAI-02] GARCH(1,1) volatility clustering parameters within 10%
    * **RL-Specific Metrics**:
        * State-action space coverage (>95% of live states)
        * Reward signal preservation across market regimes (<5% difference)
        * Sim-to-real performance gap measurement (<5% degradation)
        * Multi-regime consistency validation
    * **Adversarial Pattern Detection**:
        * Spoofing frequency matching (±20% of golden samples)
        * Fleeting liquidity preservation (sub-100ms orders)
        * Quote stuffing and market manipulation patterns
    * **Summary Score**: Multi-dimensional pass/fail criteria based on test-specific thresholds, not solely p-value > 0.05

## Non-Functional Requirements (NFR)

* **NFR1: Data Fidelity [CRITICAL - ENHANCED SCOPE]:** The primary goal. The reconstructed **actual** historical data stream must be statistically indistinguishable from live market data using a comprehensive suite of advanced validation methods. Traditional K-S tests are inadequate due to their assumptions of i.i.d. data, insensitivity to tail events, and inability to handle multivariate distributions. 
    
    **CRITICAL SUCCESS CRITERIA**: The validation must employ:
    * Anderson-Darling tests (p-value > 0.05) for tail-sensitive validation of returns
    * Energy Distance (< 0.01 normalized) for multivariate state vector validation
    * MMD with signature kernels for temporal dependency validation
    * Order book correlation > 0.99 at top levels
    * State coverage > 95% for RL applications
    * Sim-to-real performance gap < 5%
    
    **HIGH-FREQUENCY TRADING PHENOMENA PRESERVATION** (as detailed in validation-strategy.md):
    * **Event Clustering & Hawkes Processes**: Preservation of multi-scale intensity peaks (~10μs, 1-5ms), self-exciting dynamics with power-law kernels, super-Poisson clustering (Fano factor > 1), and endogenous activity patterns (80% of trades)
    * **Deep Order Book Dynamics**: Accurate representation of liquidity beyond L20, including predictive power by level (L3-10 strongest for 1-5min horizons), iceberg order signatures (85-90% matching rates), resilience metrics (<20 best limit updates for recovery), and asymmetric deterioration patterns
    * **Adversarial Pattern Signatures**: Statistical presence of quote stuffing (2000+ orders/sec, 32:1 cancellation), spoofing/layering (10-50:1 volume ratios, <500ms cancellations), momentum ignition (complete cycle <5 seconds), and fleeting quotes (sub-100ms lifetimes)
    * **Execution Quality Benchmarks**: Realistic modeling of queue position dynamics (37-49% lower implementation shortfall for first-in-queue), market impact models (square-root law, Kyle's lambda), adverse selection metrics (60%+ passive fills followed by unfavorable moves), and MEV effects
    
    All validation must be performed on real Crypto Lake data, not synthetic data
* **NFR2: Determinism:** The pipeline must be fully deterministic. Given the same input data, it must produce the exact same output event stream every time.
* **NFR3: Performance:** The pipeline must be capable of processing one month of historical BTC-USDT data on the target hardware (Beelink SER9 with 32GB RAM) within a 24-hour period. Memory usage must not exceed 28GB to allow for OS overhead. If delta feeds require more memory, implement streaming chunked processing.
* **NFR4: Configurability:** The pipeline must be configurable to run for different symbols and date ranges without code changes.
* **NFR5: Security:** The pipeline must strip API keys and credentials from all logs. WebSocket capture data must be stored with encryption at rest. No sensitive exchange credentials should be committed to version control.
* **NFR6: Throughput Performance [EXCEEDED]:** The pipeline must sustain ≥100,000 unified events/second throughput on the target hardware (Beelink SER9) to process 8M delta events per hour within the 24-hour SLA for one month of data.
    * **ACHIEVED**: 345,000 messages/second (3.45x requirement)
    * **Memory Usage**: 1.67GB for 8M events (well under 28GB limit)
    * **Checkpoint Overhead**: <1% performance impact verified
    * > [ASSUMPTION][R-ALL-01] Achieve via micro-batching (100-1000 events) for Polars vectorization ✅ VERIFIED
    * > [ASSUMPTION][R-GMN-01] Use scaled int64 arithmetic in performance-critical paths ✅ VERIFIED
* **NFR7: Data Retention Policy [DEFERRED]:** Unencrypted golden sample data must not persist in RAM longer than active processing time. Implement secure memory wiping after use. Encrypted data retention: 90 days for validation replay, then secure deletion with audit log. **STATUS**: Deferred to future "Operational Hardening" epic. This remains a critical requirement for production deployment but is not blocking MVP functionality.
* **NFR8: Pipeline Durability [IMPLEMENTED]:** The pipeline must implement Write-Ahead Logging (WAL) to ensure crash recovery and prevent data loss during processing failures. WAL enables the pipeline to resume from the last consistent state after unexpected termination.
* **NFR9: Memory-Mapped Processing [IMPLEMENTED]:** The pipeline must utilize memory-mapped file I/O for performance optimization in data loading and processing, achieving documented 13x improvement in I/O throughput.
* **NFR10: Drift Tracking [IMPLEMENTED]:** The pipeline must continuously monitor and track reconstruction accuracy drift over time, with configurable thresholds for automated alerts when drift exceeds acceptable limits (default: RMS error > 0.001).
* **NFR11: State Management Abstraction [IMPLEMENTED]:** The pipeline must implement a Pipeline State Provider interface abstraction pattern for flexible state management, enabling different state storage backends without core logic changes.

## Research Assumptions Verification Status

### VERIFIED ✅
* **[R-GMN-01]** Scaled Integer Arithmetic - Implemented and performance validated
* **[R-OAI-01]** Pending Queue Pattern - Implemented in streaming architecture  
* **[R-ALL-01]** Micro-batching - Implemented with 100-1000 event batches

### NOT VERIFIED ❌
* **[R-CLD-01]** Hybrid Delta-Event Sourcing - 40-65% memory reduction not measured
* **[R-CLD-03]** Multi-Level Spread Analysis - Not implemented
* **[R-GMN-03]** Power Law Tail Validation - Not implemented
* **[R-OAI-02]** GARCH Volatility Clustering - Not implemented
