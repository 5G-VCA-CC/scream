#!/usr/bin/env python3
"""Legacy wrapper.

This script is kept for backwards compatibility.
Use tests/plot_scream_histogram.py instead.

Old usage:
  python3 tests/plot_scream_histogram_fake_traffic.py <ect> <delay_ms> <loss_pct> <trace> <test_results_directory> <output_directory> [--no-show]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    script = Path(__file__).with_name("plot_scream_histogram.py")
    if not script.exists():
        raise SystemExit(f"ERROR: unified plotter not found: {script}")

    os.execv(sys.executable, [sys.executable, str(script)] + sys.argv[1:])


if __name__ == "__main__":
    main()
