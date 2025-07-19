# Development Setup Guide

This guide ensures consistent dependency management across all developers.

## Prerequisites

- Python 3.10 or higher
- Poetry 1.8 or higher

## Installing Poetry

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

## Project Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd rl-exec-data
```

2. Install dependencies using Poetry:
```bash
poetry install
```

This will:
- Create a virtual environment in `.venv` (configured in `poetry.toml`)
- Install all project dependencies from `pyproject.toml`
- Install development dependencies (pytest, black, ruff, etc.)

3. Activate the virtual environment:
```bash
poetry shell
```

Or use Poetry to run commands directly:
```bash
poetry run python scripts/run_analysis.py
```

## Important Notes

- **DO NOT** create virtual environments manually with `python -m venv`
- The project is configured to use `.venv` as the virtual environment location (see `poetry.toml`)
- All dependencies must be managed through Poetry, not pip directly
- To add new dependencies: `poetry add <package>`
- To add dev dependencies: `poetry add --group dev <package>`

## Common Issues

### "Poetry not found" error
- Ensure Poetry is installed and added to PATH
- Restart your terminal or reload shell configuration

### Virtual environment issues
- Remove any existing `venv` or `.venv` directories
- Run `poetry install` to recreate the environment properly

### Dependency conflicts
- Run `poetry lock --no-update` to regenerate the lock file
- If issues persist, remove `poetry.lock` and run `poetry install`

## Development Workflow

1. Always use Poetry for dependency management
2. Run tests with: `poetry run pytest`
3. Format code with: `poetry run black .`
4. Lint code with: `poetry run ruff check .`

## VS Code Integration

Add this to your workspace settings (`.vscode/settings.json`):

```json
{
    "python.defaultInterpreterPath": ".venv/bin/python",
    "python.terminal.activateEnvironment": true
}
```