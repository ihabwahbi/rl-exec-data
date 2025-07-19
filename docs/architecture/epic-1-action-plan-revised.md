# Epic 1: Analysis & Validation - Revised Action Plan

**Status**: Critical Issues - Validation-First Approach Required  
**Timeline**: Week 1-3 (Extended for validation framework)  
**Prerequisites**: ✅ Epic 0 Complete - Real data available

## ⚠️ Critical Update

Story 1.2 implementation revealed fundamental issues. This revised plan incorporates a validation-first approach to prevent further misalignments.

## Phase 1: Foundation Fixes (Week 1)

### Story 1.2 Fix: LiveCapture Correction 🔴 BLOCKING

**Issue**: Implementation transforms data instead of preserving raw format

**Fix Tasks**:
1. **Correct WebSocket URL** (1 hour)
   ```python
   # WRONG: btcusdt@depth
   # CORRECT: btcusdt@depth@100ms
   ws_url = f"wss://stream.binance.com:9443/stream?streams={symbol}@trade/{symbol}@depth@100ms"
   ```

2. **Preserve Raw Format** (2 hours)
   ```python
   # WRONG: Transform and extract fields
   # CORRECT: Preserve exact message
   output = {
       "capture_ns": time.perf_counter_ns(),
       "stream": msg["stream"],
       "data": msg["data"]  # NO transformation
   }
   ```

3. **Move to Scripts** (30 min)
   - Create `scripts/capture_live_data.py`
   - Remove embedded CLI from module

4. **Single Chronological File** (1 hour)
   - Remove separate trade/orderbook writers
   - Implement single chronological stream

**Validation**:
- [ ] Output format matches specification exactly
- [ ] WebSocket URL includes @100ms
- [ ] Script in correct location
- [ ] Chronological ordering preserved

### Story 1.1 Re-execution: Real Data Analysis 🔴 CRITICAL

**Issue**: Original execution used synthetic data

**Tasks**:
1. **Re-run with Real Data** (2 hours)
   ```python
   # Use actual Crypto Lake data from Epic 0
   analyzer = OriginTimeAnalyzer(real_data_path)
   results = analyzer.analyze()
   ```

2. **Update Findings** (1 hour)
   - Document actual origin_time reliability
   - Update architecture decisions if needed

**Validation**:
- [ ] Analysis uses real Crypto Lake data
- [ ] Results documented with actual percentages
- [ ] Architecture updated based on findings

### Golden Sample Capture (24 hours runtime)

**After fixes are validated**:
1. Capture first 24-hour sample
2. Verify raw format preservation
3. Check for gaps or issues

## Phase 2: Validation Framework (Week 2)

### New Component: ValidationFramework 🆕

**Purpose**: Empirically validate all assumptions before implementation

**Implementation Tasks**:

1. **Core Framework** (8 hours)
   ```python
   class ValidationFramework:
       def __init__(self):
           self.golden_sample_manager = GoldenSampleManager()
           self.statistical_validators = StatisticalValidators()
           self.research_validator = ResearchClaimValidator()
           self.report_generator = ReportGenerator()
   ```

2. **Statistical Validators** (12 hours)
   - Kolmogorov-Smirnov test implementation
   - Anderson-Darling test implementation
   - Power law validation (exponent 2.4±0.1)
   - Microstructure analyzers

3. **Research Claim Validators** (8 hours)
   - Origin time latency measurement
   - Snapshot frequency validation
   - WebSocket ordering tests
   - Performance benchmarks

4. **Report Generation** (4 hours)
   - Automated fidelity scoring
   - Visual comparisons
   - Go/no-go recommendations

### Empirical Research Validation 🔬

**Test each AI research claim**:

1. **Timing Claims** (4 hours)
   ```python
   def validate_latency_claims():
       # Claim: 10-50ms latency
       latencies = measure_origin_time_latencies()
       assert np.percentile(latencies, 95) < 50
   ```

2. **Data Completeness** (4 hours)
   ```python
   def validate_completeness_claims():
       # Claim: L2 snapshots may lack origin_time
       missing_rate = check_origin_time_completeness()
       document_actual_rate(missing_rate)
   ```

3. **WebSocket Behavior** (6 hours)
   ```python
   def validate_ordering_claims():
       # Claim: Combined streams prevent out-of-order
       combined_results = test_combined_stream()
       separate_results = test_separate_streams()
       compare_ordering_accuracy()
   ```

## Phase 3: Adaptive Decision Making (Week 3)

### Story 1.2.5: Technical Validation Spike 🚨

**Now includes validation results**:

1. **Delta Feed Validation** (4 hours)
   ```python
   if ValidationResults.origin_time_reliability > 0.999:
       approach = "simple_timestamp_merge"
   elif ValidationResults.origin_time_reliability > 0.95:
       approach = "smart_merge_with_fallback"
   else:
       approach = "snapshot_anchored"
   ```

2. **Memory Profiling** (4 hours)
   - Test with validated approach
   - Measure actual memory usage
   - Determine streaming requirements

3. **Performance Testing** (4 hours)
   - Benchmark chosen approach
   - Validate 100k events/sec target
   - Test on actual hardware

### Decision Documentation 📝

**Create Architecture Decision Records**:
1. ADR-004: Reconstruction approach based on validation
2. ADR-005: Memory management strategy
3. ADR-006: Performance optimization choices

## Validation Gates 🚦

### Gate 1: Story Fixes (Before proceeding)
- ✅ Story 1.2 captures raw data correctly
- ✅ Story 1.1 uses real data
- ✅ First golden sample captured

### Gate 2: Framework Operational (Week 2)
- ✅ Statistical tests implemented
- ✅ Research validators working
- ✅ Automated reports generated

### Gate 3: Go/No-Go Decision (Week 3)
- ✅ All validations complete
- ✅ Approach selected based on data
- ✅ Performance validated

## Risk Mitigation Updates

| Risk | Detection | Mitigation |
|------|-----------|------------|
| Specification misunderstanding | Validation framework | Examples in specs |
| Research claims wrong | Empirical testing | Adaptive approach |
| Performance assumptions | Early benchmarking | Multiple implementations |
| Memory constraints | Continuous profiling | Streaming fallback |

## Success Metrics - Revised

### Week 1 Success
- Story 1.2 fixed and validated
- Story 1.1 re-executed with real data
- First golden sample captured
- No specification mismatches

### Week 2 Success
- Validation framework operational
- 50%+ research claims tested
- Multiple golden samples captured
- Automated reporting working

### Week 3 Success
- All validations complete
- Architecture decisions documented
- Performance targets validated
- Clear path to Epic 2

## Communication Plan

### Daily Updates
- Validation results
- Issues discovered
- Architecture impacts

### Weekly Reports
- Empirical findings summary
- Decision recommendations
- Risk assessment updates

## Lessons Learned Integration

1. **Always show examples** in specifications
2. **Validate before building** complex features
3. **Test research claims** empirically
4. **Document why** not just what

---

**Note**: This revised plan addresses the critical issues discovered in Story 1.2 and establishes a validation-first approach that will prevent similar issues in future epics.