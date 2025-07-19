# ADR-003: Empirical Validation of AI Research Claims

## Status
Accepted

## Context
Three independent AI systems (Claude, Gemini, OpenAI) provided detailed research on building the data pipeline. While they converged on many points, these remain theoretical claims that need empirical validation. Story 1.1 was initially executed with synthetic data, demonstrating the risk of accepting research claims without verification.

## Decision
Every technical claim from AI research must be empirically validated with real data before being used as the basis for architectural decisions.

## Key Claims Requiring Validation

### 1. Timing and Latency
- **Claim**: Origin_time latency is 10-50ms
- **Validation**: Measure actual latency distribution
- **Decision Impact**: Chronological ordering strategy

### 2. Data Completeness
- **Claim**: Origin_time may be missing in L2 snapshots
- **Validation**: Check actual null/zero rates
- **Decision Impact**: Fallback ordering strategy

### 3. WebSocket Behavior
- **Claim**: Combined streams prevent out-of-order delivery
- **Validation**: Compare separate vs combined empirically
- **Decision Impact**: Connection architecture

### 4. Reconstruction Approaches
- **Claim**: Full event replay provides higher fidelity
- **Validation**: Measure actual fidelity differences
- **Decision Impact**: Implementation complexity vs benefit

## Implementation Process
1. Create ResearchClaimValidator component
2. Design specific tests for each claim
3. Run tests with production data
4. Document findings in decision records
5. Update architecture based on results

## Consequences

### Positive
- Decisions based on facts, not assumptions
- Identifies research inaccuracies early
- Builds knowledge base for future
- Reduces technical risk

### Negative
- Requires additional development time
- May invalidate some research
- Could delay implementation

### Neutral
- Changes how we consume AI research
- Requires systematic approach
- Creates validation precedent

## Success Metrics
- Number of claims validated
- Percentage of claims confirmed
- Architecture changes from findings
- Risk mitigation achieved

## References
- /docs/archive/claude-datapipeline-research.md
- /docs/archive/gemini-datapipeline-research.md
- /docs/archive/openai-datapipeline-research.md
- Story 1.1 synthetic data issue