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

This workflow illustrates how the FidelityReporter validates reconstructed data against golden samples using the three-tier validation architecture.

```mermaid
sequenceDiagram
    participant UI as User Interface
    participant FR as FidelityReporter
    participant ME as MetricEngine
    participant T1 as Tier1<br/>Streaming
    participant T2 as Tier2<br/>GPU-Accelerated
    participant T3 as Tier3<br/>Comprehensive
    participant RG as ReportGenerator
    participant GS as Golden Samples
    participant RD as Reconstructed Data
    
    Note over UI,RG: Epic 3 - Fidelity Validation Pipeline
    
    UI->>FR: Start validation
    FR->>FR: Load configuration
    FR->>ME: Initialize metric plugins
    
    ME->>ME: Discover available plugins
    ME->>ME: Resolve dependencies
    ME->>T1: Initialize streaming metrics
    ME->>T2: Initialize GPU metrics
    ME->>T3: Initialize comprehensive metrics
    
    Note over GS,RD: Data Loading Phase
    FR->>GS: Load golden sample metadata
    FR->>RD: Open reconstructed data stream
    
    loop For each data chunk
        FR->>RD: Read chunk (100k events)
        FR->>GS: Read corresponding golden chunk
        
        Note over T1: Tier 1: <1μs per event
        FR->>T1: Stream chunk through Tier 1
        T1->>T1: Hausman noise test
        T1->>T1: Sequence gap detection
        T1->>T1: Basic distribution checks
        T1-->>ME: Streaming results
        
        alt Tier 1 anomaly detected
            T1->>FR: Raise critical alert
            FR->>UI: Display real-time warning
        end
        
        Note over T2: Tier 2: <1ms per batch
        FR->>T2: Send to GPU batch queue
        T2->>T2: Anderson-Darling tests
        T2->>T2: Energy Distance calculation
        T2->>T2: Linear MMD approximation
        T2->>T2: Correlation updates
        T2-->>ME: GPU results
        
        Note over T3: Tier 3: <100ms per batch
        FR->>T3: Queue for deep analysis
        T3->>T3: Signature kernel MMD
        T3->>T3: Copula fitting
        T3->>T3: RL state coverage
        T3->>T3: Adversarial patterns
        T3-->>ME: Comprehensive results
        
        ME->>ME: Aggregate all metrics
        ME->>ME: Update running statistics
    end
    
    Note over ME,RG: Report Generation Phase
    ME->>ME: Calculate final scores
    ME->>ME: Determine PASS/FAIL
    
    ME->>RG: Send complete results
    RG->>RG: Generate visualizations
    RG->>RG: Create Q-Q plots
    RG->>RG: Build correlation heatmaps
    RG->>RG: Render 3D state space
    
    RG->>RG: Compile HTML dashboard
    RG->>RG: Generate PDF summary
    RG->>RG: Export JSON data
    
    RG-->>FR: Reports complete
    FR-->>UI: Display results
    
    alt Validation PASSED
        UI->>UI: Show success (green)
        UI->>UI: Display fidelity score
    else Validation FAILED
        UI->>UI: Show failure (red)
        UI->>UI: Highlight problem areas
        UI->>UI: Suggest remediation
    end
```

### Key Points:
- **Three-Tier Architecture**: Optimizes for both speed and thoroughness
- **Parallel Processing**: All tiers can run concurrently on different batches
- **Real-Time Alerts**: Tier 1 provides immediate feedback on critical issues
- **GPU Acceleration**: Tier 2 achieves 100x speedup for complex statistics
- **Comprehensive Analysis**: Tier 3 performs deep validation including RL metrics

## Workflow 3: Multi-Symbol Processing

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