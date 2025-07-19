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

## Risk Mitigation

* **Synthetic Data Fallback:** If actual Crypto Lake data cannot be acquired within the first week, project timeline must be extended or scope reduced. No validation work should proceed without real data.
* **Performance Validation:** All performance testing conducted on synthetic data is considered preliminary and must be re-validated with actual data patterns.
