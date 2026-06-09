#!/usr/bin/env python3
from __future__ import annotations

# Example usage:
# python3 tests/anrw26_seaborn_plots.py \
#   tests/logs/classic_fake_verizon_loss-0_rtt-20ms_20260410_1601 \
#   tests/logs/l4s_fake_verizon_loss-0_rtt-20ms_20260409_2131 \
#   tests/graphs

import argparse
import glob
import math
import re
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from matplotlib.ticker import FuncFormatter

__all__ = [
    "configure_plot_style",
    "percentile",
    "parse_sender_summary",
    "load_sender_qdelay_p95",
    "parse_tx_avg_rate_kbps",
    "parse_rx_avg_rate_kbps",
    "load_avg_rates_kbps",
    "parse_tx_avg_loss_pct",
    "load_avg_loss_pct",
    "parse_rx_total_freeze_duration_s",
    "load_freeze_duration_s",
    "parse_rx_freeze_count_total",
    "load_freeze_count_total",
    "parse_rx_ifraw_periodic_samples",
    "load_ifraw_run_medians",
    "make_qdelay_p95_violin",
    "make_rate_boxplot_seaborn",
    "make_loss_boxplot_seaborn",
    "make_freeze_duration_cdf",
    "make_freeze_count_cdf",
    "make_ifraw_median_violin",
]


def configure_plot_style() -> None:
    sns.set_theme(style="whitegrid", font_scale=2.8)


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    if p <= 0:
        return min(values)
    if p >= 100:
        return max(values)

    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    rank = (len(ordered) - 1) * (p / 100.0)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    frac = rank - lower
    return ordered[lower] * (1.0 - frac) + ordered[upper] * frac


def _fmt_stat(value: float | None, unit: str = "") -> str:
    if value is None:
        return "N/A"
    return f"{value:.3f}{unit}"


def print_metric_summary(
    experiment: str,
    metric_name: str,
    classic_values: list[float],
    l4s_values: list[float],
    unit: str = "",
    include_p95: bool = False,
    include_q1_q3: bool = False,
) -> None:
    classic_median = percentile(classic_values, 50.0)
    l4s_median = percentile(l4s_values, 50.0)

    line = (
        f"[experiment={experiment}] {metric_name}: "
        f"Classic median={_fmt_stat(classic_median, unit)} (n={len(classic_values)}), "
        f"L4S median={_fmt_stat(l4s_median, unit)} (n={len(l4s_values)})"
    )

    if include_p95:
        classic_p95 = percentile(classic_values, 95.0)
        l4s_p95 = percentile(l4s_values, 95.0)
        line += (
            f", Classic p95={_fmt_stat(classic_p95, unit)}, "
            f"L4S p95={_fmt_stat(l4s_p95, unit)}"
        )

    if include_q1_q3:
        classic_q1 = percentile(classic_values, 25.0)
        classic_q3 = percentile(classic_values, 75.0)
        l4s_q1 = percentile(l4s_values, 25.0)
        l4s_q3 = percentile(l4s_values, 75.0)
        line += (
            f", Classic Q1={_fmt_stat(classic_q1, unit)}, Classic Q3={_fmt_stat(classic_q3, unit)}, "
            f"L4S Q1={_fmt_stat(l4s_q1, unit)}, L4S Q3={_fmt_stat(l4s_q3, unit)}"
        )

    print(line)


def print_qdelay_p95_median_summary(
    experiment: str,
    classic_qdelay_p95_ms: list[float],
    l4s_qdelay_p95_ms: list[float],
) -> None:
    classic_median = percentile(classic_qdelay_p95_ms, 50.0)
    l4s_median = percentile(l4s_qdelay_p95_ms, 50.0)
    print(
        f"[experiment={experiment}] Median of per-run p95 queue delay: "
        f"Classic={_fmt_stat(classic_median, ' ms')} (n={len(classic_qdelay_p95_ms)}), "
        f"L4S={_fmt_stat(l4s_median, ' ms')} (n={len(l4s_qdelay_p95_ms)})"
    )


def print_packet_loss_median_summary(
    experiment: str,
    classic_loss_pct: list[float],
    l4s_loss_pct: list[float],
) -> None:
    classic_median = percentile(classic_loss_pct, 50.0)
    l4s_median = percentile(l4s_loss_pct, 50.0)
    print(
        f"[experiment={experiment}] Median sender packet loss: "
        f"Classic={_fmt_stat(classic_median, ' %')} (n={len(classic_loss_pct)}), "
        f"L4S={_fmt_stat(l4s_median, ' %')} (n={len(l4s_loss_pct)})"
    )


def parse_sender_summary(logfile: str | Path) -> dict[str, float] | None:
    text = Path(logfile).read_text(encoding="utf-8", errors="replace")

    summary_re = re.compile(
        r"^\s*summary\s+(?P<t>[\d.eE+-]+)\s+Transmit rate =\s+(?P<rate>[\d.eE+-]+)kbps,\s+"
        r"PLR =\s+(?P<plr_now>[\d.eE+-]+)%(?:\s*\(\s*(?P<plr_long>[\d.eE+-]+)%\s*\))?,\s+"
        r"CE =\s+(?P<ce_now>[\d.eE+-]+)%(?:\s*\(\s*(?P<ce_long>[\d.eE+-]+)%\s*\))?\[[^\]]*\],\s+"
        r"RTT =\s+(?P<rtt>[\d.eE+-]+)s,\s+Queue delay =\s+(?P<qd>[\d.eE+-]+)s",
        re.MULTILINE,
    )

    rows = list(summary_re.finditer(text))
    if not rows:
        print(
            f"ERROR: No sender summary rows found in {logfile}; cannot compute queue delay p95.",
            file=sys.stderr,
        )
        return None

    qd_samples_ms = [float(m.group("qd")) * 1000.0 for m in rows]
    qd_p95 = percentile(qd_samples_ms, 95.0)
    if qd_p95 is None:
        return None

    return {"queue_delay_p95_ms": qd_p95}


def load_sender_qdelay_p95(directory: str | Path) -> list[float]:
    p95_values: list[float] = []
    for logfile in sorted(glob.glob(str(Path(directory) / "*_tx.log"))):
        row = parse_sender_summary(logfile)
        if row is None:
            continue
        p95_values.append(row["queue_delay_p95_ms"])
    return p95_values


def parse_tx_avg_rate_kbps(logfile: str | Path) -> float | None:
    text = Path(logfile).read_text(encoding="utf-8", errors="replace")
    m = re.search(
        r"Bitrate\s+min/max/avg\s+\[kbps\]\s*:\s*[\d.eE+-]+\s*/\s*[\d.eE+-]+\s*/\s*(?P<v>[\d.eE+-]+)",
        text,
    )
    if not m:
        return None
    return float(m.group("v"))


def parse_rx_avg_rate_kbps(logfile: str | Path) -> float | None:
    text = Path(logfile).read_text(encoding="utf-8", errors="replace")
    m = re.search(
        r"Receive rate\s+min/max/avg\s+\[kbps\]\s*:\s*[\d.eE+-]+\s*/\s*[\d.eE+-]+\s*/\s*(?P<v>[\d.eE+-]+)",
        text,
    )
    if not m:
        return None
    return float(m.group("v"))


def load_avg_rates_kbps(directory: str | Path) -> tuple[list[float], list[float]]:
    tx_avg: list[float] = []
    rx_avg: list[float] = []

    for f in sorted(glob.glob(str(Path(directory) / "*_tx.log"))):
        v = parse_tx_avg_rate_kbps(f)
        if v is not None:
            tx_avg.append(v)

    for f in sorted(glob.glob(str(Path(directory) / "*_rx.log"))):
        v = parse_rx_avg_rate_kbps(f)
        if v is not None:
            rx_avg.append(v)

    return tx_avg, rx_avg


def parse_tx_avg_loss_pct(logfile: str | Path) -> float | None:
    text = Path(logfile).read_text(encoding="utf-8", errors="replace")
    m = re.search(r"Packet loss avg\s+\[%\]\s*:\s*(?P<v>[\d.eE+-]+)", text)
    if not m:
        return None
    return float(m.group("v"))


def load_avg_loss_pct(directory: str | Path) -> list[float]:
    losses: list[float] = []
    for f in sorted(glob.glob(str(Path(directory) / "*_tx.log"))):
        v = parse_tx_avg_loss_pct(f)
        if v is not None:
            losses.append(v)
    return losses


def parse_rx_total_freeze_duration_s(logfile: str | Path) -> float | None:
    text = Path(logfile).read_text(encoding="utf-8", errors="replace")
    m = re.search(r"Total freeze duration\s+\[s\]\s*:\s*(?P<v>[\d.eE+-]+)", text)
    if not m:
        return None
    return float(m.group("v"))


def load_freeze_duration_s(directory: str | Path) -> list[float]:
    durations: list[float] = []
    for f in sorted(glob.glob(str(Path(directory) / "*_rx.log"))):
        v = parse_rx_total_freeze_duration_s(f)
        if v is not None:
            durations.append(v)
    return durations


def parse_rx_freeze_count_total(logfile: str | Path) -> float | None:
    text = Path(logfile).read_text(encoding="utf-8", errors="replace")
    m = re.search(r"Freeze count total\s*:\s*(?P<v>[\d.eE+-]+)", text)
    if not m:
        return None
    return float(m.group("v"))


def load_freeze_count_total(directory: str | Path) -> list[float]:
    counts: list[float] = []
    for f in sorted(glob.glob(str(Path(directory) / "*_rx.log"))):
        v = parse_rx_freeze_count_total(f)
        if v is not None:
            counts.append(v)
    return counts


def parse_rx_ifraw_periodic_samples(logfile: str | Path) -> list[float]:
    text = Path(logfile).read_text(encoding="utf-8", errors="replace")
    pattern = re.compile(r"IF\(raw,avg\)\s*=\s*(?P<v>[\d.eE+-]+)\s*s")
    return [float(m.group("v")) for m in pattern.finditer(text)]


def load_ifraw_run_medians(directory: str | Path) -> tuple[list[float], int]:
    run_medians_s: list[float] = []
    ignored_negative_samples = 0

    for f in sorted(glob.glob(str(Path(directory) / "*_rx.log"))):
        samples = parse_rx_ifraw_periodic_samples(f)
        if not samples:
            continue

        non_negative_samples = [v for v in samples if v >= 0.0]
        ignored_negative_samples += len(samples) - len(non_negative_samples)
        if not non_negative_samples:
            continue

        med = percentile(non_negative_samples, 50.0)
        if med is not None:
            run_medians_s.append(med)

    return run_medians_s, ignored_negative_samples


def get_folder_prefix(directory: str | Path) -> str:
    name = Path(directory).name
    m = re.match(r"^(?P<prefix>.+)_\d{8}_\d{4}$", name)
    prefix = m.group("prefix") if m else name
    if prefix.startswith("classic_"):
        prefix = prefix[len("classic_") :]
    return prefix


def validate_input_dirs(classic_dir: str | Path, l4s_dir: str | Path) -> None:
    classic_name = Path(classic_dir).name.lower()
    l4s_name = Path(l4s_dir).name.lower()

    if not classic_name.startswith("classic_"):
        raise SystemExit(
            f"ERROR: classic_dir should start with 'classic_': {Path(classic_dir).name}"
        )
    if not l4s_name.startswith("l4s_"):
        raise SystemExit(
            f"ERROR: l4s_dir should start with 'l4s_': {Path(l4s_dir).name}"
        )


def make_qdelay_p95_violin(
    classic: list[float],
    l4s: list[float],
    outpath: Path,
    ylabel: str = "Queue Delay (ms)",
) -> None:
    fig, ax = plt.subplots(figsize=(8, 6.0))
    violin_width = 0.45
    violin_outline_width = 2.0
    inner_line_width = 2.0
    inner_box_width = 0.04
    inner_whisker_width = 1.8
    classic_pos = 0.5
    l4s_pos = 1.275
    muted_colors = sns.color_palette("deep", 10)
    classic_color_idx = 1
    l4s_color_idx = 0
    violin_palette = {
        "Classic": muted_colors[classic_color_idx],
        "L4S": muted_colors[l4s_color_idx],
    }

    # Use long-form tabular data so seaborn applies its documented categorical style.
    df = pd.DataFrame(
        {
            "position": [classic_pos] * len(classic) + [l4s_pos] * len(l4s),
            "queue_delay_p95_ms": classic + l4s,
            "variant": ["Classic"] * len(classic) + ["L4S"] * len(l4s),
        }
    )
    sns.violinplot(
        data=df,
        x="position",
        y="queue_delay_p95_ms",
        hue="variant",
        inner=None,
        dodge=False,
        native_scale=True,
        width=violin_width,
        linewidth=violin_outline_width,
        palette=violin_palette,
        cut=0,
        ax=ax,
    )

    # Draw an explicit inner box so quartile rectangle stays visible across seaborn versions.
    sns.boxplot(
        data=df,
        x="position",
        y="queue_delay_p95_ms",
        hue="variant",
        dodge=False,
        native_scale=True,
        width=inner_box_width,
        showfliers=False,
        boxprops={"facecolor": "black", "edgecolor": "black", "linewidth": inner_line_width},
        whiskerprops={"color": "black", "linewidth": inner_whisker_width},
        capprops={"color": "black", "linewidth": inner_whisker_width},
        medianprops={"color": "white", "linewidth": inner_line_width},
        saturation=1,
        legend=False,
        ax=ax,
    )

    for collection in ax.collections:
        collection.set_linewidth(violin_outline_width)

    legend = ax.get_legend()
    if legend is not None:
        legend.remove()

    ax.set_xticks([classic_pos, l4s_pos], ["Classic", "L4S"])
    ax.set_xlim(min(classic_pos, l4s_pos) - 0.35, max(classic_pos, l4s_pos) + 0.35)
    ax.set_xlabel("")
    ax.set_ylabel(ylabel, labelpad=10)
    ax.grid(True, axis="y", alpha=0.3)

    outpath.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(outpath, dpi=300, bbox_inches="tight")


def make_rate_boxplot_seaborn(
    classic_tx: list[float],
    classic_rx: list[float],
    l4s_tx: list[float],
    l4s_rx: list[float],
    outpath: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(8, 6.0))

    metric_palette = {"Tx": "#C07A2B", "Rx": "#2EBE6A"}

    rows = []
    rows.extend({"variant": "Classic", "metric": "Tx", "rate_kbps": v} for v in classic_tx)
    rows.extend({"variant": "Classic", "metric": "Rx", "rate_kbps": v} for v in classic_rx)
    rows.extend({"variant": "L4S", "metric": "Tx", "rate_kbps": v} for v in l4s_tx)
    rows.extend({"variant": "L4S", "metric": "Rx", "rate_kbps": v} for v in l4s_rx)
    df = pd.DataFrame(rows)

    sns.boxplot(
        data=df,
        x="variant",
        y="rate_kbps",
        hue="metric",
        order=["Classic", "L4S"],
        hue_order=["Tx", "Rx"],
        width=0.5,
        linewidth=2.0,
        showfliers=False,
        medianprops={"color": "black", "linewidth": 3.0},
        palette=metric_palette,
        ax=ax,
    )

    legend = ax.get_legend()
    if legend is not None:
        legend.set_title(None)

    ax.set_xlabel("")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v / 1000.0:g}"))
    ax.set_ylabel("Avg. Rate (Mbps)", labelpad=10)
    ax.grid(True, axis="y", alpha=0.3)

    outpath.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(outpath, bbox_inches="tight")


def make_loss_boxplot_seaborn(
    classic_loss: list[float],
    l4s_loss: list[float],
    outpath: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(8, 6.0))

    deep_colors = sns.color_palette("deep", 10)
    variant_palette = {"Classic": deep_colors[1], "L4S": deep_colors[0]}

    rows = []
    rows.extend({"variant": "Classic", "loss_pct": v} for v in classic_loss)
    rows.extend({"variant": "L4S", "loss_pct": v} for v in l4s_loss)
    df = pd.DataFrame(rows)

    sns.boxplot(
        data=df,
        x="variant",
        y="loss_pct",
        order=["Classic", "L4S"],
        width=0.5,
        linewidth=2.0,
        showfliers=True,
        flierprops={
            "marker": "o",
            "markerfacecolor": "black",
            "markeredgecolor": "black",
            "markersize": 5,
        },
        medianprops={"color": "black", "linewidth": 3.0},
        palette=variant_palette,
        ax=ax,
    )

    ax.set_xlabel("")
    ax.set_ylabel("Packet Loss (%)", labelpad=10)
    base_ticks = sorted(ax.get_yticks())
    if len(base_ticks) >= 2:
        step = base_ticks[1] - base_ticks[0]
    else:
        span = max(df["loss_pct"]) - min(df["loss_pct"])
        step = span / 4 if span > 0 else 0.1

    data_min = float(df["loss_pct"].min())
    data_max = float(df["loss_pct"].max())

    above_tick = math.ceil(data_max / step) * step
    if above_tick <= data_max:
        above_tick += step

    # Keep ticks from one interval below the observed minimum to one above maximum.
    lower_tick = math.floor(data_min / step) * step
    if lower_tick >= data_min:
        lower_tick -= step
    lower_tick = max(0.0, lower_tick)

    n_steps = int(round((above_tick - lower_tick) / step))
    all_ticks = [lower_tick + i * step for i in range(n_steps + 1)]
    
    # Ensure at least 3 ticks on the axis
    while len(all_ticks) < 3:
        step = step / 2
        n_steps = int(round((above_tick - lower_tick) / step))
        all_ticks = [lower_tick + i * step for i in range(n_steps + 1)]
    
    ax.set_yticks(all_ticks)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.2f}"))

    # Keep axis at/above zero except for a small visual padding.
    lower_lim = max(-0.05 * step, lower_tick - 0.05 * step)
    ax.set_ylim(lower_lim, above_tick + 0.05 * step)
    ax.grid(True, axis="y", alpha=0.3)

    outpath.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(outpath, bbox_inches="tight")


def make_freeze_duration_cdf(
    classic_freeze_s: list[float],
    l4s_freeze_s: list[float],
    outpath: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(8, 6.0))

    deep_colors = sns.color_palette("deep", 10)
    classic_color = deep_colors[1]
    l4s_color = deep_colors[0]

    classic_sorted = sorted(classic_freeze_s)
    l4s_sorted = sorted(l4s_freeze_s)
    classic_cdf = [(i + 1) / len(classic_sorted) for i in range(len(classic_sorted))]
    l4s_cdf = [(i + 1) / len(l4s_sorted) for i in range(len(l4s_sorted))]

    ax.plot(classic_sorted, classic_cdf, color=classic_color, linewidth=2.8, label="Classic")
    ax.plot(l4s_sorted, l4s_cdf, color=l4s_color, linewidth=2.8, label="L4S")

    ax.legend(["Classic", "L4S"], handlelength=1.0, loc="lower right")
    legend = ax.get_legend()
    if legend is not None:
        legend.set_title(None)

    ax.set_xlabel("")
    ax.set_ylabel("CDF", labelpad=10)
    ax.set_ylim(0, 1.02)
    ax.grid(True, axis="both", alpha=0.3)

    outpath.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(outpath, bbox_inches="tight")


def make_freeze_count_cdf(
    classic_freeze_count: list[float],
    l4s_freeze_count: list[float],
    outpath: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(8, 6.0))

    deep_colors = sns.color_palette("deep", 10)
    classic_color = deep_colors[1]
    l4s_color = deep_colors[0]

    classic_sorted = sorted(classic_freeze_count)
    l4s_sorted = sorted(l4s_freeze_count)
    classic_cdf = [(i + 1) / len(classic_sorted) for i in range(len(classic_sorted))]
    l4s_cdf = [(i + 1) / len(l4s_sorted) for i in range(len(l4s_sorted))]

    ax.plot(classic_sorted, classic_cdf, color=classic_color, linewidth=2.8, label="Classic")
    ax.plot(l4s_sorted, l4s_cdf, color=l4s_color, linewidth=2.8, label="L4S")

    ax.legend(["Classic", "L4S"], handlelength=1.0, loc="lower right")
    legend = ax.get_legend()
    if legend is not None:
        legend.set_title(None)

    ax.set_xlabel("")
    ax.set_ylabel("CDF", labelpad=10)
    ax.set_ylim(0, 1.02)
    ax.grid(True, axis="both", alpha=0.3)

    outpath.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(outpath, bbox_inches="tight")


def make_ifraw_median_violin(
    classic_median_s: list[float],
    l4s_median_s: list[float],
    outpath: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(8, 6.0))
    violin_outline_width = 2.0
    inner_line_width = 2.0
    inner_box_width = 0.04
    inner_whisker_width = 1.8

    deep_colors = sns.color_palette("deep", 10)
    split_palette = {"Classic": deep_colors[1], "L4S": deep_colors[0]}

    rows = []
    rows.extend({"variant": "Classic", "ifraw_s": v} for v in classic_median_s)
    rows.extend({"variant": "L4S", "ifraw_s": v} for v in l4s_median_s)
    df = pd.DataFrame(rows)

    sns.violinplot(
        data=df,
        x="variant",
        y="ifraw_s",
        order=["Classic", "L4S"],
        inner=None,
        linewidth=violin_outline_width,
        cut=0,
        palette=split_palette,
        ax=ax,
    )

    sns.boxplot(
        data=df,
        x="variant",
        y="ifraw_s",
        order=["Classic", "L4S"],
        width=inner_box_width,
        showfliers=False,
        boxprops={"facecolor": "black", "edgecolor": "black", "linewidth": inner_line_width},
        whiskerprops={"color": "black", "linewidth": inner_whisker_width},
        capprops={"color": "black", "linewidth": inner_whisker_width},
        medianprops={"color": "white", "linewidth": inner_line_width},
        saturation=1,
        ax=ax,
    )

    for collection in ax.collections:
        collection.set_linewidth(violin_outline_width)

    ax.set_xlabel("")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v * 1000.0:g}"))
    ax.set_ylabel("IF Delay (ms)", labelpad=10)
    ax.grid(True, axis="y", alpha=0.3)

    outpath.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(outpath, bbox_inches="tight")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate seaborn plots for sender queue-delay p95 and sender/receiver average rate"
    )
    parser.add_argument("classic_dir", help="Directory containing Classic *_tx.log files")
    parser.add_argument("l4s_dir", help="Directory containing L4S *_tx.log files")
    parser.add_argument("output_dir", help="Directory where the plot is written")
    parser.add_argument("--no-show", action="store_true", help="Do not display plots")
    args = parser.parse_args()

    validate_input_dirs(args.classic_dir, args.l4s_dir)
    configure_plot_style()
    output_prefix = get_folder_prefix(args.classic_dir)
    output_root = Path(args.output_dir) / output_prefix

    print(f"[experiment={output_prefix}] Metric summary (Classic vs L4S)")

    classic_p95 = load_sender_qdelay_p95(args.classic_dir)
    l4s_p95 = load_sender_qdelay_p95(args.l4s_dir)

    if not classic_p95 or not l4s_p95:
        print(
            "ERROR: Missing queue delay p95 data; cannot generate violin plot "
            f"(Classic samples={len(classic_p95)}, L4S samples={len(l4s_p95)}).",
            file=sys.stderr,
        )
        raise SystemExit(1)

    print_metric_summary(
        output_prefix,
        "Sender queue-delay p95",
        classic_p95,
        l4s_p95,
        unit=" ms",
        include_q1_q3=True,
    )
    print_qdelay_p95_median_summary(output_prefix, classic_p95, l4s_p95)

    outpath = output_root / f"{output_prefix}_sender_qdelay_p95.pdf"
    make_qdelay_p95_violin(classic_p95, l4s_p95, outpath)

    classic_tx_avg_kbps, classic_rx_avg_kbps = load_avg_rates_kbps(args.classic_dir)
    l4s_tx_avg_kbps, l4s_rx_avg_kbps = load_avg_rates_kbps(args.l4s_dir)

    made = 1
    print(f"Generated plot: {outpath}")

    if classic_tx_avg_kbps and classic_rx_avg_kbps and l4s_tx_avg_kbps and l4s_rx_avg_kbps:
        rate_outpath = output_root / f"{output_prefix}_sender_receiver_avg_rate_boxplot.pdf"
        make_rate_boxplot_seaborn(
            classic_tx_avg_kbps,
            classic_rx_avg_kbps,
            l4s_tx_avg_kbps,
            l4s_rx_avg_kbps,
            rate_outpath,
        )
        made += 1
        print(f"Generated plot: {rate_outpath}")
    else:
        print(
            "Skipped seaborn rate boxplot due to missing data: "
            f"Classic(tx={len(classic_tx_avg_kbps)}, rx={len(classic_rx_avg_kbps)}), "
            f"L4S(tx={len(l4s_tx_avg_kbps)}, rx={len(l4s_rx_avg_kbps)})",
            file=sys.stderr,
        )

    print_metric_summary(
        output_prefix,
        "Sender average rate",
        classic_tx_avg_kbps,
        l4s_tx_avg_kbps,
        unit=" kbps",
        include_q1_q3=True,
    )
    print_metric_summary(
        output_prefix,
        "Receiver average rate",
        classic_rx_avg_kbps,
        l4s_rx_avg_kbps,
        unit=" kbps",
        include_q1_q3=True,
    )

    classic_loss_pct = load_avg_loss_pct(args.classic_dir)
    l4s_loss_pct = load_avg_loss_pct(args.l4s_dir)
    if classic_loss_pct and l4s_loss_pct:
        print(f"Max loss Classic: {max(classic_loss_pct):.3f}%")
        print(f"Max loss L4S: {max(l4s_loss_pct):.3f}%")
    if classic_loss_pct and l4s_loss_pct:
        loss_outpath = output_root / f"{output_prefix}_sender_avg_loss_boxplot.pdf"
        make_loss_boxplot_seaborn(classic_loss_pct, l4s_loss_pct, loss_outpath)
        made += 1
        print(f"Generated plot: {loss_outpath}")
    else:
        print(
            "Skipped loss boxplot due to missing data: "
            f"Classic(loss={len(classic_loss_pct)}), L4S(loss={len(l4s_loss_pct)})",
            file=sys.stderr,
        )

    print_metric_summary(
        output_prefix,
        "Sender average packet loss",
        classic_loss_pct,
        l4s_loss_pct,
        unit=" %",
        include_q1_q3=True,
    )
    print_packet_loss_median_summary(output_prefix, classic_loss_pct, l4s_loss_pct)

    classic_freeze_s = load_freeze_duration_s(args.classic_dir)
    l4s_freeze_s = load_freeze_duration_s(args.l4s_dir)
    if classic_freeze_s and l4s_freeze_s:
        freeze_outpath = output_root / f"{output_prefix}_receiver_freeze_duration_cdf.pdf"
        make_freeze_duration_cdf(classic_freeze_s, l4s_freeze_s, freeze_outpath)
        made += 1
        print(f"Generated plot: {freeze_outpath}")
    else:
        print(
            "Skipped freeze-duration CDF due to missing data: "
            f"Classic(freeze={len(classic_freeze_s)}), L4S(freeze={len(l4s_freeze_s)})",
            file=sys.stderr,
        )

    print_metric_summary(
        output_prefix,
        "Receiver freeze duration",
        classic_freeze_s,
        l4s_freeze_s,
        unit=" s",
        include_p95=True,
        include_q1_q3=True,
    )

    classic_ifraw_median_s, classic_ifraw_ignored = load_ifraw_run_medians(args.classic_dir)
    l4s_ifraw_median_s, l4s_ifraw_ignored = load_ifraw_run_medians(args.l4s_dir)
    print(f"Ignored IF(raw,avg) negative samples - Classic: {classic_ifraw_ignored}")
    print(f"Ignored IF(raw,avg) negative samples - L4S: {l4s_ifraw_ignored}")
    if classic_ifraw_median_s and l4s_ifraw_median_s:
        ifraw_outpath = output_root / f"{output_prefix}_receiver_ifraw_median_violin.pdf"
        make_ifraw_median_violin(
            classic_ifraw_median_s,
            l4s_ifraw_median_s,
            ifraw_outpath,
        )
        made += 1
        print(f"Generated plot: {ifraw_outpath}")
    else:
        print(
            "Skipped IF(raw) median violin due to missing data: "
            f"Classic(median={len(classic_ifraw_median_s)}), "
            f"L4S(median={len(l4s_ifraw_median_s)})",
            file=sys.stderr,
        )

    print_metric_summary(
        output_prefix,
        "Receiver IF(raw,avg) run-median distribution",
        classic_ifraw_median_s,
        l4s_ifraw_median_s,
        unit=" s",
        include_q1_q3=True,
    )

    classic_freeze_count = load_freeze_count_total(args.classic_dir)
    l4s_freeze_count = load_freeze_count_total(args.l4s_dir)
    if classic_freeze_count and l4s_freeze_count:
        freeze_count_outpath = output_root / f"{output_prefix}_receiver_freeze_count_cdf.pdf"
        make_freeze_count_cdf(classic_freeze_count, l4s_freeze_count, freeze_count_outpath)
        made += 1
        print(f"Generated plot: {freeze_count_outpath}")
    else:
        print(
            "Skipped freeze-count CDF due to missing data: "
            f"Classic(count={len(classic_freeze_count)}), L4S(count={len(l4s_freeze_count)})",
            file=sys.stderr,
        )

    print_metric_summary(
        output_prefix,
        "Receiver freeze count total",
        classic_freeze_count,
        l4s_freeze_count,
        include_p95=True,
        include_q1_q3=True,
    )

    print(f"Generated {made} plot(s) in {Path(args.output_dir)}")

    if not args.no_show:
        plt.show()
    else:
        plt.close("all")


if __name__ == "__main__":
    main()
