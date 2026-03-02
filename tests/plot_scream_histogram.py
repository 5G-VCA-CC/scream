#!/usr/bin/env python3
"""plot_scream_histogram.py

Histogram plotter for SCReAM final-summary statistics across multiple runs.

Each *_tx.log file contributes exactly one data point (from the final summary
block printed by ScreamTx::printFinalSummary), so the histograms show the
distribution of per-run metrics across a batch of test iterations.

Usage:
  python3 tests/plot_scream_histogram.py <ect> <delay_ms> <loss_pct> <trace> <test_results_directory> <output_directory> [--video VIDEO_FILE] [--no-show]

Arguments:
  ect                    : 0 or 1 (L4S disabled/enabled)
  delay_ms               : link delay in milliseconds
  loss_pct               : packet loss rate as decimal (e.g., 0.01 for 1%)
  trace                  : path to trace file (filename will be extracted)
  test_results_directory : directory containing *_tx.log files
  output_directory       : directory to save PNG plots

Optional:
  --video VIDEO_FILE     : if provided, titles/config include video name
  --no-show              : do not display plots (useful for headless runs)

Reads all *_tx.log files from the directory and creates histogram plots from
the final summary block of each log.
"""

from __future__ import annotations

import argparse
import glob
import re
import sys
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np


def _save_fig(fig, outdir: Path, filename: str) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    fig.savefig(outdir / filename, dpi=200, bbox_inches="tight")


# ---------------------------------------------------------------------------
# Keys present in the per-run data dict returned by parse_final_summary
# ---------------------------------------------------------------------------
_SUMMARY_KEYS = [
    "run_label",
    "bitrate_min",
    "bitrate_max",
    "bitrate_avg",
    "rtt_min",
    "rtt_max",
    "rtt_avg",
    "queue_delay_max",
    "queue_delay_avg",
    "packet_loss_avg",
    "ecn_not_ect",
    "ecn_ect0",
    "ecn_ect1",
    "ecn_ce",
]


def _empty_summary_data() -> dict[str, list[Any]]:
    return {k: [] for k in _SUMMARY_KEYS}


def parse_final_summary(logfile: str | Path) -> dict[str, float | str] | None:
    """Extract the final summary block from a single *_tx.log file.

    Returns a flat dict with one value per metric, or None if the summary
    block was not found.

    The expected format (printed by ScreamTx::printFinalSummary):
        ======================== Summary ==========================
         Bitrate min/max/avg [kbps]          :  1000/ 5000/ 3000
         RTT     min/max/avg [s]             : 0.010/0.050/0.025
         Queue delay max/avg [s]             : 0.030/0.015
         Packet loss avg [%]                 : 0.123
         ECN/L4S NotECT/ECT(0)/ECT(1)/CE [%] :  0.0/100.0/  0.0/  0.0
        ===========================================================
    """

    bitrate_re = re.compile(
        r"Bitrate\s+min/max/avg\s+\[kbps\]\s*:\s*"
        r"(?P<min>[\d.eE+-]+)\s*/\s*(?P<max>[\d.eE+-]+)\s*/\s*(?P<avg>[\d.eE+-]+)"
    )
    rtt_re = re.compile(
        r"RTT\s+min/max/avg\s+\[s\]\s*:\s*"
        r"(?P<min>[\d.eE+-]+)\s*/\s*(?P<max>[\d.eE+-]+)\s*/\s*(?P<avg>[\d.eE+-]+)"
    )
    qdelay_re = re.compile(
        r"Queue delay\s+max/avg\s+\[s\]\s*:\s*"
        r"(?P<max>[\d.eE+-]+)\s*/\s*(?P<avg>[\d.eE+-]+)"
    )
    plr_re = re.compile(
        r"Packet loss avg\s+\[%\]\s*:\s*(?P<avg>[\d.eE+-]+)"
    )
    ecn_re = re.compile(
        r"ECN/L4S\s+NotECT/ECT\(0\)/ECT\(1\)/CE\s+\[%\]\s*:\s*"
        r"(?P<not_ect>[\d.eE+-]+)\s*/\s*(?P<ect0>[\d.eE+-]+)\s*/\s*"
        r"(?P<ect1>[\d.eE+-]+)\s*/\s*(?P<ce>[\d.eE+-]+)"
    )

    result: dict[str, float | str] = {}
    found_any = False

    with open(logfile, "r") as f:
        for line in f:
            m = bitrate_re.search(line)
            if m:
                result["bitrate_min"] = float(m.group("min"))
                result["bitrate_max"] = float(m.group("max"))
                result["bitrate_avg"] = float(m.group("avg"))
                found_any = True
                continue

            m = rtt_re.search(line)
            if m:
                result["rtt_min"] = float(m.group("min"))
                result["rtt_max"] = float(m.group("max"))
                result["rtt_avg"] = float(m.group("avg"))
                found_any = True
                continue

            m = qdelay_re.search(line)
            if m:
                result["queue_delay_max"] = float(m.group("max"))
                result["queue_delay_avg"] = float(m.group("avg"))
                found_any = True
                continue

            m = plr_re.search(line)
            if m:
                result["packet_loss_avg"] = float(m.group("avg"))
                found_any = True
                continue

            m = ecn_re.search(line)
            if m:
                result["ecn_not_ect"] = float(m.group("not_ect"))
                result["ecn_ect0"] = float(m.group("ect0"))
                result["ecn_ect1"] = float(m.group("ect1"))
                result["ecn_ce"] = float(m.group("ce"))
                found_any = True
                continue

    return result if found_any else None


def parse_all_logs(directory: str | Path) -> dict[str, list[Any]] | None:
    """Parse the final summary from every *_tx.log in *directory*.

    Returns a dict where each key holds a list of per-run values (one entry
    per log file), or None if no valid logs were found.
    """

    log_pattern = str(Path(directory) / "*_tx.log")
    log_files = sorted(glob.glob(log_pattern))

    if not log_files:
        print(f"No *_tx.log files found in {directory}")
        return None

    print(f"Found {len(log_files)} log files:")
    for log in log_files:
        print(f"  - {Path(log).name}")

    all_data = _empty_summary_data()
    skipped = 0

    for logfile in log_files:
        run_label = Path(logfile).stem  # e.g. "test_1_tx"
        result = parse_final_summary(logfile)
        if result is None:
            print(f"  WARNING: No final summary found in {Path(logfile).name} — skipping")
            skipped += 1
            continue

        all_data["run_label"].append(run_label)
        for key in _SUMMARY_KEYS:
            if key == "run_label":
                continue
            all_data[key].append(result.get(key, float("nan")))

    n_runs = len(all_data["run_label"])
    print(f"\nRuns parsed: {n_runs}  (skipped {skipped})")
    return all_data if n_runs > 0 else None


def _title_suffix(video_file: str | None) -> str:
    return "(BW Tool With Video Encoder)" if video_file else "(BW Tool With Fake Traffic)"


def _adaptive_bins(values: list[float]) -> int:
    """Choose a reasonable number of histogram bins for the sample count."""
    n = len(values)
    if n <= 5:
        return max(n, 2)
    if n <= 20:
        return min(n, 10)
    return min(50, max(10, int(np.sqrt(n))))


def plot_histograms(
    data: dict[str, list[Any]] | None,
    *,
    outdir: Path | None = None,
    show_plots: bool = True,
    test_config: str = "",
    video_file: str | None = None,
) -> None:
    if not data or not data.get("run_label"):
        print("No data to plot.")
        return

    n_runs = len(data["run_label"])
    suffix = _title_suffix(video_file)

    def _set_title(ax, base: str) -> None:
        title = f"{base} {suffix}"
        if test_config:
            title += f"\n{test_config}"
        title += f"\n({n_runs} runs)"
        ax.set_title(title, fontsize=13, fontweight="bold")

    def _annotate_mean(ax, values, unit="", fmt=".2f"):
        if not values:
            return
        m = np.nanmean(values)
        ax.axvline(m, color="red", linestyle="--", linewidth=2,
                   label=f"Mean: {m:{fmt}} {unit}".strip())
        ax.legend(fontsize=10)

    # --- Histogram 1: Average Bitrate (kbps → Mbps) ---
    vals = [v / 1000.0 for v in data["bitrate_avg"]]
    fig1, ax1 = plt.subplots(figsize=(12, 6))
    ax1.hist(vals, bins=_adaptive_bins(vals), color="blue", alpha=0.7, edgecolor="black")
    ax1.set_xlabel("Average Bitrate (Mbps)", fontsize=12)
    ax1.set_ylabel("Frequency (runs)", fontsize=12)
    _set_title(ax1, "Average Bitrate Distribution Across Runs")
    ax1.grid(True, alpha=0.3, axis="y")
    _annotate_mean(ax1, vals, "Mbps")
    fig1.tight_layout()
    if outdir:
        _save_fig(fig1, outdir, "hist_bitrate_avg_mbps.png")

    # --- Histogram 2: Min / Max Bitrate (kbps → Mbps) overlay ---
    vals_min = [v / 1000.0 for v in data["bitrate_min"]]
    vals_max = [v / 1000.0 for v in data["bitrate_max"]]
    fig2, ax2 = plt.subplots(figsize=(12, 6))
    bins2 = _adaptive_bins(vals_min + vals_max)
    ax2.hist(vals_min, bins=bins2, alpha=0.5, color="cyan", edgecolor="black", label="Min Bitrate")
    ax2.hist(vals_max, bins=bins2, alpha=0.5, color="orange", edgecolor="black", label="Max Bitrate")
    ax2.set_xlabel("Bitrate (Mbps)", fontsize=12)
    ax2.set_ylabel("Frequency (runs)", fontsize=12)
    _set_title(ax2, "Min / Max Bitrate Distribution Across Runs")
    ax2.grid(True, alpha=0.3, axis="y")
    ax2.legend(fontsize=10)
    fig2.tight_layout()
    if outdir:
        _save_fig(fig2, outdir, "hist_bitrate_minmax_mbps.png")

    # --- Histogram 3: Average RTT (s → ms) ---
    rtt_avg_ms = [v * 1000.0 for v in data["rtt_avg"]]
    fig3, ax3 = plt.subplots(figsize=(12, 6))
    ax3.hist(rtt_avg_ms, bins=_adaptive_bins(rtt_avg_ms), color="green", alpha=0.7, edgecolor="black")
    ax3.set_xlabel("Average RTT (ms)", fontsize=12)
    ax3.set_ylabel("Frequency (runs)", fontsize=12)
    _set_title(ax3, "Average RTT Distribution Across Runs")
    ax3.grid(True, alpha=0.3, axis="y")
    _annotate_mean(ax3, rtt_avg_ms, "ms")
    fig3.tight_layout()
    if outdir:
        _save_fig(fig3, outdir, "hist_rtt_avg_ms.png")

    # --- Histogram 4: Min / Max RTT (s → ms) overlay ---
    rtt_min_ms = [v * 1000.0 for v in data["rtt_min"]]
    rtt_max_ms = [v * 1000.0 for v in data["rtt_max"]]
    fig4, ax4 = plt.subplots(figsize=(12, 6))
    bins4 = _adaptive_bins(rtt_min_ms + rtt_max_ms)
    ax4.hist(rtt_min_ms, bins=bins4, alpha=0.5, color="cyan", edgecolor="black", label="Min RTT")
    ax4.hist(rtt_max_ms, bins=bins4, alpha=0.5, color="orange", edgecolor="black", label="Max RTT")
    ax4.set_xlabel("RTT (ms)", fontsize=12)
    ax4.set_ylabel("Frequency (runs)", fontsize=12)
    _set_title(ax4, "Min / Max RTT Distribution Across Runs")
    ax4.grid(True, alpha=0.3, axis="y")
    ax4.legend(fontsize=10)
    fig4.tight_layout()
    if outdir:
        _save_fig(fig4, outdir, "hist_rtt_minmax_ms.png")

    # --- Histogram 5: Average Queue Delay (s → ms) ---
    qd_avg_ms = [v * 1000.0 for v in data["queue_delay_avg"]]
    fig5, ax5 = plt.subplots(figsize=(12, 6))
    ax5.hist(qd_avg_ms, bins=_adaptive_bins(qd_avg_ms), color="purple", alpha=0.7, edgecolor="black")
    ax5.set_xlabel("Average Queue Delay (ms)", fontsize=12)
    ax5.set_ylabel("Frequency (runs)", fontsize=12)
    _set_title(ax5, "Average Queue Delay Distribution Across Runs")
    ax5.grid(True, alpha=0.3, axis="y")
    _annotate_mean(ax5, qd_avg_ms, "ms")
    fig5.tight_layout()
    if outdir:
        _save_fig(fig5, outdir, "hist_queue_delay_avg_ms.png")

    # --- Histogram 6: Max Queue Delay (s → ms) ---
    qd_max_ms = [v * 1000.0 for v in data["queue_delay_max"]]
    fig6, ax6 = plt.subplots(figsize=(12, 6))
    ax6.hist(qd_max_ms, bins=_adaptive_bins(qd_max_ms), color="magenta", alpha=0.7, edgecolor="black")
    ax6.set_xlabel("Max Queue Delay (ms)", fontsize=12)
    ax6.set_ylabel("Frequency (runs)", fontsize=12)
    _set_title(ax6, "Max Queue Delay Distribution Across Runs")
    ax6.grid(True, alpha=0.3, axis="y")
    _annotate_mean(ax6, qd_max_ms, "ms")
    fig6.tight_layout()
    if outdir:
        _save_fig(fig6, outdir, "hist_queue_delay_max_ms.png")

    # --- Histogram 7: Packet Loss Rate (%) ---
    plr = data["packet_loss_avg"]
    fig7, ax7 = plt.subplots(figsize=(12, 6))
    ax7.hist(plr, bins=_adaptive_bins(plr), color="red", alpha=0.7, edgecolor="black")
    ax7.set_xlabel("Packet Loss Rate (%)", fontsize=12)
    ax7.set_ylabel("Frequency (runs)", fontsize=12)
    _set_title(ax7, "Packet Loss Rate Distribution Across Runs")
    ax7.grid(True, alpha=0.3, axis="y")
    _annotate_mean(ax7, plr, "%")
    fig7.tight_layout()
    if outdir:
        _save_fig(fig7, outdir, "hist_packet_loss_avg_pct.png")

    # --- Histogram 8: ECN marking breakdown (%) ---
    fig8, ax8 = plt.subplots(figsize=(12, 6))
    bins8 = _adaptive_bins(data["ecn_ce"])
    ax8.hist(data["ecn_not_ect"], bins=bins8, alpha=0.5, color="gray", edgecolor="black", label="Not-ECT")
    ax8.hist(data["ecn_ect0"], bins=bins8, alpha=0.5, color="blue", edgecolor="black", label="ECT(0)")
    ax8.hist(data["ecn_ect1"], bins=bins8, alpha=0.5, color="green", edgecolor="black", label="ECT(1)")
    ax8.hist(data["ecn_ce"], bins=bins8, alpha=0.5, color="red", edgecolor="black", label="CE")
    ax8.set_xlabel("ECN Marking (%)", fontsize=12)
    ax8.set_ylabel("Frequency (runs)", fontsize=12)
    _set_title(ax8, "ECN Marking Distribution Across Runs")
    ax8.grid(True, alpha=0.3, axis="y")
    ax8.legend(fontsize=10)
    fig8.tight_layout()
    if outdir:
        _save_fig(fig8, outdir, "hist_ecn_pct.png")

    if show_plots:
        plt.show()

    # ---- Textual summary ----
    def _stats_line(label, values, unit="", fmt=".3f"):
        arr = np.array(values, dtype=float)
        arr = arr[~np.isnan(arr)]
        if len(arr) == 0:
            return f"  {label}: (no data)"
        return (
            f"  {label}: min={np.min(arr):{fmt}}, max={np.max(arr):{fmt}}, "
            f"mean={np.mean(arr):{fmt}}, median={np.median(arr):{fmt}} {unit}"
        )

    print(f"\n=== Per-Run Final Summary Statistics ({n_runs} runs) ===")
    print(_stats_line("Avg Bitrate (Mbps)", vals, "Mbps"))
    print(_stats_line("Min Bitrate (Mbps)", vals_min, "Mbps"))
    print(_stats_line("Max Bitrate (Mbps)", vals_max, "Mbps"))
    print(_stats_line("Avg RTT     (ms)",   rtt_avg_ms, "ms"))
    print(_stats_line("Min RTT     (ms)",   rtt_min_ms, "ms"))
    print(_stats_line("Max RTT     (ms)",   rtt_max_ms, "ms"))
    print(_stats_line("Avg Queue Delay (ms)", qd_avg_ms, "ms"))
    print(_stats_line("Max Queue Delay (ms)", qd_max_ms, "ms"))
    print(_stats_line("Packet Loss (%)",    plr, "%"))
    print(_stats_line("ECN Not-ECT (%)",    data["ecn_not_ect"], "%", ".1f"))
    print(_stats_line("ECN ECT(0)  (%)",    data["ecn_ect0"], "%", ".1f"))
    print(_stats_line("ECN ECT(1)  (%)",    data["ecn_ect1"], "%", ".1f"))
    print(_stats_line("ECN CE      (%)",    data["ecn_ce"], "%", ".1f"))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("ect", type=int, choices=[0, 1], help="0 = L4S Disabled, 1 = L4S Enabled")
    parser.add_argument("delay_ms", type=float, help="link delay in milliseconds")
    parser.add_argument("loss_pct", type=float, help="packet loss rate as decimal (e.g., 0.01 for 1%%)")
    parser.add_argument("trace", help="path to trace file")
    parser.add_argument("directory", help="test results directory containing *_tx.log files")
    parser.add_argument("outdir", help="directory to save all plots as PNGs")
    parser.add_argument("--video", default=None, help="optional path to video file (for labeling)")
    parser.add_argument("--no-show", action="store_true", help="do not display plots (useful for headless runs)")

    args = parser.parse_args(argv)

    directory = Path(args.directory).expanduser().resolve()
    if not directory.exists():
        print(f"Error: Directory '{directory}' not found.")
        sys.exit(1)
    if not directory.is_dir():
        print(f"Error: '{directory}' is not a directory.")
        sys.exit(1)

    l4s_status = "L4S Enabled" if args.ect == 1 else "L4S Disabled"
    loss_pct_percent = args.loss_pct * 100
    trace_name = Path(args.trace).name

    parts = [
        l4s_status,
        f"Delay: {args.delay_ms:.0f}ms",
        f"Loss: {loss_pct_percent:.2f}%",
        f"Trace: {trace_name}",
    ]

    video_file = args.video
    if video_file:
        parts.append(f"Video: {Path(video_file).name}")

    test_config = " | ".join(parts)

    outdir = Path(args.outdir).expanduser().resolve()
    print(f"Test Configuration: {test_config}")
    print(f"Parsing logs from directory: {directory}\n")

    all_data = parse_all_logs(directory)
    if all_data:
        print(f"Saving plots to: {outdir}")
        plot_histograms(
            all_data,
            outdir=outdir,
            show_plots=not args.no_show,
            test_config=test_config,
            video_file=video_file,
        )
        print("\nPNGs saved.")


if __name__ == "__main__":
    main()
