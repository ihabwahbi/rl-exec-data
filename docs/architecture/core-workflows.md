# Core Workflows

**Created**: 2025-07-30  
**Status**: Initial Design  
**Purpose**: Visual documentation of key data flows through the pipeline

## Overview

This document provides detailed sequence diagrams for the core workflows in the RLX Data Pipeline. These diagrams illustrate the interaction between components and the flow of data through each major process.

## Workflow 1: End-to-End Data Reconstruction

This workflow shows how raw Crypto Lake data is transformed into a unified event stream through the reconstruction pipeline.

```mermaid
sequenceDiagram
    participant DI as DataIngestion
    participant ER as EventReplayer
    participant OBE as OrderBookEngine
    participant CM as CheckpointManager
    participant DS as DataSink
    participant WAL as Write-Ahead Log
    
    Note over DI,DS: Epic 2 - Core Reconstruction Pipeline
    
    DI->>DI: Load configuration
    DI->>DI: Initialize readers (trades, book, deltas)
    
    loop For each micro-batch (1000 events)
        DI->>ER: Send batch of raw events
        Note right of DI: Events tagged by type:<br/>TRADE, BOOK_SNAPSHOT, BOOK_DELTA
        
        ER->>ER: Sort by origin_time (stable sort)
        ER->>ER: Normalize to unified schema
        
        loop For each event in chronological order
            ER->>OBE: Process event
            
            alt Event is BOOK_SNAPSHOT
                OBE->>OBE: Calculate drift if initialized
                OBE->>OBE: Resynchronize book state
                OBE-->>ER: Return drift metrics
            else Event is TRADE
                OBE->>OBE: Apply liquidity consumption
                OBE->>OBE: Update book levels
                OBE-->>ER: Return updated state
            else Event is BOOK_DELTA
                OBE->>OBE: Validate sequence (update_id)
                OBE->>OBE: Apply differential update
                OBE-->>ER: Return updated state
            end
            
            ER->>ER: Enrich event with book state
            ER->>WAL: Write event to WAL
        end
        
        ER->>DS: Send enriched batch
        DS->>DS: Convert to Parquet format
        DS->>DS: Ensure decimal128 precision
        
        alt Time for checkpoint
            ER->>CM: Request checkpoint
            CM->>OBE: Get book state snapshot
            CM->>ER: Get replay position
            CM->>CM: Create COW checkpoint
            CM-->>ER: Checkpoint complete
            Note right of CM: <100ms checkpoint creation
        end
        
        DS->>DS: Write to partitioned file
        DS->>DS: Update manifest
        DS-->>ER: Batch complete
    end
    
    DS->>DS: Finalize output files
    DS->>DS: Generate completion report
```

### Key Points:
- **Micro-batching**: Processes 1000 events at a time for optimal performance
- **Stable Sort**: Preserves order for events with same timestamp
- **State Management**: Order book maintains full L2 state throughout
- **Checkpointing**: Non-blocking COW snapshots every N batches
- **Precision**: Decimal128(38,18) maintained end-to-end

## Workflow 2: Fidelity Validation Process

This workflow illustrates how the FidelityReporter validates reconstructed data against golden samples using the advanced three-tier validation architecture aligned with HFT research requirements.

```mermaid
sequenceDiagram
    participant RC as Reconstructor
    participant FR as FidelityReporter
    participant TC as TierCoordinator
    participant T1 as Tier1<br/>Streaming<br/>(<1μs)
    participant T2 as Tier2<br/>GPU-Accelerated<br/>(<1ms)
    participant T3 as Tier3<br/>Comprehensive<br/>(<100ms)
    participant ME as MetricEngine
    participant RG as ReportGenerator
    participant DB as Dashboard
    
    Note over RC,DB: Epic 3 - Advanced Fidelity Validation with HFT Phenomena
    
    RC->>FR: Initialize validation hooks
    FR->>TC: Setup three-tier architecture
    TC->>T1: Initialize streaming metrics
    TC->>T2: Allocate GPU resources
    TC->>T3: Setup distributed compute
    
    Note over T1: Streaming Tier Metrics:
    Note over T1: • Hausman noise test
    Note over T1: • Sequence gap monitoring  
    Note over T1: • Message rate anomaly
    Note over T1: • Basic quantile checks
    
    Note over T2: GPU-Accelerated Metrics:
    Note over T2: • Anderson-Darling (vectorized)
    Note over T2: • Energy Distance
    Note over T2: • Linear MMD approximation
    Note over T2: • Real-time correlations
    Note over T2: • Deep book analysis (L1-50)
    
    Note over T3: Comprehensive Metrics:
    Note over T3: • 4D Hawkes processes
    Note over T3: • Copula dependencies
    Note over T3: • Signature kernel MMD
    Note over T3: • RL state coverage
    Note over T3: • Adversarial patterns
    
    loop Continuous Processing
        RC->>T1: Stream market events
        
        par Tier 1 Processing
            T1->>T1: Ring buffer append
            T1->>T1: <1μs metric checks
            alt Critical anomaly detected
                T1->>DB: Immediate alert
                T1->>TC: Trigger investigation
            end
            T1-->>ME: Streaming statistics
        and Tier 2 Batch Processing
            RC->>T2: Batch (10K events)
            T2->>T2: GPU memory transfer
            T2->>T2: Parallel computation
            T2->>T2: Statistical tests
            T2->>T2: Book dynamics
            T2-->>ME: Batch results
        and Tier 3 Deep Analysis
            RC->>T3: Checkpoint data
            T3->>T3: Distributed processing
            T3->>T3: Hawkes calibration
            T3->>T3: Copula fitting
            T3->>T3: Hidden liquidity
            T3->>T3: Pattern detection
            T3-->>ME: Comprehensive results
        end
        
        ME->>ME: Aggregate metrics
        ME->>DB: Update live dashboard
    end
    
    Note over ME,RG: Validation Completion
    
    ME->>ME: Calculate final scores
    ME->>ME: Check thresholds
    
    Note over ME: Critical Thresholds:
    Note over ME: • Anderson-Darling p > 0.05
    Note over ME: • Energy distance < 0.01
    Note over ME: • State coverage > 95%
    Note over ME: • Sim-to-real gap < 5%
    Note over ME: • Endogenous ratio ~80%
    
    ME->>RG: Complete metric results
    
    par Report Generation
        RG->>RG: Statistical visualizations
        RG->>RG: Event clustering heatmaps
        RG->>RG: Book depth analysis
        RG->>RG: Adversarial patterns
        RG->>RG: 3D state space
        RG->>RG: Regime analysis
    and Score Calculation
        RG->>RG: Weight metrics by tier
        RG->>RG: Apply criticality factors
        RG->>RG: Compute overall score
    end
    
    RG->>RG: Generate outputs
    Note right of RG: • HTML Dashboard
    Note right of RG: • PDF Executive Summary
    Note right of RG: • JSON API Response
    Note right of RG: • Grafana Metrics
    
    RG-->>DB: Final report ready
    
    alt Overall PASS
        DB->>DB: Show success
        DB->>DB: Display scores by category
        DB->>DB: Highlight strengths
    else Overall FAIL
        DB->>DB: Show failure details
        DB->>DB: Identify problem metrics
        DB->>DB: Suggest remediations
        DB->>DB: Show drift analysis
    end
```

### Key Architectural Points:

#### Data Flow Optimization
- **Zero-Copy Integration**: Tier 1 hooks directly into Reconstructor's event stream
- **Parallel Execution**: All three tiers process concurrently on different data windows
- **Backpressure Handling**: Each tier signals capacity to prevent overload
- **Memory Bounded**: Fixed buffers with spillover to disk under pressure

#### Latency Guarantees
- **Tier 1 (<1μs)**: C++/Rust extensions, lock-free structures, SIMD operations
- **Tier 2 (<1ms)**: CUDA kernels, persistent GPU contexts, kernel fusion
- **Tier 3 (<100ms)**: Distributed compute, work stealing, incremental updates

#### HFT Phenomena Validation
- **Event Clustering**: Multi-scale detection at 10μs, 1-5ms, 100μs windows
- **Deep Book Dynamics**: Full 50-level analysis with hidden liquidity detection
- **Adversarial Patterns**: Real-time flagging of spoofing, layering, momentum ignition
- **Microstructure Preservation**: Hawkes processes, copulas, regime transitions

#### Performance Characteristics
- **Throughput**: Maintains 336K+ messages/second with <5% overhead
- **Scalability**: Linear scaling to 100+ GPU nodes for Tier 2/3
- **Resilience**: Graceful degradation under resource constraints
- **Observability**: Full metrics export via OpenTelemetry

## Workflow 3: Integrated Fidelity Refinement (IFR) Loop

This workflow illustrates the complete IFR process for Epic 3, showing how validation failures drive systematic improvements in the Reconstructor through a data-driven feedback loop.

```mermaid
sequenceDiagram
    participant SM as Scrum Master
    participant FR as FidelityReporter
    participant ME as MetricEngine
    participant TT as Triage Team
    participant RT as ReconstructorTuner
    participant RC as Reconstructor
    participant BL as Backlog
    participant CD as Convergence<br/>Dashboard
    
    Note over SM,CD: Integrated Fidelity Refinement (IFR) Workflow
    
    rect rgb(240, 240, 255)
        Note over SM,BL: Sprint Planning (Every 2 Weeks)
        SM->>BL: Review FVS-prioritized items
        SM->>SM: Balance allocation:
        Note right of SM: • 30-40% Defects
        Note right of SM: • 50-60% New Metrics
        Note right of SM: • 10-20% Tech Debt
        SM->>BL: Pull items for sprint
    end
    
    loop Daily IFR Cycle
        rect rgb(255, 240, 240)
            Note over FR,ME: Validation Execution
            FR->>RC: Request reconstructed data
            RC-->>FR: Latest output batch
            FR->>ME: Run validation suite
            ME->>ME: Execute all tiers
            ME-->>FR: Metric results
        end
        
        alt Validation FAIL Detected
            rect rgb(255, 255, 240)
                Note over FR,TT: Triage & Root Cause Analysis
                FR->>TT: Alert: Metric failure
                Note right of FR: Failing metric: [Name]
                Note right of FR: Severity: CRITICAL
                Note right of FR: Value: Actual vs Expected
                
                TT->>TT: Initial diagnosis
                Note over TT: Apply Five Whys:
                Note over TT: 1. Why failed? → Distribution mismatch
                Note over TT: 2. Why mismatch? → Clustering absent
                Note over TT: 3. Why absent? → Hawkes params wrong
                Note over TT: 4. Why wrong? → Baseline too low
                Note over TT: 5. Root cause identified
                
                TT->>TT: Categorize failure
                
                alt Reconstructor Flaw
                    TT->>BL: Create Fidelity Defect story
                    Note right of TT: FVS Score calculated:
                    Note right of TT: Impact × Confidence / Effort
                    TT->>RT: Send tuning hints
                else FidelityReporter Bug
                    TT->>BL: Create bug ticket
                    TT->>FR: Mark metric for fix
                else Golden Sample Issue
                    TT->>BL: Create data analysis task
                    TT->>FR: Adjust thresholds
                else Environment Issue
                    TT->>SM: Escalate to DevOps
                end
            end
            
            rect rgb(240, 255, 240)
                Note over RT,RC: Automated Tuning
                RT->>RT: Analyze failure pattern
                RT->>RT: Calculate adjustments
                Note right of RT: Example adjustments:
                Note right of RT: • hawkes_excitation *= 1.1
                Note right of RT: • resilience_factor *= 1.2
                Note right of RT: • noise_std *= 1.5
                
                RT->>RC: Apply parameter updates
                RC->>RC: Update configuration
                RC->>RC: Re-run reconstruction
                RC-->>FR: New output ready
            end
            
        else Validation PASS
            FR->>CD: Update metrics
            CD->>CD: Update burn-up chart
            CD->>CD: Calculate convergence %
        end
        
        rect rgb(240, 240, 240)
            Note over BL,CD: Progress Tracking
            BL->>BL: Update story status
            CD->>CD: Refresh dashboard
            Note right of CD: Metrics shown:
            Note right of CD: • Fidelity Score: X%
            Note right of CD: • Tests Passing: Y/Z
            Note right of CD: • Convergence Rate
            Note right of CD: • Defect Burn Rate
        end
    end
    
    rect rgb(240, 255, 255)
        Note over SM,CD: Sprint Review
        SM->>CD: Show convergence progress
        CD-->>SM: Burn-up chart
        FR->>SM: Demo new metrics (failures expected)
        FR->>SM: Show fixed metrics (now passing)
        SM->>SM: Gather stakeholder feedback
    end
    
    rect rgb(255, 240, 255)
        Note over SM,TT: Sprint Retrospective
        SM->>TT: Review triage accuracy
        TT-->>SM: RCA success rate
        SM->>RT: Review tuning effectiveness
        RT-->>SM: Parameter convergence data
        SM->>SM: Identify process improvements
    end
    
    Note over SM,CD: Epic 3 Complete when:
    Note over SM,CD: • 100% metrics implemented
    Note over SM,CD: • 100% pass rate sustained 24-48hrs
    Note over SM,CD: • Documentation complete
```

### IFR Process Key Points:

#### Feedback Loop Characteristics
- **Latency**: <2 hours from failure detection to fix deployment
- **Automation**: 80% of parameter adjustments automated
- **Learning**: Each iteration improves tuning heuristics
- **Convergence**: Typically 20-30 iterations to reach 95% pass rate

#### Triage Decision Tree
```
Failure Detected
├── Reconstructor Issue (60%)
│   ├── Parameter Tuning (40%) → Automated adjustment
│   ├── Logic Bug (15%) → Developer fix required
│   └── Design Flaw (5%) → Architecture review
├── Test Issue (20%)
│   ├── Threshold Too Strict (15%) → Calibrate with golden
│   └── Implementation Bug (5%) → Fix test code
├── Data Issue (15%)
│   ├── Golden Sample Anomaly (10%) → Filter or accommodate
│   └── Source Data Gap (5%) → Document limitation
└── Environment (5%)
    └── Infrastructure Problem → DevOps escalation
```

#### FVS Scoring Example
```python
# Fidelity Defect: Hawkes branching ratio too low
Impact = 85  # Critical for event clustering
Confidence = 70  # High likelihood of fixing multiple tests
Effort = 5  # Medium complexity
FVS = (85 × 70) / 5 = 1190

# New Metric: Copula dependency test
Impact = 60  # Important but not critical
Confidence = 40  # Covers new validation area
Effort = 8  # Complex implementation
FVS = (60 × 40) / 8 = 300
```

#### Convergence Patterns
- **Week 1-2**: Rapid progress (40-60% pass rate)
- **Week 3-4**: Slower gains (60-80% pass rate)
- **Week 5-6**: Fine tuning (80-95% pass rate)
- **Week 7-8**: Final convergence (95-100% pass rate)

## Workflow 4: Multi-Symbol Processing

This workflow shows how the pipeline handles multiple trading symbols concurrently.

```mermaid
sequenceDiagram
    participant MP as Main Process
    participant SR as Symbol Router
    participant W1 as Worker-1<br/>(BTCUSDT)
    participant W2 as Worker-2<br/>(ETHUSDT)
    participant WN as Worker-N<br/>(Symbol-N)
    participant DS as Shared DataSink
    
    Note over MP,DS: Multi-Symbol Architecture
    
    MP->>MP: Parse command line args
    MP->>MP: Determine symbol list
    MP->>SR: Initialize router
    
    SR->>W1: Spawn worker process
    SR->>W2: Spawn worker process
    SR->>WN: Spawn worker process
    
    Note over SR: Create IPC queues (1000 msg buffer each)
    
    loop For each input batch
        MP->>MP: Read raw data batch
        MP->>MP: Parse messages
        
        loop For each message
            MP->>SR: Route message by symbol
            
            alt Symbol == BTCUSDT
                SR->>W1: Queue.put(message)
            else Symbol == ETHUSDT
                SR->>W2: Queue.put(message)
            else Other symbol
                SR->>WN: Queue.put(message)
            end
        end
    end
    
    Note over W1,WN: Each worker runs complete pipeline
    
    par Worker 1 Pipeline
        W1->>W1: Run EventReplayer
        W1->>W1: Maintain order book
        W1->>W1: Generate events
        W1->>DS: Write Parquet
    and Worker 2 Pipeline
        W2->>W2: Run EventReplayer
        W2->>W2: Maintain order book
        W2->>W2: Generate events
        W2->>DS: Write Parquet
    and Worker N Pipeline
        WN->>WN: Run EventReplayer
        WN->>WN: Maintain order book
        WN->>WN: Generate events
        WN->>DS: Write Parquet
    end
    
    Note over DS: Atomic file operations prevent conflicts
    
    DS->>DS: Manage partitions by symbol
    DS->>DS: Update global manifest
    DS->>DS: Ensure consistency
```

### Key Points:
- **Process Isolation**: Each symbol runs in separate process (avoids GIL)
- **Linear Scaling**: Performance scales with number of CPU cores
- **Backpressure**: Queue size limits prevent memory overflow
- **Atomic Writes**: Shared DataSink handles concurrent access safely

## Workflow 4: Checkpoint and Recovery

This workflow demonstrates the checkpoint creation and recovery process.

```mermaid
sequenceDiagram
    participant ER as EventReplayer
    participant CM as CheckpointManager
    participant OBE as OrderBookEngine
    participant FS as File System
    participant WAL as Write-Ahead Log
    
    Note over ER,FS: Checkpoint Creation (Normal Operation)
    
    loop Every N batches or M minutes
        ER->>CM: Trigger checkpoint
        CM->>OBE: Request state snapshot
        OBE->>OBE: Serialize book state
        OBE-->>CM: State data
        
        CM->>ER: Get current position
        ER-->>CM: Event offset + timestamp
        
        CM->>CM: Create checkpoint struct
        Note right of CM: Uses Copy-on-Write (COW)<br/>for efficiency
        
        CM->>FS: Write checkpoint file
        Note right of FS: checkpoint_YYYYMMDD_HHMMSS.pkl
        CM->>FS: Update checkpoint manifest
        CM->>CM: Prune old checkpoints
        CM-->>ER: Checkpoint complete
    end
    
    Note over ER,WAL: Crash Recovery Process
    
    ER->>CM: Initialize recovery
    CM->>FS: List available checkpoints
    FS-->>CM: Checkpoint list
    
    CM->>CM: Select latest valid checkpoint
    CM->>FS: Load checkpoint data
    FS-->>CM: Checkpoint content
    
    CM->>OBE: Restore book state
    OBE->>OBE: Deserialize state
    OBE-->>CM: State restored
    
    CM->>ER: Set replay position
    ER->>WAL: Seek to position
    
    Note over ER,WAL: Replay events since checkpoint
    
    loop From checkpoint to current
        WAL->>ER: Read event
        ER->>OBE: Apply event
        OBE->>OBE: Update state
        OBE-->>ER: Continue
    end
    
    ER->>ER: Resume normal operation
    ER-->>CM: Recovery complete
```

### Key Points:
- **Non-Blocking**: COW ensures checkpointing doesn't pause processing
- **Fast Recovery**: Only replay events since last checkpoint
- **Consistency**: WAL ensures no events are lost
- **Automatic Pruning**: Old checkpoints removed to save space

## Workflow 5: Live Capture Synchronization

This workflow shows the critical order book initialization process for live data capture.

```mermaid
sequenceDiagram
    participant LC as LiveCapture
    participant WS as WebSocket Stream
    participant REST as REST API
    participant BUF as Event Buffer
    participant OB as Order Book
    participant OUT as Output File
    
    Note over LC,OUT: Binance Order Book Synchronization Protocol
    
    LC->>WS: Connect to stream
    WS-->>LC: Connection established
    
    LC->>BUF: Start buffering events
    
    par WebSocket Events
        loop Continuous stream
            WS->>LC: Depth update event
            LC->>BUF: Buffer.append(event)
            Note right of BUF: Keep all events with<br/>lastUpdateId
        end
    and REST Snapshot
        LC->>REST: Request order book snapshot
        REST-->>LC: Snapshot with lastUpdateId
    end
    
    Note over LC: Critical synchronization logic
    
    LC->>LC: snapshot_id = snapshot.lastUpdateId
    LC->>BUF: Find first event where:<br/>first_id <= snapshot_id <= last_id
    
    alt Sync point found
        LC->>OB: Initialize from snapshot
        
        loop For buffered events from sync point
            BUF->>LC: Get event
            LC->>LC: Validate sequence
            LC->>OB: Apply update
        end
        
        LC->>LC: Switch to live processing
        
        loop Live stream processing
            WS->>LC: New event
            LC->>OB: Apply update
            LC->>OUT: Write enriched event
            OUT->>OUT: Add capture timestamp
        end
        
    else Sync point not found
        LC->>LC: Log error
        LC->>LC: Retry initialization
    end
```

### Key Points:
- **Guaranteed Consistency**: Follows Binance official synchronization protocol
- **No Gap Tolerance**: Must find exact sync point for integrity
- **Timestamp Precision**: Captures both exchange and local timestamps
- **Buffering Strategy**: Ensures no updates lost during initialization

## Performance Characteristics

### Throughput Metrics
- **Reconstruction**: 336-345K messages/second
- **Validation Tier 1**: 336K+ messages/second (no slowdown)
- **Validation Tier 2**: 50K messages/second (GPU batched)
- **Validation Tier 3**: 10K messages/second (comprehensive)

### Memory Usage
- **Per Symbol Pipeline**: <1GB
- **Checkpoint Size**: ~200MB per symbol
- **WAL Buffer**: 100MB rotating
- **GPU Batch Size**: Optimized for GPU memory

### Latency Targets
- **End-to-End Reconstruction**: <10s per million events
- **Checkpoint Creation**: <100ms
- **Recovery Time**: <30s from checkpoint
- **Validation Report**: <5 minutes for 24 hours of data

## Error Handling Patterns

All workflows implement consistent error handling:

1. **Retry Logic**: Transient failures retry with exponential backoff
2. **Circuit Breakers**: Prevent cascade failures
3. **Graceful Degradation**: Continue processing other symbols on failure
4. **Comprehensive Logging**: Full audit trail for debugging
5. **Alert Integration**: Critical errors trigger immediate notifications

## Conclusion

These core workflows represent the essential data flows through the RLX Data Pipeline. Each workflow is designed for high performance, reliability, and maintainability, with clear error handling and recovery mechanisms. The visual representations help ensure consistent implementation across the development team.