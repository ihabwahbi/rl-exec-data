# Requirements

## Functional Requirements (FR)

* **FR0: Data Acquisition (BLOCKING PREREQUISITE):** The project must establish and maintain access to actual Crypto Lake historical data before any validation or pipeline development can begin. This includes:
    * Secure API access and authentication to Crypto Lake
    * Successful download and verification of at least 1-2 weeks of BTC-USDT `trades` and `book` data
    * Data integrity validation and completeness checks
    * Established procedures for data refresh and updates
    * **SUCCESS CRITERIA**: Project cannot proceed to FR1 without confirmed access to actual historical data
* **FR1: Assumption Validation:** The pipeline must perform an initial analysis on the **actual** Crypto Lake data (not synthetic data) to determine the completeness and reliability of the `origin_time` field for both `trades` and `book` data types for BTC-USDT. A report must be generated detailing the percentage of null/invalid `origin_time` values for each dataset using real data patterns.
* **FR2: Data Ingestion:** The pipeline must be able to ingest actual historical `trades` and `book` (L2 snapshot) data for a specified symbol (e.g., BTC-USDT) and date range from the Crypto Lake source. **PREREQUISITE**: FR0 must be completed before FR2 implementation begins.
* **FR3: Live Data Capture:** A separate utility must be created to capture and store "golden samples" of raw, live market data (trades and differential depth updates) from the Binance combined WebSocket stream. Must capture at least 3 distinct 24-hour windows representing different market regimes:
    * High volume period (e.g., US market open, major news events)
    * Low volume period (e.g., Asian overnight, weekend)
    * Special event period (e.g., Fed announcement, options expiry, or maintenance window)
* **FR4: Chronological Unification:** Based on the finding in FR1 using actual Crypto Lake data, the pipeline must merge the historical trades and book data into a single, unified event stream, sorted chronologically. **PREREQUISITE**: FR1 must be completed with actual data before unification strategy can be determined.
    * *If delta feed is available (preferred):* Use actual `book_delta_v2` data with full event replay to capture all market microstructure changes. Process deltas in monotonic update_id order, maintaining full order book state.
    * *If `origin_time` is reliable for all events and deltas unavailable:* The primary sort key will be `origin_time`.
    * *If `origin_time` is unreliable for book snapshots:* The pipeline will use the "snapshot-anchored" method, using snapshot timestamps as the primary clock and injecting trades into their respective 100ms windows.
* **FR5: Schema Conformation:** The pipeline's final output must conform to the agreed-upon **Unified Market Event Schema**, which includes event type, timestamp, and event-specific data fields (trade price/qty or book state).
* **FR6: Automated Fidelity Reporting:** The pipeline must generate a "Fidelity Report" that quantitatively compares the statistical properties of the reconstructed **actual** historical data stream against the "golden sample" of live data (minimum 24 hours capture). **PREREQUISITE**: Both actual historical data processing and live data capture must be completed before fidelity comparison. This report must include:
    * Validation metrics from research (K-S tests on distributions of trade size, inter-event time, and bid-ask spread) comparing real historical vs live data
    * Microstructure parity metrics: sequence gap count, best bid/ask RMS error vs golden sample, per-level depth correlation
    * Live capture latency analysis (95th percentile should be < 100ms)

## Non-Functional Requirements (NFR)

* **NFR1: Data Fidelity:** The primary goal. The statistical distributions of the reconstructed **actual** historical data stream must pass a Kolmogorov-Smirnov (K-S) test against the live data sample with a p-value > 0.05, indicating no significant statistical difference. **CRITICAL**: This validation must be performed on real Crypto Lake data, not synthetic data.
* **NFR2: Determinism:** The pipeline must be fully deterministic. Given the same input data, it must produce the exact same output event stream every time.
* **NFR3: Performance:** The pipeline must be capable of processing one month of historical BTC-USDT data on the target hardware (Beelink SER9 with 32GB RAM) within a 24-hour period. Memory usage must not exceed 28GB to allow for OS overhead. If delta feeds require more memory, implement streaming chunked processing.
* **NFR4: Configurability:** The pipeline must be configurable to run for different symbols and date ranges without code changes.
* **NFR5: Security:** The pipeline must strip API keys and credentials from all logs. WebSocket capture data must be stored with encryption at rest. No sensitive exchange credentials should be committed to version control.
* **NFR6: Throughput Performance:** The pipeline must sustain ≥100,000 unified events/second throughput on the target hardware (Beelink SER9) to process 8M delta events per hour within the 24-hour SLA for one month of data.
* **NFR7: Data Retention Policy:** Unencrypted golden sample data must not persist in RAM longer than active processing time. Implement secure memory wiping after use. Encrypted data retention: 90 days for validation replay, then secure deletion with audit log.
