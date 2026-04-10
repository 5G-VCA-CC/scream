#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import re
from pathlib import Path

import matplotlib.pyplot as plt


def parse_receiver_summary(logfile: str | Path) -> dict[str, float] | None:
	text = Path(logfile).read_text(encoding="utf-8", errors="replace")

	m_rate = re.search(
		r"Receive rate min/max/avg \[(?P<u>k?Mbps|kbps|Mbps)\]\s*:\s*[\d.eE+-]+\s*/\s*[\d.eE+-]+\s*/\s*(?P<v>[\d.eE+-]+)",
		text,
	)
	m_ifdd = re.search(r"IF delay diff min/max/avg \[s\]\s*:\s*[\d.eE+-]+\s*/\s*[\d.eE+-]+\s*/\s*(?P<v>[\d.eE+-]+)", text)
	m_ifraw = re.search(r"IF arrival\s+min/max/avg \[s\]\s*:\s*[\d.eE+-]+\s*/\s*[\d.eE+-]+\s*/\s*(?P<v>[\d.eE+-]+)", text)
	m_freeze_dur = re.search(r"Total freeze duration \[s\]\s*:\s*(?P<v>[\d.eE+-]+)", text)
	m_freeze_cnt = re.search(r"Freeze count total\s*:\s*(?P<v>[\d.eE+-]+)", text)
	m_if_var = re.search(r"Inter-frame delay variance \[s\^2\]\s*:\s*(?P<v>[\d.eE+-]+)", text)

	if not (m_rate and m_ifdd and m_ifraw and m_freeze_dur and m_freeze_cnt):
		return None

	rate_v = float(m_rate.group("v"))
	unit = m_rate.group("u")
	if unit.lower().startswith("k"):
		rate_v = rate_v / 1000.0

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


def load_group(directory: str | Path) -> dict[str, list[float]]:
	data = {
		"receive_rate_avg_mbps": [],
		"ifdd_avg_ms": [],
		"ifraw_avg_ms": [],
		"freeze_duration_total_s": [],
		"freeze_count_total": [],
		"inter_frame_delay_variance_ms2": [],
	}
	for f in sorted(glob.glob(str(Path(directory) / "*_rx.log"))):
		row = parse_receiver_summary(f)
		if row is None:
			continue
		for k in data:
			if k in row:
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
	p = argparse.ArgumentParser(description="Receiver final-summary boxplots: Non-L4S vs L4S")
	p.add_argument("non_l4s_dir")
	p.add_argument("l4s_dir")
	p.add_argument("output_dir")
	p.add_argument("--no-show", action="store_true")
	args = p.parse_args()

	non = load_group(args.non_l4s_dir)
	l4s = load_group(args.l4s_dir)
	out = Path(args.output_dir)

	plots = [
		("receive_rate_avg_mbps", "Average Receive Rate [Mbps]", "Receiver Average Receive Rate"),
		("ifdd_avg_ms", "Average IF Delay Difference [ms]", "Receiver IF Delay Difference"),
		("ifraw_avg_ms", "Average Raw IF Delay [ms]", "Receiver Raw Inter-frame Delay"),
		("freeze_duration_total_s", "Total Freeze Duration [s]", "Receiver Freeze Duration"),
		("freeze_count_total", "Freeze Count", "Receiver Freeze Count"),
		("inter_frame_delay_variance_ms2", "Inter-frame Delay Variance [ms^2]", "Receiver IF Delay Variance"),
	]

	made = 0
	for key, ylabel, title in plots:
		if len(non[key]) == 0 or len(l4s[key]) == 0:
			continue
		make_boxplot(non[key], l4s[key], ylabel, title, out / f"receiver_boxplot_{key}.png")
		made += 1

	print(f"Generated {made} receiver boxplots in {out}")
	if not args.no_show and made > 0:
		plt.show()
	else:
		plt.close("all")


if __name__ == "__main__":
	main()

