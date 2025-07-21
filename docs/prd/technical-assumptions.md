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

## Risk Mitigation

* **Synthetic Data Fallback:** ✅ RESOLVED - Real data acquired and validated
* **Performance Validation:** ✅ RESOLVED - All metrics validated with real data
* **Delta Feed Gaps:** ✅ RESOLVED - 0% gaps confirmed across all market regimes
