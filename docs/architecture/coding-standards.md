# Coding Standards

These standards are **mandatory** for all code contributed to the repository, whether by human developers or AI agents, to ensure consistency and maintainability.

* **Style Guide & Linting:** All Python code **must** adhere to the `PEP 8` style guide. The project will use **`black`** for automated code formatting and **`ruff`** for high-speed linting to enforce these standards automatically.
* **Type Hinting:** All function signatures and class methods **must** include type hints using Python's `typing` module. This is critical for code clarity, static analysis, and enabling AI agents to understand the code's data contracts.
* **Modularity:** Logic must be encapsulated in small, single-responsibility functions and classes, organized within the component structure defined in the `Source Tree`.
* **Configuration:** No hardcoded values (e.g., file paths, magic numbers) are allowed. All configuration must be handled via environment variables or dedicated configuration files.
* **Documentation:** All public functions and classes must have a docstring explaining their purpose, arguments, and return values.
