# Infrastructure and Deployment

## Infrastructure

This project is designed to run entirely on a **local machine**. No cloud infrastructure (e.g., AWS, Azure, GCP) is required for the execution of this data pipeline POC.

  * **Host Machine:** A developer machine meeting the specs of a Beelink SER9 or similar, running Linux, macOS, or Windows with WSL2.
  * **Dependencies:** Python 3.10+ and Poetry for environment management.

## Deployment and Execution

"Deployment" for this project consists of setting up the local development environment. The pipeline is not a service to be deployed but a set of scripts to be executed from the command line.

1.  **Setup:**

      * Clone the Git repository.
      * Install [Poetry](https://python-poetry.org/).
      * Run `poetry install` from the project root. This will create a virtual environment and install all dependencies listed in `pyproject.toml`.
      * Create a `.env` file from the `.env.example` template and populate it with necessary credentials (e.g., AWS keys for Crypto Lake access).

2.  **Execution:**

      * Each stage of the pipeline will be executed via the CLI wrapper scripts. For example:
        ```bash
        # Run the initial data analysis
        poetry run python scripts/run_analysis.py --start-date 2024-01-01 --end-date 2024-01-07

        # Run the full reconstruction and validation pipeline
        poetry run python scripts/run_pipeline.py --start-date 2024-01-01 --end-date 2024-01-31
        ```

## Continuous Integration (CI)

A simple CI pipeline will be set up using **GitHub Actions**. On every push to the repository, the `ci.yml` workflow will:

1.  Set up the Python environment.
2.  Install dependencies using Poetry.
3.  Run a linter (e.g., `ruff`) to check for code style issues.
4.  Run the test suite using `pytest`.

This ensures that code quality and correctness are maintained throughout development.

## Observability and Monitoring

The pipeline implements comprehensive metrics collection for production monitoring:

### Key Metrics Collected

* **Performance Metrics:**
  - Processing throughput (events/second)
  - Peak heap memory usage per component
  - WAL checkpoint frequency and recovery time
  - Streaming mode activation frequency

* **Data Quality Metrics:**
  - Sequence gaps detected and filled per hour
  - Maximum mid-price deviation between vendor snapshot and rebuilt book
  - Clock skew distribution (vendor vs exchange time)
  - Decimal precision loss warnings

* **Microstructure Metrics:**
  - Order book depth distribution over time
  - Update frequency by price level
  - Trade-to-book event ratio

### Metrics Export

Metrics are exported in OpenTelemetry format to enable integration with various monitoring backends:
- Local file export (default): JSON Lines format in `data/metrics/`
- Prometheus push gateway support (optional)
- Custom webhook endpoints for alerting

## Security Requirements

### API Key and Credential Management

* **Storage:** All API keys and credentials must be stored in `.env` files, never in code
* **Access:** Use environment variable loading with validation at startup
* **Logging:** Implement credential scrubbing in all log outputs using regex patterns
* **Git:** `.env` files must be in `.gitignore` with `.env.example` templates

### Data Encryption

* **At Rest:** 
  - Golden sample captures from LiveCapture encrypted using AES-256
  - Encryption keys derived from master key in `.env`
  - Optional full dataset encryption for sensitive deployments

* **In Transit:**
  - WebSocket connections use TLS 1.3
  - No unencrypted data transmission

### Access Control

* **File Permissions:** Output directories restricted to user-only access (700)
* **Process Isolation:** Each component runs with minimal required permissions
* **Audit Trail:** All data access logged with timestamps and component IDs
