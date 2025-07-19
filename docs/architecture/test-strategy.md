# Test Strategy

The project will follow a rigorous testing strategy to ensure correctness and reliability.

* **Framework:** **`Pytest`** will be the sole framework for all test types.
* **Test Organization:** Tests will be located in the top-level `tests/` directory, mirroring the structure of the `src/rlx_datapipe/` package.
* **Unit Tests:** Each function and class **must** have corresponding unit tests that verify its logic in isolation. These tests will use small, in-memory `Polars` or `Pandas` DataFrames as input and will not touch the filesystem.
* **Integration Tests:** The interaction between components will be tested. For example, an integration test will run a small, version-controlled sample of raw data (located in `tests/fixtures/`) through the entire `Reconstructor` pipeline and assert that the output files are created correctly and conform to the target schema.
* **Continuous Integration:** The full test suite (unit and integration) will be run automatically via the GitHub Actions CI pipeline on every `git push`. A push will be blocked from merging if any tests fail.