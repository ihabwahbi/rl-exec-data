# Infrastructure and Deployment

**Last Updated**: 2025-07-31  
**Status**: Refined to focus on infrastructure, deployment, and operations

## Infrastructure

This project is designed to run entirely on a **local machine**. No cloud infrastructure (e.g., AWS, Azure, GCP) is required for the execution of this data pipeline POC.

  * **Host Machine:** A developer machine meeting the specs of a Beelink SER9 or similar, running Linux, macOS, or Windows with WSL2.
  * **Dependencies:** Python 3.10+ and Poetry for environment management.

## Deployment and Execution

"Deployment" for this project consists of setting up the local development environment. The pipeline is not a service to be deployed but a set of scripts to be executed from the command line.

### Prerequisites

- Python 3.10 or higher
- Poetry 1.8 or higher

### Installing Poetry

If Poetry is not installed:

```bash
curl -sSL https://install.python-poetry.org | python3 -
```

Add Poetry to your PATH by adding this to your shell configuration (`~/.bashrc`, `~/.zshrc`, etc.):

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Then reload your shell configuration:

```bash
source ~/.bashrc  # or source ~/.zshrc
```

### Project Setup

1.  **Clone and Navigate:**

      ```bash
      git clone <repository-url>
      cd rl-exec-data
      ```

2.  **Install Dependencies with Poetry:**

      ```bash
      poetry install
      ```

      This will:
      - Create a virtual environment in `.venv` (configured in `poetry.toml`)
      - Install all project dependencies from `pyproject.toml`
      - Install development dependencies (pytest, black, ruff, etc.)

3.  **Environment Configuration:**

      * Create a `.env` file from the `.env.example` template
      * Populate it with necessary credentials (e.g., AWS keys for Crypto Lake access)

### Important Development Notes

- **DO NOT** create virtual environments manually with `python -m venv`
- The project is configured to use `.venv` as the virtual environment location (see `poetry.toml`)
- All dependencies must be managed through Poetry, not pip directly
- To add new dependencies: `poetry add <package>`
- To add dev dependencies: `poetry add --group dev <package>`

### Common Issues and Solutions

#### "Poetry not found" error
- Ensure Poetry is installed and added to PATH
- Restart your terminal or reload shell configuration

#### Virtual environment issues
- Remove any existing `venv` or `.venv` directories
- Run `poetry install` to recreate the environment properly

#### Dependency conflicts
- Run `poetry lock --no-update` to regenerate the lock file
- If issues persist, remove `poetry.lock` and run `poetry install`

### Development Workflow

1. **Activate Virtual Environment:**
   ```bash
   poetry shell
   ```

   Or use Poetry to run commands directly:
   ```bash
   poetry run python scripts/run_analysis.py
   ```

2. **Run Tests:**
   ```bash
   poetry run pytest
   ```

3. **Format Code:**
   ```bash
   poetry run black .
   ```

4. **Lint Code:**
   ```bash
   poetry run ruff check .
   ```

### VS Code Integration

For optimal development experience with VS Code, add this to your workspace settings (`.vscode/settings.json`):

```json
{
    "python.defaultInterpreterPath": ".venv/bin/python",
    "python.terminal.activateEnvironment": true
}
```

This ensures VS Code uses the Poetry-managed virtual environment for IntelliSense, debugging, and terminal sessions.

## Pipeline Execution

Each stage of the pipeline will be executed via the CLI wrapper scripts. For example:

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

## Related Documentation

For security requirements including API key management, data encryption, and access control, see the comprehensive [Security Architecture](./security.md) document.

