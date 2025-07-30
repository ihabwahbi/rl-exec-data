# EPIC 3 Architecture Guidance

**Created**: 2025-07-24  
**Purpose**: Architectural guidance for EPIC 3 implementation based on EPIC 2 completion

## Executive Summary

EPIC 2 has successfully implemented a high-performance market reconstruction pipeline achieving 336-345K messages/second throughput with comprehensive features including multi-symbol support, COW checkpointing, and atomic data handling. This document provides architectural guidance for EPIC 3 (Fidelity Validation).

## EPIC 2 Achievements Summary

### Performance Metrics
- **Throughput**: 336-345K messages/second (3.36x above 100K requirement)
- **Memory Usage**: <1GB per symbol (well under 28GB constraint)
- **Checkpoint Overhead**: <1% performance impact
- **COW Snapshot Time**: <100ms creation
- **Sequence Integrity**: 0% gaps in delta feeds

### Implemented Components
1. **Data Ingestion**: Micro-batched readers for all data types
2. **Order Book Engine**: Perfect L2 state maintenance
3. **Event Replayer**: ChronologicalEventReplay with drift tracking
4. **Data Sink**: Partitioned Parquet with decimal128(38,18)
5. **Multi-Symbol**: Process isolation architecture
6. **Checkpointing**: Non-blocking persistence with recovery

## EPIC 3 Architectural Foundation

### Building Blocks from EPIC 2

EPIC 3 can leverage the following validated components:

1. **ValidationFramework** (from EPIC 1)
   - K-S tests already implemented
   - Power law validation ready
   - Streaming support for large files
   - 91% test coverage
   - Processing rate: 49K messages/second

2. **Reconstruction Output**
   - Partitioned Parquet files with proper schema
   - Decimal128 precision maintained
   - Chronologically ordered events
   - Complete market state at each timestamp

3. **Golden Samples** (11.15M messages)
   - High volume regime: 5.5M msgs
   - Low volume regime: 2.8M msgs
   - Weekend/special: 2.8M msgs
   - Raw format preserved for validation

## EPIC 3 Implementation Strategy

### Story 3.1: Extend FidelityReporter

The FidelityReporter should build upon the existing ValidationFramework:

```python
# Leverage existing validators
from rlx_datapipe.validation.statistical import (
    KolmogorovSmirnovValidator,
    PowerLawValidator,
    DistributionComparisonValidator
)
from rlx_datapipe.validation.validators.timing import (
    ChronologicalOrderValidator,
    SequenceGapValidator
)

# Extend for comprehensive fidelity metrics
class FidelityReporter:
    def __init__(self):
        self.validators = {
            # Order Flow Dynamics
            'trade_size_distribution': PowerLawValidator(
                expected_alpha_range=(2.0, 5.0),
                property_ref="[ASSUMPTION][R-GMN-03]"
            ),
            'inter_event_time': KolmogorovSmirnovValidator(
                threshold=0.05,
                property_ref="Event clustering patterns"
            ),
            
            # Market State Properties
            'spread_distribution': DistributionComparisonValidator(
                levels=[1, 5, 10, 15, 20],
                property_ref="[ASSUMPTION][R-CLD-03]"
            ),
            'order_book_imbalance': OrderFlowImbalanceValidator(
                property_ref="[ASSUMPTION][R-CLD-05]"
            ),
            
            # Price Return Characteristics
            'volatility_clustering': GARCHValidator(
                model_params=(1, 1),
                tolerance=0.10,
                property_ref="[ASSUMPTION][R-OAI-02]"
            ),
            'return_kurtosis': HeavyTailValidator(
                min_kurtosis=3.0,
                property_ref="Leptokurtic distribution"
            ),
            
            # Microstructure Parity
            'sequence_integrity': SequenceGapValidator(
                max_gap_rate=0.0001,
                property_ref="Delta feed continuity"
            ),
            'book_drift': BookDriftValidator(
                max_rmse=0.001,
                property_ref="Order book accuracy"
            )
        }
```

### Story 3.2: Implement Missing Validators

New validators needed for EPIC 3:

1. **OrderFlowImbalanceValidator**
   ```python
   class OrderFlowImbalanceValidator(BaseValidator):
       def validate(self, reconstructed: pl.DataFrame, golden: pl.DataFrame):
           # Calculate OFI = (V_bid - V_ask) / (V_bid + V_ask)
           # Validate predictive power for price movements
   ```

2. **GARCHValidator**
   ```python
   class GARCHValidator(BaseValidator):
       def validate(self, reconstructed: pl.DataFrame, golden: pl.DataFrame):
           # Fit GARCH(1,1) to both datasets
           # Compare parameters within 10% tolerance
   ```

3. **BookDriftValidator**
   ```python
   class BookDriftValidator(BaseValidator):
       def validate(self, reconstructed: pl.DataFrame, golden: pl.DataFrame):
           # Calculate RMSE between book states
           # Track drift over time windows
   ```

### Story 3.3: Visualization and Reporting

Leverage existing report generation patterns:

```python
class FidelityReportGenerator:
    def generate_comprehensive_report(self, validation_results: Dict):
        # Executive Summary
        overall_score = self._calculate_fidelity_score(validation_results)
        
        # Detailed Sections
        sections = {
            'order_flow_dynamics': self._create_order_flow_section(),
            'market_state_properties': self._create_market_state_section(),
            'price_returns': self._create_price_return_section(),
            'microstructure_parity': self._create_microstructure_section()
        }
        
        # Visual Reports
        visualizations = {
            'distribution_comparisons': self._create_distribution_plots(),
            'qq_plots': self._create_qq_plots(),
            'correlation_heatmaps': self._create_correlation_heatmaps(),
            'time_series_overlays': self._create_time_series_plots()
        }
```

## Technical Considerations for EPIC 3

### 1. Data Loading Strategy

Given the large Parquet files from reconstruction:

```python
# Stream processing for memory efficiency
def stream_reconstructed_data(path: Path, chunk_size: int = 100_000):
    """Generator to read reconstructed data in chunks."""
    parquet_file = pq.ParquetFile(path)
    for batch in parquet_file.iter_batches(batch_size=chunk_size):
        yield pl.from_arrow(batch)
```

### 2. Parallel Validation

Leverage multi-processing for independent validators:

```python
from concurrent.futures import ProcessPoolExecutor

def run_parallel_validations(validators: List[BaseValidator], 
                           data_chunks: Iterator[pl.DataFrame]):
    with ProcessPoolExecutor(max_workers=cpu_count()) as executor:
        futures = []
        for validator in validators:
            future = executor.submit(validator.validate_stream, data_chunks)
            futures.append((validator.name, future))
        
        results = {}
        for name, future in futures:
            results[name] = future.result()
    return results
```

### 3. Metric Aggregation

Aggregate metrics across time windows:

```python
class MetricAggregator:
    def aggregate_by_regime(self, metrics: Dict, regime_boundaries: List[Timestamp]):
        """Aggregate metrics by market regime for deeper insights."""
        regime_metrics = {}
        for regime in ['high_volume', 'low_volume', 'special_event']:
            regime_data = self._filter_by_regime(metrics, regime)
            regime_metrics[regime] = self._calculate_regime_statistics(regime_data)
        return regime_metrics
```

## Integration Points

### 1. CLI Interface

Extend existing Click CLI pattern:

```python
@click.command()
@click.option('--reconstructed-path', required=True, help='Path to reconstructed data')
@click.option('--golden-path', required=True, help='Path to golden samples')
@click.option('--output-dir', required=True, help='Output directory for reports')
@click.option('--parallel/--sequential', default=True, help='Run validations in parallel')
def run_fidelity_validation(reconstructed_path, golden_path, output_dir, parallel):
    """Run comprehensive fidelity validation."""
    reporter = FidelityReporter()
    results = reporter.validate(reconstructed_path, golden_path, parallel=parallel)
    reporter.generate_report(results, output_dir)
```

### 2. Configuration

YAML configuration for validation thresholds:

```yaml
fidelity_validation:
  validators:
    trade_size_distribution:
      enabled: true
      alpha_range: [2.0, 5.0]
      p_value_threshold: 0.05
    
    volatility_clustering:
      enabled: true
      garch_params: [1, 1]
      parameter_tolerance: 0.10
    
    book_drift:
      enabled: true
      max_rmse: 0.001
      window_size: 1000
  
  reporting:
    format: ['html', 'markdown', 'json']
    include_visualizations: true
    detailed_metrics: true
```

## Success Criteria for EPIC 3

1. **Automated Validation**: All metrics from PRD FR6 implemented
2. **Performance**: Process 1 month of data within reasonable time
3. **Reporting**: Comprehensive HTML/Markdown reports with visualizations
4. **Pass/Fail**: Clear determination based on p-value thresholds
5. **Extensibility**: Easy to add new validators for future requirements

## Risk Mitigation

1. **Memory Management**: Stream processing for large datasets
2. **Computation Time**: Parallel validation execution
3. **Statistical Validity**: Use established libraries (scipy, statsmodels)
4. **Visualization Performance**: Generate static plots, optional interactive

## Recommended Implementation Order

1. **Week 1**: Extend FidelityReporter with existing validators
2. **Week 2**: Implement new validators (OFI, GARCH, BookDrift)
3. **Week 3**: Create visualization and reporting framework
4. **Week 4**: Integration testing and performance optimization

## Conclusion

EPIC 3 can build directly on the solid foundation established by EPIC 2. The reconstruction pipeline provides high-quality data, the ValidationFramework offers proven patterns, and the architecture supports the comprehensive fidelity validation required. Focus should be on extending existing components rather than reimplementing functionality.