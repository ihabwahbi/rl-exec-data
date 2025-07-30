# Tech Stack

This technology stack is selected for performance, simplicity, and its widespread use in data science and engineering, aligning perfectly with the project's requirements.

## Technology Stack Table

| Category | Technology | Version | Purpose | Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **Language** | Python | 3.10+ | Core development language | Industry standard for data science and ML; rich ecosystem of libraries. |
| **Data Processing** | Polars | 0.20+ | High-performance data manipulation | Significantly faster than Pandas for large datasets due to its Rust backend and lazy evaluation, ideal for our data volumes. |
| **Data Processing** | Pandas | 2.2+ | Data manipulation & analysis | Used for compatibility or tasks where its API is more convenient. Polars is preferred for heavy lifting. |
| **Dependency Mgt.** | Poetry | 1.8+ | Dependency management & packaging | Provides robust dependency resolution, virtual environment management, and packaging, superior to `pip` + `requirements.txt` for a structured project. |
| **Testing** | Pytest | 8.2+ | Unit and integration testing | Powerful, flexible, and scalable testing framework for Python. |
| **Logging** | Loguru | 0.7+ | Application logging | Provides simple, powerful, and structured logging out-of-the-box, as seen in the provided reference scripts. |
| **Data Storage** | Parquet | N/A | Efficient columnar data storage | Highly efficient, compressed columnar storage format, perfect for analytical queries and use with Polars/Pandas. |
| **Data Storage** | PyArrow | 15.0+ | Decimal type support | Provides decimal128 type for precise price/quantity storage in Parquet files, preventing float rounding errors. |
| **Data Storage** | RocksDB | 0.9+ | Write-ahead log (WAL) | Embedded key-value store for crash-resistant WAL implementation in Reconstructor. |
| **Networking** | websockets | 12.0+ | WebSocket client | Async WebSocket client for LiveCapture component to connect to Binance streams. |
| **Security** | cryptography | 42.0+ | Data encryption | AES-256 encryption for golden sample data at rest. |
| **Statistics** | scipy | 1.13+ | Statistical analysis | K-S tests and other statistical metrics for FidelityReporter. |
| **Visualization** | matplotlib | 3.8+ | Static plotting | Distribution plots and basic charts for Fidelity Report. |
| **Visualization** | seaborn | 0.13+ | Statistical plots | Enhanced statistical visualizations built on matplotlib. |
| **Visualization** | plotly | 5.20+ | Interactive charts | Interactive HTML charts for detailed microstructure analysis. |
| **Monitoring** | opentelemetry-api | 1.24+ | Metrics export | Standardized metrics format for observability integration. |
| **Execution Env.** | CLI Scripts | N/A | Application architecture | A modular set of command-line scripts provides simplicity and ease of orchestration for this ETL task. No complex framework is needed. |
| **GPU Acceleration** | CUDA | 11.8+ | Tier 2 Fidelity Validation (<1ms) for advanced statistical tests (MMD, etc.) | Required to meet the performance demands of the advanced validation strategy and prevent the fidelity reporting process from becoming a bottleneck. |
| **GPU Acceleration** | RAPIDS | 24.04+ | GPU-accelerated data science libraries | Provides cuDF and cuPy for GPU-accelerated statistical computations, achieving 100x speedup for Anderson-Darling, Energy Distance, and MMD calculations. |
