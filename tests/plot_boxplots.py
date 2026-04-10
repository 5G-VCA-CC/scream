#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import re
from pathlib import Path

import matplotlib.pyplot as plt


# ----------------------------- Parsing -----------------------------

def parse_sender_summary(logfile: str | Path) -> dict[str, float] | None:
    text = Path(logfile).read_text(encoding="utf-8", errors="replace")

    bitrate = re.search(
        r"Bitrate\s+min/max/avg\s+\[kbps\]\s*:\s*[\d.eE+-]+\s*/\s*[\d.eE+-]+\s*/\s*(?P<v>[\d.eE+-]+)",
        text,
    )
    rtt = re.search(
        r"RTT\s+min/max/avg\s+\[s\]\s*:\s*[\d.eE+-]+\s*/\s*[\d.eE+-]+\s*/\s*(?P<v>[\d.eE+-]+)",
        text,
    )
    qd = re.search(
        r"Queue delay\s+max/avg\s+\[s\]\s*:\s*[\d.eE+-]+\s*/\s*(?P<v>[\d.eE+-]+)",
        text,
    )
    plr = re.search(r"Packet loss avg\s+\[%\]\s*:\s*(?P<v>[\d.eE+-]+)", text)
    ecn_ce = re.search(
        r"ECN/L4S\s+NotECT/ECT\(0\)/ECT\(1\)/CE\s+\[%\]\s*:\s*"
        r"[\d.eE+-]+\s*/\s*[\d.eE+-]+\s*/\s*[\d.eE+-]+\s*/\s*(?P<v>[\d.eE+-]+)",
        text,
    )

    if not (bitrate and rtt and qd and plr):
        return None

    out = {
        "bitrate_avg_mbps": float(bitrate.group("v")) / 1000.0,
        "rtt_avg_ms": float(rtt.group("v")) * 1000.0,
        "queue_delay_avg_ms": float(qd.group("v")) * 1000.0,
        "packet_loss_avg_pct": float(plr.group("v")),
    }
    if ecn_ce:
        out["ecn_ce_pct"] = float(ecn_ce.group("v"))
    return out


def parse_receiver_summary(logfile: str | Path) -> dict[str, float] | None:
    text = Path(logfile).read_text(encoding="utf-8", errors="replace")

    m_rate = re.search(
        r"Receive rate min/max/avg \[(?P<u>k?Mbps|kbps|Mbps)\]\s*:\s*"
        r"[\d.eE+-]+\s*/\s*[\d.eE+-]+\s*/\s*(?P<v>[\d.eE+-]+)",
        text,
    )
    m_ifdd = re.search(
        r"IF delay diff min/max/avg \[s\]\s*:\s*[\d.eE+-]+\s*/\s*[\d.eE+-]+\s*/\s*(?P<v>[\d.eE+-]+)",
        text,
    )
    m_ifraw = re.search(
        r"IF arrival\s+min/max/avg \[s\]\s*:\s*[\d.eE+-]+\s*/\s*[\d.eE+-]+\s*/\s*(?P<v>[\d.eE+-]+)",
        text,
    )
    m_freeze_dur = re.search(r"Total freeze duration \[s\]\s*:\s*(?P<v>[\d.eE+-]+)", text)
    m_freeze_cnt = re.search(r"Freeze count total\s*:\s*(?P<v>[\d.eE+-]+)", text)
    m_if_var = re.search(r"Inter-frame delay variance \[s\^2\]\s*:\s*(?P<v>[\d.eE+-]+)", text)

    if not (m_rate and m_ifdd and m_ifraw and m_freeze_dur and m_freeze_cnt):
        return None

    rate_v = float(m_rate.group("v"))
    if m_rate.group("u").lower().startswith("k"):
        rate_v /= 1000.0

    out = {
        "receive_rate_avg_mbps": rate_v,
        "ifdd_avg_ms": float(m_ifdd.group("v")) * 1000.0,
        "ifraw_avg_ms": float(m_ifraw.group("v")) * 1000.0,
        "freeze_duration_total_s": float(m_freeze_dur.group("v")),
        "freeze_count_total": float(m_freeze_cnt.group("v")),
    }
    if m_if_var:
        out["inter_frame_delay_variance_ms2"] = float(m_if_var.group("v")) * 1e6
    return out


# ----------------------------- Loading -----------------------------

def load_sender_group(directory: str | Path) -> dict[str, list[float]]:
    keys = [
        "bitrate_avg_mbps",
        "rtt_avg_ms",
        "queue_delay_avg_ms",
        "packet_loss_avg_pct",
        "ecn_ce_pct",
    ]
    data = {k: [] for k in keys}
    for f in sorted(glob.glob(str(Path(directory) / "*_tx.log"))):
        row = parse_sender_summary(f)
        if row is None:
            continue
        for k in keys:
            if k in row:
                data[k].append(row[k])
    return data


def load_receiver_group(directory: str | Path) -> dict[str, list[float]]:
    keys = [
        "receive_rate_avg_mbps",
        "ifdd_avg_ms",
        "ifraw_avg_ms",
        "freeze_duration_total_s",
        "freeze_count_total",
        "inter_frame_delay_variance_ms2",
    ]
    data = {k: [] for k in keys}
    for f in sorted(glob.glob(str(Path(directory) / "*_rx.log"))):
        row = parse_receiver_summary(f)
        if row is None:
            continue
        for k in keys:
            if k in row:
                data[k].append(row[k])
    return data


# ----------------------------- Plotting -----------------------------

def make_boxplot(
    classic: list[float],
    l4s: list[float],
    ylabel: str,
    title: str,
    outpath: Path,
    show_fliers: bool,
) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.boxplot(
        [classic, l4s],
        tick_labels=["Classic", "L4S"],
        showmeans=True,
        showfliers=show_fliers,
    )
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    outpath.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(outpath, dpi=220, bbox_inches="tight")


def main() -> None:
    p = argparse.ArgumentParser(
        description="Final-summary boxplots for sender+receiver (Classic vs L4S)"
    )
    p.add_argument("classic_dir", help="Directory containing Classic *_tx.log and *_rx.log")
    p.add_argument("l4s_dir", help="Directory containing L4S *_tx.log and *_rx.log")
    p.add_argument("output_dir", help="Directory where plots are written")
    p.add_argument("--show-fliers", action="store_true", help="Show outlier circles")
    p.add_argument("--no-show", action="store_true", help="Do not display plots")
    args = p.parse_args()

    out = Path(args.output_dir)

    non_tx = load_sender_group(args.classic_dir)
    l4s_tx = load_sender_group(args.l4s_dir)
    non_rx = load_receiver_group(args.classic_dir)
    l4s_rx = load_receiver_group(args.l4s_dir)

    sender_plots = [
        ("bitrate_avg_mbps", "Average Bitrate [Mbps]", "Sender Average Bitrate"),
        ("rtt_avg_ms", "Average RTT [ms]", "Sender Average RTT"),
        ("queue_delay_avg_ms", "Average Queue Delay [ms]", "Sender Average Queue Delay"),
        ("packet_loss_avg_pct", "Packet Loss [%]", "Sender Packet Loss"),
        ("ecn_ce_pct", "CE Marking [%]", "Sender CE Marking"),
    ]

    receiver_plots = [
        ("receive_rate_avg_mbps", "Average Receive Rate [Mbps]", "Receiver Average Receive Rate"),
        ("ifdd_avg_ms", "Average IF Delay Difference [ms]", "Receiver IF Delay Difference"),
        ("ifraw_avg_ms", "Average Raw IF Delay [ms]", "Receiver Raw Inter-frame Delay"),
        ("freeze_duration_total_s", "Total Freeze Duration [s]", "Receiver Freeze Duration"),
        ("freeze_count_total", "Freeze Count", "Receiver Freeze Count"),
        (
            "inter_frame_delay_variance_ms2",
            "Inter-frame Delay Variance [ms^2]",
            "Receiver IF Delay Variance",
        ),
    ]

    made = 0

    for key, ylabel, title in sender_plots:
        if len(non_tx[key]) == 0 or len(l4s_tx[key]) == 0:
            continue
        make_boxplot(
            non_tx[key],
            l4s_tx[key],
            ylabel,
            title,
            out / "sender" / f"sender_boxplot_{key}.png",
            args.show_fliers,
        )
        made += 1

    for key, ylabel, title in receiver_plots:
        if len(non_rx[key]) == 0 or len(l4s_rx[key]) == 0:
            continue
        make_boxplot(
            non_rx[key],
            l4s_rx[key],
            ylabel,
            title,
            out / "receiver" / f"receiver_boxplot_{key}.png",
            args.show_fliers,
        )
        made += 1

    print(f"Generated {made} boxplots in {out}")

    if not args.no_show and made > 0:
        plt.show()
    else:
        plt.close("all")


if __name__ == "__main__":
    main()
