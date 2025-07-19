# Data Acquisition Checklist - Epic 0

## 🚨 CRITICAL: No Other Work Can Proceed Until This Is Complete

### Pre-Flight Checks (Day 1)

#### Access Verification
- [ ] **Crypto Lake Subscription**
  - Contact: ________________
  - Account Status: ________________
  - Subscription Tier: ________________
  - Data Access Level: ________________

- [ ] **API Credentials**
  - API Key Holder: ________________
  - Last Verified: ________________
  - Test Endpoint: https://api.crypto-lake.com/v1/health
  - Test Result: ________________

- [ ] **Budget Authorization**
  - Estimated Data Cost: $________________
  - Approved By: ________________
  - Budget Code: ________________

### Technical Setup (Day 1-2)

#### Environment Configuration
- [ ] Create secure credential storage (NOT in code)
  ```bash
  export CRYPTO_LAKE_API_KEY="..."
  export CRYPTO_LAKE_API_SECRET="..."
  ```

- [ ] Set up data directories
  ```bash
  mkdir -p data/staging/{raw,validating,ready,quarantine}
  mkdir -p data/logs/{download,validation,manifest}
  ```

- [ ] Install required dependencies
  ```bash
  pip install aiohttp asyncio polars pyarrow boto3
  ```

### Data Requirements Definition (Day 2)

#### Specify Exact Requirements
- [ ] **Primary Dataset**
  - Symbol: BTC-USDT
  - Exchange: binance
  - Start Date: 2024-01-01
  - End Date: 2024-12-31
  - Tables Required:
    - [ ] trades
    - [ ] book (L2 snapshots)
    - [ ] book_delta_v2 (if available)

- [ ] **Data Volume Estimates**
  - Trades: ~50GB compressed
  - Book Snapshots: ~150GB compressed
  - Book Deltas: ~20GB compressed
  - Total Storage Needed: ~500GB uncompressed

### Test Download (Day 2-3)

#### Small Sample Validation
- [ ] Download 1 day of data (suggest: 2024-06-15)
  ```python
  # Sample download code
  params = {
      "symbol": "BTC-USDT",
      "exchange": "binance",
      "start_date": "2024-06-15",
      "end_date": "2024-06-15",
      "data_type": "trades"
  }
  ```

- [ ] **Validate Sample Data**
  - [ ] File integrity (checksum matches)
  - [ ] Schema validation (expected columns present)
  - [ ] Data quality checks:
    - [ ] origin_time present and monotonic
    - [ ] No negative prices/quantities
    - [ ] Reasonable value ranges
  - [ ] Row count sanity check

### Full Download Planning (Day 3-4)

#### Download Strategy
- [ ] **Chunking Plan**
  - Chunk Size: 1 week per download
  - Total Chunks: 52
  - Parallel Downloads: 3 (respect rate limits)

- [ ] **Monitoring Setup**
  - [ ] Progress tracking dashboard
  - [ ] Download speed monitoring
  - [ ] Failure alerting
  - [ ] Disk space monitoring

- [ ] **Recovery Planning**
  - [ ] Resume capability for failed chunks
  - [ ] Checksum validation for each chunk
  - [ ] Quarantine process for bad data

### Production Download (Week 2)

#### Execution
- [ ] **Day 1-2**: Download Q1 2024
- [ ] **Day 3-4**: Download Q2 2024  
- [ ] **Day 5**: Download Q3 2024
- [ ] **Weekend**: Download Q4 2024

#### Daily Validation
- [ ] Run integrity checks on completed downloads
- [ ] Update progress tracking
- [ ] Address any failures immediately
- [ ] Monitor storage usage

### Data Validation & Certification (Week 3)

#### Comprehensive Validation
- [ ] **Completeness Checks**
  - [ ] All 365 days present
  - [ ] No gaps in trading hours
  - [ ] Holiday schedule matches exchange

- [ ] **Cross-Table Validation**
  - [ ] Trade timestamps align with book snapshots
  - [ ] Symbol/exchange consistency
  - [ ] Volume sanity checks

- [ ] **Statistical Validation**
  - [ ] Daily trade counts within expected range
  - [ ] Price continuity (no massive gaps)
  - [ ] Spread characteristics reasonable

#### Readiness Certification
- [ ] Generate data manifest with:
  - File inventory
  - Date coverage report
  - Validation results
  - Known issues/gaps

- [ ] **Final Certification**
  - Data Ready: YES / NO
  - Certified By: ________________
  - Date: ________________
  - Epic 1 Can Begin: YES / NO

### Contingency Plans

#### If Access Denied
1. Immediate escalation to VP Engineering
2. Explore alternative data vendors (Kaiko, Tardis)
3. Full stop on project - communicate to stakeholders

#### If Data Quality Issues
1. Document all issues in detail
2. Contact Crypto Lake support
3. Determine if issues are acceptable for PoC
4. Get written acceptance of limitations

#### If Download Fails
1. Implement exponential backoff retry
2. Switch to different time of day
3. Reduce parallelism
4. Contact vendor support

### Success Criteria

✅ **Data Acquisition Complete When:**
1. 12 months of BTC-USDT data downloaded
2. All files pass integrity validation
3. Schema matches documentation
4. No critical gaps identified
5. Data manifest complete
6. Readiness certificate issued

### Communication Plan

#### Daily Updates During Acquisition
- Slack: #rlx-data-pipeline
- Format: "Day X/15: Downloaded Y%, Z issues found"

#### Escalation Path
1. Technical issues → Lead Engineer
2. Access issues → VP Engineering  
3. Budget issues → Product Owner
4. Timeline impact → All Stakeholders

### Post-Acquisition

Once data is certified ready:
1. Update PROJECT_STATUS_SUMMARY
2. Enable Epic 1 work to begin
3. Schedule re-run of Story 1.1 with real data
4. Communicate success to all stakeholders

---

**Remember**: This is not optional busy work. Without real data, the entire project is building on quicksand. Every day of delay here saves weeks of rework later.