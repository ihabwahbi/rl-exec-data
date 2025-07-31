# Test Strategy

**Last Updated**: 2025-07-31  
**Status**: Enhanced with specialized testing strategies

The project will follow a rigorous testing strategy to ensure correctness and reliability.

* **Framework:** **`Pytest`** will be the sole framework for all test types.
* **Test Organization:** Tests will be located in the top-level `tests/` directory, mirroring the structure of the `src/rlx_datapipe/` package.
* **Unit Tests:** Each function and class **must** have corresponding unit tests that verify its logic in isolation. These tests will use small, in-memory `Polars` or `Pandas` DataFrames as input and will not touch the filesystem.
* **Integration Tests:** The interaction between components will be tested. For example, an integration test will run a small, version-controlled sample of raw data (located in `tests/fixtures/`) through the entire `Reconstructor` pipeline and assert that the output files are created correctly and conform to the target schema.
* **Continuous Integration:** The full test suite (unit and integration) will be run automatically via the GitHub Actions CI pipeline on every `git push`. A push will be blocked from merging if any tests fail.

## Specialized Testing Strategies

Beyond standard unit and integration tests, this complex system requires specialized validation approaches to ensure comprehensive quality:

### Fidelity Validation Testing

The system's output must be validated against rigorous statistical and microstructure metrics to ensure the reconstructed data faithfully represents actual market behavior.

- **Strategy**: Plugin-based metric system with three-tier execution model (Streaming, GPU, Comprehensive)
- **Metrics**: Advanced statistical tests including Anderson-Darling, Energy Distance, and Maximum Mean Discrepancy
- **Reference**: See [FidelityReporter component](./components.md#component-4-fidelityreporter--in-progress---epic-3) for the comprehensive metric catalogue

### Performance Testing

Performance is a critical non-functional requirement with validated baselines that must be maintained.

- **Validated Baselines**: 
  - Throughput: 12.97M events/sec (130x above 100K requirement)
  - Memory: 1.67GB for 8M events (14x safety margin)
  - I/O: 7.75GB/s read, 3.07GB/s write
- **Testing Approach**: Regular benchmarking against representative workloads
- **Reference**: See [Performance Achievements](./architecture-status.md#performance-achievements) for detailed metrics

### Fault Tolerance Testing

The system must be resilient against various failure modes including crashes, network interruptions, and data corruption.

- **Patterns Tested**:
  - Write-Ahead Logging (WAL) recovery after crashes
  - Checkpointing with <1% performance overhead
  - Sequence gap detection and recovery
  - Memory pressure handling with graceful degradation
- **Reference**: See [Error Handling](./error-handling.md) for comprehensive resilience patterns

### Memory Constraint Testing

Given the 28GB hardware constraint, memory usage must be continuously validated.

- **Test Scenarios**:
  - Extended runs (24+ hours) to detect memory leaks
  - Peak load conditions with multiple symbols
  - Streaming mode activation under memory pressure
- **Reference**: See [Memory-Bounded Processing](./high-level-architecture.md#memory-bounded-processing) patterns

### Data Precision Testing

The system must maintain precise decimal handling throughout the pipeline.

- **Test Cases**:
  - Round-trip precision preservation for all symbol types
  - Edge cases for exotic pairs with extreme precision requirements
  - Decimal128 vs int64 pips performance validation
- **Reference**: See [Data Precision Strategy](./data-models.md#data-precision-strategy)

### Security Testing

Security requirements must be validated including encryption, access control, and credential management.

- **Test Areas**:
  - API credential scrubbing in logs
  - AES-256 encryption for golden samples
  - File permission enforcement (700 for output directories)
- **Reference**: See [Security Architecture](./security.md) for complete requirements

## Test Coverage Requirements

- **Unit Tests**: Minimum 80% code coverage
- **Integration Tests**: All component interfaces must be tested
- **Performance Tests**: Must run on every release candidate
- **Fidelity Tests**: Required for any changes to reconstruction logic