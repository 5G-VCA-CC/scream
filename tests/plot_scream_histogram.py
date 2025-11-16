#!/usr/bin/env python3
"""
Plot histograms of SCReAM congestion control parameters from multiple test runs.

Usage:
    python3 plot_scream_histogram.py <test_results_directory>

Reads all *_tx.log files from the directory and creates histogram plots.
"""

import sys
import re
import matplotlib.pyplot as plt
from pathlib import Path
import glob


def parse_scream_log(logfile):
    """Parse SCReAM CWND debug logs and extract parameters."""
    pattern = re.compile(
        r'\[SCREAM-CWND\] cwnd=(?P<cwnd>\d+)\s+'
        r'sRtt=(?P<srtt>[\d.eE+-]+)\s+'
        r'rateLeft=(?P<rateleft>[\d.eE+-]+)\s+'
        r'stream\[0\]\.rateShare=(?P<rateshare>[\d.eE+-]+)\s+'
        r'targetBitrateH=(?P<target>[\d.eE+-]+)'
    )
    
    data = {
        'cwnd': [],
        'srtt': [],
        'rateLeft': [],
        'rateShare': [],
        'targetBitrateH': []
    }
    
    with open(logfile, 'r') as f:
        for line in f:
            match = pattern.search(line)
            if match:
                data['cwnd'].append(int(match.group('cwnd')))
                data['srtt'].append(float(match.group('srtt')))
                data['rateLeft'].append(float(match.group('rateleft')))
                data['rateShare'].append(float(match.group('rateshare')))
                data['targetBitrateH'].append(float(match.group('target')))
    
    return data


def parse_all_logs(directory):
    """Parse all *_tx.log files in the directory."""
    log_pattern = str(Path(directory) / "*_tx.log")
    log_files = glob.glob(log_pattern)
    
    if not log_files:
        print(f"No *_tx.log files found in {directory}")
        return None
    
    print(f"Found {len(log_files)} log files:")
    for log in sorted(log_files):
        print(f"  - {Path(log).name}")
    
    # Aggregate data from all logs
    all_data = {
        'cwnd': [],
        'srtt': [],
        'rateLeft': [],
        'rateShare': [],
        'targetBitrateH': []
    }
    
    for logfile in sorted(log_files):
        data = parse_scream_log(logfile)
        for key in all_data.keys():
            all_data[key].extend(data[key])
    
    print(f"\nTotal samples collected: {len(all_data['cwnd'])}")
    return all_data


def plot_histograms(data):
    """Create three histogram plots."""
    
    if not data or not data['cwnd']:
        print("No data to plot.")
        return
    
    # Histogram 1: CWND
    fig1, ax1 = plt.subplots(figsize=(12, 6))
    ax1.hist(data['cwnd'], bins=50, color='blue', alpha=0.7, edgecolor='black')
    ax1.set_xlabel('CWND (bytes)', fontsize=12)
    ax1.set_ylabel('Frequency', fontsize=12)
    ax1.set_title('SCReAM Congestion Window Distribution', fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.3, axis='y')
    ax1.axvline(sum(data['cwnd'])/len(data['cwnd']), color='red', linestyle='--', 
                linewidth=2, label=f"Mean: {sum(data['cwnd'])/len(data['cwnd']):.0f}")
    ax1.legend(fontsize=10)
    fig1.tight_layout()
    
    # Histogram 2: sRTT
    fig2, ax2 = plt.subplots(figsize=(12, 6))
    srtt_ms = [s * 1000 for s in data['srtt']]  # Convert to ms
    ax2.hist(srtt_ms, bins=50, color='green', alpha=0.7, edgecolor='black')
    ax2.set_xlabel('sRTT (ms)', fontsize=12)
    ax2.set_ylabel('Frequency', fontsize=12)
    ax2.set_title('SCReAM Smoothed Round-Trip Time Distribution', fontsize=14, fontweight='bold')
    ax2.grid(True, alpha=0.3, axis='y')
    mean_srtt = sum(srtt_ms)/len(srtt_ms)
    ax2.axvline(mean_srtt, color='red', linestyle='--', 
                linewidth=2, label=f"Mean: {mean_srtt:.2f} ms")
    ax2.legend(fontsize=10)
    fig2.tight_layout()
    
    # Histogram 3: Rate parameters (all three on same plot)
    fig3, ax3 = plt.subplots(figsize=(12, 6))
    rateLeft_mbps = [r / 1e6 for r in data['rateLeft']]
    rateShare_mbps = [r / 1e6 for r in data['rateShare']]
    targetBitrateH_mbps = [t / 1e6 for t in data['targetBitrateH']]
    
    # Create overlaid histograms with different colors
    ax3.hist(rateLeft_mbps, bins=50, alpha=0.5, label='rateLeft', color='red', edgecolor='black')
    ax3.hist(rateShare_mbps, bins=50, alpha=0.5, label='rateShare', color='blue', edgecolor='black')
    ax3.hist(targetBitrateH_mbps, bins=50, alpha=0.5, label='targetBitrateH', color='magenta', edgecolor='black')
    
    ax3.set_xlabel('Bitrate (Mbps)', fontsize=12)
    ax3.set_ylabel('Frequency', fontsize=12)
    ax3.set_title('SCReAM Rate Allocation Distribution', fontsize=14, fontweight='bold')
    ax3.grid(True, alpha=0.3, axis='y')
    ax3.legend(fontsize=10, loc='best')
    fig3.tight_layout()
    
    # Show all plots
    plt.show()
    
    # Summary statistics
    print("\n=== Summary Statistics ===")
    print(f"Total samples: {len(data['cwnd'])}")
    print(f"\nCWND (bytes):")
    print(f"  min={min(data['cwnd'])}, max={max(data['cwnd'])}, "
          f"mean={sum(data['cwnd'])/len(data['cwnd']):.1f}, "
          f"median={sorted(data['cwnd'])[len(data['cwnd'])//2]}")
    
    print(f"\nsRTT (ms):")
    print(f"  min={min(srtt_ms):.2f}, max={max(srtt_ms):.2f}, "
          f"mean={mean_srtt:.2f}, "
          f"median={sorted(srtt_ms)[len(srtt_ms)//2]:.2f}")
    
    print(f"\nrateLeft (Mbps):")
    mean_rateLeft = sum(rateLeft_mbps)/len(rateLeft_mbps)
    print(f"  min={min(rateLeft_mbps):.2f}, max={max(rateLeft_mbps):.2f}, "
          f"mean={mean_rateLeft:.2f}")
    
    print(f"\nrateShare (Mbps):")
    mean_rateShare = sum(rateShare_mbps)/len(rateShare_mbps)
    print(f"  min={min(rateShare_mbps):.2f}, max={max(rateShare_mbps):.2f}, "
          f"mean={mean_rateShare:.2f}")
    
    print(f"\ntargetBitrateH (Mbps):")
    mean_target = sum(targetBitrateH_mbps)/len(targetBitrateH_mbps)
    print(f"  min={min(targetBitrateH_mbps):.2f}, max={max(targetBitrateH_mbps):.2f}, "
          f"mean={mean_target:.2f}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nError: Please provide a test results directory path.")
        sys.exit(1)
    
    directory = sys.argv[1]
    
    if not Path(directory).exists():
        print(f"Error: Directory '{directory}' not found.")
        sys.exit(1)
    
    if not Path(directory).is_dir():
        print(f"Error: '{directory}' is not a directory.")
        sys.exit(1)
    
    print(f"Parsing logs from directory: {directory}\n")
    all_data = parse_all_logs(directory)
    
    if all_data:
        plot_histograms(all_data)
        print("\nHistograms displayed. Close the plot windows to exit.")


if __name__ == '__main__':
    main()
