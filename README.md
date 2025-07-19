# RLX Data Pipeline

A high-performance data pipeline for processing cryptocurrency market data to train reinforcement learning agents.

## 🚨 CRITICAL: Current Project Status

**VALIDATION REQUIRED** - Story 1.2.5 (Technical Validation Spike) must be completed before ANY other development work. See `/docs/DEVELOPER_HANDOFF.md` for immediate actions.

## Overview

This project processes historical BTC-USDT L2 order book data from Crypto Lake to create a unified, high-fidelity dataset for backtesting and training reinforcement learning agents. The pipeline captures complete market microstructure using delta feeds and ensures decimal precision for ML training.

## Features

- Historical data analysis and validation
- Real-time data capture from Binance WebSocket
- Data quality assessment and fidelity reporting
- High-performance processing using Polars

## Installation

See [Development Setup Guide](docs/SETUP.md) for detailed installation instructions.

Quick start:
```bash
poetry install
```

## Usage

See individual scripts in the `scripts/` directory for specific functionality.

## Development

This project uses:
- Poetry for dependency management
- Polars for high-performance data processing
- Pytest for testing
- Black for code formatting
- Ruff for linting