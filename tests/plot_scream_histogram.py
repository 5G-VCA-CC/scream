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
        r'summary\s+[\d.]+\s+Transmit rate\s*=\s*(?P<rate>[\d.]+)kbps,\s*'
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
        'packetLossRate': []  # in %
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
                    print(f"Warning: Skipping corrupted line in {logfile}: {e}")
                    continue
            
            # Check for frame size
            frame_match = frame_size_pattern.search(line)
            if frame_match:
                data['frameSize'].append(int(frame_match.group('size')))
            
            # Check for statistics summary
            stats_match = stats_pattern.search(line)
            if stats_match:
                try:
                    # Convert kbps to Mbps
                    rate_kbps = float(stats_match.group('rate'))
                    data['transmitRate'].append(rate_kbps / 1000.0)
                    
                    # PLR is already in percentage
                    data['packetLossRate'].append(float(stats_match.group('plr')))
                except ValueError as e:
                    print(f"Warning: Skipping corrupted statistics line in {logfile}: {e}")
                    continue
    
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
        'queueDelay': [],
        'bytesInFlight': [],
        'rateLeft': [],
        'rateShare': [],
        'targetBitrateH': [],
        'frameSize': [],
        'transmitRate': [],
        'packetLossRate': []
    }
    
    for logfile in sorted(log_files):
        data = parse_scream_log(logfile)
        for key in all_data.keys():
            all_data[key].extend(data[key])
    
    print(f"\nTotal samples collected: {len(all_data['cwnd'])}")
    return all_data


def plot_histograms(data):
    """Create four histogram plots."""
    
    if not data or not data['cwnd']:
        print("No data to plot.")
        return
    
    # Histogram 1: CWND
    fig1, ax1 = plt.subplots(figsize=(12, 6))
    ax1.hist(data['cwnd'], bins=50, color='blue', alpha=0.7, edgecolor='black')
    ax1.set_xlabel('CWND (bytes)', fontsize=12)
    ax1.set_ylabel('Frequency', fontsize=12)
    ax1.set_title('SCReAM Congestion Window Distribution (BW Tool)', fontsize=14, fontweight='bold')
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
    ax2.set_title('SCReAM Smoothed Round-Trip Time Distribution (BW Tool)', fontsize=14, fontweight='bold')
    ax2.grid(True, alpha=0.3, axis='y')
    mean_srtt = sum(srtt_ms)/len(srtt_ms)
    ax2.axvline(mean_srtt, color='red', linestyle='--', 
                linewidth=2, label=f"Mean: {mean_srtt:.2f} ms")
    ax2.legend(fontsize=10)
    fig2.tight_layout()
    
    # Histogram 3: Queue Delay
    fig3, ax3 = plt.subplots(figsize=(12, 6))
    queueDelay_ms = [q * 1000 for q in data['queueDelay']]  # Convert to ms
    ax3.hist(queueDelay_ms, bins=50, color='purple', alpha=0.7, edgecolor='black')
    ax3.set_xlabel('Queue Delay (ms)', fontsize=12)
    ax3.set_ylabel('Frequency', fontsize=12)
    ax3.set_title('SCReAM Queue Delay Distribution (BW Tool)', fontsize=14, fontweight='bold')
    ax3.grid(True, alpha=0.3, axis='y')
    mean_qd = sum(queueDelay_ms)/len(queueDelay_ms)
    ax3.axvline(mean_qd, color='red', linestyle='--', 
                linewidth=2, label=f"Mean: {mean_qd:.2f} ms")
    ax3.legend(fontsize=10)
    fig3.tight_layout()
    
    # Histogram 4: Bytes in Flight
    fig4, ax4 = plt.subplots(figsize=(12, 6))
    bytesInFlight_kb = [b / 1024 for b in data['bytesInFlight']]  # Convert to KB
    ax4.hist(bytesInFlight_kb, bins=50, color='cyan', alpha=0.7, edgecolor='black')
    ax4.set_xlabel('Bytes in Flight (KB)', fontsize=12)
    ax4.set_ylabel('Frequency', fontsize=12)
    ax4.set_title('SCReAM Bytes in Flight Distribution (BW Tool)', fontsize=14, fontweight='bold')
    ax4.grid(True, alpha=0.3, axis='y')
    mean_bif = sum(bytesInFlight_kb)/len(bytesInFlight_kb)
    ax4.axvline(mean_bif, color='red', linestyle='--', 
                linewidth=2, label=f"Mean: {mean_bif:.2f} KB")
    ax4.legend(fontsize=10)
    fig4.tight_layout()
    
    # Histogram 5: Rate parameters (all three on same plot)
    fig5, ax5 = plt.subplots(figsize=(12, 6))
    rateLeft_mbps = [r / 1e6 for r in data['rateLeft']]
    rateShare_mbps = [r / 1e6 for r in data['rateShare']]
    targetBitrateH_mbps = [t / 1e6 for t in data['targetBitrateH']]
    
    # Create overlaid histograms with different colors
    ax5.hist(rateLeft_mbps, bins=50, alpha=0.5, label='rateLeft', color='red', edgecolor='black')
    ax5.hist(rateShare_mbps, bins=50, alpha=0.5, label='rateShare', color='blue', edgecolor='black')
    ax5.hist(targetBitrateH_mbps, bins=50, alpha=0.5, label='targetBitrateH', color='magenta', edgecolor='black')
    
    ax5.set_xlabel('Bitrate (Mbps)', fontsize=12)
    ax5.set_ylabel('Frequency', fontsize=12)
    ax5.set_title('SCReAM Rate Allocation Distribution (BW Tool)', fontsize=14, fontweight='bold')
    ax5.grid(True, alpha=0.3, axis='y')
    ax5.legend(fontsize=10, loc='best')
    fig5.tight_layout()
    
    # Histogram 6: Frame sizes
    if data['frameSize']:
        fig6, ax6 = plt.subplots(figsize=(12, 6))
        frame_size_kb = [f / 1024 for f in data['frameSize']]  # Convert to KB
        ax6.hist(frame_size_kb, bins=50, color='orange', alpha=0.7, edgecolor='black')
        ax6.set_xlabel('Frame Size (KB)', fontsize=12)
        ax6.set_ylabel('Frequency', fontsize=12)
        ax6.set_title('Encoded Frame Size Distribution (BW Tool)', fontsize=14, fontweight='bold')
        ax6.grid(True, alpha=0.3, axis='y')
        mean_frame_kb = sum(frame_size_kb)/len(frame_size_kb)
        ax6.axvline(mean_frame_kb, color='red', linestyle='--', 
                    linewidth=2, label=f"Mean: {mean_frame_kb:.2f} KB")
        ax6.legend(fontsize=10)
        fig6.tight_layout()
    
    # Histogram 7: Transmit Rate
    if data['transmitRate']:
        fig7, ax7 = plt.subplots(figsize=(12, 6))
        ax7.hist(data['transmitRate'], bins=50, color='purple', alpha=0.7, edgecolor='black')
        ax7.set_xlabel('Transmit Rate (Mbps)', fontsize=12)
        ax7.set_ylabel('Frequency', fontsize=12)
        ax7.set_title('Transmit Rate Distribution (BW Tool)', fontsize=14, fontweight='bold')
        ax7.grid(True, alpha=0.3, axis='y')
        mean_txrate = sum(data['transmitRate'])/len(data['transmitRate'])
        ax7.axvline(mean_txrate, color='red', linestyle='--', 
                    linewidth=2, label=f"Mean: {mean_txrate:.2f} Mbps")
        ax7.legend(fontsize=10)
        fig7.tight_layout()
    
    # Histogram 8: Packet Loss Rate
    if data['packetLossRate']:
        fig8, ax8 = plt.subplots(figsize=(12, 6))
        ax8.hist(data['packetLossRate'], bins=50, color='red', alpha=0.7, edgecolor='black')
        ax8.set_xlabel('Packet Loss Rate (%)', fontsize=12)
        ax8.set_ylabel('Frequency', fontsize=12)
        ax8.set_title('Packet Loss Rate Distribution (BW Tool)', fontsize=14, fontweight='bold')
        ax8.grid(True, alpha=0.3, axis='y')
        mean_plr = sum(data['packetLossRate'])/len(data['packetLossRate'])
        ax8.axvline(mean_plr, color='darkred', linestyle='--', 
                    linewidth=2, label=f"Mean: {mean_plr:.2f}%")
        ax8.legend(fontsize=10)
        fig8.tight_layout()
    
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
    
    print(f"\nQueue Delay (ms):")
    print(f"  min={min(queueDelay_ms):.2f}, max={max(queueDelay_ms):.2f}, "
          f"mean={mean_qd:.2f}, "
          f"median={sorted(queueDelay_ms)[len(queueDelay_ms)//2]:.2f}")
    
    print(f"\nBytes in Flight (KB):")
    print(f"  min={min(bytesInFlight_kb):.2f}, max={max(bytesInFlight_kb):.2f}, "
          f"mean={mean_bif:.2f}, "
          f"median={sorted(bytesInFlight_kb)[len(bytesInFlight_kb)//2]:.2f}")
    
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
    
    if data['frameSize']:
        print(f"\nFrame sizes: {len(data['frameSize'])} frames")
        print(f"  min={min(data['frameSize'])} bytes, max={max(data['frameSize'])} bytes, "
              f"mean={sum(data['frameSize'])/len(data['frameSize']):.1f} bytes")
        frame_size_kb = [f / 1024 for f in data['frameSize']]
        print(f"  min={min(frame_size_kb):.2f} KB, max={max(frame_size_kb):.2f} KB, "
              f"mean={sum(frame_size_kb)/len(frame_size_kb):.2f} KB")
    
    if data['transmitRate']:
        print(f"\nTransmit Rate: {len(data['transmitRate'])} samples")
        print(f"  min={min(data['transmitRate']):.2f} Mbps, max={max(data['transmitRate']):.2f} Mbps, "
              f"mean={sum(data['transmitRate'])/len(data['transmitRate']):.2f} Mbps")
    
    if data['packetLossRate']:
        print(f"\nPacket Loss Rate: {len(data['packetLossRate'])} samples")
        print(f"  min={min(data['packetLossRate']):.2f}%, max={max(data['packetLossRate']):.2f}%, "
              f"mean={sum(data['packetLossRate'])/len(data['packetLossRate']):.2f}%")


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
