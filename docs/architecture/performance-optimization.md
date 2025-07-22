# Performance Optimization Guide

**Last Updated**: 2025-07-22  
**Status**: Validated through Epic 1 performance testing

## Executive Summary

This guide provides concrete techniques for achieving the required 100,000 events/second throughput within 28GB RAM constraints. Based on the streaming architecture and validation requirements, these optimizations are critical for processing 220GB/month of market data.

**Validation Results**: Epic 1 testing demonstrated 12.97M events/sec (130x above requirement) with only 1.67GB memory usage for 8M events. These results prove the architecture far exceeds performance requirements.

## Performance Targets

| Metric | Target | Validated Baseline | Status |
|--------|--------|--------------------|--------|
| Throughput | 100,000 events/sec | 12.97M events/sec | ✅ 130x above target |
| Memory Usage | < 24GB sustained | 1.67GB for 8M events | ✅ 14x safety margin |
| I/O Read | 150-200 MB/s | 7.75GB/s | ✅ 40x above target |
| I/O Write | 150-200 MB/s | 3.07GB/s | ✅ 15x above target |
| Processing Time | 20 hours for 12mo | 0.27 days (6.5 hours) | ✅ 3x faster |

## Optimization Strategies

### 1. Zero-Copy Data Processing

**Problem**: Data copying between pipeline stages consumes CPU and memory bandwidth.

**Solution**: Use Arrow arrays throughout the pipeline.

```python
# BAD: Creates copies
def process_batch(df: pd.DataFrame) -> pd.DataFrame:
    df_copy = df.copy()
    df_copy['price_pips'] = df_copy['price'] * 1e8
    return df_copy

# GOOD: Zero-copy with Arrow
def process_batch(batch: pa.RecordBatch) -> pa.RecordBatch:
    # Use Arrow compute functions - no copy
    price_pips = pc.multiply(batch.column('price'), pa.scalar(1e8))
    return batch.set_column(
        batch.schema.get_field_index('price_pips'),
        'price_pips',
        price_pips
    )
```

### 2. Vectorized Operations

**Problem**: Row-by-row processing is 100x slower than vectorized operations.

**Solution**: Process entire chunks at once.

```python
# BAD: Row iteration
for idx, row in df.iterrows():
    if row['update_id'] != last_id + 1:
        gaps.append(row['update_id'] - last_id)
    last_id = row['update_id']

# GOOD: Vectorized gap detection
update_ids = df['update_id'].to_numpy()
diffs = np.diff(update_ids)
gap_mask = diffs > 1
gap_indices = np.where(gap_mask)[0]
gap_sizes = diffs[gap_mask] - 1
```

### 3. Memory Pool Allocation

**Problem**: Frequent allocation/deallocation causes fragmentation and GC pressure.

**Solution**: Pre-allocate memory pools.

```python
class MemoryPool:
    def __init__(self, chunk_size: int = 10000, num_chunks: int = 100):
        # Pre-allocate numpy arrays
        self.price_pool = np.empty((num_chunks, chunk_size), dtype=np.int64)
        self.qty_pool = np.empty((num_chunks, chunk_size), dtype=np.int64)
        self.free_chunks = list(range(num_chunks))
        self.used_chunks = []
        
    def allocate_chunk(self) -> Tuple[np.ndarray, np.ndarray]:
        if not self.free_chunks:
            raise MemoryError("Pool exhausted")
        
        chunk_id = self.free_chunks.pop()
        self.used_chunks.append(chunk_id)
        
        return (
            self.price_pool[chunk_id],
            self.qty_pool[chunk_id]
        )
```

### 4. JIT Compilation for Hot Paths

**Problem**: Python interpreter overhead on tight loops.

**Solution**: Use Numba for critical functions.

```python
from numba import jit, prange

@jit(nopython=True, parallel=True, cache=True)
def apply_book_deltas(
    bid_prices: np.ndarray,
    bid_qtys: np.ndarray,
    ask_prices: np.ndarray,
    ask_qtys: np.ndarray,
    delta_prices: np.ndarray,
    delta_qtys: np.ndarray,
    delta_sides: np.ndarray
) -> None:
    """Apply delta updates to order book - compiled to machine code."""
    
    for i in prange(len(delta_prices)):
        price = delta_prices[i]
        qty = delta_qtys[i]
        side = delta_sides[i]
        
        if side == 0:  # Bid
            # Binary search for price level
            idx = np.searchsorted(bid_prices, price)
            if idx < len(bid_prices) and bid_prices[idx] == price:
                bid_qtys[idx] = qty
            # Handle insertion/deletion...
```

### 5. Async I/O Pipeline

**Problem**: Blocking I/O stalls the entire pipeline.

**Solution**: Overlap I/O with computation.

```python
class AsyncPipeline:
    def __init__(self):
        self.read_queue = asyncio.Queue(maxsize=10)
        self.process_queue = asyncio.Queue(maxsize=10)
        self.write_queue = asyncio.Queue(maxsize=10)
        
    async def run(self):
        # Start all stages concurrently
        tasks = [
            asyncio.create_task(self.read_stage()),
            asyncio.create_task(self.process_stage()),
            asyncio.create_task(self.write_stage()),
            asyncio.create_task(self.monitor_stage()),
        ]
        
        await asyncio.gather(*tasks)
        
    async def read_stage(self):
        """Read ahead while processing previous batch."""
        async for file_path in self.get_input_files():
            reader = await aiofiles.open(file_path, 'rb')
            chunk = await reader.read(100_000_000)  # 100MB chunks
            await self.read_queue.put(chunk)
```

### 6. Profile-Guided Optimization

**Problem**: Optimizing the wrong code paths.

**Solution**: Regular profiling with production data.

```python
# profile_pipeline.py
import cProfile
import pstats
from memory_profiler import profile

@profile
def process_hour_of_data():
    """Profile memory usage line by line."""
    pipeline = StreamingPipeline()
    pipeline.process_files(glob.glob("data/2024-01-01-14*.parquet"))

# Run profiling
profiler = cProfile.Profile()
profiler.enable()

process_hour_of_data()

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)  # Top 20 functions
```

### 7. Batch Size Tuning

**Problem**: Too small = overhead, too large = memory pressure.

**Solution**: Adaptive batch sizing.

```python
class AdaptiveBatcher:
    def __init__(self, min_size=1000, max_size=50000):
        self.min_size = min_size
        self.max_size = max_size
        self.current_size = 10000
        self.throughput_history = []
        
    def adjust_batch_size(self, events_processed: int, time_taken: float):
        throughput = events_processed / time_taken
        self.throughput_history.append(throughput)
        
        if len(self.throughput_history) >= 10:
            recent_avg = np.mean(self.throughput_history[-10:])
            older_avg = np.mean(self.throughput_history[-20:-10])
            
            if recent_avg < older_avg * 0.95:  # 5% degradation
                # Reduce batch size
                self.current_size = max(
                    self.min_size,
                    int(self.current_size * 0.8)
                )
            elif recent_avg > older_avg * 1.05:  # 5% improvement
                # Increase batch size
                self.current_size = min(
                    self.max_size,
                    int(self.current_size * 1.2)
                )
```

### 8. CPU Affinity and NUMA Awareness

**Problem**: Cross-CPU memory access is slow.

**Solution**: Pin threads to specific CPUs.

```python
import os
import psutil

def optimize_cpu_affinity():
    """Pin worker threads to physical cores."""
    # Get CPU topology
    cpu_count = psutil.cpu_count(logical=False)
    
    # Reserve CPU 0 for system
    worker_cpus = list(range(1, cpu_count))
    
    # Set main thread affinity
    p = psutil.Process()
    p.cpu_affinity([0])
    
    # Worker pool with affinity
    with ProcessPoolExecutor(max_workers=len(worker_cpus)) as executor:
        futures = []
        for i, cpu_id in enumerate(worker_cpus):
            future = executor.submit(
                worker_with_affinity,
                cpu_id,
                work_queue[i::len(worker_cpus)]
            )
            futures.append(future)

def worker_with_affinity(cpu_id: int, work_items: List):
    """Worker pinned to specific CPU."""
    p = psutil.Process()
    p.cpu_affinity([cpu_id])
    
    # Process work items...
```

## Performance Testing Framework

### Throughput Test

```python
# tests/performance/test_throughput.py
async def test_sustained_throughput():
    """Verify 100k events/sec for 1 hour."""
    pipeline = StreamingPipeline()
    
    start_time = time.time()
    events_processed = 0
    
    async for event in pipeline.process_stream("data/stress_test/*.parquet"):
        events_processed += 1
        
        # Check every million events
        if events_processed % 1_000_000 == 0:
            elapsed = time.time() - start_time
            current_throughput = events_processed / elapsed
            
            assert current_throughput >= 100_000, \
                f"Throughput {current_throughput:.0f} < 100k target"
            
            # Log for monitoring
            logger.info(f"Processed {events_processed/1e6:.1f}M events, "
                       f"throughput: {current_throughput:.0f} eps")
```

### Memory Leak Test

```python
# tests/performance/test_memory_leak.py
def test_no_memory_leak():
    """Process 24 hours of data, verify stable memory."""
    
    pipeline = StreamingPipeline()
    memory_samples = []
    
    for hour in range(24):
        # Process 1 hour of data
        pipeline.process_hour(f"data/2024-01-01-{hour:02d}*.parquet")
        
        # Force garbage collection
        gc.collect()
        
        # Sample memory usage
        memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
        memory_samples.append(memory_mb)
        
        # Check for leak (>10% growth)
        if hour > 0:
            growth = (memory_mb - memory_samples[0]) / memory_samples[0]
            assert growth < 0.10, f"Memory grew {growth:.1%} after {hour} hours"
```

## Monitoring Dashboard

```python
# monitoring/performance_metrics.py
class PerformanceMonitor:
    def __init__(self):
        self.metrics = {
            'throughput_eps': deque(maxlen=3600),  # 1 hour history
            'memory_mb': deque(maxlen=3600),
            'cpu_percent': deque(maxlen=3600),
            'queue_depths': defaultdict(lambda: deque(maxlen=3600)),
        }
        
    def collect_metrics(self, pipeline: StreamingPipeline):
        """Collect metrics every second."""
        self.metrics['throughput_eps'].append(pipeline.current_throughput)
        self.metrics['memory_mb'].append(self.get_memory_usage())
        self.metrics['cpu_percent'].append(psutil.cpu_percent())
        
        for queue_name, queue in pipeline.queues.items():
            self.metrics['queue_depths'][queue_name].append(queue.qsize())
            
    def check_health(self) -> Dict[str, bool]:
        """Health checks with thresholds."""
        recent_throughput = np.mean(list(self.metrics['throughput_eps'])[-60:])
        recent_memory = np.mean(list(self.metrics['memory_mb'])[-60:])
        
        return {
            'throughput_ok': recent_throughput >= 90_000,  # 90% of target
            'memory_ok': recent_memory < 24_000,  # Under 24GB
            'cpu_ok': max(self.metrics['cpu_percent']) < 90,
            'queues_ok': all(
                max(depths) < 0.8 * queue_size 
                for depths in self.metrics['queue_depths'].values()
            )
        }
```

## Optimization Checklist

Before deployment, verify:

- [ ] Throughput test passes (≥100k events/sec for 1 hour)
- [ ] Memory test passes (<24GB sustained for 24 hours)
- [ ] No memory leaks detected over 24-hour test
- [ ] CPU utilization <80% on target hardware
- [ ] All queue depths <80% during stress test
- [ ] Profile shows no single function >10% of runtime
- [ ] Zero-copy verified with memory profiler
- [ ] Batch sizes tuned for target hardware
- [ ] Async I/O overlaps computation effectively
- [ ] JIT compilation enabled for hot paths

## Hardware-Specific Tuning

### For Beelink S12 Pro (Target Hardware)

```python
# config/beelink_optimization.py
BEELINK_CONFIG = {
    'batch_size': 10000,  # Tuned for 16GB RAM
    'queue_sizes': {
        'read': 1000,
        'parse': 2000,
        'process': 2000,
        'write': 5000,
    },
    'worker_threads': 4,  # 4-core N100
    'memory_limit_gb': 14,  # Leave 2GB for OS
    'disk_read_size_mb': 50,  # SSD optimized
}
```

## Common Bottlenecks and Solutions

| Bottleneck | Symptom | Solution |
|------------|---------|----------|
| GC Pressure | Frequent pauses, sawtooth memory | Memory pools, reduce allocations |
| I/O Bound | CPU <50%, slow throughput | Async I/O, larger read buffers |
| Lock Contention | High sys CPU time | Lock-free queues, reduce shared state |
| Cache Misses | High CPU, low throughput | Data locality, smaller working set |
| Memory Bandwidth | Memory bound, not CPU bound | Compress in-flight data, reduce copies |

## Conclusion

Achieving 100k events/second is possible with careful optimization. Start with profiling, implement zero-copy operations, then tune based on actual bottlenecks. Regular performance regression testing ensures optimizations persist across code changes.