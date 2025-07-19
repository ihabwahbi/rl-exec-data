# Source Tree

The project will be organized as a Python monorepo to facilitate code sharing between components and to simplify dependency management. We will use a standard `src` layout.

```plaintext
rlx-data-pipeline/
├── .github/
│   └── workflows/
│       └── ci.yml            # Continuous integration (linting & testing)
├── data/                     # (Gitignored) For raw, processed, and sample data
│   ├── golden_sample/
│   └── raw/
│       └── spot_lake/
├── docs/                     # Project documentation
│   ├── PRD.md
│   ├── architecture.md
│   └── reports/              # Output directory for Fidelity Reports
├── notebooks/                # Jupyter notebooks for data exploration (Epic 1)
├── scripts/                  # CLI entry points for running pipeline stages
│   ├── run_analysis.py
│   ├── run_capture.py
│   └── run_pipeline.py
├── src/
│   └── rlx_datapipe/         # Main source package
│       ├── __init__.py
│       ├── analysis/         # Code for the DataAssessor component
│       ├── capture/          # Code for the LiveCapture component
│       ├── common/           # Shared utilities (e.g., schemas, constants)
│       ├── reconstruction/   # Code for the Reconstructor component
│       │   └── strategies/   # Implementations of the Strategy Pattern
│       └── validation/       # Code for the FidelityReporter component
├── tests/                    # Pytest tests, mirroring the src structure
├── .env.example              # Template for environment variables (e.g., API keys)
├── .gitignore
├── pyproject.toml            # Project metadata and dependencies for Poetry
└── README.md
```
