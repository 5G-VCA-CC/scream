#!/usr/bin/env python3
"""Legacy wrapper.

This script is kept for backwards compatibility.
Use tests/plot_scream_histogram.py instead.

Old usage:
  python3 tests/plot_scream_histogram_video_traffic.py <ect> <delay_ms> <loss_pct> <trace> <video> <test_results_directory> <output_directory> [--no-show]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 8:
        raise SystemExit(
            "Usage: plot_scream_histogram_video_traffic.py <ect> <delay_ms> <loss_pct> <trace> <video> <directory> <outdir> [--no-show]"
        )

    ect = sys.argv[1]
    delay_ms = sys.argv[2]
    loss_pct = sys.argv[3]
    trace = sys.argv[4]
    video = sys.argv[5]
    directory = sys.argv[6]
    outdir = sys.argv[7]
    extra = sys.argv[8:]

    script = Path(__file__).with_name("plot_scream_histogram.py")
    if not script.exists():
        raise SystemExit(f"ERROR: unified plotter not found: {script}")

    argv = [ect, delay_ms, loss_pct, trace, directory, outdir, "--video", video] + extra
    os.execv(sys.executable, [sys.executable, str(script)] + argv)


if __name__ == "__main__":
    main()
