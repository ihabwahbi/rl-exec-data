# Components

The data pipeline will be composed of four primary components, each implemented as a distinct Python module with a clear CLI interface.

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

## Component 3: `Reconstructor`

  * **Responsibility:** This is the core ETL engine implementing the **Chronological Event Replay** algorithm (as defined in Epic 2 and research). It ingests raw Crypto Lake data, applies sophisticated reconstruction to bridge the paradigm gap between snapshot-based historical data and differential live feeds, creating a high-fidelity unified event stream.
  * **Key Interfaces:**
      * **Input:** 
        - Path to raw Crypto Lake data (trades, book snapshots, book_delta_v2)
        - Chosen reconstruction strategy: 
          - `full_event_replay` (preferred): Uses book_delta_v2 for complete microstructure
          - `snapshot_anchored`: Falls back to 100ms snapshots if deltas unavailable
          - `origin_time_sort`: Simple time-based merge if origin_time is reliable
      * **Output:** Processed data conforming to the "Unified Market Event" schema, stored in partitioned Parquet files with decimal128(38,18) precision.
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
      * **Sequence Gap Detection**: Monitors update_id continuity, recovers from snapshots on gaps
      * **Write-Ahead Log (WAL)**: Ensures crash recovery without data corruption
      * **Streaming Mode**: Processes data in chunks if memory constraints are exceeded
      * **Monotonic Ordering**: Ensures update_id ordering within same timestamp
  * **Dependencies:** Relies on the analysis report from `DataAssessor` to select its operational strategy.
  * **Technology Stack:** Python, Polars, PyArrow (for decimal types or int64 pips fallback), Parquet (for simple WAL segments - avoiding RocksDB C++ dependency).
  * **Implementation Notes:**
      * **Bounded Async Queue**: Use `asyncio.Queue(maxsize=2000)` between parser and order book engine to prevent OOM
      * **WAL Design**: Simple append-only Parquet segments with atomic "DONE" markers for crash recovery
      * **Decimal Strategy**: If Polars decimal128 ops fail performance tests, use int64 pips (price * 10^8) internally
      * **Stable Sort Critical**: Must use stable sort to preserve event ordering within same timestamp

## Component 4: `FidelityReporter`

  * **Responsibility:** To automate comprehensive quality assurance implementing the full **Fidelity Validation Metrics Catalogue** from the research (as defined in Epic 3). It performs deep statistical and microstructure validation between reconstructed historical data and golden samples to ensure the backtesting environment is a faithful replica of reality.
  * **Key Interfaces:**
      * **Input:** 
        - Path to the reconstructed data (Unified Event Stream)
        - Path to the golden sample data (minimum 24 hours, multiple market regimes)
        - Validation configuration (thresholds, metrics to compute)
      * **Output:** A comprehensive Fidelity Report in Markdown/HTML format with:
        - **Executive Summary**: Fidelity Score (weighted average of p-values), PASS/FAIL determination
        - **Order Flow Dynamics Metrics**:
          - Trade Size Distribution: Histogram, moments (mean, variance, skew, kurtosis), K-S test
          - Inter-Event Time Distribution: Event clustering analysis, K-S test, Hawkes process fit
        - **Market State Properties Metrics**:
          - Bid-Ask Spread Distribution: Time series, histogram, K-S test
          - Top-of-Book Depth Distribution: Liquidity analysis, K-S test
          - Order Book Imbalance: OI = (V_bid - V_ask)/(V_bid + V_ask), predictive power analysis
        - **Price Return Characteristics**:
          - Volatility Clustering: Autocorrelation of squared log-returns corr(r²_t, r²_{t+τ})
          - Heavy Tails of Returns: Kurtosis validation (should be > 3 for leptokurtic distribution)
        - **Microstructure Parity Metrics**:
          - Sequence gap count and distribution analysis
          - Best bid/ask RMS error vs golden sample (per 10ms window)
          - Per-level depth correlation (Pearson ρ for levels 1-20)
          - Book drift quantification from snapshot resynchronization
        - **Visual Reports**: Side-by-side distribution plots, Q-Q plots, correlation heatmaps
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
                  metric_name="Trade Size Distribution"
              )
              
              metrics['inter_event_time'] = self.analyze_event_clustering(
                  reconstructed['event_timestamp'],
                  golden['timestamp']
              )
              
              # Market State Properties  
              metrics['spread'] = self.analyze_spread_dynamics(
                  self.calculate_spreads(reconstructed),
                  self.calculate_spreads(golden)
              )
              
              metrics['book_imbalance'] = self.calculate_order_book_imbalance(
                  reconstructed, golden, levels=5
              )
              
              # Price Return Characteristics
              metrics['volatility_clustering'] = self.test_volatility_clustering(
                  self.calculate_returns(reconstructed),
                  self.calculate_returns(golden)
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
