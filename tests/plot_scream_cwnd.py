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


def parse_scream_log(logfile):
    """Parse SCReAM CWND debug logs and frame sizes."""
    cwnd_pattern = re.compile(
        r'\[SCREAM-CWND\] cwnd=(?P<cwnd>\d+)\s+'
        r'sRtt=(?P<srtt>[\d.eE+-]+)\s+'
        r'rateLeft=(?P<rateleft>[\d.eE+-]+)\s+'
        r'stream\[0\]\.rateShare=(?P<rateshare>[\d.eE+-]+)\s+'
        r'targetBitrateH=(?P<target>[\d.eE+-]+)'
    )
    
    frame_size_pattern = re.compile(r'Frame size:\s+(?P<size>\d+)')
    
    data = {
        'cwnd': [],
        'srtt': [],
        'rateLeft': [],
        'rateShare': [],
        'targetBitrateH': [],
        'frameSize': []
    }
    
    with open(logfile, 'r') as f:
        for line in f:
            # Check for CWND data
            match = cwnd_pattern.search(line)
            if match:
                data['cwnd'].append(int(match.group('cwnd')))
                data['srtt'].append(float(match.group('srtt')))
                data['rateLeft'].append(float(match.group('rateleft')))
                data['rateShare'].append(float(match.group('rateshare')))
                data['targetBitrateH'].append(float(match.group('target')))
            
            # Check for frame size
            frame_match = frame_size_pattern.search(line)
            if frame_match:
                data['frameSize'].append(int(frame_match.group('size')))
    
    return data


def plot_scream_data(data, output_prefix='scream_cwnd'):
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
    ax1.set_title('SCReAM Congestion Window', fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    ax1.legend(fontsize=10)
    fig1.tight_layout()
    
    # Plot 2: sRTT over time
    fig2, ax2 = plt.subplots(figsize=(12, 5))
    srtt_ms = [s * 1000 for s in data['srtt']]  # Convert to ms for readability
    ax2.plot(samples, srtt_ms, 'g-', linewidth=1.5, label='sRTT')
    ax2.set_xlabel('Sample', fontsize=12)
    ax2.set_ylabel('sRTT (ms)', fontsize=12)
    ax2.set_title('SCReAM Smoothed Round-Trip Time', fontsize=14, fontweight='bold')
    ax2.grid(True, alpha=0.3)
    ax2.legend(fontsize=10)
    fig2.tight_layout()
    
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
    ax3.set_title('SCReAM Rate Allocation', fontsize=14, fontweight='bold')
    ax3.grid(True, alpha=0.3)
    ax3.legend(fontsize=10, loc='best')
    fig3.tight_layout()
    
    # Plot 4: Frame sizes over time
    if data['frameSize']:
        fig4, ax4 = plt.subplots(figsize=(12, 5))
        frame_samples = list(range(len(data['frameSize'])))
        frame_size_kb = [f / 1024 for f in data['frameSize']]  # Convert to KB
        ax4.plot(frame_samples, frame_size_kb, 'orange', linewidth=1, marker='o', 
                markersize=3, alpha=0.7, label='Frame Size')
        ax4.set_xlabel('Frame Number', fontsize=12)
        ax4.set_ylabel('Frame Size (KB)', fontsize=12)
        ax4.set_title('Encoded Frame Sizes', fontsize=14, fontweight='bold')
        ax4.grid(True, alpha=0.3)
        ax4.legend(fontsize=10)
        fig4.tight_layout()
    
    # Show all plots
    plt.show()
    
    # Summary statistics
    print("\n=== Summary Statistics ===")
    print(f"Total samples: {len(data['cwnd'])}")
    print(f"CWND: min={min(data['cwnd'])}, max={max(data['cwnd'])}, avg={sum(data['cwnd'])/len(data['cwnd']):.1f}")
    print(f"sRTT (ms): min={min(srtt_ms):.2f}, max={max(srtt_ms):.2f}, avg={sum(srtt_ms)/len(srtt_ms):.2f}")
    print(f"targetBitrateH (Mbps): min={min(targetBitrateH_mbps):.2f}, max={max(targetBitrateH_mbps):.2f}, avg={sum(targetBitrateH_mbps)/len(targetBitrateH_mbps):.2f}")
    
    if data['frameSize']:
        print(f"\nFrame sizes: {len(data['frameSize'])} frames")
        print(f"  min={min(data['frameSize'])} bytes, max={max(data['frameSize'])} bytes, "
              f"avg={sum(data['frameSize'])/len(data['frameSize']):.1f} bytes")
        print(f"  min={min(data['frameSize'])/1024:.2f} KB, max={max(data['frameSize'])/1024:.2f} KB, "
              f"avg={sum(data['frameSize'])/len(data['frameSize'])/1024:.2f} KB")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nError: Please provide a log file path.")
        sys.exit(1)
    
    logfile = sys.argv[1]
    
    if not Path(logfile).exists():
        print(f"Error: File '{logfile}' not found.")
        sys.exit(1)
    
    print(f"Parsing log file: {logfile}")
    data = parse_scream_log(logfile)
    
    plot_scream_data(data)
    
    print("\nPlots displayed. Close the plot windows to exit.")


if __name__ == '__main__':
    main()
