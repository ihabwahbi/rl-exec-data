# Error Handling Strategy

**Last Updated**: 2025-07-19  
**Status**: Comprehensive guide combining general and streaming-specific patterns

## Design Philosophy

The pipeline implements a **fail-explicit** approach - errors are never silently ignored. All errors are captured with context through structured logging via **Loguru** for effective debugging and monitoring.

## Error Categories

### 1. Data Ingestion Errors

**Principle**: Skip bad data chunks but continue processing.

| Error Type | Response | Logging |
|------------|----------|---------|
| Missing data period | Skip period, continue | WARNING |
| Corrupt data | Skip chunk, continue | ERROR |
| Schema validation failure | Skip chunk, continue | ERROR |

**Implementation**:
```python
async def process_data_chunk(chunk_id: str, data: pd.DataFrame):
    try:
        validate_schema(data)
        return process_chunk(data)
    except SchemaValidationError as e:
        logger.error(f"Schema validation failed for {chunk_id}: {e}")
        metrics.record_failed_chunk(chunk_id, reason="schema")
        return None  # Continue with next chunk
```

### 2. Configuration Errors

**Principle**: Fail fast at startup.

```python
def validate_configuration():
    """Check all critical configs before starting."""
    required = ['CRYPTO_LAKE_API_KEY', 'DATA_PATH', 'OUTPUT_PATH']
    missing = [k for k in required if not os.getenv(k)]
    
    if missing:
        raise ConfigurationError(f"Missing required config: {missing}")
```

### 3. Reconstruction Errors

**Principle**: Log with full context, attempt to continue.

```python
def handle_reconstruction_error(error: Exception, chunk_id: str):
    logger.error(
        f"Reconstruction failed for {chunk_id}",
        exc_info=True,
        extra={
            'chunk_id': chunk_id,
            'error_type': type(error).__name__,
            'traceback': traceback.format_exc()
        }
    )
    # Attempt next chunk
```

### 4. Fidelity Validation Errors

**Principle**: Generate detailed report, signal failure clearly.

```python
def validate_fidelity(reconstructed: pd.DataFrame, golden: pd.DataFrame):
    results = run_fidelity_tests(reconstructed, golden)
    
    if results.p_value < 0.05:
        logger.critical(
            f"Fidelity validation FAILED: p-value = {results.p_value}",
            extra={'report': results.to_dict()}
        )
        return FidelityStatus.FAIL
```

## Streaming-Specific Error Handling

### 1. Sequence Gap Detection

**Critical for delta feeds** - monitors update_id continuity.

```python
class SequenceGapHandler:
    def handle_gap(self, gap: SequenceGap):
        if gap.size <= 10:
            # Small gap - likely reordering
            logger.warning(f"Small gap: {gap}")
            return Action.CONTINUE
            
        elif gap.size <= 1000:
            # Medium gap - try recovery
            logger.warning(f"Medium gap: {gap}, attempting recovery")
            return Action.RECOVER_FROM_SNAPSHOT
            
        else:
            # Large gap - data loss
            logger.error(f"Unrecoverable gap: {gap}")
            metrics.record_data_loss(gap)
            return Action.MARK_CORRUPT_PERIOD
```

### 2. Memory Pressure Management

**Prevents OOM with 28GB limit**:

```python
class MemoryPressureHandler:
    THRESHOLDS = {
        0.70: "reduce_batch_size",
        0.80: "drop_caches", 
        0.85: "spill_to_disk",
        0.95: "emergency_shutdown"
    }
    
    async def monitor(self):
        usage = get_memory_usage_ratio()
        
        for threshold, action in self.THRESHOLDS.items():
            if usage > threshold:
                logger.warning(f"Memory at {usage:.1%}, triggering {action}")
                await getattr(self, action)()
                break
```

### 3. Backpressure Handling

**Prevents queue overflow**:

```python
async def handle_backpressure(queue_depth: int, max_depth: int):
    fill_ratio = queue_depth / max_depth
    
    if fill_ratio > 0.9:
        # Level 1: Throttle
        await throttle_input(factor=0.5)
    elif fill_ratio > 0.95:
        # Level 2: Pause
        await pause_input()
        await wait_for_drain(target=0.5)
    else:
        # Level 3: Emergency flush
        await emergency_flush()
```

### 4. Clock Skew Compensation

**Handles timing discrepancies**:

```python
def compensate_clock_skew(event: dict) -> dict:
    skew = event['origin_time'] - event['exchange_time']
    
    if abs(skew) > 100:  # ms
        logger.warning(f"Clock skew detected: {skew}ms")
        
        if abs(skew) > 1000:
            # Large skew - use exchange time
            event['corrected_time'] = event['exchange_time']
        else:
            # Small skew - average
            event['corrected_time'] = (
                event['origin_time'] + event['exchange_time']
            ) / 2
            
    return event
```

### 5. Write-Ahead Log Recovery

**Ensures data integrity**:

```python
class WALRecovery:
    def recover_on_startup(self):
        incomplete_segments = self.scan_wal_directory()
        
        if incomplete_segments:
            logger.info(f"Found {len(incomplete_segments)} incomplete WAL segments")
            
            for segment in incomplete_segments:
                try:
                    state = self.recover_segment(segment)
                    logger.info(f"Recovered segment {segment.id}")
                except CorruptedWALError:
                    logger.error(f"WAL segment {segment.id} corrupted")
                    # Never skip silently - data integrity paramount
                    raise
```

## Circuit Breaker Pattern

**Prevents cascading failures**:

```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, timeout=60.0):
        self.states = defaultdict(lambda: 'closed')
        self.failures = defaultdict(int)
        
    async def call(self, component: str, func: Callable):
        if self.states[component] == 'open':
            if self.should_retry(component):
                self.states[component] = 'half-open'
            else:
                raise CircuitOpenError(component)
                
        try:
            result = await func()
            if self.states[component] == 'half-open':
                self.states[component] = 'closed'
                self.failures[component] = 0
            return result
            
        except Exception as e:
            self.failures[component] += 1
            if self.failures[component] >= self.failure_threshold:
                self.states[component] = 'open'
                logger.error(f"Circuit opened for {component}")
            raise
```

## Pipeline Stall Detection

**Identifies stuck stages**:

```python
class StallDetector:
    def __init__(self, timeout=30.0):
        self.last_activity = {}
        
    async def monitor(self, pipeline):
        for stage_name, stage in pipeline.stages.items():
            if self.is_stalled(stage_name, stage):
                await self.handle_stall(stage_name)
                
    def is_stalled(self, name: str, stage) -> bool:
        current = stage.events_processed
        if name in self.last_activity:
            last_count, last_time = self.last_activity[name]
            if current == last_count:
                return (time.time() - last_time) > self.timeout
        self.last_activity[name] = (current, time.time())
        return False
```

## Error Aggregation

**Prevents log spam, identifies patterns**:

```python
class ErrorAggregator:
    def __init__(self, window_seconds=60):
        self.errors = defaultdict(deque)
        self.window = window_seconds
        
    def record(self, error: Exception, context: dict):
        error_type = type(error).__name__
        self.errors[error_type].append({
            'time': time.time(),
            'error': error,
            'context': context
        })
        
        # Report if threshold exceeded
        recent = self.count_recent(error_type)
        if recent > 10:
            logger.error(f"{error_type}: {recent} errors in {self.window}s")
            if recent > 100:
                self.send_alert(error_type, recent)
```

## Recovery Priority Matrix

| Error Type | Detection | Recovery | Data Loss Risk | Priority |
|------------|-----------|----------|----------------|----------|
| Memory Pressure | Immediate | 1-5 min | Low | Critical |
| Sequence Gap | Immediate | 1-10 min | Medium | High |
| Backpressure | <5 sec | <1 min | Low | High |
| Pipeline Stall | 30 sec | 1-5 min | Medium | High |
| Network Partition | Immediate | 1-60 min | High | Medium |
| Checkpoint Corruption | On restart | 5-30 min | Low | Medium |

## Testing Error Scenarios

```python
# Simulate backpressure
async def test_backpressure_handling():
    pipeline = create_test_pipeline()
    
    # Slow down consumer
    pipeline.stages['write'].add_delay(0.1)
    
    # Feed data rapidly
    for i in range(100_000):
        await pipeline.input(generate_event())
        
    # Verify no data loss
    assert pipeline.metrics.backpressure_events > 0
    assert pipeline.metrics.data_loss == 0

# Test memory pressure
async def test_memory_spill():
    pipeline = StreamingPipeline(memory_limit_gb=10.0)
    
    # Allocate pressure
    large_buffer = np.zeros((1_000_000_000,))  # 8GB
    
    # Process normally
    await pipeline.process(test_data)
    
    # Verify spill occurred
    assert pipeline.metrics.spill_events > 0
    assert pipeline.peak_memory_gb < 10.0
```

## Monitoring and Alerting

```python
class ErrorMonitor:
    ALERT_THRESHOLDS = {
        'sequence_gap_rate': 0.001,     # 0.1%
        'memory_usage_ratio': 0.9,      # 90%
        'error_rate_per_min': 100,
        'stall_duration_sec': 60,
    }
    
    def check_alerts(self, metrics: PipelineMetrics) -> List[Alert]:
        alerts = []
        
        if metrics.gap_ratio > self.ALERT_THRESHOLDS['sequence_gap_rate']:
            alerts.append(Alert(
                level='critical',
                message=f"Gap rate {metrics.gap_ratio:.2%} exceeds threshold",
                action='Check data source connectivity'
            ))
            
        return alerts
```

## Best Practices

1. **Never Silent Failures**: Always log errors with context
2. **Graceful Degradation**: Continue processing when possible
3. **Clear Status Reporting**: Make failure states obvious
4. **Recovery Over Restart**: Attempt automatic recovery first
5. **Preserve Data Integrity**: Never skip WAL recovery
6. **Monitor Continuously**: Detect issues before they cascade
7. **Test Chaos Scenarios**: Regularly validate error handling

## Integration with Epic 0 Learnings

Based on our successful Epic 0 implementation:

1. **Proven Patterns**:
   - Retry with exponential backoff (used in lakeapi client)
   - Detailed error context in exceptions
   - Progress tracking with clear status

2. **New Requirements**:
   - Handle streaming at scale (220GB/month)
   - Manage memory within 28GB constraint
   - Process 100k events/second

This comprehensive error handling ensures the pipeline can handle both batch processing (Epic 0) and streaming workloads (Epic 2) reliably.