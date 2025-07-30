# Multi-Symbol Architecture Design

## Overview

This document describes the multi-symbol processing architecture for the rlx-data-pipeline, enabling concurrent processing of multiple trading symbols while avoiding Python GIL contention.

## Process Topology

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

## Inter-Process Communication Strategy

### Communication Mechanism
- **Primary**: `multiprocessing.Queue` for router → worker communication
- **Queue Sizes**: 1000 messages per symbol queue (configurable)
- **Message Format**: Pickled Python objects (messages from parser)
- **Backpressure**: Queue size limits provide natural backpressure

### IPC Flow
1. Main process reads from disk using existing DiskReader
2. Parser processes messages in main process
3. Symbol Router examines symbol field and routes to appropriate queue
4. Worker processes consume from their dedicated queues
5. Each worker runs complete pipeline (Order Book Engine → Event Formatter → Parquet Writer)

## Message Routing Protocol

### Routing Strategy
```python
class RoutingStrategy(Enum):
    DIRECT = "direct"      # Route based on message symbol field
    HASH = "hash"          # Hash-based distribution
    ROUND_ROBIN = "round_robin"  # Round-robin distribution
```

### Message Structure
```python
@dataclass
class RoutedMessage:
    symbol: str
    message: Any  # Original parsed message
    timestamp: float  # Router timestamp for monitoring
    sequence: int  # Router sequence number
```

### Routing Logic
```python
def route_message(self, message: ParsedMessage) -> None:
    symbol = message.symbol
    if symbol not in self.workers:
        logger.warning(f"No worker for symbol {symbol}, dropping message")
        return
    
    routed_msg = RoutedMessage(
        symbol=symbol,
        message=message,
        timestamp=time.time(),
        sequence=self.sequence_counter
    )
    
    try:
        self.workers[symbol]['queue'].put_nowait(routed_msg)
    except queue.Full:
        self.metrics.increment('dropped_messages', symbol)
```

## Process Lifecycle Management

### Worker Lifecycle States
```
INITIALIZING → RUNNING → STOPPING → STOPPED
                  ↓
              CRASHED → RESTARTING
```

### Process Manager Responsibilities
1. **Startup**: Create worker processes with proper configuration
2. **Monitoring**: Track worker health via heartbeats
3. **Recovery**: Automatically restart crashed workers
4. **Shutdown**: Graceful termination with data flush

### Health Monitoring
```python
class WorkerHealth:
    process: multiprocessing.Process
    last_heartbeat: float
    messages_processed: int
    errors_count: int
    restart_count: int
    memory_usage: float
    cpu_percent: float
```

### Graceful Shutdown Sequence
1. Stop accepting new messages at router
2. Send shutdown signal to all workers
3. Wait for workers to flush pending messages (timeout: 30s)
4. Force terminate any remaining workers
5. Collect final metrics

## Resource Management

### Memory Allocation
- Per-worker memory limit: 1GB (enforced via resource.setrlimit)
- Router overhead: ~100MB
- Total system: N × 1GB + 100MB

### CPU Affinity
```python
def set_cpu_affinity(pid: int, cpus: List[int]) -> None:
    """Set CPU affinity for a process"""
    if hasattr(os, 'sched_setaffinity'):
        os.sched_setaffinity(pid, cpus)
```

### Resource Monitoring
- Use `psutil` for per-process metrics
- Collect RSS memory, CPU percent, open files
- Export via OpenTelemetry metrics API

## Configuration Schema

```yaml
multi_symbol:
  enabled: true
  routing_strategy: direct
  symbols:
    - name: BTC-USDT
      enabled: true
      memory_limit_mb: 1024
      cpu_affinity: [0, 1]
      queue_size: 1000
    - name: ETH-USDT
      enabled: true
      memory_limit_mb: 1024
      cpu_affinity: [2, 3]
      queue_size: 1000
  
  process_manager:
    health_check_interval_seconds: 5
    restart_delay_seconds: 2
    max_restart_attempts: 3
    shutdown_timeout_seconds: 30
  
  monitoring:
    enable_metrics: true
    metrics_interval_seconds: 10
```

## Error Handling

### Worker Crashes
1. Health monitor detects missing heartbeat
2. Log crash with context (symbol, last message, memory state)
3. Increment restart counter
4. If under max_restart_attempts, restart worker
5. If exceeded, mark symbol as failed and alert

### Queue Overflow
1. Monitor queue sizes
2. Log dropped messages with symbol and count
3. Emit metrics for monitoring
4. Consider dynamic queue resizing if pattern emerges

### Data Integrity
- Each worker maintains own checkpoint state
- Crash recovery resumes from last checkpoint
- No cross-worker dependencies ensure isolation

## Performance Considerations

### Expected Scaling
- Single worker: 336K messages/second (validated)
- Multi-worker: 95% × N scaling factor
- Router overhead: <5% CPU usage
- IPC latency: <1ms per message

### Optimization Points
1. Batch message routing for efficiency
2. Use shared memory for read-only config
3. CPU affinity for cache optimization
4. Zero-copy message passing where possible

## Testing Strategy

### Unit Tests
- ProcessManager lifecycle operations
- SymbolRouter routing logic
- Worker message processing
- Resource limit enforcement

### Integration Tests
- Multi-symbol end-to-end flow
- Graceful shutdown scenarios
- Configuration hot-reload
- Output partitioning verification

### Fault Tolerance Tests
- Worker crash simulation
- Queue overflow handling
- Network partition scenarios
- Resource exhaustion