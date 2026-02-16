#!/usr/bin/env python3
"""plot_scream_histogram.py

Unified histogram plotter for SCReAM congestion control debug logs.

This replaces:
  - plot_scream_histogram_fake_traffic.py
  - plot_scream_histogram_video_traffic.py

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

Reads all *_tx.log files from the directory and creates histogram plots.
"""

from __future__ import annotations

import argparse
import glob
import re
import sys
from pathlib import Path

import matplotlib.pyplot as plt


def _save_fig(fig, outdir: Path, filename: str) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    fig.savefig(outdir / filename, dpi=200, bbox_inches="tight")


def parse_scream_log(logfile: str | Path) -> dict[str, list[float] | list[int]]:
    """Parse SCReAM CWND debug logs, frame sizes, and statistics."""

    cwnd_pattern = re.compile(
        r"\[SCREAM-CWND\] cwnd=(?P<cwnd>\d+)\s+"
        r"sRtt=(?P<srtt>[\d.eE+-]+)\s+"
        r"queueDelay=(?P<queuedelay>[\d.eE+-]+)\s+"
        r"bytesInFlight=(?P<bytesinflight>\d+)\s+"
        r"rateLeft=(?P<rateleft>[\d.eE+-]+)\s+"
        r"stream\[0\]\.rateShare=(?P<rateshare>[\d.eE+-]+)\s+"
        r"targetBitrateH=(?P<target>[\d.eE+-]+)"
    )

    frame_size_pattern = re.compile(r"Frame size:\s+(?P<size>\d+)")

    stats_pattern = re.compile(
        r"summary\s+[\d.]+\s+Transmit rate\s*=\s*(?P<rate>[\d.]+)kbps,\s*"
        r"PLR\s*=\s*(?P<plr>[\d.]+)%"
    )

    data: dict[str, list] = {
        "cwnd": [],
        "srtt": [],
        "queueDelay": [],
        "bytesInFlight": [],
        "rateLeft": [],
        "rateShare": [],
        "targetBitrateH": [],
        "frameSize": [],
        "transmitRate": [],  # Mbps
        "packetLossRate": [],  # %
    }

    with open(logfile, "r") as f:
        for line in f:
            match = cwnd_pattern.search(line)
            if match:
                try:
                    data["cwnd"].append(int(match.group("cwnd")))
                    data["srtt"].append(float(match.group("srtt")))
                    data["queueDelay"].append(float(match.group("queuedelay")))
                    data["bytesInFlight"].append(int(match.group("bytesinflight")))
                    data["rateLeft"].append(float(match.group("rateleft")))
                    data["rateShare"].append(float(match.group("rateshare")))
                    data["targetBitrateH"].append(float(match.group("target")))
                except ValueError as exc:
                    print(f"Warning: Skipping corrupted line in {logfile}: {exc}")
                    continue

            frame_match = frame_size_pattern.search(line)
            if frame_match:
                try:
                    data["frameSize"].append(int(frame_match.group("size")))
                except ValueError:
                    pass

            stats_match = stats_pattern.search(line)
            if stats_match:
                try:
                    rate_kbps = float(stats_match.group("rate"))
                    data["transmitRate"].append(rate_kbps / 1000.0)
                    data["packetLossRate"].append(float(stats_match.group("plr")))
                except ValueError as exc:
                    print(f"Warning: Skipping corrupted statistics line in {logfile}: {exc}")
                    continue

    return data


def parse_all_logs(directory: str | Path) -> dict[str, list] | None:
    """Parse all *_tx.log files in the directory and aggregate into one dataset."""

    log_pattern = str(Path(directory) / "*_tx.log")
    log_files = glob.glob(log_pattern)

    if not log_files:
        print(f"No *_tx.log files found in {directory}")
        return None

    print(f"Found {len(log_files)} log files:")
    for log in sorted(log_files):
        print(f"  - {Path(log).name}")

    all_data: dict[str, list] = {
        "cwnd": [],
        "srtt": [],
        "queueDelay": [],
        "bytesInFlight": [],
        "rateLeft": [],
        "rateShare": [],
        "targetBitrateH": [],
        "frameSize": [],
        "transmitRate": [],
        "packetLossRate": [],
    }

    for logfile in sorted(log_files):
        data = parse_scream_log(logfile)
        for key in all_data.keys():
            all_data[key].extend(data[key])

    print(f"\nTotal samples collected: {len(all_data['cwnd'])}")
    return all_data


def _title_suffix(video_file: str | None) -> str:
    return "(BW Tool With Video Encoder)" if video_file else "(BW Tool With Fake Traffic)"


def plot_histograms(
    data: dict[str, list] | None,
    *,
    outdir: Path | None = None,
    show_plots: bool = True,
    test_config: str = "",
    video_file: str | None = None,
) -> None:
    if not data or not data.get("cwnd"):
        print("No data to plot.")
        return

    suffix = _title_suffix(video_file)

    def _set_title(ax, base: str) -> None:
        title = f"{base} {suffix}"
        if test_config:
            title += f"\n{test_config}"
        ax.set_title(title, fontsize=14, fontweight="bold")

    # Histogram 1: CWND
    fig1, ax1 = plt.subplots(figsize=(12, 6))
    ax1.hist(data["cwnd"], bins=50, color="blue", alpha=0.7, edgecolor="black")
    ax1.set_xlabel("CWND (bytes)", fontsize=12)
    ax1.set_ylabel("Frequency", fontsize=12)
    _set_title(ax1, "SCReAM Congestion Window Distribution")
    ax1.grid(True, alpha=0.3, axis="y")
    mean_cwnd = sum(data["cwnd"]) / len(data["cwnd"])
    ax1.axvline(mean_cwnd, color="red", linestyle="--", linewidth=2, label=f"Mean: {mean_cwnd:.0f}")
    ax1.legend(fontsize=10)
    fig1.tight_layout()
    if outdir:
        _save_fig(fig1, outdir, "hist_cwnd.png")

    # Histogram 2: sRTT
    fig2, ax2 = plt.subplots(figsize=(12, 6))
    srtt_ms = [s * 1000 for s in data["srtt"]]
    ax2.hist(srtt_ms, bins=50, color="green", alpha=0.7, edgecolor="black")
    ax2.set_xlabel("sRTT (ms)", fontsize=12)
    ax2.set_ylabel("Frequency", fontsize=12)
    _set_title(ax2, "SCReAM Smoothed Round-Trip Time Distribution")
    ax2.grid(True, alpha=0.3, axis="y")
    mean_srtt = sum(srtt_ms) / len(srtt_ms)
    ax2.axvline(mean_srtt, color="red", linestyle="--", linewidth=2, label=f"Mean: {mean_srtt:.2f} ms")
    ax2.legend(fontsize=10)
    fig2.tight_layout()
    if outdir:
        _save_fig(fig2, outdir, "hist_srtt_ms.png")

    # Histogram 3: Queue Delay
    fig3, ax3 = plt.subplots(figsize=(12, 6))
    queue_delay_ms = [q * 1000 for q in data["queueDelay"]]
    ax3.hist(queue_delay_ms, bins=50, color="purple", alpha=0.7, edgecolor="black")
    ax3.set_xlabel("Queue Delay (ms)", fontsize=12)
    ax3.set_ylabel("Frequency", fontsize=12)
    _set_title(ax3, "SCReAM Queue Delay Distribution")
    ax3.grid(True, alpha=0.3, axis="y")
    mean_qd = sum(queue_delay_ms) / len(queue_delay_ms)
    ax3.axvline(mean_qd, color="red", linestyle="--", linewidth=2, label=f"Mean: {mean_qd:.2f} ms")
    ax3.legend(fontsize=10)
    fig3.tight_layout()
    if outdir:
        _save_fig(fig3, outdir, "hist_queue_delay_ms.png")

    # Histogram 4: Bytes in Flight
    fig4, ax4 = plt.subplots(figsize=(12, 6))
    bytes_in_flight_kb = [b / 1024 for b in data["bytesInFlight"]]
    ax4.hist(bytes_in_flight_kb, bins=50, color="cyan", alpha=0.7, edgecolor="black")
    ax4.set_xlabel("Bytes in Flight (KB)", fontsize=12)
    ax4.set_ylabel("Frequency", fontsize=12)
    _set_title(ax4, "SCReAM Bytes in Flight Distribution")
    ax4.grid(True, alpha=0.3, axis="y")
    mean_bif = sum(bytes_in_flight_kb) / len(bytes_in_flight_kb)
    ax4.axvline(mean_bif, color="red", linestyle="--", linewidth=2, label=f"Mean: {mean_bif:.2f} KB")
    ax4.legend(fontsize=10)
    fig4.tight_layout()
    if outdir:
        _save_fig(fig4, outdir, "hist_bytes_in_flight_kb.png")

    # Histogram 5: Rate parameters
    fig5, ax5 = plt.subplots(figsize=(12, 6))
    rate_left_mbps = [r / 1e6 for r in data["rateLeft"]]
    rate_share_mbps = [r / 1e6 for r in data["rateShare"]]
    target_bitrate_h_mbps = [t / 1e6 for t in data["targetBitrateH"]]

    ax5.hist(rate_left_mbps, bins=50, alpha=0.5, label="rateLeft", color="red", edgecolor="black")
    ax5.hist(rate_share_mbps, bins=50, alpha=0.5, label="rateShare", color="blue", edgecolor="black")
    ax5.hist(target_bitrate_h_mbps, bins=50, alpha=0.5, label="targetBitrateH", color="magenta", edgecolor="black")

    ax5.set_xlabel("Bitrate (Mbps)", fontsize=12)
    ax5.set_ylabel("Frequency", fontsize=12)
    _set_title(ax5, "SCReAM Rate Allocation Distribution")
    ax5.grid(True, alpha=0.3, axis="y")
    ax5.legend(fontsize=10, loc="best")
    fig5.tight_layout()
    if outdir:
        _save_fig(fig5, outdir, "hist_rate_params_mbps.png")

    # Histogram 6: Frame sizes
    if data.get("frameSize"):
        fig6, ax6 = plt.subplots(figsize=(12, 6))
        frame_size_kb = [f / 1024 for f in data["frameSize"]]
        ax6.hist(frame_size_kb, bins=50, color="orange", alpha=0.7, edgecolor="black")
        ax6.set_xlabel("Frame Size (KB)", fontsize=12)
        ax6.set_ylabel("Frequency", fontsize=12)
        _set_title(ax6, "Encoded Frame Size Distribution")
        ax6.grid(True, alpha=0.3, axis="y")
        mean_frame_kb = sum(frame_size_kb) / len(frame_size_kb)
        ax6.axvline(mean_frame_kb, color="red", linestyle="--", linewidth=2, label=f"Mean: {mean_frame_kb:.2f} KB")
        ax6.legend(fontsize=10)
        fig6.tight_layout()
        if outdir:
            _save_fig(fig6, outdir, "hist_frame_size_kb.png")

    # Histogram 7: Transmit Rate
    if data.get("transmitRate"):
        fig7, ax7 = plt.subplots(figsize=(12, 6))
        ax7.hist(data["transmitRate"], bins=50, color="purple", alpha=0.7, edgecolor="black")
        ax7.set_xlabel("Transmit Rate (Mbps)", fontsize=12)
        ax7.set_ylabel("Frequency", fontsize=12)
        _set_title(ax7, "Transmit Rate Distribution")
        ax7.grid(True, alpha=0.3, axis="y")
        mean_tx = sum(data["transmitRate"]) / len(data["transmitRate"])
        ax7.axvline(mean_tx, color="red", linestyle="--", linewidth=2, label=f"Mean: {mean_tx:.2f} Mbps")
        ax7.legend(fontsize=10)
        fig7.tight_layout()
        if outdir:
            _save_fig(fig7, outdir, "hist_transmit_rate_mbps.png")

    # Histogram 8: Packet Loss Rate
    if data.get("packetLossRate"):
        fig8, ax8 = plt.subplots(figsize=(12, 6))
        ax8.hist(data["packetLossRate"], bins=50, color="red", alpha=0.7, edgecolor="black")
        ax8.set_xlabel("Packet Loss Rate (%)", fontsize=12)
        ax8.set_ylabel("Frequency", fontsize=12)
        _set_title(ax8, "Packet Loss Rate Distribution")
        ax8.grid(True, alpha=0.3, axis="y")
        mean_plr = sum(data["packetLossRate"]) / len(data["packetLossRate"])
        ax8.axvline(mean_plr, color="darkred", linestyle="--", linewidth=2, label=f"Mean: {mean_plr:.2f}%")
        ax8.legend(fontsize=10)
        fig8.tight_layout()
        if outdir:
            _save_fig(fig8, outdir, "hist_packet_loss_rate_pct.png")

    if show_plots:
        plt.show()

    # Summary
    print("\n=== Summary Statistics ===")
    print(f"Total samples: {len(data['cwnd'])}")
    print("\nCWND (bytes):")
    print(
        f"  min={min(data['cwnd'])}, max={max(data['cwnd'])}, "
        f"mean={sum(data['cwnd'])/len(data['cwnd']):.1f}, "
        f"median={sorted(data['cwnd'])[len(data['cwnd'])//2]}"
    )

    print("\nsRTT (ms):")
    print(
        f"  min={min(srtt_ms):.2f}, max={max(srtt_ms):.2f}, "
        f"mean={mean_srtt:.2f}, "
        f"median={sorted(srtt_ms)[len(srtt_ms)//2]:.2f}"
    )

    print("\nQueue Delay (ms):")
    print(
        f"  min={min(queue_delay_ms):.2f}, max={max(queue_delay_ms):.2f}, "
        f"mean={mean_qd:.2f}, "
        f"median={sorted(queue_delay_ms)[len(queue_delay_ms)//2]:.2f}"
    )

    print("\nBytes in Flight (KB):")
    print(
        f"  min={min(bytes_in_flight_kb):.2f}, max={max(bytes_in_flight_kb):.2f}, "
        f"mean={mean_bif:.2f}, "
        f"median={sorted(bytes_in_flight_kb)[len(bytes_in_flight_kb)//2]:.2f}"
    )

    print("\nrateLeft (Mbps):")
    print(f"  min={min(rate_left_mbps):.2f}, max={max(rate_left_mbps):.2f}, mean={sum(rate_left_mbps)/len(rate_left_mbps):.2f}")

    print("\nrateShare (Mbps):")
    print(
        f"  min={min(rate_share_mbps):.2f}, max={max(rate_share_mbps):.2f}, mean={sum(rate_share_mbps)/len(rate_share_mbps):.2f}"
    )

    print("\ntargetBitrateH (Mbps):")
    print(
        f"  min={min(target_bitrate_h_mbps):.2f}, max={max(target_bitrate_h_mbps):.2f}, mean={sum(target_bitrate_h_mbps)/len(target_bitrate_h_mbps):.2f}"
    )

    if data.get("frameSize"):
        print(f"\nFrame sizes: {len(data['frameSize'])} frames")
        print(
            f"  min={min(data['frameSize'])} bytes, max={max(data['frameSize'])} bytes, "
            f"mean={sum(data['frameSize'])/len(data['frameSize']):.1f} bytes"
        )

    if data.get("transmitRate"):
        print(f"\nTransmit Rate: {len(data['transmitRate'])} samples")
        print(
            f"  min={min(data['transmitRate']):.2f} Mbps, max={max(data['transmitRate']):.2f} Mbps, "
            f"mean={sum(data['transmitRate'])/len(data['transmitRate']):.2f} Mbps"
        )

    if data.get("packetLossRate"):
        print(f"\nPacket Loss Rate: {len(data['packetLossRate'])} samples")
        print(
            f"  min={min(data['packetLossRate']):.2f}%, max={max(data['packetLossRate']):.2f}%, "
            f"mean={sum(data['packetLossRate'])/len(data['packetLossRate']):.2f}%"
        )


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
