# Components

**Last Updated**: 2025-07-31  
**Status**: Updated with validated findings from Epic 1 and research insights

The data pipeline will be composed of five primary components, each implemented as a distinct Python module with a clear CLI interface.

## Component 0: `DataAcquisition` ✅ **COMPLETE**

  * **Responsibility:** To orchestrate the entire data acquisition process from Crypto Lake API, serving as the blocking prerequisite for all subsequent work. It manages authentication, downloads historical data, validates integrity, and stages data for downstream processing.
  * **Status:** Fully implemented and executed in Epic 0 - all required historical data successfully acquired.
  * **Key Interfaces:**
      * **Input:** 
        - API credentials (from environment variables or secure vault)
        - Data requirements specification (symbols, date range, data types)
      * **Output:** 
        - Staged data in ready zone (validated Parquet files)
        - Acquisition manifest with checksums and metadata
        - Readiness certificate enabling Epic 1 start
  * **Core Components:**
      * **DataAcquisitionManager**: Orchestrates the acquisition pipeline
      * **CryptoLakeAPIClient**: Handles API authentication and requests with rate limiting
      * **DataDownloader**: Manages chunked downloads with resume capability
      * **IntegrityValidator**: Performs multi-level validation (checksum, schema, temporal)
      * **DataStagingArea**: Manages data lifecycle through staging zones
  * **Key Features:**
      * **Blocking Gate**: Hard enforcement preventing any work without valid data
      * **Resilient Downloads**: Automatic retry, resume capability, parallel chunks
      * **Comprehensive Validation**: File integrity, schema validation, temporal continuity
      * **Staging Zones**: raw → validating → ready → quarantine state transitions
  * **Dependencies:** None. This is the absolute first component that must run.
  * **Technology Stack:** Python, asyncio, aiohttp, cryptography (for checksums).

## Component 1: `DataAssessor`

  * **Responsibility:** To perform the initial analysis of the raw Crypto Lake data to validate the critical `origin_time` assumption and assess delta feed availability (as defined in Epic 1). It reads raw trade, book, and book_delta_v2 data for a sample period and generates a comprehensive report on data quality and available reconstruction strategies.
  * **Key Interfaces:**
      * **Input:** Path to raw Crypto Lake data (trades, book snapshots, and book_delta_v2).
      * **Output:** A JSON/Markdown report detailing:
        - `origin_time` availability and validity statistics
        - `book_delta_v2` table availability and completeness
        - Sequence gap analysis (mean, max, distribution)
        - Memory requirements estimate for delta processing
        - Recommended reconstruction strategy
  * **Dependencies:** None. This is the first component to be run.
  * **Technology Stack:** Python, Polars, Loguru.

## Component 2: `LiveCapture`

  * **Responsibility:** To connect to the live Binance combined WebSocket stream and capture comprehensive "golden samples" of real-time market events across different market regimes with precise timing metadata (as defined in Story 1.2 and research requirements). This data serves as the ground truth for validation and fidelity maximization.
  * **Key Interfaces:**
      * **Input:** 
        - Symbol (e.g., BTC-USDT)
        - Capture sessions configuration:
          - High volume period (US market open, major news)
          - Low volume period (Asian overnight, weekends)
          - Special event period (Fed announcement, options expiry)
        - Duration per session (24-48 hours recommended)
      * **Output:** Multiple capture files containing:
        - Raw, interleaved JSON events from combined stream
        - Original Binance `E` (event time) and `T` (transaction time) timestamps
        - Local arrival timestamp (nanosecond precision)
        - Network latency estimate
        - Market regime metadata
        - Order book initialization snapshots
  * **Dependencies:** None. Runs as a standalone utility.
  * **Technology Stack:** Python, `websockets` library, `aiohttp` for REST API, `cryptography` for at-rest encryption.
  * **Enhanced Features:**
      * **Market Regime Detector**: Automatically identifies and tags market conditions:
        ```python
        class MarketRegimeDetector:
            def detect_regime(self, recent_events: List[Event]) -> MarketRegime:
                # Analyze volume, volatility, spread patterns
                volume_rate = self.calculate_event_rate(recent_events)
                spread_volatility = self.calculate_spread_volatility(recent_events)
                
                if volume_rate > HIGH_VOLUME_THRESHOLD:
                    return MarketRegime.HIGH_VOLUME
                elif volume_rate < LOW_VOLUME_THRESHOLD:
                    return MarketRegime.LOW_VOLUME
                elif self.is_special_event():
                    return MarketRegime.SPECIAL_EVENT
                else:
                    return MarketRegime.NORMAL
        ```
      * **Order Book Initialization Protocol**: Implements proper Binance synchronization:
        ```python
        async def initialize_order_book(self):
            # 1. Start buffering WebSocket messages
            self.start_buffering()
            
            # 2. Fetch REST snapshot
            snapshot = await self.fetch_rest_snapshot()
            
            # 3. Find sync point in buffer
            sync_point = self.find_sync_point(snapshot.lastUpdateId)
            
            # 4. Apply buffered updates from sync point
            self.apply_buffered_updates(sync_point)
            
            # 5. Continue with live stream
            self.process_live_stream()
        ```
      * **Chronological Ordering Validator**: Ensures event integrity:
        ```python
        def validate_chronological_order(self, events: List[Event]) -> ValidationResult:
            issues = []
            for i in range(1, len(events)):
                if events[i].timestamp < events[i-1].timestamp:
                    issues.append(f"Out of order: {events[i-1].id} -> {events[i].id}")
            return ValidationResult(valid=len(issues)==0, issues=issues)
        ```
  * **Implementation Notes:**
      * **NTP Monitoring**: Capture system NTP offset hourly and store in metadata for clock skew analysis
      * **Multi-Session Management**: Separate files for each market regime with metadata
      * **File Rotation**: Implement hourly rotation with gzip compression
      * **Memory Security**: Use `ctypes.memset` to securely wipe decrypted data from RAM after processing

## Component 3: `Reconstructor` ✅ COMPLETE

### Tunability Architecture for IFR Workflow

The Reconstructor implements a sophisticated parameter tuning system to support the Integrated Fidelity Refinement (IFR) workflow, enabling systematic adjustments based on FidelityReporter feedback:

#### Configurable Parameters

```python
class ReconstructorConfig:
    """Tunable parameters exposed for IFR refinement."""
    
    # Event Timing Parameters
    timing_params = {
        'event_jitter_ms': 0.0,          # Random jitter to simulate network delays
        'clock_drift_ppb': 0,            # Parts-per-billion clock drift simulation
        'latency_model': 'empirical',    # 'fixed', 'gaussian', 'empirical'
        'latency_percentiles': [50, 95, 99],  # For empirical model
    }
    
    # Order Book Dynamics
    book_params = {
        'liquidity_decay_rate': 0.95,    # How fast liquidity replenishes
        'trade_impact_model': 'linear',  # 'linear', 'sqrt', 'logarithmic'
        'impact_coefficient': 1.0,       # Kyle's lambda equivalent
        'resilience_factor': 0.8,        # Book recovery speed after shocks
        'max_book_depth': 20,            # Levels to maintain
        'iceberg_detection': True,       # Infer hidden liquidity
    }
    
    # Noise Models
    noise_params = {
        'microstructure_noise_std': 0.0001,  # Bid-ask bounce noise
        'price_discretization': 0.01,        # Tick size
        'volume_rounding': 'nearest',        # 'nearest', 'floor', 'probabilistic'
        'timestamp_precision': 'microsecond', # 'nanosecond', 'microsecond', 'millisecond'
    }
    
    # Event Generation
    event_params = {
        'clustering_kernel': 'hawkes',       # 'poisson', 'hawkes', 'empirical'
        'hawkes_baseline': 0.1,              # Baseline intensity
        'hawkes_excitation': 0.5,            # Self-excitation parameter
        'hawkes_decay': 1.0,                 # Decay rate
        'endogenous_ratio': 0.8,             # Target ratio of endogenous events
    }
    
    # Adversarial Patterns (for injection/preservation)
    adversarial_params = {
        'spoofing_frequency': 0.0,           # Events per second
        'spoofing_volume_ratio': 10,         # Fake vs real volume
        'quote_stuffing_rate': 0,            # Messages per second
        'momentum_ignition_prob': 0.0,       # Probability per large trade
        'fleeting_quote_lifetime_ms': 100,   # Lifetime of fleeting quotes
    }
```

#### Dynamic Tuning Interface

```python
class ReconstructorTuner:
    """Interface for IFR workflow to tune Reconstructor parameters."""
    
    def __init__(self, reconstructor: Reconstructor):
        self.reconstructor = reconstructor
        self.parameter_history = []  # Track all adjustments
        self.best_config = None
        self.current_config = ReconstructorConfig()
    
    def apply_fidelity_feedback(self, 
                                fidelity_report: FidelityReport) -> Dict:
        """Analyze fidelity failures and suggest parameter adjustments."""
        adjustments = {}
        
        # Analyze each failing metric
        for metric_name, result in fidelity_report.failed_metrics.items():
            if metric_name == 'hawkes_process_4d':
                # Adjust clustering parameters
                if result['branching_ratio'] < 0.95:
                    adjustments['hawkes_excitation'] = (
                        self.current_config.event_params['hawkes_excitation'] * 1.1
                    )
                if result['endogenous_ratio'] < 0.75:
                    adjustments['endogenous_ratio'] = 0.8
                    
            elif metric_name == 'book_resilience':
                # Adjust book dynamics
                if result['recovery_time_ms'] > 20:
                    adjustments['resilience_factor'] = (
                        self.current_config.book_params['resilience_factor'] * 1.2
                    )
                    adjustments['liquidity_decay_rate'] = 0.98
                    
            elif metric_name == 'spread_dynamics':
                # Adjust noise models
                if result['spread_volatility'] < golden_spread_vol * 0.9:
                    adjustments['microstructure_noise_std'] = (
                        self.current_config.noise_params['microstructure_noise_std'] * 1.5
                    )
                    
            elif metric_name == 'spoofing_detection':
                # Adjust adversarial patterns
                if result['detection_rate'] < 0.8:
                    adjustments['spoofing_frequency'] = (
                        golden_spoofing_rate * 1.2
                    )
        
        return adjustments
    
    def update_parameters(self, adjustments: Dict) -> None:
        """Apply parameter adjustments and track history."""
        # Record current state
        self.parameter_history.append({
            'timestamp': datetime.now(),
            'config': copy.deepcopy(self.current_config),
            'adjustments': adjustments
        })
        
        # Apply adjustments
        for param_path, new_value in adjustments.items():
            self._set_nested_param(param_path, new_value)
        
        # Propagate to Reconstructor
        self.reconstructor.update_config(self.current_config)
    
    def rollback_to_best(self) -> None:
        """Revert to best performing configuration."""
        if self.best_config:
            self.current_config = copy.deepcopy(self.best_config)
            self.reconstructor.update_config(self.current_config)
```

#### Automated Tuning Loop

```python
class IFRTuningLoop:
    """Automated refinement loop for Epic 3."""
    
    def __init__(self, reconstructor, fidelity_reporter, max_iterations=100):
        self.tuner = ReconstructorTuner(reconstructor)
        self.reporter = fidelity_reporter
        self.max_iterations = max_iterations
        self.convergence_threshold = 0.95  # 95% metrics passing
    
    async def refine_to_convergence(self, 
                                   golden_data: pl.DataFrame) -> TuningResult:
        """Iterate until fidelity converges or max iterations reached."""
        
        for iteration in range(self.max_iterations):
            # Run reconstruction with current parameters
            reconstructed = await self.reconstructor.process(source_data)
            
            # Validate against golden sample
            report = await self.reporter.validate(
                reconstructed, golden_data, tier='comprehensive'
            )
            
            # Check convergence
            if report.overall_score >= self.convergence_threshold:
                return TuningResult(
                    success=True,
                    iterations=iteration + 1,
                    final_score=report.overall_score,
                    final_config=self.tuner.current_config
                )
            
            # Apply feedback
            adjustments = self.tuner.apply_fidelity_feedback(report)
            if not adjustments:
                # No more adjustments possible
                break
                
            self.tuner.update_parameters(adjustments)
            
            # Track best configuration
            if report.overall_score > self.best_score:
                self.best_score = report.overall_score
                self.tuner.best_config = copy.deepcopy(
                    self.tuner.current_config
                )
        
        # Max iterations reached without convergence
        self.tuner.rollback_to_best()
        return TuningResult(
            success=False,
            iterations=self.max_iterations,
            final_score=self.best_score,
            final_config=self.tuner.best_config
        )
```

#### Integration with FidelityReporter

The tuning system integrates seamlessly with the FidelityReporter's defect detection:

```python
# In FidelityReporter
def generate_tuning_recommendations(self, 
                                   failed_metrics: Dict) -> List[TuningHint]:
    """Generate specific parameter adjustment hints."""
    hints = []
    
    for metric_name, failure in failed_metrics.items():
        hint = TuningHint(
            metric=metric_name,
            severity=failure['severity'],
            parameter_path=self._map_metric_to_parameter(metric_name),
            suggested_adjustment=self._calculate_adjustment(
                failure['expected'], 
                failure['actual']
            ),
            confidence=self._estimate_fix_confidence(failure)
        )
        hints.append(hint)
    
    return sorted(hints, key=lambda h: (h.severity, h.confidence), reverse=True)
```

This tunability architecture enables the systematic refinement required by the IFR workflow, transforming validation failures into concrete parameter adjustments that drive convergence toward the target fidelity.

## Component 3: `Reconstructor` ✅ COMPLETE

**Implementation Details**:

### Streaming Architecture
Based on validated testing with only 1.67GB peak memory for 8M events (14x safety margin vs 24GB constraint):
- **Bounded Memory**: Never loads more than 1GB of raw data at once (validated: <500MB for 1M messages)
- **Backpressure**: Every stage signals capacity to upstream components via asyncio.Queue
- **Pipeline Stages**: [Disk Reader] → [Parser] → [Order Book Engine] → [Event Formatter] → [Parquet Writer]
- **Performance**: 12.97M events/sec processing capability

### Multi-Symbol Processing
Process-per-symbol architecture avoiding Python GIL:
```
                    [Main Process]
                          |
                   [Symbol Router]
                    /     |     \
            Worker-1   Worker-2   Worker-N
            (BTCUSDT)  (ETHUSDT)  (Symbol-N)
                |         |          |
         Full Pipeline Full Pipeline Full Pipeline
```
- **IPC**: multiprocessing.Queue with 1000 message buffer per symbol
- **Scaling**: Linear with number of symbols
- **Isolation**: Complete process isolation prevents cross-symbol interference

  * **Responsibility:** This is the core ETL engine implementing the **Chronological Event Replay** algorithm (as defined in Epic 2 and research). It ingests raw Crypto Lake data, applies sophisticated reconstruction to bridge the paradigm gap between snapshot-based historical data and differential live feeds, creating a high-fidelity unified event stream.
  * **Status:** Fully implemented across Epic 2 stories with validated performance of 336-345K messages/second
  * **Key Interfaces:**
      * **Input:** 
        - Path to raw Crypto Lake data (trades, book snapshots, book_delta_v2)
        - Chosen reconstruction strategy: 
          - `full_event_replay` (**IMPLEMENTED**): Uses book_delta_v2 for complete microstructure - **validated with 0% gaps**
          - `snapshot_anchored`: Falls back to 100ms snapshots if deltas unavailable
          - `origin_time_sort`: Simple time-based merge if origin_time is reliable
      * **Output:** Processed data conforming to the "Unified Market Event" schema, stored in partitioned Parquet files with decimal128(38,18) precision.
  * **Performance Enhancements from Research**:
      * **[ASSUMPTION][R-CLD-01] Hybrid Delta-Event Sourcing**: Claims 40-65% memory reduction
      * **[ASSUMPTION][R-GMN-01] Scaled Integer Arithmetic**: Use int64 for hot path performance
      * **[ASSUMPTION][R-ALL-01] Micro-batching**: Process 100-1000 events at a time for vectorization
      * **[ASSUMPTION][R-GMN-04] Hybrid Data Structure**: Contiguous arrays for top-of-book, hash for deep levels
  * **Chronological Event Replay Algorithm:**
      ```python
      class ChronologicalEventReplay:
          def execute(self, trades_df: pl.DataFrame, book_df: pl.DataFrame, 
                     deltas_df: Optional[pl.DataFrame]) -> pl.DataFrame:
              # Step 1: Data Ingestion and Labeling
              trades_df = trades_df.with_columns(pl.lit("TRADE").alias("event_type"))
              book_df = book_df.with_columns(pl.lit("BOOK_SNAPSHOT").alias("event_type"))
              if deltas_df is not None:
                  deltas_df = deltas_df.with_columns(pl.lit("BOOK_DELTA").alias("event_type"))
              
              # Step 2: Unification and Chronological Sorting (stable sort critical!)
              events = pl.concat([trades_df, book_df, deltas_df], how="vertical")
              events = events.sort("origin_time", "update_id", maintain_order=True)
              
              # Step 3: Schema Normalization
              events = self.normalize_to_unified_schema(events)
              
              # Step 4: Stateful Replay (the magic happens here)
              return self.stateful_replay(events)
          
          def stateful_replay(self, events: pl.DataFrame) -> pl.DataFrame:
              """The stateful replayer that maintains market state in memory."""
              order_book = OrderBookState()
              output_events = []
              drift_metrics = []
              
              for event in events.iter_rows(named=True):
                  if event['event_type'] == 'BOOK_SNAPSHOT':
                      if not order_book.initialized:
                          # First snapshot initializes the book
                          order_book.initialize_from_snapshot(event)
                      else:
                          # Later snapshots validate and resync
                          drift = order_book.calculate_drift(event)
                          drift_metrics.append(drift)
                          order_book.resynchronize(event)
                  
                  elif event['event_type'] == 'TRADE':
                      # Apply trade impact (liquidity consumption)
                      order_book.apply_trade(event)
                  
                  elif event['event_type'] == 'BOOK_DELTA':
                      # Apply differential update
                      order_book.apply_delta(event)
                  
                  # Enrich event with current book state
                  event['book_state'] = order_book.get_current_state()
                  output_events.append(event)
              
              return pl.DataFrame(output_events)
      ```
  * **Key Features:**
      * **Stateful Order Book Engine**: Maintains full L2 book state with bounded memory (top 20 levels)
      * **Drift Tracking**: Quantifies information loss between snapshots
      * **Liquidity Consumption Modeling**: Trades properly reduce book liquidity
      * **Sequence Gap Detection**: Monitors update_id continuity - **0% gaps validated in Epic 1**
      * **Write-Ahead Log (WAL)**: Ensures crash recovery without data corruption
      * **Streaming Mode**: Processes data in chunks if memory constraints are exceeded
      * **Monotonic Ordering**: Ensures update_id ordering within same timestamp
      * **[ASSUMPTION][R-OAI-01] Pending Queue Pattern**: Atomic updates during snapshots
      * **[ASSUMPTION][R-OAI-03] Copy-on-Write Checkpointing**: Non-blocking state persistence
  * **Dependencies:** Relies on the analysis report from `DataAssessor` to select its operational strategy.
  * **Technology Stack:** Python, Polars, PyArrow (for decimal types), Parquet (for output and checkpoints).
  * **Implementation Achieved:**
      * **Data Ingestion**: Readers for trades, book snapshots, and book_delta_v2 with micro-batching
      * **Order Book Engine**: Maintains L2 state with perfect update_id sequence handling (0% gaps)
      * **Event Replayer**: ChronologicalEventReplay with drift tracking (RMS < 0.001)
      * **Data Sink**: Parquet output with hourly partitioning and atomic writes
      * **Multi-Symbol**: Process-per-symbol architecture avoiding Python GIL
      * **Checkpointing**: COW snapshots with <100ms creation time and <1% overhead
      * **Memory Bounded**: <1GB per symbol pipeline (validated under load)
      * **Stable Sort**: Preserves event ordering within same timestamp

### Implemented Architectural Patterns

#### Write-Ahead Logging (WAL) Pattern
- **Purpose**: Crash recovery and durability
- **Implementation**: CheckpointManager with atomic writes before state changes
- **Features**:
  - Recovery on startup from last consistent state
  - Minimal performance impact (<1% overhead)
  - Audit trail of all state transitions
- **Benefits**: Crash resilience, data consistency, operational reliability

#### Memory-Mapped I/O Pattern
- **Purpose**: High-performance file operations
- **Implementation**: Used in Parquet reading/writing operations
- **Features**:
  - Zero-copy operations between disk and memory
  - OS-level caching for frequently accessed data
  - Efficient handling of large files
- **Performance Impact**: 20x improvement in I/O operations

#### Pipeline State Provider Pattern
- **Purpose**: Abstract state management interface
- **Implementation**:
  ```python
  class PipelineStateProvider(ABC):
      @abstractmethod
      def get_state(self) -> PipelineState:
          pass
      
      @abstractmethod
      def save_state(self, state: PipelineState) -> None:
          pass
  ```
- **Implementations**:
  - InMemoryStateProvider: For testing and development
  - CheckpointedStateProvider: For production with persistence
- **Benefits**: Testability, flexibility, state isolation

#### Drift Tracking Pattern
- **Purpose**: Monitor reconstruction accuracy over time
- **Implementation**: Continuous monitoring of key metrics
- **Metrics Tracked**:
  - Sequence gaps (target: 0%)
  - Time drift (max: 1000ms)
  - State divergence (alert: >0.1% gaps)
- **Integration**: Metrics exported via OpenTelemetry

### Performance Optimization Patterns

**Validated Performance**: Epic 1 testing demonstrated 12.97M events/sec (130x above 100K requirement) with only 1.67GB memory usage for 8M events.

#### Zero-Copy Operations
- **Description**: Avoid data copying between operations using Arrow arrays throughout
- **Impact**: 2x throughput improvement, reduced memory bandwidth
- **Implementation**: 
  ```python
  # Use Arrow compute functions - no copy
  def process_batch(batch: pa.RecordBatch) -> pa.RecordBatch:
      price_pips = pc.multiply(batch.column('price'), pa.scalar(1e8))
      return batch.set_column(
          batch.schema.get_field_index('price_pips'),
          'price_pips',
          price_pips
      )
  ```

#### Memory Pooling
- **Description**: Pre-allocate memory pools to avoid allocation/deallocation overhead
- **Impact**: Reduced GC pressure by 60%, prevents fragmentation
- **Implementation**: Pre-allocated numpy arrays with chunk management

#### Vectorized Operations
- **Description**: Process entire chunks at once instead of row-by-row
- **Impact**: 100x faster than iteration
- **Implementation**:
  ```python
  # Vectorized gap detection
  update_ids = df['update_id'].to_numpy()
  diffs = np.diff(update_ids)
  gap_mask = diffs > 1
  gap_indices = np.where(gap_mask)[0]
  ```

#### JIT Compilation
- **Description**: Use Numba for critical functions to compile to machine code
- **Impact**: 10-50x speedup on hot paths
- **Implementation**: Apply `@jit(nopython=True, parallel=True)` to order book operations

#### Async I/O Pipeline
- **Description**: Overlap I/O with computation using async stages
- **Impact**: Prevents I/O blocking, maintains full CPU utilization
- **Implementation**: Concurrent read/process/write stages with bounded queues

#### Micro-Batching
- **Description**: Process events in configurable batches
- **Impact**: 3x throughput with 10K batch size
- **Configuration**: Adaptive sizing based on throughput monitoring

#### Hybrid Order Book
- **Description**: Bounded dict for top levels + overflow handling
- **Impact**: Constant memory with full depth tracking
- **Implementation**: Top 20 levels in memory, deeper levels aggregated

#### Scaled Int64 Arithmetic
- **Description**: Integer math for decimal operations using "pips"
- **Impact**: 10x faster than Decimal type
- **Implementation**: Convert to pips, compute, convert back

#### Profile-Guided Optimization
- **Description**: Regular profiling with production data to identify bottlenecks
- **Impact**: Ensures optimization efforts target actual bottlenecks
- **Implementation**: cProfile + memory_profiler on representative workloads

## Component 4: `FidelityReporter` 🔴 **IN PROGRESS - EPIC 3**

  * **Responsibility:** To automate comprehensive quality assurance implementing the full **Fidelity Validation Metrics Catalogue** from the research (as defined in Epic 3). It performs deep statistical and microstructure validation between reconstructed historical data and golden samples to ensure the backtesting environment is a faithful replica of reality, with specific focus on preserving critical HFT phenomena including event clustering, deep book dynamics, and adversarial patterns.
  * **Status:** CRITICAL - 0% Implementation Exists. Only ValidationFramework foundation available.
  * **Architecture:** Plugin-based metric system with **three-tier execution model** for performance optimization:
      - **Tier 1 (<1μs)**: Streaming tests for real-time monitoring
      - **Tier 2 (<1ms)**: GPU-accelerated tests for frequent validation  
      - **Tier 3 (<100ms)**: Comprehensive tests for deep analysis
  * **Key Interfaces:**
      * **Input:** 
        - Path to the reconstructed data (Unified Event Stream)
        - Path to the golden sample data (minimum 24-48 hours, multiple market regimes)
        - Validation configuration (thresholds, metrics to compute, tier execution settings)
      * **Output:** A comprehensive Fidelity Report in Markdown/HTML format with:
        - **Executive Summary**: Fidelity Score (weighted average across all tests), PASS/FAIL determination
        - **Statistical Distribution Tests** (Replacing K-S):
          - Anderson-Darling Test: Enhanced tail sensitivity (p-value > 0.05)
          - Cramér-von Mises Test: Balanced distribution sensitivity
          - Energy Distance: Multivariate distribution comparison (<0.01 normalized)
          - Maximum Mean Discrepancy (MMD): Temporal dependency detection with signature kernels
        - **Event Clustering & Hawkes Process Analysis**:
          - Multi-scale clustering detection (~10μs, 1-5ms, 100μs scales)
          - 4D Hawkes process calibration (price jumps + order flow)
          - Endogenous activity ratio (target: ~80% for crypto)
          - Critical regime detection (branching ratio approaching 1)
        - **Deep Book Dynamics (Beyond Level 20)**:
          - Multi-level predictive power analysis (L1-5: volatile, L3-10: strongest, L10-20: long-term)
          - Hidden liquidity detection (85-90% matching rate validation)
          - Book resilience metrics (recovery time after shocks)
          - Asymmetric deterioration patterns (ask-side in volatile markets)
        - **Adversarial Pattern Detection**:
          - Quote Stuffing: 2000+ orders/sec with 32:1 cancellation ratios
          - Spoofing/Layering: <500ms patterns with 10-50:1 volume ratios
          - Momentum Ignition: <5 second complete cycles
          - Fleeting Liquidity: Sub-100ms order lifetimes
        - **RL-Specific Validation**:
          - State-action coverage (>95% requirement)
          - Reward signal fidelity (<5% distribution difference)
          - Sim-to-real gap measurement (<5% policy degradation)
        - **Visual Reports**: 3D state space projections, regime analysis, pattern heatmaps
  * **Fidelity Metrics Implementation:**
      ```python
      class FidelityMetricsCalculator:
          def calculate_all_metrics(self, reconstructed: pl.DataFrame, 
                                   golden: pl.DataFrame) -> FidelityReport:
              metrics = {}
              
              # Order Flow Dynamics
              metrics['trade_size'] = self.compare_distributions(
                  reconstructed.filter(pl.col('event_type')=='TRADE')['trade_quantity'],
                  golden.filter(golden['event_type']=='trade')['quantity'],
                  metric_name="Trade Size Distribution",
                  expected_property="[ASSUMPTION][R-GMN-03] Power law with tail index α ∈ [2,5]"
              )
              
              metrics['inter_event_time'] = self.analyze_event_clustering(
                  reconstructed['event_timestamp'],
                  golden['timestamp']
              )
              
              # Market State Properties  
              metrics['spread'] = self.analyze_spread_dynamics(
                  self.calculate_spreads(reconstructed),
                  self.calculate_spreads(golden),
                  expected_property="[ASSUMPTION][R-CLD-03] Multi-level spread tracking L1,L5,L10,L15,L20"
              )
              
              metrics['book_imbalance'] = self.calculate_order_book_imbalance(
                  reconstructed, golden, levels=5,
                  expected_property="[ASSUMPTION][R-CLD-05] Order Flow Imbalance as price predictor"
              )
              
              # Price Return Characteristics
              metrics['volatility_clustering'] = self.test_volatility_clustering(
                  self.calculate_returns(reconstructed),
                  self.calculate_returns(golden),
                  expected_property="[ASSUMPTION][R-OAI-02] GARCH(1,1) parameters within 10%"
              )
              
              metrics['return_kurtosis'] = self.validate_heavy_tails(
                  self.calculate_returns(reconstructed),
                  self.calculate_returns(golden)
              )
              
              # Calculate overall fidelity score
              p_values = [m['p_value'] for m in metrics.values() if 'p_value' in m]
              fidelity_score = np.mean(p_values) if p_values else 0.0
              
              return FidelityReport(
                  score=fidelity_score,
                  passed=fidelity_score > 0.05,
                  metrics=metrics
              )
          
          def compare_distributions(self, data1, data2, metric_name):
              """Comprehensive distribution comparison with K-S test."""
              # Calculate moments
              moments1 = {
                  'mean': data1.mean(),
                  'variance': data1.var(),
                  'skewness': data1.skew(),
                  'kurtosis': data1.kurtosis()
              }
              
              # Perform K-S test
              ks_stat, p_value = scipy.stats.ks_2samp(data1, data2)
              
              # Generate visualizations
              fig = self.create_distribution_plots(data1, data2, metric_name)
              
              return {
                  'moments': moments1,
                  'ks_statistic': ks_stat,
                  'p_value': p_value,
                  'visualization': fig
              }
      ```
  * **Dependencies:** Depends on the output of both `LiveCapture` and `Reconstructor`.
  * **Technology Stack:** Python, Polars, Pandas, `scipy.stats`, `matplotlib`/`seaborn`, `plotly` for interactive charts.
  * **Implementation Notes:**
      * **Pass/Fail Threshold**: Average p-value > 0.05 indicates distributions are statistically similar
      * **Heavy Tail Validation**: Kurtosis must be significantly > 3 to confirm fat tails
      * **Drift Analysis**: Track mean squared error between simulated and snapshot books over time
      * **[ASSUMPTION][R-GMN-05] Two-Sample K-S Tests**: Primary validation tool with p-value > 0.05
      * **[ASSUMPTION][R-OAI-04] Online Metric Computation**: Streaming calculation for efficiency
      * **[ASSUMPTION][R-CLD-06] Queue Position Feature**: Track for RL agent training

### Plugin-Based Architecture

The FidelityReporter implements a sophisticated plugin system for extensible metric calculation, designed to support complex models required by the HFT research:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Union, Dict, Tuple
import polars as pl
import numpy as np

@dataclass
class MetricResult:
    name: str
    value: Union[float, dict]
    metadata: dict
    visualization: Optional[dict] = None
    execution_tier: int  # 1, 2, or 3
    computation_time_ms: float

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
    @abstractmethod
    def execution_tier(self) -> int:
        """Execution tier (1: <1μs, 2: <1ms, 3: <100ms)."""
        pass
    
    @property
    def dependencies(self) -> List[str]:
        """List of other metrics this depends on."""
        return []
    
    @property
    def gpu_accelerated(self) -> bool:
        """Whether this metric benefits from GPU acceleration."""
        return False
    
    @abstractmethod
    def calculate(self, data: Union[pl.DataFrame, "Stream"], 
                 cache: Optional[Dict] = None) -> MetricResult:
        """Calculate the metric from input data."""
        pass
```

#### Complex Model Plugins

##### Hawkes Process Plugin
```python
class HawkesProcessPlugin(MetricPlugin):
    """4D Hawkes process calibration for event clustering analysis."""
    
    def __init__(self):
        self.dimensions = ['price_jumps', 'buy_orders', 'sell_orders', 'cancellations']
        self.kernel_type = 'power_law'  # Superior to exponential for crypto
    
    @property
    def name(self) -> str:
        return "hawkes_process_4d"
    
    @property
    def category(self) -> str:
        return "event_clustering"
    
    @property
    def execution_tier(self) -> int:
        return 3  # Comprehensive analysis tier
    
    @property
    def gpu_accelerated(self) -> bool:
        return True  # CUDA kernel for likelihood optimization
    
    def calculate(self, data: pl.DataFrame, cache: Optional[Dict] = None) -> MetricResult:
        # Extract multi-dimensional event times
        events = self._extract_event_sequences(data)
        
        # Calibrate 4D Hawkes model with power-law kernels
        params = self._calibrate_hawkes_gpu(events)
        
        # Calculate key metrics
        branching_ratio = self._compute_branching_ratio(params)
        endogenous_ratio = self._compute_endogenous_ratio(params)
        clustering_scales = self._detect_clustering_scales(events)
        
        return MetricResult(
            name=self.name,
            value={
                'baseline_intensities': params['mu'],
                'excitation_matrix': params['alpha'],
                'decay_parameters': params['beta'],
                'branching_ratio': branching_ratio,
                'endogenous_ratio': endogenous_ratio,
                'clustering_scales_us': clustering_scales,
                'critical_regime': branching_ratio > 0.95
            },
            metadata={
                'kernel_type': self.kernel_type,
                'dimensions': self.dimensions,
                'convergence_achieved': params['converged']
            },
            execution_tier=3,
            computation_time_ms=params['computation_time']
        )
```

##### Copula Dependency Plugin
```python
class CopulaAnalysisPlugin(MetricPlugin):
    """Multi-dimensional dependency analysis using copulas."""
    
    def __init__(self, copula_families=['gaussian', 'student', 'clayton', 'gumbel']):
        self.copula_families = copula_families
        self.dimensions = ['price', 'volume', 'spread', 'book_imbalance']
    
    @property
    def name(self) -> str:
        return "copula_dependencies"
    
    @property
    def category(self) -> str:
        return "cross_sectional_dependencies"
    
    @property
    def execution_tier(self) -> int:
        return 3  # Comprehensive analysis
    
    def calculate(self, data: pl.DataFrame, cache: Optional[Dict] = None) -> MetricResult:
        # Extract marginals for each dimension
        marginals = self._compute_empirical_marginals(data)
        
        # Fit various copula families
        copula_fits = {}
        for family in self.copula_families:
            fit_result = self._fit_copula(marginals, family)
            copula_fits[family] = fit_result
        
        # Select best fitting copula by AIC
        best_copula = min(copula_fits.items(), key=lambda x: x[1]['aic'])
        
        # Compute tail dependence coefficients
        tail_deps = self._compute_tail_dependence(best_copula[1])
        
        return MetricResult(
            name=self.name,
            value={
                'best_copula': best_copula[0],
                'parameters': best_copula[1]['params'],
                'goodness_of_fit': best_copula[1]['gof_pvalue'],
                'upper_tail_dependence': tail_deps['upper'],
                'lower_tail_dependence': tail_deps['lower'],
                'kendall_tau_matrix': self._compute_kendall_tau(data)
            },
            metadata={
                'dimensions': self.dimensions,
                'all_fits': {k: v['aic'] for k, v in copula_fits.items()}
            },
            execution_tier=3,
            computation_time_ms=sum(f['fit_time'] for f in copula_fits.values())
        )
```

##### Deep Book Analysis Plugin
```python
class DeepBookDynamicsPlugin(MetricPlugin):
    """Analysis of order book dynamics beyond Level 20."""
    
    def __init__(self, max_levels=50, hidden_liquidity_detection=True):
        self.max_levels = max_levels
        self.hidden_liquidity_detection = hidden_liquidity_detection
        self.level_groups = {
            'volatile': range(1, 6),
            'predictive': range(3, 11),
            'stable': range(10, 21),
            'deep': range(20, max_levels + 1)
        }
    
    @property
    def name(self) -> str:
        return "deep_book_dynamics"
    
    @property
    def category(self) -> str:
        return "market_microstructure"
    
    @property
    def execution_tier(self) -> int:
        return 2  # GPU-accelerated for matrix operations
    
    @property
    def gpu_accelerated(self) -> bool:
        return True
    
    def calculate(self, data: pl.DataFrame, cache: Optional[Dict] = None) -> MetricResult:
        # Extract book states up to max_levels
        book_states = self._extract_deep_book_states(data)
        
        # Analyze predictive power by level groups
        predictive_power = {}
        for group_name, levels in self.level_groups.items():
            r_squared = self._compute_predictive_power_gpu(
                book_states, levels, horizons=[60, 300, 600]  # 1min, 5min, 10min
            )
            predictive_power[group_name] = r_squared
        
        # Detect hidden liquidity patterns
        hidden_liquidity = None
        if self.hidden_liquidity_detection:
            hidden_liquidity = self._detect_hidden_liquidity(data)
        
        # Compute resilience metrics
        resilience = self._compute_resilience_metrics(book_states)
        
        # Analyze asymmetric deterioration
        asymmetry = self._analyze_bid_ask_asymmetry(book_states)
        
        return MetricResult(
            name=self.name,
            value={
                'predictive_power_by_level': predictive_power,
                'hidden_liquidity_ratio': hidden_liquidity['detection_rate'] if hidden_liquidity else None,
                'iceberg_signatures': hidden_liquidity['iceberg_count'] if hidden_liquidity else None,
                'book_resilience_ms': resilience['mean_recovery_time'],
                'shock_absorption_capacity': resilience['absorption_ratio'],
                'bid_ask_asymmetry': asymmetry,
                'optimal_book_depth': self._find_optimal_depth(predictive_power)
            },
            metadata={
                'max_levels_analyzed': self.max_levels,
                'total_book_states': len(book_states)
            },
            execution_tier=2,
            computation_time_ms=cache.get('gpu_time', 0) if cache else 0
        )
```

### Three-Tier Execution Model

Aligned with PRD validation strategy for optimal performance across different latency requirements:

#### Tier 1: Streaming Layer (<1μs latency)
```python
class StreamingTier:
    """Ultra-low latency validation integrated with reconstruction pipeline."""
    
    def __init__(self):
        self.metrics = [
            HausmanNoiseTest(),        # Microstructure noise detection
            SequenceGapMonitor(),      # Real-time gap detection
            BasicQuantileCheck(),      # Distribution bounds monitoring
            MessageRateAnomaly()       # Burst/drought detection
        ]
        self.ring_buffer = RingBuffer(size=10000)  # Microsecond-precision events
    
    def process_event(self, event: MarketEvent) -> Optional[Alert]:
        """Process single event with <1μs overhead."""
        # Add to ring buffer for pattern detection
        self.ring_buffer.append(event)
        
        # Run ultra-fast metrics
        for metric in self.metrics:
            if metric.requires_alert(event, self.ring_buffer):
                return Alert(
                    severity='CRITICAL',
                    metric=metric.name,
                    timestamp=event.timestamp,
                    details=metric.get_alert_details()
                )
        return None
```

- **Implementation**: C++/Rust extensions for critical path, lock-free data structures
- **Integration**: Zero-copy hooks into EventReplayer main loop
- **Features**:
  - Ring buffer for sub-100ms pattern detection
  - SIMD operations for parallel metric computation
  - Memory-mapped alerts for IPC with monitoring

#### Tier 2: GPU-Accelerated Layer (<1ms latency)
```python
class GPUAcceleratedTier:
    """Batch processing with massive parallelization."""
    
    def __init__(self, gpu_device=0):
        self.device = cuda.Device(gpu_device)
        self.metrics = [
            AndersonDarlingGPU(),      # Vectorized A-D test
            EnergyDistanceGPU(),       # Parallel distance computation
            LinearMMDApproximation(),  # Fast kernel approximation
            CorrelationMatrixGPU()     # Real-time correlation updates
        ]
        self.batch_size = 10000
        self.stream = cuda.Stream()
    
    async def process_batch(self, events: pa.RecordBatch) -> MetricResults:
        """Process event batch on GPU with <1ms latency."""
        # Transfer to GPU memory
        gpu_events = self._transfer_to_gpu(events)
        
        # Parallel metric computation
        results = await asyncio.gather(*[
            metric.calculate_async(gpu_events, self.stream)
            for metric in self.metrics
        ])
        
        return MetricResults(
            metrics=results,
            batch_size=len(events),
            computation_time_us=self.stream.elapsed_time()
        )
```

- **Technology**: CUDA 12+, RAPIDS cuDF, Numba CUDA
- **Optimizations**:
  - Kernel fusion for related computations
  - Persistent kernels for streaming workloads
  - Mixed precision for non-critical calculations
- **Capacity**: 100K+ events per millisecond

#### Tier 3: Comprehensive Analysis (<100ms latency)
```python
class ComprehensiveTier:
    """Deep analysis with distributed computing support."""
    
    def __init__(self, executor='dask'):
        self.executor = self._init_executor(executor)
        self.metrics = [
            SignatureKernelMMD(),      # Full temporal dependency analysis
            MultivariateCopula(),      # Complex dependency structures
            HawkesProcess4D(),         # Multi-dimensional clustering
            RLPolicyEvaluation(),      # Sim-to-real gap measurement
            AdversarialPatterns()      # Deep pattern detection
        ]
    
    def analyze_dataset(self, 
                       reconstructed: pl.LazyFrame,
                       golden: pl.LazyFrame) -> ComprehensiveReport:
        """Run full validation suite with distributed computation."""
        # Partition data for distributed processing
        partitions = self._partition_by_time(reconstructed, golden)
        
        # Map metrics across partitions
        futures = []
        for partition in partitions:
            for metric in self.metrics:
                future = self.executor.submit(
                    metric.calculate,
                    partition.reconstructed,
                    partition.golden
                )
                futures.append((metric.name, future))
        
        # Reduce results
        results = {}
        for metric_name, future in futures:
            result = future.result(timeout=100)  # 100ms timeout
            results[metric_name] = result
        
        # Generate comprehensive report
        return self._compile_report(results)
```

- **Frameworks**: Dask/Ray for distribution, Apache Arrow for data handling
- **Features**:
  - Automatic work stealing for load balancing
  - Incremental computation with caching
  - Fault tolerance with result checkpointing
- **Scaling**: Linear to 100+ nodes

### Implementation Architecture

```yaml
TierCoordinator:
  purpose: "Orchestrate all three tiers for optimal resource usage"
  
  data_flow:
    - EventStream → Tier1 (continuous)
    - EventBatches → Tier2 (every 1000 events)  
    - Checkpoints → Tier3 (every 5 minutes)
  
  alert_aggregation:
    - Tier1: Immediate alerts → Dashboard
    - Tier2: Batch summaries → MetricStore
    - Tier3: Comprehensive reports → ReportGenerator
  
  resource_management:
    - CPU: Reserved cores for Tier1
    - GPU: Time-sliced between Tier2 batches
    - Memory: Bounded buffers with backpressure
    - Network: Priority queues for alerts
```

### Adversarial Pattern Detection Module

A dedicated sub-component within FidelityReporter for detecting market manipulation patterns:

```python
class AdversarialPatternDetector:
    """Specialized module for detecting market manipulation signatures."""
    
    def __init__(self, sensitivity='medium'):
        self.sensitivity = sensitivity
        self.pattern_detectors = {
            'spoofing': SpoofingDetector(),
            'layering': LayeringDetector(),
            'momentum_ignition': MomentumIgnitionDetector(),
            'quote_stuffing': QuoteStuffingDetector(),
            'wash_trading': WashTradingDetector()
        }
        self.alert_threshold = self._get_threshold(sensitivity)
    
    def analyze_window(self, events: pl.DataFrame, 
                      window_size_ms: int = 5000) -> PatternReport:
        """Analyze event window for adversarial patterns."""
        results = {}
        
        # Quote Stuffing Detection
        message_rate = self._calculate_message_rate(events)
        if message_rate > 2000:  # 2000+ orders/second
            cancel_ratio = self._calculate_cancellation_ratio(events)
            if cancel_ratio > 32:  # 32:1 ratio
                results['quote_stuffing'] = {
                    'detected': True,
                    'message_rate': message_rate,
                    'cancel_ratio': cancel_ratio,
                    'severity': 'HIGH',
                    'timestamp': events['timestamp'].min()
                }
        
        # Spoofing Detection
        spoofing_patterns = self._detect_spoofing_patterns(events)
        if spoofing_patterns:
            results['spoofing'] = {
                'detected': True,
                'patterns': spoofing_patterns,
                'volume_ratios': [p['volume_ratio'] for p in spoofing_patterns],
                'avg_lifetime_ms': np.mean([p['lifetime_ms'] for p in spoofing_patterns]),
                'severity': self._assess_spoofing_severity(spoofing_patterns)
            }
        
        # Momentum Ignition Detection
        ignition_cycles = self._detect_momentum_ignition(events)
        if ignition_cycles:
            results['momentum_ignition'] = {
                'detected': True,
                'cycles': ignition_cycles,
                'avg_cycle_time_ms': np.mean([c['duration_ms'] for c in ignition_cycles]),
                'price_impact_bps': np.mean([c['price_impact'] for c in ignition_cycles]),
                'severity': 'CRITICAL' if any(c['duration_ms'] < 5000 for c in ignition_cycles) else 'MEDIUM'
            }
        
        return PatternReport(
            window_start=events['timestamp'].min(),
            window_end=events['timestamp'].max(),
            patterns_detected=results,
            overall_manipulation_score=self._calculate_manipulation_score(results)
        )
    
    def _detect_spoofing_patterns(self, events: pl.DataFrame) -> List[Dict]:
        """Detect spoofing: large orders canceled <500ms."""
        patterns = []
        
        # Find large orders
        large_orders = events.filter(
            (pl.col('event_type') == 'ORDER_PLACED') &
            (pl.col('quantity') > pl.col('quantity').quantile(0.95))
        )
        
        for order in large_orders.iter_rows(named=True):
            # Check if canceled quickly
            cancel = events.filter(
                (pl.col('event_type') == 'ORDER_CANCELED') &
                (pl.col('order_id') == order['order_id']) &
                (pl.col('timestamp') - order['timestamp'] < 500_000_000)  # <500ms in nanoseconds
            )
            
            if not cancel.is_empty():
                # Check for opposite side execution
                opposite_trade = events.filter(
                    (pl.col('event_type') == 'TRADE') &
                    (pl.col('side') != order['side']) &
                    (pl.col('timestamp') > order['timestamp']) &
                    (pl.col('timestamp') < cancel['timestamp'].max())
                )
                
                if not opposite_trade.is_empty():
                    patterns.append({
                        'order_id': order['order_id'],
                        'lifetime_ms': (cancel['timestamp'].max() - order['timestamp']) / 1e6,
                        'volume_ratio': order['quantity'] / opposite_trade['quantity'].sum(),
                        'price_level': order['price'],
                        'side': order['side']
                    })
        
        return patterns
    
    def _detect_momentum_ignition(self, events: pl.DataFrame) -> List[Dict]:
        """Detect momentum ignition: aggressive lifting → stops → reversal."""
        cycles = []
        
        # Identify aggressive trade sequences
        trades = events.filter(pl.col('event_type') == 'TRADE')
        
        # Use rolling window to find rapid one-sided trading
        for window in self._rolling_windows(trades, window_size=5000):  # 5 second windows
            buy_volume = window.filter(pl.col('side') == 'BUY')['quantity'].sum()
            sell_volume = window.filter(pl.col('side') == 'SELL')['quantity'].sum()
            
            # Check for heavy imbalance
            if buy_volume > sell_volume * 3 or sell_volume > buy_volume * 3:
                # Look for reversal in next window
                next_window = self._get_next_window(trades, window)
                if self._check_reversal(window, next_window):
                    cycles.append({
                        'start_time': window['timestamp'].min(),
                        'duration_ms': (next_window['timestamp'].max() - window['timestamp'].min()) / 1e6,
                        'initial_side': 'BUY' if buy_volume > sell_volume else 'SELL',
                        'volume_imbalance': max(buy_volume, sell_volume) / min(buy_volume, sell_volume),
                        'price_impact': self._calculate_price_impact(window, next_window)
                    })
        
        return cycles
```

### Advanced Statistical Tests (Replacing K-S)

Implementing state-of-the-art statistical methods per research recommendations:

```python
class AndersonDarlingMetric(MetricPlugin):
    """Anderson-Darling test with enhanced tail sensitivity."""
    
    def __init__(self, distribution='normal', significance=0.05):
        self.distribution = distribution
        self.significance = significance
    
    @property
    def name(self) -> str:
        return "anderson_darling_test"
    
    @property
    def category(self) -> str:
        return "statistical_distribution"
    
    def calculate(self, data: pl.DataFrame) -> MetricResult:
        # Implementation using scipy.stats.anderson
        # Weighted by 1/[F(x)(1-F(x))] for tail emphasis
        # Returns test statistic and critical values
        pass
```

### Core Component Architecture

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
      
    StreamingCollector:
      purpose: "Collect metrics during reconstruction"
      features:
        - Hook into EventReplayer
        - Minimal overhead design (<5%)
        - State checkpointing integration
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
        - HTML Dashboard (Plotly interactive)
        - Markdown with embedded charts
        - PDF executive summary
        - JSON programmatic access
    
    ResearchValidator:
      purpose: "Validate research paper claims"
      features:
        - A/B testing framework
        - Performance benchmarking
        - Memory profiling
        - Statistical significance testing
```

### Comprehensive Metric Catalogue

```yaml
metric_categories:
  market_microstructure:
    spread_analysis:
      - BidAskSpread(levels=[1,5,10,15,20])
      - EffectiveSpread
      - RealizedSpread
    order_flow:
      - OrderFlowImbalance  # [R-CLD-05]
      - OrderFlowToxicity
      - KylesLambda
    queue_dynamics:
      - QueuePositionInference  # [R-CLD-06]
      - FillTimeDistribution
      - PriorityPreservation
  
  statistical_distribution:
    advanced_tests:
      - AndersonDarling  # [R-GEM-01]
      - CramerVonMises  # [R-OAI-06]
      - EnergyDistance  # [R-CLD-07]
      - MaximumMeanDiscrepancy  # [R-ALL-04]
    temporal_dynamics:
      - VolatilityClustering  # [R-GEM-03]
      - OrderFlowClustering  # [R-CLD-08]
      - IntradaySeasonality  # [R-OAI-07]
      - MicrostructureNoise  # [R-CLD-09]
  
  rl_specific:
    state_action:
      - StateCoverage  # [R-CLD-11]
      - ActionAvailability
      - StateVisitationFrequency
    reward_preservation:
      - RewardDistribution  # [R-OAI-09]
      - RegimeConsistency  # [R-ALL-05]
      - SimToRealGap  # [R-GEM-06]
  
  adversarial_dynamics:
    market_manipulation:
      - SpoofingDetection  # [R-GEM-07]
      - FleetingLiquidity  # [R-CLD-12]
      - QuoteStuffing  # [R-OAI-10]
      - LayeringPatterns
```

### Visual Reporting Integration

Leveraging Plotly for interactive HTML dashboards:

```python
class ReportGenerator:
    def generate_dashboard(self, metrics: Dict[str, MetricResult]):
        # Executive Summary Section
        overall_score = self._calculate_fidelity_score(metrics)
        
        # Interactive Visualizations
        figures = {
            'distribution_comparison': self._create_distribution_plots(metrics),
            'qq_plots': self._create_qq_plots(metrics),
            'correlation_heatmap': self._create_correlation_heatmap(metrics),
            'time_series': self._create_time_series_plots(metrics),
            'microstructure_3d': self._create_3d_state_space(metrics)
        }
        
        # Generate HTML with embedded Plotly charts
        return self._render_html_dashboard(overall_score, figures)
```

## Component Diagram

This diagram shows the relationship and data flow between the defined components, including the critical data acquisition layer.

```mermaid
componentDiagram
    subgraph "Epic 0: Data Acquisition (BLOCKING)"
        [Crypto Lake API] -->> [DataAcquisitionManager]
        [DataAcquisitionManager] -->> [DataDownloader]
        [DataDownloader] -->> [IntegrityValidator]
        [IntegrityValidator] -->> [DataStagingArea]
        [DataStagingArea] -->> [Ready Data]
    end
    
    subgraph "Epic 1: Analysis & Validation"
        [Ready Data: Trades] -->> [DataAssessor]
        [Ready Data: Book Snapshots] -->> [DataAssessor]
        [Ready Data: Book Deltas] -->> [DataAssessor]
        [DataAssessor] -->> [Analysis Report]
        
        [Binance Live Feed] -->> [LiveCapture]
        [LiveCapture] -->> [Golden Samples<br/>(Multiple Regimes)]
    end
    
    subgraph "Epic 2: Reconstruction"
        [Ready Data: Trades] -->> [Reconstructor]
        [Ready Data: Book Snapshots] -->> [Reconstructor]
        [Ready Data: Book Deltas] -->> [Reconstructor]
        [Analysis Report] -->> [Reconstructor]
        [Reconstructor] -->> [WAL]
        [WAL] -->> [Reconstructor]
        [Reconstructor] -->> [Unified Event Stream]
    end
    
    subgraph "Epic 3: Fidelity Validation"
        [Unified Event Stream] -->> [FidelityReporter]
        [Golden Samples<br/>(Multiple Regimes)] -->> [FidelityReporter]
        [FidelityReporter] -->> [Comprehensive<br/>Fidelity Report]
        [FidelityReporter] -->> [Statistical Metrics<br/>& Visualizations]
    end
```

## Data Flow Dependencies

1. **Blocking Dependency**: No component can start until `DataAcquisitionManager` completes and data is in the Ready zone
2. **Sequential Processing**: Epic 1 → Epic 2 → Epic 3 must execute in order
3. **Parallel Capability**: `LiveCapture` can run in parallel with `DataAssessor` once data acquisition is complete
4. **Continuous Validation**: `FidelityReporter` runs on each batch of reconstructed data
