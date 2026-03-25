import re
import glob
import math
from pathlib import Path
import matplotlib.pyplot as plt
import argparse
from collections import defaultdict

_METRIC_KEYS = [
    "elapsed_time",
    "datagrams_received",
    "bytes_received",
    "receive_rate_mbps",
    "frames_completed",
    "frames_rendered",
    "freeze_count",
    "freeze_duration",
    "inter_frame_delay",
    "inter_frame_delay_difference",
]

def _nan() -> float:
    return float("nan")

def parse_stats_file(filename):
    """Parse one *_rx.log and extract per-interval metrics (aligned)."""
    stats = defaultdict(list)

    patterns = {
        "elapsed_time": r"RECEIVER STATS \(last ([\d.]+)s\)",
        "datagrams_received": r"Datagrams received:\s*([\d.]+)",
        "bytes_received": r"Bytes received:\s*([\d.]+)",
        "receive_rate_mbps": r"Receive rate:\s*([\d.]+)",
        "frames_completed": r"Frames completed:\s*([\d.]+)",
        "frames_rendered": r"Total frames rendered:\s*([\d.]+)",
        "freeze_count": r"Freeze count:\s*([\d.]+)",
        "freeze_duration": r"total freeze duration:\s*([\d.]+)",
        "inter_frame_delay": r"Total Inter-Frame Delay:\s*([\d.]+)",
        "inter_frame_delay_difference": r"Inter-Frame Delay difference:\s*([\d.]+)",
    }

    content = Path(filename).read_text(errors="replace")
    blocks = content.split("=== RECEIVER STATS")
    blocks = blocks[1:]  # first split is preamble

    for block in blocks:
        # Ensure every metric gets exactly one entry per block
        for key in _METRIC_KEYS:
            stats[key].append(_nan())

        for key, pattern in patterns.items():
            m = re.search(pattern, block)
            if m:
                stats[key][-1] = float(m.group(1))

    # Per-run time axis (1..N)
    stats["time"] = list(range(1, len(blocks) + 1))
    return stats

def parse_stats_path(input_path: str):
    """If input_path is a file -> parse it.
       If directory -> parse all *_rx.log and concatenate into one timeline."""
    p = Path(input_path).expanduser().resolve()
    if p.is_file():
        s = parse_stats_file(str(p))
        s["run_breaks"] = []  # optional separators
        s["run_files"] = [str(p)]
        return s

    if not p.is_dir():
        raise FileNotFoundError(f"Not a file or directory: {p}")

    files = sorted(glob.glob(str(p / "*_rx.log")))
    if not files:
        raise FileNotFoundError(f"No *_rx.log files found in: {p}")

    combined = defaultdict(list)
    run_breaks = []
    run_files = []

    for f in files:
        s = parse_stats_file(f)
        n = len(s["time"])
        if n == 0:
            continue

        # Append metrics
        for key in _METRIC_KEYS:
            combined[key].extend(s.get(key, []))

        run_files.append(f)
        run_breaks.append(len(combined["datagrams_received"]))  # break AFTER this run

    # Continuous time axis across the concatenated batch
    total_n = len(combined["datagrams_received"])
    combined["time"] = list(range(1, total_n + 1))

    # Don’t draw a separator after the last run
    if run_breaks:
        run_breaks = run_breaks[:-1]

    combined["run_breaks"] = run_breaks
    combined["run_files"] = run_files
    return combined

def _draw_run_breaks(ax, stats):
    breaks = stats.get("run_breaks", [])
    for b in breaks:
        ax.axvline(b + 0.5, color="k", linewidth=1, alpha=0.15)

def plot_stats(stats, output_prefix="stats"):
    time = stats["time"]
    plt.style.use("seaborn-v0_8-darkgrid" if "seaborn-v0_8-darkgrid" in plt.style.available else "ggplot")

    # Plot 1: Datagrams received, Bytes received
    fig1, ax1 = plt.subplots(figsize=(10, 6))
    ax2 = ax1.twinx()

    line1, = ax1.plot(time, stats["datagrams_received"], "b-", label="Datagrams Received", linewidth=2)
    line2, = ax2.plot(time, stats["bytes_received"], "r-", label="Bytes Received", linewidth=2)

    _draw_run_breaks(ax1, stats)

    ax1.set_xlabel("Time (interval index)", fontsize=12)
    ax1.set_ylabel("Datagrams Received", color="b", fontsize=12)
    ax2.set_ylabel("Bytes Received", color="r", fontsize=12)
    ax1.tick_params(axis="y", labelcolor="b")
    ax2.tick_params(axis="y", labelcolor="r")

    ax1.legend([line1, line2], [line1.get_label(), line2.get_label()], loc="upper left")
    plt.title("Datagrams and Bytes Received Over Time", fontsize=14)
    plt.tight_layout()
    plt.savefig(f"{output_prefix}_datagrams_bytes.png", dpi=150)
    plt.close()

    # Plot 2: Receive Rate (Mbps)
    fig2, ax = plt.subplots(figsize=(10, 6))
    ax.plot(time, stats["receive_rate_mbps"], "g-", linewidth=2, marker="o", markersize=3)
    _draw_run_breaks(ax, stats)
    ax.set_xlabel("Time (interval index)", fontsize=12)
    ax.set_ylabel("Receive Rate (Mbps)", fontsize=12)
    ax.set_title("Receive Rate Over Time", fontsize=14)
    plt.tight_layout()
    plt.savefig(f"{output_prefix}_receive_rate.png", dpi=150)
    plt.close()

    # Plot 3: Inter-frame delay difference
    fig3, ax = plt.subplots(figsize=(10, 6))
    ax.plot(time, stats["inter_frame_delay_difference"], "m-", linewidth=2, marker="o", markersize=3)
    _draw_run_breaks(ax, stats)
    ax.set_xlabel("Time (interval index)", fontsize=12)
    ax.set_ylabel("Inter-frame delay difference (s)", fontsize=12)
    ax.set_title("Inter-frame delay difference", fontsize=14)
    plt.tight_layout()
    plt.savefig(f"{output_prefix}_interframe_delay.png", dpi=150)
    plt.close()

    # Plot 4: Freeze Count, Total Freeze Duration
    fig4, ax1 = plt.subplots(figsize=(10, 6))
    ax2 = ax1.twinx()

    line1, = ax1.plot(time, stats["freeze_count"], "b-", label="Freeze Count", linewidth=2, marker="o", markersize=3)
    line2, = ax2.plot(time, stats["freeze_duration"], "r-", label="Total Freeze Duration (s)", linewidth=2, marker=".", markersize=4)

    _draw_run_breaks(ax1, stats)

    ax1.set_xlabel("Time (interval index)", fontsize=12)
    ax1.set_ylabel("Freeze Count", color="b", fontsize=12)
    ax2.set_ylabel("Total Freeze Duration (s)", color="r", fontsize=12)
    ax1.tick_params(axis="y", labelcolor="b")
    ax2.tick_params(axis="y", labelcolor="r")

    ax1.legend([line1, line2], [line1.get_label(), line2.get_label()], loc="upper left")
    plt.title("Freeze Statistics Over Time", fontsize=14)
    plt.tight_layout()
    plt.savefig(f"{output_prefix}_freezes.png", dpi=150)
    plt.close()

    # Plot 5: Frames completed vs frames rendered
    fig5, ax1 = plt.subplots(figsize=(10, 6))
    ax2 = ax1.twinx()

    line1, = ax1.plot(time, stats["frames_completed"], "b-", label="Frames Completed", linewidth=2, marker="o", markersize=3)
    line2, = ax2.plot(time, stats["frames_rendered"], "g-", label="Frames Rendered", linewidth=2, marker=".", markersize=4)

    _draw_run_breaks(ax1, stats)

    ax1.set_xlabel("Time (interval index)", fontsize=12)
    ax1.set_ylabel("Frames Completed", color="b", fontsize=12)
    ax2.set_ylabel("Frames Rendered", color="g", fontsize=12)

    ax1.legend([line1, line2], [line1.get_label(), line2.get_label()], loc="upper left")
    plt.title("Frames Completed vs Frames Rendered", fontsize=14)
    plt.tight_layout()
    plt.savefig(f"{output_prefix}_frame_stats.png", dpi=150)
    plt.close()

    print(f"Time-series plots saved with prefix '{output_prefix}_*.png'")

def plot_histograms(stats, output_prefix="stats"):
    plt.style.use("seaborn-v0_8-darkgrid" if "seaborn-v0_8-darkgrid" in plt.style.available else "ggplot")

    def _finite(vals):
        return [v for v in vals if v is not None and not (isinstance(v, float) and math.isnan(v))]

    def plot_single_hist(data, title, xlabel, color, filename):
        data = _finite(data)
        if not data:
            return
        mean_val = sum(data) / len(data)
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.hist(data, bins=30, color=color, alpha=0.7, edgecolor="black", linewidth=0.5)
        ax.axvline(mean_val, color="k", linestyle="dashed", linewidth=1.5, label=f"Mean: {mean_val:.2f}")
        ax.set_title(title, fontsize=14)
        ax.set_xlabel(xlabel, fontsize=12)
        ax.set_ylabel("Frequency", fontsize=12)
        ax.legend()
        plt.tight_layout()
        plt.savefig(filename, dpi=150)
        plt.close()

    plot_single_hist(stats["receive_rate_mbps"], "Distribution of Receive Rate", "Receive Rate (Mbps)", "green",
                     f"{output_prefix}_hist_receive_rate.png")
    plot_single_hist(stats["freeze_duration"], "Distribution of Freeze Duration per Interval", "Freeze Duration (s)", "red",
                     f"{output_prefix}_hist_freeze_duration.png")
    plot_single_hist(stats["inter_frame_delay_difference"], "Distribution of Inter-Frame Delay difference", "difference (s)", "purple",
                     f"{output_prefix}_hist_difference.png")

    print(f"Histogram plots saved with prefix '{output_prefix}_hist_*.png'")

def plot_all_in_one(stats, output_filename="stats_combined.png"):
    time = stats["time"]
    fig, axes = plt.subplots(3, 2, figsize=(14, 12))
    fig.suptitle("Receiver Statistics Over Time (Batch)", fontsize=16, fontweight="bold")

    ax1 = axes[0, 0]
    ax1_twin = ax1.twinx()
    ax1.plot(time, stats["datagrams_received"], "b-", linewidth=2)
    ax1_twin.plot(time, stats["bytes_received"], "r-", linewidth=2)
    _draw_run_breaks(ax1, stats)
    ax1.set_title("Datagrams & Bytes Received")

    ax2 = axes[0, 1]
    ax2.plot(time, stats["receive_rate_mbps"], "g-", linewidth=2)
    _draw_run_breaks(ax2, stats)
    ax2.set_title("Receive Rate (Mbps)")

    ax3 = axes[1, 0]
    ax3.plot(time, stats["inter_frame_delay_difference"], "m-", linewidth=2)
    _draw_run_breaks(ax3, stats)
    ax3.set_title("Inter-frame Delay Difference")

    ax4 = axes[1, 1]
    ax4_twin = ax4.twinx()
    ax4.plot(time, stats["freeze_count"], "b-", linewidth=2)
    ax4_twin.plot(time, stats["freeze_duration"], "r-", linewidth=2)
    _draw_run_breaks(ax4, stats)
    ax4.set_title("Freezes")

    ax5 = axes[2, 0]
    ax5_twin = ax5.twinx()
    ax5.plot(time, stats["frames_completed"], "b-", linewidth=2)
    ax5_twin.plot(time, stats["frames_rendered"], "g-", linewidth=2)
    _draw_run_breaks(ax5, stats)
    ax5.set_title("Frame Stats")

    axes[2, 1].axis("off")

    plt.tight_layout()
    plt.savefig(output_filename, dpi=150)
    plt.close()
    print(f"Combined plot saved as '{output_filename}'")

def main():
    parser = argparse.ArgumentParser(description="Parse and plot receiver statistics.")
    parser.add_argument("input_path", help="Input *_rx.log file OR directory containing *_rx.log files")
    parser.add_argument("-o", "--output", default="stats", help="Output prefix for plot files")
    parser.add_argument("-c", "--combined", action="store_true", help="Also generate combined plot")
    args = parser.parse_args()

    print(f"Parsing: {args.input_path}")
    stats = parse_stats_path(args.input_path)
    print(f"Found {len(stats['time'])} data points across {len(stats.get('run_files', []))} run(s)")

    plot_stats(stats, args.output)
    plot_histograms(stats, args.output)
    if args.combined:
        plot_all_in_one(stats, f"{args.output}_combined.png")

if __name__ == "__main__":
    main()