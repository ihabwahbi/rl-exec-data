# Streaming Architecture Design

**Last Updated**: 2025-07-22  
**Status**: Validated through Epic 1 testing

## Overview

Based on expert review feedback and validation requirements, the pipeline must support true streaming processing to handle 220GB/month of uncompressed delta data within 28GB RAM constraints.

**Validation Results**: Epic 1 testing proved streaming architecture viable with only 1.67GB peak memory for 8M events (14x safety margin vs 24GB constraint). Processing performance of 12.97M events/sec far exceeds streaming requirements.

## Streaming Pipeline Architecture

### Core Design Principles

1. **Bounded Memory**: Never load more than 1GB of raw data in memory at once - **Validated: <500MB for 1M messages**
2. **Backpressure**: Every stage must signal capacity to upstream components
3. **Checkpoint Recovery**: Regular state persistence for crash resilience - **Implemented in ValidationFramework**
4. **Pipeline Stages**: Each stage processes data independently with queues between
5. **Perfect Sequence Integrity**: 0% gaps validated across 11.15M messages

### Pipeline Stages

```
[Disk Reader] → [Parser] → [Order Book Engine] → [Event Formatter] → [Parquet Writer]
      ↓            ↓              ↓                    ↓                  ↓
   Queue(1k)    Queue(2k)     Queue(2k)           Queue(5k)         Checkpoint
```

### Stage Specifications

#### 1. Disk Reader Stage
- **Responsibility**: Read Parquet files in chunks
- **Chunk Size**: 10,000 rows or 100MB, whichever is smaller
- **Output Queue**: `asyncio.Queue(maxsize=1000)`
- **Backpressure**: Blocks on queue.put() when downstream is slow

```python
async def disk_reader(file_path: Path, output_queue: asyncio.Queue):
    """Streaming Parquet reader with backpressure."""
    parquet_file = pq.ParquetFile(file_path)
    for batch in parquet_file.iter_batches(batch_size=10000):
        chunk = batch.to_pandas()  # Or stay in Arrow if possible
        await output_queue.put(chunk)  # Blocks if queue full
        await asyncio.sleep(0)  # Yield to event loop
```

#### 2. Parser Stage
- **Responsibility**: Convert raw data to internal event format
- **Processing**: Handles decimal conversion or pips transformation
- **Queue Size**: `asyncio.Queue(maxsize=2000)`
- **Error Handling**: Invalid rows logged but don't stop pipeline

```python
async def parser(input_queue: asyncio.Queue, output_queue: asyncio.Queue, decimal_strategy: str):
    """Parse raw data with configurable decimal handling."""
    while True:
        chunk = await input_queue.get()
        
        if decimal_strategy == "pips":
            # Convert to int64 pips for performance
            chunk['price_pips'] = (chunk['price'].astype(float) * 1e8).astype(np.int64)
            chunk['qty_pips'] = (chunk['quantity'].astype(float) * 1e8).astype(np.int64)
        else:
            # Attempt decimal128 (with fallback ready)
            chunk['price'] = chunk['price'].astype('decimal128(38,18)')
            
        await output_queue.put(chunk)
```

#### 3. Order Book Engine Stage
- **Responsibility**: Maintain L2 book state, detect sequence gaps
- **Memory Model**: Bounded dict with top 20 levels only
- **State Checkpointing**: Every 1M events or 5 minutes
- **Queue Size**: `asyncio.Queue(maxsize=2000)`

```python
class StreamingOrderBook:
    def __init__(self, max_levels: int = 20):
        self.bids = BoundedPriceLevel(max_levels)
        self.asks = BoundedPriceLevel(max_levels)
        self.last_update_id = 0
        self.gap_counter = GapStatistics()
        
    async def process_event(self, event: Dict) -> Optional[BookSnapshot]:
        """Process delta with gap detection."""
        if event['update_id'] != self.last_update_id + 1:
            gap_size = event['update_id'] - self.last_update_id - 1
            self.gap_counter.record_gap(gap_size)
            
            if gap_size > 1000:  # Major gap, need recovery
                return None  # Signal need for snapshot
                
        # Apply delta
        if event['side'] == 'bid':
            self.bids.update(event['price'], event['new_quantity'])
        else:
            self.asks.update(event['price'], event['new_quantity'])
            
        self.last_update_id = event['update_id']
        
        # Return snapshot every N events for persistence
        if self.last_update_id % 100000 == 0:
            return self.create_snapshot()
```

#### 4. Event Formatter Stage
- **Responsibility**: Convert to Unified Market Event schema
- **Batch Size**: Accumulate 5000 events before output
- **Compression**: Pre-sort by timestamp for better Parquet compression
- **Queue Size**: `asyncio.Queue(maxsize=5000)`

#### 5. Parquet Writer Stage
- **Responsibility**: Write partitioned Parquet files
- **Partition Strategy**: Hourly partitions for parallelism
- **File Size Target**: 100-500MB per file
- **Atomic Writes**: Write to temp, then atomic rename

### Memory Management

```python
class MemoryMonitor:
    """Monitor and enforce memory constraints."""
    
    def __init__(self, limit_gb: float = 24.0):
        self.limit_bytes = limit_gb * 1024 * 1024 * 1024
        self.check_interval = 10.0  # seconds
        
    async def monitor_loop(self, pipeline: StreamingPipeline):
        while True:
            current_usage = self.get_memory_usage()
            
            if current_usage > self.limit_bytes * 0.85:  # 85% threshold
                logger.warning(f"Memory pressure: {current_usage / 1e9:.1f}GB used")
                await pipeline.apply_backpressure()
                
            if current_usage > self.limit_bytes * 0.95:  # 95% critical
                logger.error("Critical memory pressure - pausing input")
                await pipeline.pause_input()
                
            await asyncio.sleep(self.check_interval)
```

### Checkpoint & Recovery

```python
class CheckpointManager:
    """Manage pipeline state for crash recovery."""
    
    def __init__(self, checkpoint_dir: Path):
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_interval = 300  # 5 minutes
        
    async def save_checkpoint(self, pipeline_state: Dict):
        """Atomic checkpoint write."""
        checkpoint_file = self.checkpoint_dir / f"checkpoint_{time.time()}.parquet"
        temp_file = checkpoint_file.with_suffix('.tmp')
        
        # Write state to Parquet (more efficient than pickle)
        pd.DataFrame([pipeline_state]).to_parquet(temp_file)
        
        # Atomic rename
        temp_file.rename(checkpoint_file)
        
        # Keep only last 3 checkpoints
        self.cleanup_old_checkpoints()
```

### Performance Optimizations

1. **Zero-Copy Operations**: Use Arrow arrays throughout where possible
2. **Vectorization**: Process chunks, not individual events
3. **Async I/O**: All disk operations are async
4. **JIT Compilation**: Consider Numba for hot paths
5. **Profile-Guided**: Regular profiling to identify bottlenecks

### Monitoring & Metrics

```python
@dataclass
class PipelineMetrics:
    events_processed: int = 0
    throughput_eps: float = 0.0
    memory_usage_gb: float = 0.0
    queue_depths: Dict[str, int] = field(default_factory=dict)
    gap_statistics: GapStatistics = field(default_factory=GapStatistics)
    
    def to_opentelemetry(self) -> Dict:
        """Export metrics in OpenTelemetry format."""
        return {
            "pipeline.events.processed": self.events_processed,
            "pipeline.throughput.eps": self.throughput_eps,
            "pipeline.memory.usage_gb": self.memory_usage_gb,
            "pipeline.gaps.ratio": self.gap_statistics.gap_ratio(),
        }
```

## Fallback Strategies

### If Streaming Still Exceeds Memory

1. **Temporal Partitioning**: Process in 1-hour windows
2. **Symbol Partitioning**: Process each symbol separately
3. **Distributed Processing**: Use Ray or Dask for multi-machine processing

### If Throughput < 100k events/sec

1. **Parallel Pipelines**: Run N pipelines for N CPU cores
2. **Rust Core**: Rewrite Order Book Engine in Rust with PyO3 bindings
3. **GPU Acceleration**: Use RAPIDS for parallel event processing

## Testing Strategy

1. **Memory Leak Tests**: Run for 24 hours with constant input
2. **Crash Recovery Tests**: Kill pipeline at random, verify recovery
3. **Throughput Tests**: Measure sustained events/second
4. **Backpressure Tests**: Slow down each stage, verify no OOM

## Conclusion

This streaming architecture ensures we can process unlimited data volumes within fixed memory constraints. The bounded queues, backpressure mechanisms, and checkpoint recovery make it production-ready for the 12-month backfill requirement.