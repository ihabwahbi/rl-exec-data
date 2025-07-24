#!/usr/bin/env python3
"""Script to run the multi-symbol reconstruction pipeline."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.rlx_datapipe.reconstruction.multi_symbol_main import main

if __name__ == "__main__":
    main()