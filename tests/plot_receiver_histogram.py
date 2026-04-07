#!/usr/bin/env python3
"""plot_receiver_histogram.py

Histogram plotter for SCReAM receiver final-summary statistics across multiple runs.

Each *_rx.log file contributes exactly one data point (from the final summary
block printed by ScreamRx::Statistics::printFinalSummary), so the histograms
show the distribution of per-run receiver metrics across a batch.
"""

from __future__ import annotations

import argparse
import glob
import re
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np


_SUMMARY_KEYS = [
    "run_label",
    "receive_rate_min_mbps",
    "receive_rate_max_mbps",
    "receive_rate_avg_mbps",
    "ifdd_min_s",
    "ifdd_max_s",
    "ifdd_avg_s",
    "ifraw_min_s",
    "ifraw_max_s",
    "ifraw_avg_s",
    "total_inter_frame_delay_s",
    "total_squared_inter_frame_delay_s2",
    "inter_frame_delay_variance_s2",
    "datagrams_total",
    "bytes_total",
    "frames_completed_total",
    "frames_rendered_total",
    "freeze_count_total",
    "freeze_duration_total_s",
]


def _empty_summary_data() -> dict[str, list[Any]]:
    return {k: [] for k in _SUMMARY_KEYS}


def _save_fig(fig, outdir: Path, filename: str) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    fig.savefig(outdir / filename, dpi=200, bbox_inches="tight")


def _adaptive_bins(values: list[float]) -> int:
    n = len(values)
    if n <= 5:
        return max(2, n)
    if n <= 20:
        return min(10, n)
    return min(50, max(10, int(np.sqrt(n))))


def parse_final_summary(logfile: str | Path) -> dict[str, float | str] | None:
    """Extract receiver final summary from one *_rx.log.

    Expected lines (from ScreamRx::Statistics::printFinalSummary):
      Receive rate min/max/avg [Mbps]       : a/b/c
      IF delay diff min/max/avg [s]         : a/b/c
        IF arrival  min/max/avg [s]           : a/b/c
        Total inter-frame delay [s]           : x
        Total squared inter-frame delay [s^2] : x
        Inter-frame delay variance [s^2]      : x
      Datagrams total                       : x
      Bytes total                           : x
      Frames completed total                : x
      Frames rendered total                 : x
      Freeze count total                    : x
      Total freeze duration [s]             : x
    """

    rate_re = re.compile(
        r"Receive rate min/max/avg \[Mbps\]\s*:\s*"
        r"(?P<min>[\d.eE+-]+)\s*/\s*(?P<max>[\d.eE+-]+)\s*/\s*(?P<avg>[\d.eE+-]+)"
    )
    ifdd_re = re.compile(
        r"IF delay diff min/max/avg \[s\]\s*:\s*"
        r"(?P<min>[\d.eE+-]+)\s*/\s*(?P<max>[\d.eE+-]+)\s*/\s*(?P<avg>[\d.eE+-]+)"
    )
    ifraw_re = re.compile(
        r"IF arrival\s+min/max/avg \[s\]\s*:\s*"
        r"(?P<min>[\d.eE+-]+)\s*/\s*(?P<max>[\d.eE+-]+)\s*/\s*(?P<avg>[\d.eE+-]+)"
    )
    total_if_re = re.compile(r"Total inter-frame delay \[s\]\s*:\s*(?P<v>[\d.eE+-]+)")
    total_sq_if_re = re.compile(r"Total squared inter-frame delay \[s\^2\]\s*:\s*(?P<v>[\d.eE+-]+)")
    var_if_re = re.compile(r"Inter-frame delay variance \[s\^2\]\s*:\s*(?P<v>[\d.eE+-]+)")
    dgrams_re = re.compile(r"Datagrams total\s*:\s*(?P<v>[\d.eE+-]+)")
    bytes_re = re.compile(r"Bytes total\s*:\s*(?P<v>[\d.eE+-]+)")
    fcomp_re = re.compile(r"Frames completed total\s*:\s*(?P<v>[\d.eE+-]+)")
    frend_re = re.compile(r"Frames rendered total\s*:\s*(?P<v>[\d.eE+-]+)")
    fcnt_re = re.compile(r"Freeze count total\s*:\s*(?P<v>[\d.eE+-]+)")
    fdur_re = re.compile(r"Total freeze duration \[s\]\s*:\s*(?P<v>[\d.eE+-]+)")

    with open(logfile, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    m_rate = rate_re.search(text)
    if not m_rate:
        return None

    result: dict[str, float | str] = {
        "receive_rate_min_mbps": float(m_rate.group("min")),
        "receive_rate_max_mbps": float(m_rate.group("max")),
        "receive_rate_avg_mbps": float(m_rate.group("avg")),
    }

    m_ifdd = ifdd_re.search(text)
    if m_ifdd:
        result["ifdd_min_s"] = float(m_ifdd.group("min"))
        result["ifdd_max_s"] = float(m_ifdd.group("max"))
        result["ifdd_avg_s"] = float(m_ifdd.group("avg"))

    m_ifraw = ifraw_re.search(text)
    if m_ifraw:
        result["ifraw_min_s"] = float(m_ifraw.group("min"))
        result["ifraw_max_s"] = float(m_ifraw.group("max"))
        result["ifraw_avg_s"] = float(m_ifraw.group("avg"))

    m_total_if = total_if_re.search(text)
    if m_total_if:
        result["total_inter_frame_delay_s"] = float(m_total_if.group("v"))

    m_total_sq_if = total_sq_if_re.search(text)
    if m_total_sq_if:
        result["total_squared_inter_frame_delay_s2"] = float(m_total_sq_if.group("v"))

    m_var_if = var_if_re.search(text)
    if m_var_if:
        result["inter_frame_delay_variance_s2"] = float(m_var_if.group("v"))

    for key, rex in [
        ("datagrams_total", dgrams_re),
        ("bytes_total", bytes_re),
        ("frames_completed_total", fcomp_re),
        ("frames_rendered_total", frend_re),
        ("freeze_count_total", fcnt_re),
        ("freeze_duration_total_s", fdur_re),
    ]:
        m = rex.search(text)
        if m:
            result[key] = float(m.group("v"))

    return result


def parse_all_logs(directory: str | Path) -> dict[str, list[Any]] | None:
    log_pattern = str(Path(directory) / "*_rx.log")
    log_files = sorted(glob.glob(log_pattern))

    if not log_files:
        print(f"No *_rx.log files found in: {directory}")
        return None

    print(f"Found {len(log_files)} receiver logs")
    data = _empty_summary_data()
    skipped = 0

    for logfile in log_files:
        summary = parse_final_summary(logfile)
        if summary is None:
            skipped += 1
            continue

        data["run_label"].append(Path(logfile).stem)
        for k in _SUMMARY_KEYS:
            if k == "run_label":
                continue
            data[k].append(float(summary.get(k, np.nan)))

    n_runs = len(data["run_label"])
    print(f"Runs parsed: {n_runs} (skipped {skipped})")
    return data if n_runs > 0 else None


def _annotate_mean(ax, values: list[float], unit: str = "", fmt: str = ".3f") -> None:
    vals = [v for v in values if not np.isnan(v)]
    if not vals:
        return
    m = float(np.mean(vals))
    ax.axvline(m, color="red", linestyle="--", linewidth=2, label=f"Mean: {m:{fmt}} {unit}".strip())
    ax.legend(fontsize=10)


def plot_histograms(data: dict[str, list[Any]] | None, outdir: Path, show_plots: bool = True) -> None:
    if not data or not data.get("run_label"):
        print("No receiver summary data found; nothing to plot")
        return

    n_runs = len(data["run_label"])

    def _title(ax, t: str) -> None:
        ax.set_title(f"{t}\n({n_runs} runs)", fontsize=14)

    # 1) Avg receive rate
    vals = [float(v) for v in data["receive_rate_avg_mbps"] if not np.isnan(v)]
    fig1, ax1 = plt.subplots(figsize=(12, 6))
    ax1.hist(vals, bins=_adaptive_bins(vals), color="green", alpha=0.75, edgecolor="black")
    ax1.set_xlabel("Average Receive Rate (Mbps)")
    ax1.set_ylabel("Frequency (runs)")
    ax1.grid(True, axis="y", alpha=0.3)
    _title(ax1, "Receiver Average Receive Rate Distribution")
    _annotate_mean(ax1, vals, "Mbps", ".2f")
    fig1.tight_layout()
    _save_fig(fig1, outdir, "receiver_hist_avg_receive_rate_mbps.png")

    # 2) Min/Max receive rate overlay
    vals_min = [float(v) for v in data["receive_rate_min_mbps"] if not np.isnan(v)]
    vals_max = [float(v) for v in data["receive_rate_max_mbps"] if not np.isnan(v)]
    fig2, ax2 = plt.subplots(figsize=(12, 6))
    bins2 = _adaptive_bins(vals_min + vals_max)
    ax2.hist(vals_min, bins=bins2, alpha=0.5, color="cyan", edgecolor="black", label="Min")
    ax2.hist(vals_max, bins=bins2, alpha=0.5, color="orange", edgecolor="black", label="Max")
    ax2.set_xlabel("Receive Rate (Mbps)")
    ax2.set_ylabel("Frequency (runs)")
    ax2.grid(True, axis="y", alpha=0.3)
    ax2.legend(fontsize=10)
    _title(ax2, "Receiver Min/Max Receive Rate Distribution")
    fig2.tight_layout()
    _save_fig(fig2, outdir, "receiver_hist_min_max_receive_rate_mbps.png")

    # 3) Avg IF delay diff (ms)
    ifdd_ms = [1000.0 * float(v) for v in data["ifdd_avg_s"] if not np.isnan(v)]
    fig3, ax3 = plt.subplots(figsize=(12, 6))
    ax3.hist(ifdd_ms, bins=_adaptive_bins(ifdd_ms), color="purple", alpha=0.75, edgecolor="black")
    ax3.set_xlabel("Average IF Delay Difference (ms)")
    ax3.set_ylabel("Frequency (runs)")
    ax3.grid(True, axis="y", alpha=0.3)
    _title(ax3, "Receiver Average IF Delay Difference Distribution")
    _annotate_mean(ax3, ifdd_ms, "ms", ".3f")
    fig3.tight_layout()
    _save_fig(fig3, outdir, "receiver_hist_avg_ifdd_ms.png")

    # 4) Avg IF raw inter-frame arrival delay (ms)
    ifraw_ms = [1000.0 * float(v) for v in data["ifraw_avg_s"] if not np.isnan(v)]
    fig4, ax4 = plt.subplots(figsize=(12, 6))
    ax4.hist(ifraw_ms, bins=_adaptive_bins(ifraw_ms), color="slateblue", alpha=0.75, edgecolor="black")
    ax4.set_xlabel("Average IF Raw Arrival Delay (ms)")
    ax4.set_ylabel("Frequency (runs)")
    ax4.grid(True, axis="y", alpha=0.3)
    _title(ax4, "Receiver Average IF Raw Arrival Delay Distribution")
    _annotate_mean(ax4, ifraw_ms, "ms", ".3f")
    fig4.tight_layout()
    _save_fig(fig4, outdir, "receiver_hist_avg_ifraw_ms.png")

    # 5) Total inter-frame delay (s)
    total_if = [float(v) for v in data["total_inter_frame_delay_s"] if not np.isnan(v)]
    fig5, ax5 = plt.subplots(figsize=(12, 6))
    ax5.hist(total_if, bins=_adaptive_bins(total_if), color="mediumpurple", alpha=0.75, edgecolor="black")
    ax5.set_xlabel("Total Inter-frame Delay (s)")
    ax5.set_ylabel("Frequency (runs)")
    ax5.grid(True, axis="y", alpha=0.3)
    _title(ax5, "Receiver Total Inter-frame Delay Distribution")
    _annotate_mean(ax5, total_if, "s", ".3f")
    fig5.tight_layout()
    _save_fig(fig5, outdir, "receiver_hist_total_interframe_delay_s.png")

    # 6) Inter-frame delay variance (ms^2)
    if_var_ms2 = [1e6 * float(v) for v in data["inter_frame_delay_variance_s2"] if not np.isnan(v)]
    fig6, ax6 = plt.subplots(figsize=(12, 6))
    ax6.hist(if_var_ms2, bins=_adaptive_bins(if_var_ms2), color="indigo", alpha=0.75, edgecolor="black")
    ax6.set_xlabel("Inter-frame Delay Variance (ms^2)")
    ax6.set_ylabel("Frequency (runs)")
    ax6.grid(True, axis="y", alpha=0.3)
    _title(ax6, "Receiver Inter-frame Delay Variance Distribution")
    _annotate_mean(ax6, if_var_ms2, "ms^2", ".3f")
    fig6.tight_layout()
    _save_fig(fig6, outdir, "receiver_hist_interframe_delay_variance_ms2.png")

    # 7) Freeze duration total
    frz_dur = [float(v) for v in data["freeze_duration_total_s"] if not np.isnan(v)]
    fig7, ax7 = plt.subplots(figsize=(12, 6))
    ax7.hist(frz_dur, bins=_adaptive_bins(frz_dur), color="red", alpha=0.75, edgecolor="black")
    ax7.set_xlabel("Total Freeze Duration (s)")
    ax7.set_ylabel("Frequency (runs)")
    ax7.grid(True, axis="y", alpha=0.3)
    _title(ax7, "Receiver Total Freeze Duration Distribution")
    _annotate_mean(ax7, frz_dur, "s", ".3f")
    fig7.tight_layout()
    _save_fig(fig7, outdir, "receiver_hist_total_freeze_duration_s.png")

    # 8) Freeze count total
    frz_cnt = [float(v) for v in data["freeze_count_total"] if not np.isnan(v)]
    fig8, ax8 = plt.subplots(figsize=(12, 6))
    ax8.hist(frz_cnt, bins=_adaptive_bins(frz_cnt), color="steelblue", alpha=0.75, edgecolor="black")
    ax8.set_xlabel("Total Freeze Count")
    ax8.set_ylabel("Frequency (runs)")
    ax8.grid(True, axis="y", alpha=0.3)
    _title(ax8, "Receiver Total Freeze Count Distribution")
    _annotate_mean(ax8, frz_cnt, "", ".2f")
    fig8.tight_layout()
    _save_fig(fig8, outdir, "receiver_hist_total_freeze_count.png")

    # 9) Bytes total (MB)
    bytes_mb = [float(v) / 1e6 for v in data["bytes_total"] if not np.isnan(v)]
    fig9, ax9 = plt.subplots(figsize=(12, 6))
    ax9.hist(bytes_mb, bins=_adaptive_bins(bytes_mb), color="teal", alpha=0.75, edgecolor="black")
    ax9.set_xlabel("Total Bytes Received (MB)")
    ax9.set_ylabel("Frequency (runs)")
    ax9.grid(True, axis="y", alpha=0.3)
    _title(ax9, "Receiver Total Bytes Distribution")
    _annotate_mean(ax9, bytes_mb, "MB", ".2f")
    fig9.tight_layout()
    _save_fig(fig9, outdir, "receiver_hist_total_bytes_mb.png")

    if show_plots:
        plt.show()
    else:
        plt.close("all")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot receiver final-summary histograms across batch runs"
    )
    parser.add_argument("test_results_directory", help="Directory containing *_rx.log files")
    parser.add_argument("output_directory", help="Directory where PNG plots are saved")
    parser.add_argument("--no-show", action="store_true", help="Do not display plots (headless)")
    args = parser.parse_args()

    outdir = Path(args.output_directory)
    data = parse_all_logs(args.test_results_directory)
    plot_histograms(data, outdir=outdir, show_plots=not args.no_show)
if __name__ == "__main__":
    main()
