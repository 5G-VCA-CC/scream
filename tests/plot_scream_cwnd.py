#!/usr/bin/env python3
"""
Plot SCReAM congestion control parameters from log file.

Usage:
    python3 plot_scream_cwnd.py <logfile>

Expected log format:
    [SCREAM-CWND] cwnd=12345 sRtt=0.0123 rateLeft=1234567 stream[0].rateShare=1234567 targetBitrateH=1234567
"""

import sys
import re
import matplotlib.pyplot as plt
from pathlib import Path
import argparse


def _save_fig(fig, outdir: Path, filename: str) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    fig.savefig(outdir / filename, dpi=200, bbox_inches='tight')


def parse_scream_log(logfile):
    """Parse SCReAM CWND debug logs, frame sizes, and statistics."""
    cwnd_pattern = re.compile(
        r'\[SCREAM-CWND\] cwnd=(?P<cwnd>\d+)\s+'
        r'sRtt=(?P<srtt>[\d.eE+-]+)\s+'
        r'queueDelay=(?P<queuedelay>[\d.eE+-]+)\s+'
        r'bytesInFlight=(?P<bytesinflight>\d+)\s+'
        r'rateLeft=(?P<rateleft>[\d.eE+-]+)\s+'
        r'stream\[0\]\.rateShare=(?P<rateshare>[\d.eE+-]+)\s+'
        r'targetBitrateH=(?P<target>[\d.eE+-]+)'
    )
    
    frame_size_pattern = re.compile(r'Frame size:\s+(?P<size>\d+)')
    
    # Pattern for statistics summary line
    stats_pattern = re.compile(
        r'summary\s+(?P<time>[\d.]+)\s+Transmit rate\s*=\s*(?P<rate>[\d.]+)kbps,\s*'
        r'PLR\s*=\s*(?P<plr>[\d.]+)%'
    )
    
    data = {
        'cwnd': [],
        'srtt': [],
        'queueDelay': [],
        'bytesInFlight': [],
        'rateLeft': [],
        'rateShare': [],
        'targetBitrateH': [],
        'frameSize': [],
        'transmitRate': [],  # in Mbps
        'transmitRateTime': [],  # timestamps
        'packetLossRate': [],  # in %
        'packetLossRateTime': []  # timestamps
    }
    
    with open(logfile, 'r') as f:
        for line in f:
            # Check for CWND data
            match = cwnd_pattern.search(line)
            if match:
                try:
                    data['cwnd'].append(int(match.group('cwnd')))
                    data['srtt'].append(float(match.group('srtt')))
                    data['queueDelay'].append(float(match.group('queuedelay')))
                    data['bytesInFlight'].append(int(match.group('bytesinflight')))
                    data['rateLeft'].append(float(match.group('rateleft')))
                    data['rateShare'].append(float(match.group('rateshare')))
                    data['targetBitrateH'].append(float(match.group('target')))
                except ValueError as e:
                    # Skip corrupted lines where output got interleaved
                    print(f"Warning: Skipping corrupted line: {e}")
                    continue
            
            # Check for frame size
            frame_match = frame_size_pattern.search(line)
            if frame_match:
                data['frameSize'].append(int(frame_match.group('size')))
            
            # Check for statistics summary
            stats_match = stats_pattern.search(line)
            if stats_match:
                try:
                    time_s = float(stats_match.group('time'))
                    # Convert kbps to Mbps
                    rate_kbps = float(stats_match.group('rate'))
                    data['transmitRate'].append(rate_kbps / 1000.0)
                    data['transmitRateTime'].append(time_s)
                    
                    # PLR is already in percentage
                    data['packetLossRate'].append(float(stats_match.group('plr')))
                    data['packetLossRateTime'].append(time_s)
                except ValueError as e:
                    print(f"Warning: Skipping corrupted statistics line: {e}")
                    continue
    
    return data


def plot_scream_data(data, outdir: Path | None = None, show_plots: bool = True):
    """Create four plots: CWND, sRTT, rate parameters, and frame sizes."""
    
    if not data['cwnd']:
        print("No [SCREAM-CWND] log entries found in file.")
        return
    
    samples = list(range(len(data['cwnd'])))
    
    # Plot 1: CWND over time
    fig1, ax1 = plt.subplots(figsize=(12, 5))
    ax1.plot(samples, data['cwnd'], 'b-', linewidth=1.5, label='CWND')
    ax1.set_xlabel('Sample', fontsize=12)
    ax1.set_ylabel('CWND (bytes)', fontsize=12)
    ax1.set_title('SCReAM Congestion Window (BW Tool)', fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    ax1.legend(fontsize=10)
    fig1.tight_layout()
    if outdir:
        _save_fig(fig1, outdir, 'cwnd_over_samples.png')
    
    # Plot 2: sRTT and Queue Delay over time
    fig2, (ax2a, ax2b) = plt.subplots(2, 1, figsize=(12, 8))
    srtt_ms = [s * 1000 for s in data['srtt']]  # Convert to ms for readability
    queueDelay_ms = [q * 1000 for q in data['queueDelay']]  # Convert to ms
    
    ax2a.plot(samples, srtt_ms, 'g-', linewidth=1.5, label='sRTT')
    ax2a.set_xlabel('Sample', fontsize=12)
    ax2a.set_ylabel('sRTT (ms)', fontsize=12)
    ax2a.set_title('SCReAM Smoothed Round-Trip Time (BW Tool)', fontsize=14, fontweight='bold')
    ax2a.grid(True, alpha=0.3)
    ax2a.legend(fontsize=10)
    
    ax2b.plot(samples, queueDelay_ms, 'purple', linewidth=1.5, label='Queue Delay')
    ax2b.set_xlabel('Sample', fontsize=12)
    ax2b.set_ylabel('Queue Delay (ms)', fontsize=12)
    ax2b.set_title('SCReAM Queue Delay (BW Tool)', fontsize=14, fontweight='bold')
    ax2b.grid(True, alpha=0.3)
    ax2b.legend(fontsize=10)
    fig2.tight_layout()
    if outdir:
        _save_fig(fig2, outdir, 'srtt_queue_delay_over_samples.png')
    
    # Plot 3: Rate parameters (rateLeft, rateShare, targetBitrateH) in Mbps
    fig3, ax3 = plt.subplots(figsize=(12, 6))
    rateLeft_mbps = [r / 1e6 for r in data['rateLeft']]
    rateShare_mbps = [r / 1e6 for r in data['rateShare']]
    targetBitrateH_mbps = [t / 1e6 for t in data['targetBitrateH']]
    
    ax3.plot(samples, rateLeft_mbps, 'r-', linewidth=1.5, alpha=0.7, label='rateLeft')
    ax3.plot(samples, rateShare_mbps, 'b-', linewidth=1.5, alpha=0.7, label='rateShare')
    ax3.plot(samples, targetBitrateH_mbps, 'm--', linewidth=2, label='targetBitrateH')
    ax3.set_xlabel('Sample', fontsize=12)
    ax3.set_ylabel('Bitrate (Mbps)', fontsize=12)
    ax3.set_title('SCReAM Rate Allocation (BW Tool)', fontsize=14, fontweight='bold')
    ax3.grid(True, alpha=0.3)
    ax3.legend(fontsize=10, loc='best')
    fig3.tight_layout()
    if outdir:
        _save_fig(fig3, outdir, 'rate_params_over_samples.png')
    
    # Plot 4: Bytes in Flight over time
    fig4, ax4 = plt.subplots(figsize=(12, 5))
    bytesInFlight_kb = [b / 1024 for b in data['bytesInFlight']]  # Convert to KB
    ax4.plot(samples, bytesInFlight_kb, 'cyan', linewidth=1.5, label='Bytes in Flight')
    ax4.set_xlabel('Sample', fontsize=12)
    ax4.set_ylabel('Bytes in Flight (KB)', fontsize=12)
    ax4.set_title('SCReAM Bytes in Flight (BW Tool)', fontsize=14, fontweight='bold')
    ax4.grid(True, alpha=0.3)
    ax4.legend(fontsize=10)
    fig4.tight_layout()
    if outdir:
        _save_fig(fig4, outdir, 'bytes_in_flight_over_samples.png')
    
    # Plot 5: Frame sizes over time
    if data['frameSize']:
        fig5, ax5 = plt.subplots(figsize=(12, 5))
        frame_samples = list(range(len(data['frameSize'])))
        frame_size_kb = [f / 1024 for f in data['frameSize']]  # Convert to KB
        ax5.plot(frame_samples, frame_size_kb, 'orange', linewidth=1, marker='o', 
                markersize=3, alpha=0.7, label='Frame Size')
        ax5.set_xlabel('Frame Number', fontsize=12)
        ax5.set_ylabel('Frame Size (KB)', fontsize=12)
        ax5.set_title('Encoded Frame Sizes (BW Tool)', fontsize=14, fontweight='bold')
        ax5.grid(True, alpha=0.3)
        ax5.legend(fontsize=10)
        fig5.tight_layout()
        if outdir:
            _save_fig(fig5, outdir, 'frame_size_over_frames.png')
    
    # Plot 6: Transmit Rate over time
    if data['transmitRate']:
        fig6, ax6 = plt.subplots(figsize=(12, 6))
        ax6.plot(data['transmitRateTime'], data['transmitRate'], 
                 color='purple', linewidth=1.5, label='Transmit Rate')
        ax6.set_xlabel('Time (s)', fontsize=12)
        ax6.set_ylabel('Transmit Rate (Mbps)', fontsize=12)
        ax6.set_title('Transmit Rate Over Time (BW Tool)', fontsize=14, fontweight='bold')
        ax6.grid(True, alpha=0.3)
        mean_txrate = sum(data['transmitRate'])/len(data['transmitRate'])
        ax6.axhline(mean_txrate, color='red', linestyle='--', 
                    linewidth=1.5, alpha=0.7, label=f'Mean: {mean_txrate:.2f} Mbps')
        ax6.legend(fontsize=10)
        fig6.tight_layout()
        if outdir:
            _save_fig(fig6, outdir, 'transmit_rate_over_time.png')
    
    # Plot 7: Packet Loss Rate over time
    if data['packetLossRate']:
        fig7, ax7 = plt.subplots(figsize=(12, 6))
        ax7.plot(data['packetLossRateTime'], data['packetLossRate'], 
                 color='red', linewidth=1.5, label='Packet Loss Rate')
        ax7.set_xlabel('Time (s)', fontsize=12)
        ax7.set_ylabel('Packet Loss Rate (%)', fontsize=12)
        ax7.set_title('Packet Loss Rate Over Time (BW Tool)', fontsize=14, fontweight='bold')
        ax7.grid(True, alpha=0.3)
        mean_plr = sum(data['packetLossRate'])/len(data['packetLossRate'])
        ax7.axhline(mean_plr, color='darkred', linestyle='--', 
                    linewidth=1.5, alpha=0.7, label=f'Mean: {mean_plr:.2f}%')
        ax7.legend(fontsize=10)
        fig7.tight_layout()
        if outdir:
            _save_fig(fig7, outdir, 'packet_loss_rate_over_time.png')
    
    if show_plots:
        plt.show()
    
    # Summary statistics
    print("\n=== Summary Statistics ===")
    print(f"Total samples: {len(data['cwnd'])}")
    print(f"CWND: min={min(data['cwnd'])}, max={max(data['cwnd'])}, avg={sum(data['cwnd'])/len(data['cwnd']):.1f}")
    print(f"sRTT (ms): min={min(srtt_ms):.2f}, max={max(srtt_ms):.2f}, avg={sum(srtt_ms)/len(srtt_ms):.2f}")
    print(f"queueDelay (ms): min={min(queueDelay_ms):.2f}, max={max(queueDelay_ms):.2f}, avg={sum(queueDelay_ms)/len(queueDelay_ms):.2f}")
    print(f"bytesInFlight (KB): min={min(bytesInFlight_kb):.2f}, max={max(bytesInFlight_kb):.2f}, avg={sum(bytesInFlight_kb)/len(bytesInFlight_kb):.2f}")
    print(f"targetBitrateH (Mbps): min={min(targetBitrateH_mbps):.2f}, max={max(targetBitrateH_mbps):.2f}, avg={sum(targetBitrateH_mbps)/len(targetBitrateH_mbps):.2f}")
    
    if data['frameSize']:
        print(f"\nFrame sizes: {len(data['frameSize'])} frames")
        print(f"  min={min(data['frameSize'])} bytes, max={max(data['frameSize'])} bytes, "
              f"avg={sum(data['frameSize'])/len(data['frameSize']):.1f} bytes")
        print(f"  min={min(data['frameSize'])/1024:.2f} KB, max={max(data['frameSize'])/1024:.2f} KB, "
              f"avg={sum(data['frameSize'])/len(data['frameSize'])/1024:.2f} KB")
    
    if data['transmitRate']:
        print(f"\nTransmit Rate: {len(data['transmitRate'])} samples")
        print(f"  min={min(data['transmitRate']):.2f} Mbps, max={max(data['transmitRate']):.2f} Mbps, "
              f"avg={sum(data['transmitRate'])/len(data['transmitRate']):.2f} Mbps")
    
    if data['packetLossRate']:
        print(f"\nPacket Loss Rate: {len(data['packetLossRate'])} samples")
        print(f"  min={min(data['packetLossRate']):.2f}%, max={max(data['packetLossRate']):.2f}%, "
              f"avg={sum(data['packetLossRate'])/len(data['packetLossRate']):.2f}%")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('logfile', help='path to *_tx.log file')
    parser.add_argument('-o', '--outdir', default=None, help='directory to save all plots as PNGs')
    parser.add_argument('--no-show', action='store_true', help='do not display plots (useful for headless runs)')
    args = parser.parse_args()

    logfile = args.logfile
    
    if not Path(logfile).exists():
        print(f"Error: File '{logfile}' not found.")
        sys.exit(1)
    
    print(f"Parsing log file: {logfile}")
    data = parse_scream_log(logfile)

    outdir = Path(args.outdir).expanduser().resolve() if args.outdir else None
    if outdir:
        # Avoid overwriting when saving multiple logs into the same directory
        stem = Path(logfile).stem
        outdir = outdir / stem
        print(f"Saving plots to: {outdir}")

    plot_scream_data(data, outdir=outdir, show_plots=not args.no_show)

    if outdir:
        print("\nPNGs saved.")
    if not args.no_show:
        print("\nPlots displayed. Close the plot windows to exit.")


if __name__ == '__main__':
    main()
