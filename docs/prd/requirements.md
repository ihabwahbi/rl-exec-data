# Requirements

## Functional Requirements (FR)

### Implemented Features Not Originally Documented
* **WAL (Write-Ahead Logging):** Implemented for crash recovery and data durability. Ensures no data loss during pipeline failures.
* **Memory-Mapped Processing:** Implemented for performance optimization in data loading and processing.
* **Drift Tracking Metrics:** Implemented to monitor and track reconstruction accuracy drift over time.
* **Pipeline State Provider:** Interface abstraction pattern implemented for flexible state management.

* **FR0: Data Acquisition (BLOCKING PREREQUISITE):** The project must establish and maintain access to actual Crypto Lake historical data before any validation or pipeline development can begin. This includes:
    * Secure API access and authentication to Crypto Lake
    * Successful download and verification of at least 1-2 weeks of BTC-USDT `trades` and `book` data
    * Data integrity validation and completeness checks
    * Established procedures for data refresh and updates
    * **SUCCESS CRITERIA**: Project cannot proceed to FR1 without confirmed access to actual historical data
* **FR1: Assumption Validation:** The pipeline must perform an initial analysis on the **actual** Crypto Lake data (not synthetic data) to determine the completeness and reliability of the `origin_time` field for both `trades` and `book` data types for BTC-USDT. A report must be generated detailing the percentage of null/invalid `origin_time` values for each dataset using real data patterns.
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
* **FR6: Automated Fidelity Reporting [PARTIALLY COMPLETE - Foundation Only]:** The pipeline must generate a "Fidelity Report" that quantitatively compares the statistical properties of the reconstructed **actual** historical data stream against the "golden sample" of live data (minimum 24 hours capture). **STATUS**: Validation framework exists but FidelityReporter component not implemented. **EPIC 3 DEPENDENCY**: Full implementation required. **PREREQUISITE**: Both actual historical data processing and live data capture must be completed before fidelity comparison. This report must include:
    * **Distributional Tests** (from research):
        * Kolmogorov-Smirnov tests on trade size, inter-event time, and bid-ask spread distributions
        * Anderson-Darling test for order size distributions
        * Power law validation for trade sizes (exponent 2.4±0.1)
        * > [ASSUMPTION][R-GMN-03] Power law tail validation for returns with α ∈ [2,5]
    * **Microstructure Metrics**:
        * Sequence gap detection and count in order book updates
        * Best bid/ask price RMSE vs golden sample
        * Order book depth correlation at each price level
        * Spread dynamics and mean reversion characteristics
        * > [ASSUMPTION][R-CLD-03] Multi-level spread analysis (L1,L5,L10,L15,L20)
        * > [ASSUMPTION][R-CLD-05] Order Flow Imbalance (OFI) distribution validation
        * > [ASSUMPTION][R-OAI-02] GARCH(1,1) volatility clustering parameters within 10%
    * **Execution Quality Metrics**:
        * Fill rate accuracy within 5% of historical
        * Slippage estimation with R² > 0.8 vs actual market impact
    * **Summary Score**: Overall fidelity score with PASS/FAIL based on p-value > 0.05

## Non-Functional Requirements (NFR)

* **NFR1: Data Fidelity:** The primary goal. The statistical distributions of the reconstructed **actual** historical data stream must pass a Kolmogorov-Smirnov (K-S) test against the live data sample with a p-value > 0.05, indicating no significant statistical difference. **CRITICAL**: This validation must be performed on real Crypto Lake data, not synthetic data.
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
* **NFR7: Data Retention Policy [NOT IMPLEMENTED]:** Unencrypted golden sample data must not persist in RAM longer than active processing time. Implement secure memory wiping after use. Encrypted data retention: 90 days for validation replay, then secure deletion with audit log. **STATUS**: Not implemented or verified in current codebase. **ACTION**: Create explicit story for implementation or remove from requirements.

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
