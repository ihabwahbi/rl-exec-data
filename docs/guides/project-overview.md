# RLX Data Pipeline - Project Overview

**For New Team Members**

## Quick Start

1. **Read First**: 
   - `/docs/prd/index.md` - Product requirements and current status
   - `/docs/prd/project-status.md` - Current project state
   - `/docs/architecture/index.md` - Technical architecture

2. **Current Status**: Epic 0 (Data Acquisition) is complete. We can now work with real Crypto Lake data.

3. **Next Tasks**: Epic 1 stories (1.1, 1.2, 1.2.5) need to be implemented using real data.

## Project Structure

```
/docs/
├── prd/                    # Product documentation
│   ├── index.md           # Main PRD document
│   ├── project-status.md  # Current status (START HERE)
│   ├── epics.md          # All epics and stories
│   └── research/         # Background research
├── architecture/         # Technical design
│   ├── index.md         # Architecture overview
│   └── *.md            # Component designs
├── stories/            # Implementation stories
│   ├── 0.1.*          # ✅ Epic 0 (COMPLETE)
│   ├── 1.1.*          # ⏳ Epic 1 (IN PROGRESS)
│   └── 1.2.*          # ⏳ Epic 1 stories
└── guides/            # This directory
```

## Key Achievements

### Epic 0: Data Acquisition ✅ COMPLETE
- Built production-ready pipeline using lakeapi
- 49% test coverage with comprehensive error handling
- CLI with 6 commands for data operations
- Successfully downloaded and validated real market data

### What's Ready
- Crypto Lake API authentication
- Data download and validation pipeline
- Staging area management
- Comprehensive test suite

## Technical Stack

- **Language**: Python 3.10+
- **Data Access**: lakeapi (official Crypto Lake package)
- **Data Processing**: Polars (for decimal128 support)
- **Storage**: Parquet files
- **Testing**: pytest with 49% coverage
- **CLI**: Click framework

## Next Steps for Development

### Epic 1: Foundational Analysis
1. **Story 1.1**: Re-run origin_time analysis with real data
2. **Story 1.2**: Implement live data capture from Binance
3. **Story 1.2.5**: Technical validation spike (critical Go/No-Go)

### Key Commands

```bash
# Test Crypto Lake connection
python scripts/acquire_data_lakeapi.py test-connection

# List available data
python scripts/acquire_data_lakeapi.py list-inventory

# Download data
python scripts/acquire_data_lakeapi.py download \
  --start-date 2024-01-01 \
  --end-date 2024-01-31

# Run tests
pytest tests/acquisition/ -v --cov=src/rlx_datapipe/acquisition
```

## Critical Context

### Why Epic 0 Was Added
- Initial validation used synthetic data (invalid)
- Real Crypto Lake data was never acquired
- All previous work had to be redone

### Lessons Learned
1. Always validate with real data
2. Test coverage is essential (QA review caught gaps)
3. Document consolidation prevents confusion
4. Clear epic dependencies prevent wasted work

## Key Files

### Implementation
- `/src/rlx_datapipe/acquisition/` - Data acquisition modules
- `/scripts/acquire_data_lakeapi.py` - Main CLI tool
- `/tests/acquisition/` - Test suite

### Documentation
- `/docs/prd/project-status.md` - Always check current status
- `/docs/stories/` - Detailed implementation guides
- `/docs/DATA_ACQUISITION_USER_GUIDE.md` - How to use the pipeline

## Contact Points

- **Product**: Review PRD and project status
- **Architecture**: Check architecture docs
- **Implementation**: See story files
- **Testing**: Run test suite

## Success Criteria

The project succeeds when:
1. ✅ Real data is accessible (DONE)
2. ⏳ Technical validation passes (Epic 1)
3. ⏸️ Pipeline achieves >99.9% fidelity (Epic 2)
4. ⏸️ RL agent achieves -5bp improvement (Future)

Welcome to the team! Start with the project status document and work your way through the epics.