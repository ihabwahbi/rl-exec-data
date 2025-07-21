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

## **Epic 2: Core Data Reconstruction Pipeline** 🟢 **READY TO START**

*Goal: To build the main ETL pipeline that transforms raw historical data into a high-fidelity, unified event stream, based on the findings from Epic 1.*

**PREREQUISITE**: ✅ All prerequisites met. Epic 1 validation complete with GO decision. 

**Strategy Decision**: Based on the **0% sequence gaps** discovered in the delta feed validation, Epic 2 will implement the **FullReconstruction strategy**. This approach provides maximum fidelity by replaying every order book change event from the `book_delta_v2` data, ensuring the backtesting environment perfectly mirrors live trading conditions. The ValidationFramework will provide continuous quality assurance against the 11.15M golden sample messages.

* **Story 2.1: Implement Data Ingestion & Unification:** Build the core pipeline logic that loads the separate `trades` and `book` data, labels them by type, and merges them into a single chronological stream according to the strategy determined in Epic 1.
* **Story 2.1b: Implement Delta Feed Parser & Order Book Engine:** ✅ Delta feed validated with 0% gaps. Implement parser for `book_delta_v2` data and full order book reconstruction engine. Process deltas in update_id order with sequence gap detection and recovery.
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

**PREREQUISITE**: Epic 3 requires completed Epic 2 pipeline. Note that much of the validation capability has already been built in Story 1.3 (ValidationFramework), which can be leveraged and extended for automated fidelity reporting.

* **Story 3.1: Implement Statistical Fidelity Metrics:** Develop a Python library implementing the full Fidelity Validation Metrics Catalogue from the research:
    * **Order Flow Dynamics**: Trade size distributions, inter-event time distributions
    * **Market State Properties**: Bid-ask spread distributions, top-of-book depth distributions, order book imbalance metrics
    * **Price Return Characteristics**: Volatility clustering (autocorrelation of squared returns), heavy tails of returns (kurtosis > 3)
    * Implement Kolmogorov-Smirnov tests for all distribution comparisons
    * Calculate p-values and establish pass/fail thresholds (p > 0.05)
    * Generate visual comparisons (histograms, Q-Q plots, time series)
* **Story 3.2: Generate Fidelity Report:** Create a script that uses the metrics library from Story 3.1 to generate a standardized "Fidelity Report" in a human-readable format (e.g., Markdown or HTML), including plots and statistical test results.
* **Story 3.3: Integrate Reporting into Pipeline:** Integrate the Fidelity Report generation into the main pipeline script from Epic 2, so that a report is automatically generated upon the successful processing of any new batch of data.
