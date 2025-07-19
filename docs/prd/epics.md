# Epics

The work is structured into four logical epics, with Epic 0 (Data Acquisition) as the critical prerequisite that ensures all subsequent work uses real market data.

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

## **Epic 1: Foundational Analysis**

*Goal: To analyze actual Crypto Lake data characteristics and validate technical assumptions before building the reconstruction pipeline.*

**Status**: Ready to start. All stories can now proceed using real Crypto Lake data from Epic 0.
* **Story 1.1: Analyze `origin_time` Completeness:** Write a script to analyze the acquired Crypto Lake data (both `trades` and `book` tables) for BTC-USDT. The script will calculate and report the percentage of rows where `origin_time` is null, zero, or otherwise invalid for each data type. This will provide a definitive answer to our core assumption **using actual data**.
* **Story 1.2: Implement Live Data Capture Utility:** Develop a robust Python script that connects to the Binance combined WebSocket stream for BTC-USDT to capture comprehensive "golden samples":
    * Connect to combined stream: `btcusdt@trade` and `btcusdt@depth@100ms`
    * Save raw, interleaved JSON messages with nanosecond timestamp precision
    * Capture multiple 24-48 hour windows representing different market regimes:
        - High volume/volatility periods (US market open, major news)
        - Low volume periods (Asian overnight, weekends)
        - Special events (Fed announcements, options expiry)
    * Implement proper order book initialization using REST snapshot + WebSocket sync
    * Validate chronological ordering and sequence integrity
    * These golden samples will serve as ground truth for fidelity validation
* **Story 1.2.5: Delta Feed & Technical Viability Validation:** Comprehensive technical validation spike using actual Crypto Lake data to de-risk Epic 2 implementation:
    * Analyze actual `book_delta_v2` data quality: sequence gaps, completeness, update frequency
    * Memory profiling: Process 1 hour of actual data (8M events) on Beelink, must stay under 24GB P95
    * Throughput testing: Validate ≥100k events/second sustained performance on real data
    * Decimal128 pipeline PoC: Test Polars decimal operations at scale with actual price data, implement int64 pips fallback if needed
    * I/O analysis: Measure disk read/write throughput for actual 1 month of data (220GB uncompressed)
    * Create performance baseline harness for ongoing monitoring using real data patterns
    * **Go/No-Go Gate**: If gap ratio >0.1% or memory >24GB, must reassess strategy and -5bp target
* **Story 1.3: Initial Comparative Analysis & Data Profiling:** Write a comprehensive analysis script based on the research methodology to:
    * Profile actual Crypto Lake data structure (trades table, book snapshots, delta feeds if available)
    * Capture multiple "golden samples" from Binance live data (different market regimes)
    * Perform statistical comparison using the full fidelity metrics catalogue:
        - Trade size distributions, inter-event time distributions
        - Bid-ask spread distributions, top-of-book depth distributions
        - Order book imbalance metrics, volatility clustering analysis
        - Heavy tails of returns (kurtosis analysis)
    * Run Kolmogorov-Smirnov tests on all distributions
    * Identify specific gaps between historical and live data formats
    * Document reconstruction requirements to maximize fidelity

## **Epic 2: Core Data Reconstruction Pipeline**

*Goal: To build the main ETL pipeline that transforms raw historical data into a high-fidelity, unified event stream, based on the findings from Epic 1.*

**PREREQUISITE**: Epic 2 cannot begin until Epic 1 is fully complete with actual Crypto Lake data acquisition and validation. All Epic 2 development must be based on real data patterns discovered in Epic 1.

* **Story 2.1: Implement Data Ingestion & Unification:** Build the core pipeline logic that loads the separate `trades` and `book` data, labels them by type, and merges them into a single chronological stream according to the strategy determined in Epic 1.
* **Story 2.1b: Implement Delta Feed Parser & Order Book Engine:** If Story 1.2.5 validates delta feed viability, implement parser for `book_delta_v2` data and full order book reconstruction engine. Process deltas in update_id order with proper sequence gap handling.
* **Story 2.2: Implement Stateful Event Replayer & Schema Normalization:** Develop the Chronological Event Replay algorithm as defined in the research:
    * Build stateful replayer that maintains market state in memory
    * Initialize order book from first snapshot encountered
    * Apply trade events to update book state (liquidity consumption)
    * Use periodic snapshots for validation and drift measurement
    * Implement resynchronization logic to correct accumulated drift
    * Transform events into Unified Market Event Schema with proper nullable fields
    * Track and report book drift metrics for quality assurance
* **Story 2.3: Implement Data Sink:** Write the final stage of the pipeline, which saves the processed unified event stream into partitioned Parquet files with decimal128(38,18) precision for price/quantity fields, optimized for efficient reading by the backtesting environment.

## **Epic 3: Automated Fidelity Validation & Reporting**

*Goal: To build the automated quality assurance framework that proves the backtesting data is a faithful replica of the live market.*

**PREREQUISITE**: Epic 3 requires completed Epic 2 pipeline processing actual Crypto Lake data. All fidelity validation must compare real historical data against live market data, not synthetic data.

* **Story 3.1: Implement Statistical Fidelity Metrics:** Develop a Python library implementing the full Fidelity Validation Metrics Catalogue from the research:
    * **Order Flow Dynamics**: Trade size distributions, inter-event time distributions
    * **Market State Properties**: Bid-ask spread distributions, top-of-book depth distributions, order book imbalance metrics
    * **Price Return Characteristics**: Volatility clustering (autocorrelation of squared returns), heavy tails of returns (kurtosis > 3)
    * Implement Kolmogorov-Smirnov tests for all distribution comparisons
    * Calculate p-values and establish pass/fail thresholds (p > 0.05)
    * Generate visual comparisons (histograms, Q-Q plots, time series)
* **Story 3.2: Generate Fidelity Report:** Create a script that uses the metrics library from Story 3.1 to generate a standardized "Fidelity Report" in a human-readable format (e.g., Markdown or HTML), including plots and statistical test results.
* **Story 3.3: Integrate Reporting into Pipeline:** Integrate the Fidelity Report generation into the main pipeline script from Epic 2, so that a report is automatically generated upon the successful processing of any new batch of data.
