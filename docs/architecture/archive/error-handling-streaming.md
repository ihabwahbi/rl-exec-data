# Streaming Error Handling Strategy

## Overview

This document extends the base error handling strategy with streaming-specific failure modes and recovery procedures. Given the pipeline must process 220GB/month continuously, robust error handling is critical for maintaining data integrity.

## Streaming-Specific Error Categories

### 1. Backpressure Errors

**Definition**: Downstream stages cannot keep up with upstream data production.

**Detection**:
```python
class BackpressureError(Exception):
    def __init__(self, stage: str, queue_depth: int, max_depth: int):
        self.stage = stage
        self.queue_depth = queue_depth
        self.max_depth = max_depth
        super().__init__(
            f"Backpressure in {stage}: queue {queue_depth}/{max_depth}"
        )
```

**Handling Strategy**:
```python
async def handle_backpressure(pipeline: StreamingPipeline, error: BackpressureError):
    # Level 1: Slow down input
    if error.queue_depth < error.max_depth * 0.9:
        await pipeline.throttle_input(factor=0.5)
        await asyncio.sleep(1.0)
        return
    
    # Level 2: Pause input
    if error.queue_depth < error.max_depth * 0.95:
        await pipeline.pause_input()
        await pipeline.wait_for_drain(target_fill=0.5)
        await pipeline.resume_input()
        return
        
    # Level 3: Emergency flush
    logger.error(f"Emergency flush triggered for {error.stage}")
    await pipeline.emergency_flush(error.stage)
```

### 2. Memory Pressure Errors

**Definition**: Pipeline approaching memory limits.

**Detection and Response**:
```python
class MemoryPressureHandler:
    def __init__(self, limit_gb: float = 24.0):
        self.limit_bytes = limit_gb * 1024**3
        self.strategies = [
            (0.7, self.reduce_batch_sizes),
            (0.8, self.drop_cache),
            (0.9, self.spill_to_disk),
            (0.95, self.emergency_shutdown),
        ]
        
    async def check_memory(self) -> None:
        current = psutil.Process().memory_info().rss
        ratio = current / self.limit_bytes
        
        for threshold, strategy in self.strategies:
            if ratio > threshold:
                await strategy(ratio)
                break
                
    async def spill_to_disk(self, ratio: float):
        """Spill in-memory buffers to disk."""
        logger.warning(f"Memory at {ratio:.1%}, spilling to disk")
        
        # Identify largest buffers
        buffers = self.pipeline.get_spillable_buffers()
        buffers.sort(key=lambda b: b.memory_usage, reverse=True)
        
        # Spill until under threshold
        for buffer in buffers:
            await buffer.spill_to_disk()
            if self.get_memory_ratio() < 0.8:
                break
```

### 3. Sequence Gap Errors

**Definition**: Missing events in delta feed sequence.

**Detection**:
```python
@dataclass
class SequenceGap:
    symbol: str
    expected_id: int
    received_id: int
    gap_size: int
    timestamp: datetime
    
class GapDetector:
    def __init__(self, max_acceptable_gap: int = 1000):
        self.max_acceptable_gap = max_acceptable_gap
        self.last_ids = {}
        self.gap_history = deque(maxlen=10000)
        
    def check_sequence(self, event: Dict) -> Optional[SequenceGap]:
        symbol = event['symbol']
        update_id = event['update_id']
        
        if symbol in self.last_ids:
            expected = self.last_ids[symbol] + 1
            if update_id != expected:
                gap = SequenceGap(
                    symbol=symbol,
                    expected_id=expected,
                    received_id=update_id,
                    gap_size=update_id - expected,
                    timestamp=datetime.now()
                )
                self.gap_history.append(gap)
                return gap
                
        self.last_ids[symbol] = update_id
        return None
```

**Recovery Strategy**:
```python
async def handle_sequence_gap(gap: SequenceGap) -> RecoveryAction:
    if gap.gap_size <= 10:
        # Small gap - likely network reordering
        return RecoveryAction.CONTINUE_WITH_WARNING
        
    elif gap.gap_size <= 1000:
        # Medium gap - attempt recovery from snapshot
        logger.warning(f"Gap of {gap.gap_size} for {gap.symbol}")
        await request_snapshot_recovery(gap.symbol, gap.expected_id)
        return RecoveryAction.BUFFER_UNTIL_RECOVERY
        
    else:
        # Large gap - mark as corrupt period
        logger.error(f"Unrecoverable gap of {gap.gap_size} for {gap.symbol}")
        await mark_corrupt_period(
            gap.symbol,
            start_id=gap.expected_id,
            end_id=gap.received_id
        )
        return RecoveryAction.SKIP_AND_CONTINUE
```

### 4. Pipeline Stall Detection

**Definition**: Stage stops processing despite available input.

**Implementation**:
```python
class StallDetector:
    def __init__(self, timeout_seconds: float = 30.0):
        self.timeout = timeout_seconds
        self.last_activity = {}
        
    async def monitor_pipeline(self, pipeline: StreamingPipeline):
        while True:
            for stage_name, stage in pipeline.stages.items():
                current_count = stage.events_processed
                
                if stage_name in self.last_activity:
                    last_count, last_time = self.last_activity[stage_name]
                    
                    if current_count == last_count:
                        stall_duration = time.time() - last_time
                        
                        if stall_duration > self.timeout:
                            await self.handle_stall(stage_name, stall_duration)
                            
                self.last_activity[stage_name] = (current_count, time.time())
                
            await asyncio.sleep(5.0)
            
    async def handle_stall(self, stage_name: str, duration: float):
        logger.error(f"Stage {stage_name} stalled for {duration:.1f}s")
        
        # Attempt recovery
        recovery_actions = [
            self.check_deadlock,
            self.restart_stage,
            self.bypass_stage,
            self.emergency_shutdown
        ]
        
        for action in recovery_actions:
            if await action(stage_name):
                break
```

### 5. Checkpoint Corruption

**Definition**: Checkpoint files corrupted or incompatible.

**Handling**:
```python
class CheckpointRecovery:
    def __init__(self, checkpoint_dir: Path):
        self.checkpoint_dir = checkpoint_dir
        self.checkpoints = self.scan_checkpoints()
        
    def load_latest_valid_checkpoint(self) -> Optional[PipelineState]:
        """Try checkpoints in reverse chronological order."""
        for checkpoint in reversed(self.checkpoints):
            try:
                state = self.load_checkpoint(checkpoint)
                if self.validate_checkpoint(state):
                    logger.info(f"Recovered from checkpoint: {checkpoint}")
                    return state
            except Exception as e:
                logger.warning(f"Checkpoint {checkpoint} corrupted: {e}")
                continue
                
        logger.error("No valid checkpoints found")
        return None
        
    def validate_checkpoint(self, state: PipelineState) -> bool:
        """Verify checkpoint integrity."""
        checks = [
            state.pipeline_version == CURRENT_VERSION,
            state.last_event_time < datetime.now(),
            state.events_processed > 0,
            all(qd >= 0 for qd in state.queue_depths.values()),
        ]
        return all(checks)
```

### 6. Network Partition Handling

**Definition**: Network issues causing data source disconnection.

**Implementation**:
```python
class NetworkPartitionHandler:
    def __init__(self, max_retry_seconds: int = 300):
        self.max_retry_seconds = max_retry_seconds
        self.disconnected_sources = {}
        
    async def handle_disconnection(self, source: str, error: Exception):
        """Exponential backoff with jitter."""
        if source not in self.disconnected_sources:
            self.disconnected_sources[source] = {
                'attempts': 0,
                'first_failure': time.time()
            }
            
        info = self.disconnected_sources[source]
        info['attempts'] += 1
        
        # Calculate backoff with jitter
        backoff = min(
            2 ** info['attempts'] + random.uniform(0, 1),
            self.max_retry_seconds
        )
        
        logger.warning(f"Source {source} disconnected, retry in {backoff:.1f}s")
        await asyncio.sleep(backoff)
        
        try:
            await self.reconnect_source(source)
            del self.disconnected_sources[source]
            logger.info(f"Reconnected to {source}")
        except Exception as e:
            # Check if we should give up
            elapsed = time.time() - info['first_failure']
            if elapsed > 3600:  # 1 hour
                logger.error(f"Giving up on {source} after {elapsed:.0f}s")
                raise
            else:
                await self.handle_disconnection(source, e)
```

## Error Aggregation and Reporting

```python
class ErrorAggregator:
    """Aggregate errors to prevent log spam and identify patterns."""
    
    def __init__(self, window_seconds: int = 60):
        self.window = window_seconds
        self.errors = defaultdict(lambda: deque(maxlen=1000))
        self.last_report = defaultdict(float)
        
    def record_error(self, error: Exception, context: Dict):
        error_type = type(error).__name__
        self.errors[error_type].append({
            'timestamp': time.time(),
            'error': error,
            'context': context
        })
        
        # Check if we should report
        if time.time() - self.last_report[error_type] > self.window:
            self.report_errors(error_type)
            
    def report_errors(self, error_type: str):
        recent_errors = [
            e for e in self.errors[error_type]
            if time.time() - e['timestamp'] < self.window
        ]
        
        if len(recent_errors) > 10:
            logger.error(
                f"{error_type}: {len(recent_errors)} errors in last {self.window}s"
            )
            # Send alert if error rate too high
            if len(recent_errors) > 100:
                self.send_critical_alert(error_type, recent_errors)
                
        self.last_report[error_type] = time.time()
```

## Circuit Breaker Pattern

```python
class CircuitBreaker:
    """Prevent cascading failures in streaming pipeline."""
    
    def __init__(self, failure_threshold: int = 5, timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failures = defaultdict(int)
        self.last_failure_time = defaultdict(float)
        self.state = defaultdict(lambda: 'closed')  # closed, open, half-open
        
    async def call(self, stage_name: str, func: Callable, *args, **kwargs):
        if self.state[stage_name] == 'open':
            if time.time() - self.last_failure_time[stage_name] > self.timeout:
                self.state[stage_name] = 'half-open'
            else:
                raise CircuitOpenError(f"{stage_name} circuit is open")
                
        try:
            result = await func(*args, **kwargs)
            
            # Success - reset failure count
            if self.state[stage_name] == 'half-open':
                self.state[stage_name] = 'closed'
            self.failures[stage_name] = 0
            
            return result
            
        except Exception as e:
            self.failures[stage_name] += 1
            self.last_failure_time[stage_name] = time.time()
            
            if self.failures[stage_name] >= self.failure_threshold:
                self.state[stage_name] = 'open'
                logger.error(f"Circuit breaker opened for {stage_name}")
                
            raise
```

## Recovery Priority Matrix

| Error Type | Detection Time | Recovery Time | Data Loss Risk | Action Priority |
|-----------|----------------|---------------|----------------|-----------------|
| Memory Pressure | Immediate | 1-5 min | Low | Critical |
| Sequence Gap | Immediate | 1-10 min | Medium | High |
| Backpressure | <5 seconds | <1 min | Low | High |
| Pipeline Stall | 30 seconds | 1-5 min | Medium | High |
| Network Partition | Immediate | 1-60 min | High | Medium |
| Checkpoint Corruption | On restart | 5-30 min | Low | Medium |

## Testing Error Scenarios

```python
# tests/error_handling/test_streaming_errors.py
async def test_backpressure_handling():
    """Simulate slow consumer causing backpressure."""
    pipeline = StreamingPipeline()
    
    # Slow down write stage
    original_write = pipeline.stages['write'].process
    
    async def slow_write(*args, **kwargs):
        await asyncio.sleep(0.1)  # Artificial delay
        return await original_write(*args, **kwargs)
        
    pipeline.stages['write'].process = slow_write
    
    # Feed data rapidly
    start_time = time.time()
    for i in range(100_000):
        await pipeline.input_queue.put(generate_event())
        
    # Verify backpressure was handled
    assert pipeline.metrics.backpressure_events > 0
    assert pipeline.metrics.data_loss == 0
    
async def test_memory_pressure_recovery():
    """Verify memory pressure triggers spill to disk."""
    # Allocate large buffers to simulate pressure
    pressure_buffer = np.zeros((1_000_000_000,), dtype=np.float64)  # 8GB
    
    pipeline = StreamingPipeline(memory_limit_gb=10.0)
    
    # Process data
    await pipeline.process_files(test_files)
    
    # Verify spill occurred
    assert pipeline.metrics.spill_events > 0
    assert pipeline.memory_monitor.peak_usage_gb < 10.0
```

## Monitoring and Alerting

```python
# monitoring/error_alerts.py
class ErrorAlertSystem:
    def __init__(self):
        self.alert_thresholds = {
            'sequence_gap_rate': 0.001,  # 0.1%
            'memory_usage_ratio': 0.9,    # 90%
            'error_rate_per_min': 100,
            'stall_duration_sec': 60,
        }
        
    def check_alerts(self, metrics: PipelineMetrics):
        alerts = []
        
        if metrics.sequence_gap_ratio > self.alert_thresholds['sequence_gap_rate']:
            alerts.append(Alert(
                level='critical',
                message=f"Sequence gap rate {metrics.sequence_gap_ratio:.2%} exceeds threshold",
                action='Check network connectivity and data source health'
            ))
            
        # Check other thresholds...
        
        return alerts
```

## Conclusion

Streaming error handling requires proactive detection and automated recovery. The strategies outlined here ensure the pipeline can process 220GB/month reliably, recovering from transient failures while alerting on systemic issues. Regular chaos testing validates these mechanisms work under stress.