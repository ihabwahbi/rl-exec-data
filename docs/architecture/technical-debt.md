# Technical Debt Registry

**Created**: 2025-07-30  
**Status**: Active Registry  
**Purpose**: Track and manage technical debt items for prioritization and resolution

## Overview

This document serves as the central registry for technical debt in the RLX Data Pipeline. Technical debt items are tracked here to ensure visibility, enable prioritization discussions with the Product Owner, and guide future refactoring efforts.

## Debt Classification

- **Impact**: High / Medium / Low - Business impact if not addressed
- **Effort**: Story points or day estimates for resolution
- **Risk**: Probability of causing issues if left unresolved
- **Type**: Architecture / Code Quality / Performance / Security / Documentation

## Current Technical Debt Items

### 1. Trade Matching Simplification
- **Description**: Current implementation uses simplified trade matching without partial fill support
- **Impact**: Medium - May need enhancement for real trading scenarios
- **Effort**: 2-3 days
- **Risk**: Low for backtesting, High for live trading
- **Type**: Architecture
- **Recommendation**: Address before any live trading implementation
- **Story**: Implement partial fill support and complex order matching logic

### 2. Decimal Precision Workarounds
- **Description**: Polars 0.20.31 requires verbose workarounds for decimal128 operations
- **Impact**: Low - Works correctly but code is verbose
- **Effort**: Minimal (wait for library update)
- **Risk**: Low - No functional impact
- **Type**: Code Quality
- **Resolution**: Wait for Polars update with better decimal support
- **Notes**: Current workarounds are well-tested and functional

### 3. DataFrame Row Iteration
- **Description**: EventReplayer uses row-by-row iteration instead of vectorized operations
- **Impact**: Low - Performance still exceeds requirements (345K msg/s)
- **Effort**: 1-2 days for optimization
- **Risk**: Low - Current performance is acceptable
- **Type**: Performance
- **Recommendation**: Consider optimization if performance requirements increase
- **Potential Improvement**: 20-30% throughput gain with vectorization

### 4. Basic Error Recovery
- **Description**: Error handling uses simple retry logic without sophisticated backoff or circuit breakers
- **Impact**: Medium - Works for POC but not production-ready
- **Effort**: 3-5 days for production hardening
- **Risk**: Medium - Could cause cascading failures under stress
- **Type**: Architecture
- **Recommendation**: Implement before production deployment
- **Required Enhancements**:
  - Exponential backoff for retries
  - Circuit breaker pattern for external services
  - Dead letter queue for failed messages
  - Comprehensive error categorization

### 5. Memory Management Simplicity
- **Description**: Fixed memory pools without dynamic adjustment
- **Impact**: Low - Current approach works within constraints
- **Effort**: 5-7 days for adaptive memory management
- **Risk**: Low - System operates well within 28GB limit
- **Type**: Performance
- **Notes**: Current fixed pools achieve required performance

### 6. Monitoring Gaps
- **Description**: Basic OpenTelemetry integration without comprehensive dashboards
- **Impact**: Medium - Operational visibility limited
- **Effort**: 3-5 days for full observability
- **Risk**: High - Difficult to diagnose production issues
- **Type**: Architecture
- **Required Components**:
  - Grafana dashboards
  - Alert rules
  - SLO definitions
  - Distributed tracing

## Resolved Debt Items

### ~~Sequence Gap Handling~~ ✅
- **Resolution Date**: 2025-07-15
- **Description**: Initially assumed gaps in delta feed would require complex handling
- **Resolution**: Validation showed 0% gaps in 11.15M messages
- **Outcome**: Simplified architecture, removed unnecessary complexity

### ~~Memory Constraint Concerns~~ ✅
- **Resolution Date**: 2025-07-20
- **Description**: Worried about 28GB memory limit
- **Resolution**: Achieved 1.67GB usage for 8M events (14x safety margin)
- **Outcome**: No memory optimization needed

## Debt Prioritization Matrix

| Priority | Items | Rationale |
|----------|-------|-----------|
| **P0 - Critical** | None currently | No items blocking current functionality |
| **P1 - High** | Error Recovery, Monitoring Gaps | Required for production readiness |
| **P2 - Medium** | Trade Matching, Decimal Workarounds | Enhance capability and maintainability |
| **P3 - Low** | DataFrame Iteration, Memory Management | Performance optimizations |

## Debt Metrics

- **Total Items**: 6
- **High Impact**: 2
- **Total Estimated Effort**: 16-25 days
- **Technical Debt Ratio**: ~10% of codebase

## Review Process

1. **Weekly Review**: Development team reviews new debt items
2. **Monthly Prioritization**: Product Owner and Architect prioritize items
3. **Quarterly Planning**: Allocate capacity for debt reduction
4. **Continuous Tracking**: Update this registry as debt is created or resolved

## Guidelines for Adding Debt

When adding new technical debt:
1. Clearly describe the issue and its impact
2. Provide effort estimates
3. Suggest resolution approach
4. Link to relevant code or documentation
5. Tag with appropriate labels

## Integration with Development Process

- **Story Creation**: Each P1 debt item should have a corresponding story
- **Sprint Planning**: Allocate 15-20% capacity for debt reduction
- **Definition of Done**: New features should not increase debt ratio
- **Code Reviews**: Identify and document new debt during reviews