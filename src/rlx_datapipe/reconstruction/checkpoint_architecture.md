# Checkpoint Architecture Design

## Overview

The checkpointing system implements a copy-on-write (COW) mechanism for non-blocking state persistence, enabling the pipeline to recover from failures without data loss while maintaining high throughput.

## Integration Points

### 1. Order Book Engine
- **Location**: `order_book_engine.py:_save_checkpoint()`
- **Integration**: Engine provides `get_checkpoint_state()` method returning current book state
- **Trigger**: Every 1M updates or via external trigger

### 2. Symbol Worker
- **Location**: `symbol_worker.py:_checkpoint()`
- **Integration**: Coordinates checkpoint across all pipeline components
- **Trigger**: Time-based (5 min) or event-based (1M events)

### 3. Pipeline Integration
- **Location**: `pipeline_integration.py`
- **Integration**: Recovery process reads checkpoint and seeks to saved position
- **Trigger**: On startup when checkpoint exists

### 4. Data Sink
- **Location**: Via `symbol_worker.py`
- **Integration**: Flushes pending writes before checkpoint
- **Trigger**: Coordinated with main checkpoint

## Non-Blocking Persistence Approach

### Copy-on-Write Mechanism
1. **Snapshot Creation** (<100ms target):
   - Shallow copy of state references
   - Deep copy only for mutable nested structures
   - No locks on main processing pipeline

2. **Async Persistence**:
   - Snapshot persisted in background task
   - Uses Parquet format with compression
   - Atomic write pattern (temp file + rename)

3. **Memory Management**:
   - Double-buffering for zero-copy snapshots
   - Pre-allocated memory pools
   - Minimal GC pressure during snapshot

### Checkpoint Flow
```
Main Pipeline Process
    |
    v
[Trigger Detected] --> [Create COW Snapshot] --> [Continue Processing]
                              |                            |
                              v                            |
                        [Background Task]                  |
                              |                            |
                              v                            |
                        [Persist to Parquet]               |
                              |                            |
                              v                            |
                        [Atomic File Write]                |
                              |                            |
                              v                            v
                        [Update Manifest] <-- [Next Event Processing]
```

## State Components

### Pipeline State Structure
```python
PipelineState:
    - order_book_state: Dict[str, Any]  # Complete book state
    - last_update_id: int               # Sequence tracking
    - current_file: str                 # Input file path
    - file_offset: int                  # Position in file
    - events_processed: int             # Total event count
    - gap_statistics: Dict              # Gap tracking
    - drift_metrics: Dict               # Drift measurements
    - processing_rate: float            # Events/second
    - checkpoint_timestamp: int         # When created
    - snapshot_duration_ms: float       # Performance metric
```

### Parquet Schema
- Flat structure for efficient columnar storage
- Complex objects serialized as JSON strings
- Metadata includes version and integrity info

## Recovery Process

1. **Checkpoint Discovery**:
   - Find latest valid checkpoint file
   - Verify file integrity and permissions
   - Load state into memory

2. **State Restoration**:
   - Restore order book state
   - Restore pipeline progress
   - Initialize performance metrics

3. **Input Seeking**:
   - Open saved input file
   - Seek to saved offset
   - Validate continuity

4. **Processing Resume**:
   - Skip already processed events
   - Continue from checkpoint position
   - Monitor for gaps

## Performance Optimizations

1. **Snapshot Speed**:
   - COW technique for O(1) snapshot creation
   - Lazy copying of large structures
   - Memory pool pre-allocation

2. **Persistence Efficiency**:
   - Parquet compression (Snappy)
   - Async I/O for disk writes
   - Batch metadata updates

3. **Recovery Speed**:
   - Indexed checkpoint files
   - Fast Parquet deserialization
   - Parallel state restoration

## Security Measures

1. **File Permissions**:
   - Checkpoint files: 0600 (owner only)
   - Checkpoint directory: 0700
   - Atomic permission setting

2. **Integrity Validation**:
   - Metadata verification on load
   - Symbol matching checks
   - Corruption detection

## Monitoring

Key metrics tracked:
- Snapshot creation time
- Checkpoint size
- Recovery duration
- Gap detection after recovery
- Throughput impact percentage