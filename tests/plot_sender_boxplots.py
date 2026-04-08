#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def parse_sender_summary(logfile: str | Path) -> dict[str, float] | None:
	text = Path(logfile).read_text(encoding="utf-8", errors="replace")
	bitrate = re.search(r"Bitrate\s+min/max/avg\s+\[kbps\]\s*:\s*[\d.eE+-]+\s*/\s*[\d.eE+-]+\s*/\s*(?P<v>[\d.eE+-]+)", text)
	rtt = re.search(r"RTT\s+min/max/avg\s+\[s\]\s*:\s*[\d.eE+-]+\s*/\s*[\d.eE+-]+\s*/\s*(?P<v>[\d.eE+-]+)", text)
	qd = re.search(r"Queue delay\s+max/avg\s+\[s\]\s*:\s*[\d.eE+-]+\s*/\s*(?P<v>[\d.eE+-]+)", text)
	plr = re.search(r"Packet loss avg\s+\[%\]\s*:\s*(?P<v>[\d.eE+-]+)", text)
	ecn_ce = re.search(r"ECN/L4S\s+NotECT/ECT\(0\)/ECT\(1\)/CE\s+\[%\]\s*:\s*[\d.eE+-]+\s*/\s*[\d.eE+-]+\s*/\s*[\d.eE+-]+\s*/\s*(?P<v>[\d.eE+-]+)", text)
	if not (bitrate and rtt and qd and plr and ecn_ce):
		return None
	return {
		"bitrate_avg_mbps": float(bitrate.group("v")) / 1000.0,
		"rtt_avg_ms": float(rtt.group("v")) * 1000.0,
		"queue_delay_avg_ms": float(qd.group("v")) * 1000.0,
		"packet_loss_avg_pct": float(plr.group("v")),
		"ecn_ce_pct": float(ecn_ce.group("v")),
	}


def load_group(directory: str | Path) -> dict[str, list[float]]:
	data = {
		"bitrate_avg_mbps": [],
		"rtt_avg_ms": [],
		"queue_delay_avg_ms": [],
		"packet_loss_avg_pct": [],
		"ecn_ce_pct": [],
	}
	for f in sorted(glob.glob(str(Path(directory) / "*_tx.log"))):
		row = parse_sender_summary(f)
		if row is None:
			continue
		for k in data:
			data[k].append(row[k])
	return data


def make_boxplot(non_l4s: list[float], l4s: list[float], ylabel: str, title: str, outpath: Path) -> None:
	fig, ax = plt.subplots(figsize=(8, 5))
	ax.boxplot([non_l4s, l4s], tick_labels=["Non-L4S", "L4S"], showmeans=True)
	ax.set_ylabel(ylabel)
	ax.set_title(title)
	ax.grid(True, axis="y", alpha=0.3)
	fig.tight_layout()
	outpath.parent.mkdir(parents=True, exist_ok=True)
	fig.savefig(outpath, dpi=220, bbox_inches="tight")


def main() -> None:
	p = argparse.ArgumentParser(description="Sender final-summary boxplots: Non-L4S vs L4S")
	p.add_argument("non_l4s_dir")
	p.add_argument("l4s_dir")
	p.add_argument("output_dir")
	p.add_argument("--no-show", action="store_true")
	args = p.parse_args()

	non = load_group(args.non_l4s_dir)
	l4s = load_group(args.l4s_dir)
	out = Path(args.output_dir)

	plots = [
		("bitrate_avg_mbps", "Average Bitrate [Mbps]", "Sender Average Bitrate"),
		("rtt_avg_ms", "Average RTT [ms]", "Sender Average RTT"),
		("queue_delay_avg_ms", "Average Queue Delay [ms]", "Sender Average Queue Delay"),
		("packet_loss_avg_pct", "Packet Loss [%]", "Sender Packet Loss"),
		("ecn_ce_pct", "CE Marking [%]", "Sender CE Marking"),
	]

	made = 0
	for key, ylabel, title in plots:
		if len(non[key]) == 0 or len(l4s[key]) == 0:
			continue
		make_boxplot(non[key], l4s[key], ylabel, title, out / f"sender_boxplot_{key}.png")
		made += 1

	print(f"Generated {made} sender boxplots in {out}")
	if not args.no_show and made > 0:
		plt.show()
	else:
		plt.close("all")


if __name__ == "__main__":
	main()

