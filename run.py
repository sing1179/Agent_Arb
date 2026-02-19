#!/usr/bin/env python3
"""Convenience launcher for AI Arbitrage Agent."""
import sys
from pathlib import Path

# Ensure arb_agent root is on path
root = Path(__file__).resolve().parent
sys.path.insert(0, str(root))

from src.main import main

if __name__ == "__main__":
    main()
