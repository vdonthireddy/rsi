#!/usr/bin/env python3
"""Convenience launcher for the RSI demo without requiring package installation."""

from pathlib import Path
import sys

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from rsi_demo.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
