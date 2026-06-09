#!/usr/bin/env python3
from __future__ import annotations

# Example usage:
# python3 tests/anrw26_seaborn_plots_video_regimes.py \
#   tests/logs/lowmo \
#   tests/logs/medmo \
#   tests/logs/highmo \
#   tests/graphs

import argparse
import glob
import re
import sys
from pathlib import Path
import importlib
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

pd = None
sns = None

if TYPE_CHECKING:
    import pandas as _pd

    DataFrame = _pd.DataFrame
else:
    DataFrame = object


def configure_plot_style() -> None:
    global sns
    if sns is None:
        try:
            sns = importlib.import_module("seaborn")
        except Exception as exc:
            raise SystemExit(
                "ERROR: seaborn is unavailable in this environment. "
                "Use --tx-rx-timeseries mode or install compatible plotting dependencies. "
                f"Details: {exc}"
            )
    sns.set_theme(style="whitegrid", font_scale=2.8)


def require_dataframe_support() -> None:
    global pd
    if pd is None:
        try:
            pd = importlib.import_module("pandas")
        except Exception as exc:
            raise SystemExit(
                "ERROR: pandas is unavailable in this environment. "
                "Use --tx-rx-timeseries mode or install compatible plotting dependencies. "
                f"Details: {exc}"
            )


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
        non_negative = [v for v in samples if v >= 0.0]
        ignored_negative_samples += len(samples) - len(non_negative)
        if not non_negative:
            continue
        med = percentile(non_negative, 50.0)
        if med is not None:
            run_medians_s.append(med)
    return run_medians_s, ignored_negative_samples


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


def parse_tx_rate_timeseries(logfile: str | Path) -> tuple[list[float], list[float]]:
    text = Path(logfile).read_text(encoding="utf-8", errors="replace")
    pattern = re.compile(
        r"^\s*summary\s+(?P<t>[\d.eE+-]+)\s+Transmit rate =\s+(?P<rate>[\d.eE+-]+)kbps,",
        re.MULTILINE,
    )
    rows = list(pattern.finditer(text))
    if not rows:
        raise SystemExit(f"ERROR: No TX time-series rows found in {logfile}")
    times_s = [float(m.group("t")) for m in rows]
    rates_kbps = [float(m.group("rate")) for m in rows]
    return times_s, rates_kbps


def parse_rx_rate_timeseries(logfile: str | Path) -> tuple[list[float], list[float]]:
    text = Path(logfile).read_text(encoding="utf-8", errors="replace")
    pattern = re.compile(
        r"RX\s+periodic\s+\((?P<period>[\d.eE+-]+)s\):\s+rate=\s*(?P<rate>[\d.eE+-]+)\s+kbps"
    )
    rows = list(pattern.finditer(text))
    if not rows:
        raise SystemExit(f"ERROR: No RX time-series rows found in {logfile}")

    times_s: list[float] = []
    rates_kbps: list[float] = []
    t_acc = 0.0
    for m in rows:
        t_acc += float(m.group("period"))
        times_s.append(t_acc)
        rates_kbps.append(float(m.group("rate")))
    return times_s, rates_kbps


def load_run_tx_rx_timeseries(
    directory: str | Path, run_number: int
) -> tuple[list[float], list[float], list[float], list[float]]:
    tx_log = Path(directory) / f"test_{run_number}_tx.log"
    rx_log = Path(directory) / f"test_{run_number}_rx.log"

    if not tx_log.exists():
        raise SystemExit(f"ERROR: Missing TX log file: {tx_log}")
    if not rx_log.exists():
        raise SystemExit(f"ERROR: Missing RX log file: {rx_log}")

    tx_t_s, tx_rate_kbps = parse_tx_rate_timeseries(tx_log)
    rx_t_s, rx_rate_kbps = parse_rx_rate_timeseries(rx_log)
    return tx_t_s, tx_rate_kbps, rx_t_s, rx_rate_kbps


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


def find_variant_subdir(regime_dir: str | Path, prefix: str) -> Path:
    regime_path = Path(regime_dir)
    matches = sorted(
        [
            p
            for p in regime_path.iterdir()
            if p.is_dir() and p.name.lower().startswith(prefix.lower())
        ]
    )
    if not matches:
        raise SystemExit(
            f"ERROR: No subfolder starting with '{prefix}' found in {regime_path}"
        )
    if len(matches) > 1:
        names = ", ".join(p.name for p in matches)
        raise SystemExit(
            f"ERROR: Multiple subfolders starting with '{prefix}' in {regime_path}: {names}"
        )
    return matches[0]


def collect_regime_rows(regime_label: str, regime_dir: str | Path) -> tuple[list[dict[str, object]], int, int]:
    classic_dir = find_variant_subdir(regime_dir, "classic")
    l4s_dir = find_variant_subdir(regime_dir, "l4s")

    classic_medians, classic_ignored = load_ifraw_run_medians(classic_dir)
    l4s_medians, l4s_ignored = load_ifraw_run_medians(l4s_dir)

    rows: list[dict[str, object]] = []
    rows.extend({"regime": regime_label, "variant": "Classic", "ifraw_s": v} for v in classic_medians)
    rows.extend({"regime": regime_label, "variant": "L4S", "ifraw_s": v} for v in l4s_medians)

    if not classic_medians or not l4s_medians:
        raise SystemExit(
            "ERROR: Missing IF(raw,avg) medians for regime "
            f"'{regime_label}' (Classic={len(classic_medians)}, L4S={len(l4s_medians)})"
        )

    return rows, classic_ignored, l4s_ignored


def collect_regime_qdelay_rows(regime_label: str, regime_dir: str | Path) -> list[dict[str, object]]:
    classic_dir = find_variant_subdir(regime_dir, "classic")
    l4s_dir = find_variant_subdir(regime_dir, "l4s")

    classic_p95 = load_sender_qdelay_p95(classic_dir)
    l4s_p95 = load_sender_qdelay_p95(l4s_dir)

    rows: list[dict[str, object]] = []
    rows.extend(
        {"regime": regime_label, "variant": "Classic", "queue_delay_p95_ms": v}
        for v in classic_p95
    )
    rows.extend(
        {"regime": regime_label, "variant": "L4S", "queue_delay_p95_ms": v}
        for v in l4s_p95
    )

    if not classic_p95 or not l4s_p95:
        raise SystemExit(
            "ERROR: Missing queue delay p95 samples for regime "
            f"'{regime_label}' (Classic={len(classic_p95)}, L4S={len(l4s_p95)})"
        )

    return rows


def collect_regime_freeze_rows(regime_label: str, regime_dir: str | Path) -> list[dict[str, object]]:
    classic_dir = find_variant_subdir(regime_dir, "classic")
    l4s_dir = find_variant_subdir(regime_dir, "l4s")

    classic_freeze_s = load_freeze_duration_s(classic_dir)
    l4s_freeze_s = load_freeze_duration_s(l4s_dir)

    rows: list[dict[str, object]] = []
    rows.extend(
        {"regime": regime_label, "variant": "Classic", "freeze_duration_s": v}
        for v in classic_freeze_s
    )
    rows.extend(
        {"regime": regime_label, "variant": "L4S", "freeze_duration_s": v}
        for v in l4s_freeze_s
    )

    if not classic_freeze_s or not l4s_freeze_s:
        raise SystemExit(
            "ERROR: Missing freeze-duration samples for regime "
            f"'{regime_label}' (Classic={len(classic_freeze_s)}, L4S={len(l4s_freeze_s)})"
        )

    return rows


def collect_regime_freeze_count_rows(regime_label: str, regime_dir: str | Path) -> list[dict[str, object]]:
    classic_dir = find_variant_subdir(regime_dir, "classic")
    l4s_dir = find_variant_subdir(regime_dir, "l4s")

    classic_counts = load_freeze_count_total(classic_dir)
    l4s_counts = load_freeze_count_total(l4s_dir)

    rows: list[dict[str, object]] = []
    rows.extend(
        {"regime": regime_label, "variant": "Classic", "freeze_count": v}
        for v in classic_counts
    )
    rows.extend(
        {"regime": regime_label, "variant": "L4S", "freeze_count": v}
        for v in l4s_counts
    )

    if not classic_counts or not l4s_counts:
        raise SystemExit(
            "ERROR: Missing freeze-count samples for regime "
            f"'{regime_label}' (Classic={len(classic_counts)}, L4S={len(l4s_counts)})"
        )

    return rows


def collect_regime_rate_rows(regime_label: str, regime_dir: str | Path) -> list[dict[str, object]]:
    classic_dir = find_variant_subdir(regime_dir, "classic")
    l4s_dir = find_variant_subdir(regime_dir, "l4s")

    classic_tx, classic_rx = load_avg_rates_kbps(classic_dir)
    l4s_tx, l4s_rx = load_avg_rates_kbps(l4s_dir)

    rows: list[dict[str, object]] = []
    rows.extend(
        {"regime": regime_label, "variant": "Classic", "metric": "Tx", "rate_kbps": v}
        for v in classic_tx
    )
    rows.extend(
        {"regime": regime_label, "variant": "Classic", "metric": "Rx", "rate_kbps": v}
        for v in classic_rx
    )
    rows.extend(
        {"regime": regime_label, "variant": "L4S", "metric": "Tx", "rate_kbps": v}
        for v in l4s_tx
    )
    rows.extend(
        {"regime": regime_label, "variant": "L4S", "metric": "Rx", "rate_kbps": v}
        for v in l4s_rx
    )

    if not classic_tx or not classic_rx or not l4s_tx or not l4s_rx:
        raise SystemExit(
            "ERROR: Missing avg-rate samples for regime "
            f"'{regime_label}' (Classic tx={len(classic_tx)}, rx={len(classic_rx)}; "
            f"L4S tx={len(l4s_tx)}, rx={len(l4s_rx)})"
        )

    return rows


def make_ifraw_split_violin(df: DataFrame, outpath: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 7.0))

    deep_colors = sns.color_palette("deep", 10)
    palette = {"Classic": deep_colors[1], "L4S": deep_colors[0]}

    sns.violinplot(
        data=df,
        x="regime",
        y="ifraw_s",
        hue="variant",
        order=["Low", "Medium", "High"],
        hue_order=["Classic", "L4S"],
        split=True,
        inner="quart",
        linewidth=2.0,
        cut=0,
        palette=palette,
        ax=ax,
    )

    # Seaborn does not expose a dedicated quartile-line width argument.
    # The inner quartile markers are regular line artists, so adjust them after draw.
    for line in ax.lines:
        line.set_linewidth(3.0)

    # Draw a center divider for each split violin (Classic on one side, L4S on the other).
    for xpos in ax.get_xticks():
        ax.axvline(x=xpos, ymin=0.0, ymax=1.0, color="black", linewidth=1.4, alpha=0.9, zorder=4)

    legend = ax.get_legend()
    if legend is not None:
        legend.set_title(None)

    ax.set_xlabel("")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v * 1000.0:g}"))
    ax.set_ylabel("IF Delay (ms)", labelpad=10)
    ax.grid(True, axis="y", alpha=0.3)

    outpath.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(outpath, bbox_inches="tight")


def make_qdelay_p95_split_violin(df: DataFrame, outpath: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 7.0))

    deep_colors = sns.color_palette("deep", 10)
    palette = {"Classic": deep_colors[1], "L4S": deep_colors[0]}

    sns.violinplot(
        data=df,
        x="regime",
        y="queue_delay_p95_ms",
        hue="variant",
        order=["Low", "Medium", "High"],
        hue_order=["Classic", "L4S"],
        split=True,
        inner="quart",
        linewidth=2.0,
        cut=0,
        palette=palette,
        ax=ax,
    )

    for line in ax.lines:
        line.set_linewidth(3.0)

    # Draw a center divider for each split violin (Classic on one side, L4S on the other).
    for xpos in ax.get_xticks():
        ax.axvline(x=xpos, ymin=0.0, ymax=1.0, color="black", linewidth=1.4, alpha=0.9, zorder=4)

    legend = ax.get_legend()
    if legend is not None:
        legend.set_title(None)

    ax.set_xlabel("")
    ax.set_ylabel("Queue Delay p95 (ms)", labelpad=10)
    ax.grid(True, axis="y", alpha=0.3)

    outpath.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(outpath, bbox_inches="tight")


def make_freeze_duration_split_violin(df: DataFrame, outpath: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 7.0))

    deep_colors = sns.color_palette("deep", 10)
    palette = {"Classic": deep_colors[1], "L4S": deep_colors[0]}

    sns.violinplot(
        data=df,
        x="regime",
        y="freeze_duration_s",
        hue="variant",
        order=["Low", "Medium", "High"],
        hue_order=["Classic", "L4S"],
        split=True,
        inner="quart",
        linewidth=2.0,
        cut=0,
        palette=palette,
        ax=ax,
    )

    for line in ax.lines:
        line.set_linewidth(3.0)

    # Draw a center divider for each split violin (Classic on one side, L4S on the other).
    for xpos in ax.get_xticks():
        ax.axvline(x=xpos, ymin=0.0, ymax=1.0, color="black", linewidth=1.4, alpha=0.9, zorder=4)

    legend = ax.get_legend()
    if legend is not None:
        legend.set_title(None)

    ax.set_xlabel("")
    ax.set_ylabel("Freeze Duration (s)", labelpad=10)
    ax.grid(True, axis="y", alpha=0.3)

    outpath.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(outpath, bbox_inches="tight")


def make_freeze_count_split_violin(df: DataFrame, outpath: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 7.0))

    deep_colors = sns.color_palette("deep", 10)
    palette = {"Classic": deep_colors[1], "L4S": deep_colors[0]}

    sns.violinplot(
        data=df,
        x="regime",
        y="freeze_count",
        hue="variant",
        order=["Low", "Medium", "High"],
        hue_order=["Classic", "L4S"],
        split=True,
        inner="quart",
        linewidth=2.0,
        cut=0,
        palette=palette,
        ax=ax,
    )

    for line in ax.lines:
        line.set_linewidth(3.0)

    # Draw a center divider for each split violin (Classic on one side, L4S on the other).
    for xpos in ax.get_xticks():
        ax.axvline(x=xpos, ymin=0.0, ymax=1.0, color="black", linewidth=1.4, alpha=0.9, zorder=4)

    legend = ax.get_legend()
    if legend is not None:
        legend.set_title(None)

    ax.set_xlabel("")
    ax.set_ylabel("Freeze Count", labelpad=10)
    ax.grid(True, axis="y", alpha=0.3)

    outpath.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(outpath, bbox_inches="tight")


def make_rate_boxplot_video_regimes(df: DataFrame, outpath: Path, variant: str) -> None:
    fig, ax = plt.subplots(1, 1, figsize=(11, 6.5))

    metric_palette = {"Tx": "#8A2BE2", "Rx": "#2EBE6A"}
    regime_order = ["Low", "Medium", "High"]
    metric_order = ["Tx", "Rx"]

    variant_df = df[df["variant"] == variant]

    sns.boxplot(
        data=variant_df,
        x="regime",
        y="rate_kbps",
        hue="metric",
        order=regime_order,
        hue_order=metric_order,
        width=0.55,
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
    ax.set_xticks(range(len(regime_order)), regime_order)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v / 1000.0:g}"))
    ax.set_ylabel(f"{variant} Avg. Rate (Mbps)", labelpad=10)
    ax.grid(True, axis="y", alpha=0.3)

    outpath.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(outpath, bbox_inches="tight")


def make_tx_rx_timeseries_plot(
    classic_tx_t: list[float],
    classic_tx_rate: list[float],
    classic_rx_t: list[float],
    classic_rx_rate: list[float],
    l4s_tx_t: list[float],
    l4s_tx_rate: list[float],
    l4s_rx_t: list[float],
    l4s_rx_rate: list[float],
    outpath: Path,
    run_number: int,
) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(11, 12), sharex=True)

    tx_color = "#C07A2B"
    rx_color = "#2EBE6A"

    axes[0].plot(classic_tx_t, classic_tx_rate, color=tx_color, linewidth=2.4, label="Tx")
    axes[0].plot(classic_rx_t, classic_rx_rate, color=rx_color, linewidth=2.4, label="Rx")
    axes[0].set_title("Classic")
    axes[0].set_ylabel("Rate (Mbps)", labelpad=10)
    axes[0].yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v / 1000.0:g}"))
    axes[0].grid(True, axis="both", alpha=0.3)
    axes[0].legend(loc="upper right")

    axes[1].plot(l4s_tx_t, l4s_tx_rate, color=tx_color, linewidth=2.4, label="Tx")
    axes[1].plot(l4s_rx_t, l4s_rx_rate, color=rx_color, linewidth=2.4, label="Rx")
    axes[1].set_title("L4S")
    axes[1].set_ylabel("Rate (Mbps)", labelpad=10)
    axes[1].yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v / 1000.0:g}"))
    axes[1].grid(True, axis="both", alpha=0.3)
    axes[1].legend(loc="upper right")
    axes[1].set_xlabel("Time (s)")

    fig.suptitle(f"Tx/Rx Rate Time Series - test_{run_number}")
    outpath.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(outpath, bbox_inches="tight")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Split violin for IF(raw,avg) medians across low/medium/high motion regimes"
    )
    parser.add_argument("low_motion_dir", nargs="?", help="Regime root folder for low motion")
    parser.add_argument("medium_motion_dir", nargs="?", help="Regime root folder for medium motion")
    parser.add_argument("high_motion_dir", nargs="?", help="Regime root folder for high motion")
    parser.add_argument("output_dir", nargs="?", help="Directory where plot is written")
    parser.add_argument(
        "--tx-rx-timeseries",
        action="store_true",
        help="Generate only Tx/Rx time-series for one run using classic/l4s folders",
    )
    parser.add_argument("--classic-dir", help="Classic folder for --tx-rx-timeseries mode")
    parser.add_argument("--l4s-dir", help="L4S folder for --tx-rx-timeseries mode")
    parser.add_argument("--run-number", type=int, help="Run number n for test_n_tx.log/test_n_rx.log")
    parser.add_argument("--no-show", action="store_true", help="Do not display plots")
    args = parser.parse_args()

    if args.tx_rx_timeseries:
        output_dir = args.output_dir if args.output_dir else args.low_motion_dir
        if not args.classic_dir or not args.l4s_dir or args.run_number is None or not output_dir:
            raise SystemExit(
                "ERROR: --tx-rx-timeseries requires: --classic-dir, --l4s-dir, --run-number, and output_dir"
            )

        classic_tx_t, classic_tx_rate, classic_rx_t, classic_rx_rate = load_run_tx_rx_timeseries(
            args.classic_dir, args.run_number
        )
        l4s_tx_t, l4s_tx_rate, l4s_rx_t, l4s_rx_rate = load_run_tx_rx_timeseries(
            args.l4s_dir, args.run_number
        )

        output_subdir = Path(output_dir) / "video_regimes"
        output_subdir.mkdir(parents=True, exist_ok=True)
        outpath = output_subdir / f"tx_rx_timeseries_test_{args.run_number}.pdf"

        make_tx_rx_timeseries_plot(
            classic_tx_t,
            classic_tx_rate,
            classic_rx_t,
            classic_rx_rate,
            l4s_tx_t,
            l4s_tx_rate,
            l4s_rx_t,
            l4s_rx_rate,
            outpath,
            args.run_number,
        )
        print(f"Generated plot: {outpath}")

        if not args.no_show:
            plt.show()
        else:
            plt.close("all")
        return

    if not args.low_motion_dir or not args.medium_motion_dir or not args.high_motion_dir or not args.output_dir:
        raise SystemExit(
            "ERROR: default mode requires positional args: low_motion_dir medium_motion_dir high_motion_dir output_dir"
        )

    require_dataframe_support()
    configure_plot_style()

    rows: list[dict[str, object]] = []
    low_rows, low_ignored_classic, low_ignored_l4s = collect_regime_rows(
        "Low", args.low_motion_dir
    )
    med_rows, med_ignored_classic, med_ignored_l4s = collect_regime_rows(
        "Medium", args.medium_motion_dir
    )
    high_rows, high_ignored_classic, high_ignored_l4s = collect_regime_rows(
        "High", args.high_motion_dir
    )
    rows.extend(low_rows)
    rows.extend(med_rows)
    rows.extend(high_rows)

    print(
        "Ignored IF(raw,avg) negative samples - "
        f"Low(Classic={low_ignored_classic}, L4S={low_ignored_l4s}), "
        f"Medium(Classic={med_ignored_classic}, L4S={med_ignored_l4s}), "
        f"High(Classic={high_ignored_classic}, L4S={high_ignored_l4s})"
    )

    df = pd.DataFrame(rows)
    output_subdir = Path(args.output_dir) / "video_regimes"
    output_subdir.mkdir(parents=True, exist_ok=True)
    outpath = output_subdir / "ifraw_split_violin_video_regimes.pdf"
    make_ifraw_split_violin(df, outpath)
    print(f"Generated plot: {outpath}")

    qdelay_rows: list[dict[str, object]] = []
    qdelay_rows.extend(collect_regime_qdelay_rows("Low", args.low_motion_dir))
    qdelay_rows.extend(collect_regime_qdelay_rows("Medium", args.medium_motion_dir))
    qdelay_rows.extend(collect_regime_qdelay_rows("High", args.high_motion_dir))

    qdelay_df = pd.DataFrame(qdelay_rows)
    qdelay_outpath = output_subdir / "sender_qdelay_p95_split_violin_video_regimes.pdf"
    make_qdelay_p95_split_violin(qdelay_df, qdelay_outpath)
    print(f"Generated plot: {qdelay_outpath}")

    freeze_rows: list[dict[str, object]] = []
    freeze_rows.extend(collect_regime_freeze_rows("Low", args.low_motion_dir))
    freeze_rows.extend(collect_regime_freeze_rows("Medium", args.medium_motion_dir))
    freeze_rows.extend(collect_regime_freeze_rows("High", args.high_motion_dir))

    freeze_df = pd.DataFrame(freeze_rows)
    freeze_outpath = output_subdir / "receiver_freeze_duration_split_violin_video_regimes.pdf"
    make_freeze_duration_split_violin(freeze_df, freeze_outpath)
    print(f"Generated plot: {freeze_outpath}")

    freeze_count_rows: list[dict[str, object]] = []
    freeze_count_rows.extend(collect_regime_freeze_count_rows("Low", args.low_motion_dir))
    freeze_count_rows.extend(collect_regime_freeze_count_rows("Medium", args.medium_motion_dir))
    freeze_count_rows.extend(collect_regime_freeze_count_rows("High", args.high_motion_dir))

    freeze_count_df = pd.DataFrame(freeze_count_rows)
    freeze_count_outpath = output_subdir / "receiver_freeze_count_split_violin_video_regimes.pdf"
    make_freeze_count_split_violin(freeze_count_df, freeze_count_outpath)
    print(f"Generated plot: {freeze_count_outpath}")

    rate_rows: list[dict[str, object]] = []
    rate_rows.extend(collect_regime_rate_rows("Low", args.low_motion_dir))
    rate_rows.extend(collect_regime_rate_rows("Medium", args.medium_motion_dir))
    rate_rows.extend(collect_regime_rate_rows("High", args.high_motion_dir))

    rate_df = pd.DataFrame(rate_rows)
    rate_outpath_classic = output_subdir / "sender_receiver_avg_rate_boxplot_video_regimes_classic.pdf"
    make_rate_boxplot_video_regimes(rate_df, rate_outpath_classic, "Classic")
    print(f"Generated plot: {rate_outpath_classic}")

    rate_outpath_l4s = output_subdir / "sender_receiver_avg_rate_boxplot_video_regimes_l4s.pdf"
    make_rate_boxplot_video_regimes(rate_df, rate_outpath_l4s, "L4S")
    print(f"Generated plot: {rate_outpath_l4s}")

    if not args.no_show:
        plt.show()
    else:
        plt.close("all")


if __name__ == "__main__":
    main()
