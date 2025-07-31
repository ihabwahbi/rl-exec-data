# High Level Architecture

**Last Updated**: 2025-07-31  
**Status**: Updated with Epic 3 architecture and validated findings

## Executive Summary

The RLX Co-Pilot Data Pipeline architecture has successfully guided the implementation of Epic 0 (Data Acquisition), Epic 1 (Validation), and Epic 2 (Reconstruction). With real Crypto Lake data now accessible and validated, the architecture provides proven patterns while maintaining the critical lessons learned about data-first development.

## Critical Architecture Decisions

### 1. Data-First Blocking Gate ✅ VALIDATED
**Decision**: No development, validation, or analysis work can begin until actual historical data is acquired from Crypto Lake.

**Rationale**: Synthetic data validation creates false confidence and leads to months of wasted effort when real data behaves differently.

**Implementation**: 
- Epic 0 successfully blocked other work until completion
- DataAcquisitionManager implemented with lakeapi integration
- Data staging area proven effective with 2.3M+ records

### 2. Paradigm Bridge Pattern
**Decision**: Implement Chronological Event Replay algorithm to bridge the gap between Crypto Lake's snapshot-based historical data and Binance's differential real-time feeds.

**Rationale**: The two data sources have fundamentally different paradigms that must be reconciled for high-fidelity reconstruction.

**Implementation**:
- 4-step algorithm: Ingestion → Unification → Normalization → Stateful Replay
- Origin_time as universal clock
- Stable sort to preserve event ordering
- Order book state management with drift tracking

### 3. Market Regime Awareness
**Decision**: Capture and validate across multiple market conditions (high volume, low volume, special events).

**Rationale**: Market behavior varies dramatically across different regimes; validation on only one regime creates blind spots.

**Implementation**:
- LiveCapture with MarketRegimeDetector
- Multi-session capture strategy (24-48h per regime)
- Separate golden samples for each regime

### 4. Comprehensive Fidelity Validation
**Decision**: Implement full metrics catalogue beyond K-S tests, including advanced statistical tests and microstructure analysis.

**Rationale**: Simple price/volume checks miss critical market dynamics that affect RL agent training.

**Implementation**:
- Three-tier validation architecture (Streaming, GPU, Comprehensive)
- Advanced tests: Anderson-Darling, Energy Distance, MMD
- Interactive HTML dashboards with Plotly
- p-value > 0.05 threshold for statistical similarity

### 5. Memory-Bounded Processing
**Decision**: Maintain only top 20 order book levels in memory with streaming fallback.

**Rationale**: Must process 220GB/month of data within 28GB RAM constraint.

**Implementation**:
- Bounded dictionaries for order book
- Streaming mode for large datasets
- Write-ahead log for recovery
- Backpressure handling

## Key Architectural Principles

1. **Reality First**: All work grounded in actual market data
2. **Fidelity Maximization**: Every decision optimizes statistical similarity
3. **Memory Awareness**: Bounded processing within hardware constraints
4. **Fail Fast**: Early validation gates prevent wasted effort
5. **Comprehensive Validation**: Multiple metrics across all market regimes

## Technical Summary

The system will be architected as a modular, command-line-driven ETL (Extract, Transform, Load) pipeline written in Python. **Critical prerequisite**: The pipeline cannot begin any processing until actual historical data is acquired from Crypto Lake through a dedicated data acquisition layer. The architecture implements a "data-first, validation-second" approach, with Epic 0 establishing data access as the blocking gate for all subsequent work. 

**Validated Architecture**: Epic 1 has proven all critical assumptions with real data. The pipeline will use the FullReconstruction strategy based on perfect delta feed quality (0% gaps in 11.15M messages). Performance validation shows 12.97M events/sec capability (130x requirement) with memory usage of only 1.67GB for 8M events (14x safety margin). The system bridges the paradigm gap between Crypto Lake's snapshot-based historical data and Binance's differential real-time feeds through validated streaming architecture.

## High-Level Project Diagram

This diagram illustrates the flow of data through the major components of the pipeline, corresponding to the epics defined in the PRD. Note the critical Epic 0 which blocks all subsequent work.

```mermaid
graph TD
    subgraph "Epic 0: Data Acquisition [BLOCKING]"
        Z1[Crypto Lake API Access] --> Z2[DataAcquisitionManager]
        Z2 --> Z3[Download & Validate]
        Z3 --> Z4[Data Staging Area]
        Z4 --> Z5{Data Ready?}
        Z5 -->|No| Z6[BLOCK ALL WORK]
        Z5 -->|Yes| Z7[Enable Epic 1]
    end

    subgraph "Staged Data Sources"
        A1[Validated Trades Data]
        A2[Validated Book Snapshots]
        A3[Validated Book Deltas<br>(book_delta_v2)]
    end

    subgraph "Epic 1: Analysis & Validation"
        B(DataAssessor<br>Analyzes all data sources)
        C(LiveCapture<br>Multiple market regimes)
        D[Analysis Report<br>& Strategy Selection]
        E[Golden Samples<br>High/Low/Special Events]
    end

    subgraph "Epic 2: Reconstruction Pipeline"
        F(Reconstructor<br>Chronological Event Replay)
        G[WAL<br>Write-Ahead Log]
        H[Unified Event Stream<br>Decimal128 Parquet]
    end

    subgraph "Epic 3: Fidelity Reporting"
        I(FidelityReporter<br>Plugin-based metric system<br>3-tier execution model)
        J[Comprehensive Fidelity Report<br>Advanced Statistical Tests, RL Metrics<br>Interactive HTML Dashboards]
    end

    Z7 --> A1
    Z7 --> A2
    Z7 --> A3
    
    A1 --> B
    A2 --> B
    A3 --> B
    B --> D
    
    C --> E
    
    A1 --> F
    A2 --> F
    A3 --> F
    D --> F
    F <--> G
    F --> H
    
    H --> I
    E --> I
    I --> J
```

## Architectural and Design Patterns

  * **Data-First Architecture:** No processing can begin without actual historical data. Epic 0 implements a blocking gate pattern that prevents synthetic data validation and ensures all work is grounded in reality.
  
  * **Paradigm Bridge Pattern:** The architecture explicitly addresses the fundamental challenge of reconciling two different data paradigms:
    - **Historical (Crypto Lake)**: Separate tables, periodic snapshots, exchange timestamps
    - **Live (Binance)**: Interleaved stream, differential updates, guaranteed chronological ordering
    - The Chronological Event Replay algorithm bridges this gap through sophisticated state management
  
  * **ETL (Extract, Transform, Load):** The entire system is a classic ETL pipeline, extracting raw data, transforming it into the unified schema, and loading it into a final set of processed Parquet files.
  
  * **Strategy Pattern:** The `Reconstructor` component implements this pattern with a core interface for data reconstruction and three concrete strategies:
    1.  `FullEventReplayStrategy` (preferred): Uses `book_delta_v2` data to replay every market event, maintaining complete order book state. Processes deltas in monotonic `update_id` order with sequence gap detection.
    2.  `SnapshotAnchoredStrategy`: Fallback when deltas are unavailable. Uses 100ms book snapshots as anchors and places trades within appropriate windows.
    3.  `OriginTimeSortStrategy`: Simple time-based merge when `origin_time` is highly reliable (>95%) and deltas are unavailable.
        
    The strategy selection is automated based on the `DataAssessor` findings, prioritizing microstructure fidelity.
    
  * **Chronological Event Replay:** The core algorithm that enables high-fidelity reconstruction:
    1. **Data Ingestion & Labeling**: Tag all events by type
    2. **Unification & Stable Sort**: Merge all events using origin_time as master clock
    3. **Schema Normalization**: Transform to unified schema
    4. **Stateful Replay**: Maintain order book state, apply trades, validate with snapshots
    
  * **Market Regime Awareness:** The `LiveCapture` component specifically captures different market conditions (high volume, low volume, special events) to ensure comprehensive validation across all market states.
  
  * **Fidelity-Driven Validation:** Every component is designed to maximize and validate statistical fidelity:
    - Comprehensive metrics catalogue (K-S tests, microstructure analysis)
    - Multiple validation points throughout the pipeline
    - Continuous quality assurance with automated reporting
  
  * **Monorepo:** As specified in the PRD, all code for the different components (Analyzer, Reconstructor, etc.) will be organized within a single Git repository to simplify dependency management and code sharing.
  
  * **Memory-Bounded Processing:** The architecture enforces strict memory constraints to operate within 28GB usable RAM:
    - Order books maintain only top 20 levels in memory using bounded dictionaries
    - Deeper levels tracked with lossy counters for volume statistics
    - Streaming mode activated when processing would exceed memory limits
    - Write-ahead log ensures recovery without full data reload
    
  * **Precision-First Design:** All price/quantity data stored as decimal128(38,18) in Parquet, with float conversion only at ML boundaries.
