# Epic 3: FidelityReporter Architecture Design

**Status**: Design Phase  
**Created**: 2025-07-24  
**Priority**: CRITICAL - 0% Implementation Exists

## Executive Summary

The FidelityReporter component is completely missing from the current implementation. Only the ValidationFramework exists, which provides some foundational capabilities but is not the FidelityReporter specified in the PRD. This document defines the complete architecture needed for Epic 3.

## Current State Analysis

### What Exists
- **ValidationFramework**: Basic K-S tests and sequence validation
- **Golden Samples**: 11.15M messages for comparison
- **Parquet Output**: Reconstructed data ready for analysis

### What's Missing (Everything)
- ❌ FidelityReporter component
- ❌ 60% of required metrics
- ❌ Visual reporting capability
- ❌ Automated report generation
- ❌ Research validation framework

## FidelityReporter Architecture

### Core Design Principles
1. **Plugin-Based Metrics**: Extensible metric system
2. **Streaming + Batch Hybrid**: Optimize for performance and accuracy
3. **Visual-First Reporting**: Charts and dashboards as primary output
4. **Research Validation**: Measure claimed vs actual benefits
5. **Multi-Symbol Aware**: Aggregate and compare across symbols

### Component Architecture

```yaml
FidelityReporter:
  core_components:
    MetricEngine:
      purpose: "Orchestrate metric calculation and aggregation"
      responsibilities:
        - Plugin discovery and loading
        - Dependency resolution between metrics
        - Parallel execution management
        - Result caching and storage
      
    MetricPlugin:
      purpose: "Abstract base for all metric implementations"
      interface:
        - name: str
        - category: MetricCategory
        - dependencies: List[str]
        - streaming_capable: bool
        - calculate(data: Union[DataFrame, Stream]) -> MetricResult
        - validate_requirements(data_schema: Schema) -> ValidationResult
        - get_visualization_spec() -> VizSpec
    
    StreamingCollector:
      purpose: "Collect metrics during reconstruction"
      features:
        - Hook into EventReplayer
        - Minimal overhead design
        - State checkpointing
        - Memory-bounded buffers
    
    BatchAnalyzer:
      purpose: "Post-reconstruction metric calculation"
      features:
        - Parquet file processing
        - Distributed computation support
        - Progress tracking
        - Incremental updates
    
    ReportGenerator:
      purpose: "Create visual and text reports"
      outputs:
        - HTML Dashboard
        - Markdown with charts
        - PDF executive summary
        - JSON programmatic access
        - Jupyter notebooks
    
    ResearchValidator:
      purpose: "Validate research paper claims"
      features:
        - A/B testing framework
        - Performance benchmarking
        - Memory profiling
        - Statistical significance testing
```

### Metric Taxonomy

```yaml
metric_categories:
  market_microstructure:
    spread_analysis:
      - BidAskSpread(levels=[1,5,10,15,20])
      - EffectiveSpread
      - RealizedSpread
      - QuotedSpread
    
    order_flow:
      - OrderFlowImbalance
      - OrderFlowToxicity
      - TradeArrivalRate
      - OrderBookImbalance
    
    price_impact:
      - KylesLambda
      - AmihudsIlliquidity
      - PriceImpactRatio
      - TemporaryImpact
  
  statistical_distribution:
    tail_behavior:
      - PowerLawExponent
      - TailIndex
      - ExtremeValueStatistics
      - FatTailDetection
    
    volatility:
      - GARCH11Model
      - VolatilityClustering
      - RealizedVolatility
      - IntradayVolatilityPattern
    
    jumps:
      - JumpDetection
      - JumpIntensity
      - JumpSizeDistribution
      - CojumpAnalysis
  
  data_quality:
    sequence_integrity:
      - SequenceGapRate
      - DuplicateMessageRate
      - OutOfOrderRate
      - MessageLossRate
    
    timing_accuracy:
      - LatencyDistribution
      - ClockDrift
      - TimestampConsistency
      - ProcessingDelay
    
    state_consistency:
      - OrderBookCrossRate
      - NegativeSpreadRate
      - PriceCoherenceScore
      - VolumeConsistency
```

### Implementation Strategy

#### Phase 1: Foundation (Story 3.0)
```yaml
deliverables:
  week_1:
    - MetricPlugin interface and base classes
    - MetricEngine with plugin loading
    - Basic StreamingCollector hooks
    - Simple text report generation
  
  week_2:
    - BatchAnalyzer for Parquet processing
    - First 3 basic metrics (spread, volume, trades)
    - JSON report output
    - Unit test framework
```

#### Phase 2: Core Metrics (Story 3.1a)
```yaml
deliverables:
  week_3:
    - All spread analysis metrics
    - Order flow imbalance implementation
    - Kyle's Lambda calculation
    - Basic HTML dashboard
  
  week_4:
    - Integration with reconstruction pipeline
    - Streaming metric collection
    - Performance optimization
    - Visual chart generation
```

#### Phase 3: Advanced Metrics (Story 3.1b)
```yaml
deliverables:
  week_5:
    - Power law validation
    - GARCH implementation
    - Jump detection algorithms
    - Statistical significance tests
  
  week_6:
    - Complete metric catalogue
    - Advanced visualizations
    - Multi-symbol aggregation
    - Production hardening
```

#### Phase 4: Research Validation (Story 3.5)
```yaml
deliverables:
  week_7:
    - A/B testing framework
    - Performance benchmarks
    - Memory profiling tools
    - Research claim validation
  
  week_8:
    - Complete validation report
    - Executive dashboard
    - Recommendation engine
    - Documentation
```

## Technical Implementation Details

### Metric Plugin Example
```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Union
import polars as pl

@dataclass
class MetricResult:
    name: str
    value: Union[float, dict]
    metadata: dict
    visualization: Optional[dict] = None

class MetricPlugin(ABC):
    """Base class for all fidelity metrics."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique metric identifier."""
        pass
    
    @property
    @abstractmethod
    def category(self) -> str:
        """Metric category for organization."""
        pass
    
    @property
    def dependencies(self) -> List[str]:
        """List of other metrics this depends on."""
        return []
    
    @property
    def streaming_capable(self) -> bool:
        """Whether this metric can be calculated in streaming mode."""
        return False
    
    @abstractmethod
    def calculate(self, data: Union[pl.DataFrame, "Stream"]) -> MetricResult:
        """Calculate the metric from input data."""
        pass
    
    @abstractmethod
    def validate_requirements(self, schema: dict) -> bool:
        """Check if input data has required columns."""
        pass
    
    def get_visualization_spec(self) -> dict:
        """Return visualization specification."""
        return {
            "type": "line",
            "x": "timestamp",
            "y": self.name,
            "title": f"{self.name} Over Time"
        }

class BidAskSpreadMetric(MetricPlugin):
    """Calculate bid-ask spread at various levels."""
    
    def __init__(self, levels: List[int] = [1, 5, 10, 15, 20]):
        self.levels = levels
    
    @property
    def name(self) -> str:
        return "bid_ask_spread"
    
    @property
    def category(self) -> str:
        return "market_microstructure"
    
    def calculate(self, data: pl.DataFrame) -> MetricResult:
        spreads = {}
        for level in self.levels:
            bid_col = f"bid_price_{level}"
            ask_col = f"ask_price_{level}"
            if bid_col in data.columns and ask_col in data.columns:
                spread = (data[ask_col] - data[bid_col]).mean()
                spreads[f"L{level}"] = float(spread)
        
        return MetricResult(
            name=self.name,
            value=spreads,
            metadata={
                "levels": self.levels,
                "sample_size": len(data)
            },
            visualization={
                "type": "bar",
                "data": spreads,
                "title": "Bid-Ask Spread by Level"
            }
        )
    
    def validate_requirements(self, schema: dict) -> bool:
        required = [f"bid_price_{l}" for l in self.levels]
        required.extend([f"ask_price_{l}" for l in self.levels])
        return all(col in schema for col in required)
```

### Streaming Collector Integration
```python
class StreamingMetricCollector:
    """Collects metrics during reconstruction pipeline execution."""
    
    def __init__(self, metrics: List[MetricPlugin]):
        self.streaming_metrics = [m for m in metrics if m.streaming_capable]
        self.accumulators = {m.name: m.create_accumulator() for m in self.streaming_metrics}
    
    def on_event(self, event: dict):
        """Hook called by EventReplayer for each event."""
        for metric in self.streaming_metrics:
            if metric.should_process(event):
                self.accumulators[metric.name].update(event)
    
    def on_checkpoint(self):
        """Save accumulator state during checkpointing."""
        return {
            name: acc.get_state() 
            for name, acc in self.accumulators.items()
        }
    
    def get_results(self) -> dict:
        """Get final metric results."""
        return {
            name: acc.compute() 
            for name, acc in self.accumulators.items()
        }
```

### Report Generator Architecture
```yaml
report_generator:
  template_engine: "Jinja2"
  visualization_library: "Plotly"
  
  report_types:
    executive_summary:
      format: "PDF"
      sections:
        - overall_fidelity_score
        - key_metrics_summary
        - risk_indicators
        - recommendations
    
    technical_report:
      format: "HTML"
      sections:
        - detailed_metrics
        - interactive_charts
        - statistical_tests
        - raw_data_access
    
    research_validation:
      format: "Markdown"
      sections:
        - hypothesis_tests
        - performance_comparison
        - memory_analysis
        - conclusion
```

## Integration Points

### With Reconstruction Pipeline
```python
# In EventReplayer
class EventReplayer:
    def __init__(self, ..., metric_collector: Optional[StreamingMetricCollector] = None):
        self.metric_collector = metric_collector
    
    def process_event(self, event):
        # Normal processing
        result = self._process_event_internal(event)
        
        # Metric collection hook
        if self.metric_collector:
            self.metric_collector.on_event(event)
        
        return result
```

### With Checkpoint System
```python
# In CheckpointManager
def save_checkpoint(self):
    checkpoint_data = {
        "pipeline_state": self.get_pipeline_state(),
        "metric_state": self.metric_collector.on_checkpoint() if self.metric_collector else {}
    }
    # Save checkpoint
```

## Performance Considerations

### Memory Management
- Streaming metrics use bounded buffers
- Batch processing reads Parquet in chunks
- Results cached to disk for large datasets
- Memory profiling for each metric

### Throughput Impact
- Target: <10% overhead on reconstruction
- Streaming metrics must be O(1) per event
- Batch metrics run post-reconstruction
- Parallel metric calculation where possible

## Testing Strategy

### Unit Tests
- Each metric plugin thoroughly tested
- Mock data generators for edge cases
- Visualization spec validation
- Performance benchmarks

### Integration Tests
- Full pipeline with metrics enabled
- Multi-symbol scenarios
- Checkpoint/recovery with metrics
- Report generation validation

### Validation Tests
- Compare with known good implementations
- Statistical test correctness
- Visual output quality
- Research claim verification

## Risk Mitigation

### Technical Risks
1. **Performance Impact**
   - Mitigation: Careful profiling, optional metrics
   
2. **Complex Metric Implementation**
   - Mitigation: Use established libraries where possible
   
3. **Memory Usage**
   - Mitigation: Streaming design, bounded buffers

### Project Risks
1. **Scope Creep**
   - Mitigation: Phased delivery, core metrics first
   
2. **Integration Complexity**
   - Mitigation: Clean interfaces, minimal coupling
   
3. **Testing Coverage**
   - Mitigation: Test-driven development, automated validation

## Success Criteria

1. **All PRD Metrics Implemented**: 100% coverage
2. **Performance Maintained**: <10% overhead
3. **Visual Reports Generated**: HTML, PDF, Markdown
4. **Research Validated**: All claims measured
5. **Production Ready**: Full test coverage, documentation

## Conclusion

The FidelityReporter represents significant new development work for Epic 3. This architecture provides a solid foundation for implementing the missing component while maintaining the high quality demonstrated in Epic 2. The phased approach allows for incremental delivery and validation of the most critical metrics first.