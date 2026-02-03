import re
import matplotlib.pyplot as plt
import argparse
from collections import defaultdict

def parse_stats_file(filename):
    """Parse the stats file and extract all metrics."""
    
    stats = defaultdict(list)
    
    # Regex patterns for each metric
    patterns = {
        'elapsed_time': r'RECEIVER STATS \(last ([\d.]+)s\)',
        'datagrams_received': r'Datagrams received:\s*([\d.]+)',
        'bytes_received': r'Bytes received:\s*([\d.]+)',
        'receive_rate_mbps': r'Receive rate:\s*([\d.]+)',
        'frames_completed': r'Frames completed:\s*([\d.]+)',
        'frames_rendered': r'Total frames rendered:\s*([\d.]+)',
        'freeze_count': r'Freeze count:\s*([\d.]+)',
        'freeze_duration': r'total freeze duration:\s*([\d.]+)',
        'inter_frame_delay': r'Total Inter-Frame Delay:\s*([\d.]+)',
        'inter_frame_delay_difference': r'Inter-Frame Delay difference:\s*([\d.]+)',
    }
    
    with open(filename, 'r') as f:
        content = f.read()
    
    # Split by stats blocks
    blocks = content.split('=== RECEIVER STATS')
    
    for block in blocks[1:]:  # Skip first empty split
        for key, pattern in patterns.items():
            match = re.search(pattern, block)
            if match:
                stats[key].append(float(match.group(1)))
    
    # Create time axis (assuming 1s intervals)
    stats['time'] = list(range(1, len(stats['datagrams_received']) + 1))
    
    return stats


def plot_stats(stats, output_prefix='stats'):
    """Create separate plots for each group of metrics."""
    
    time = stats['time']
    
    # Set up the style
    plt.style.use('seaborn-v0_8-darkgrid' if 'seaborn-v0_8-darkgrid' in plt.style.available else 'ggplot')
    
    # Plot 1: Datagrams received, Bytes received
    fig1, ax1 = plt.subplots(figsize=(10, 6))
    ax2 = ax1.twinx()
    
    line1, = ax1.plot(time, stats['datagrams_received'], 'b-', label='Datagrams Received', linewidth=2)
    line2, = ax2.plot(time, stats['bytes_received'], 'r-', label='Bytes Received', linewidth=2)
    
    ax1.set_xlabel('Time (s)', fontsize=12)
    ax1.set_ylabel('Datagrams Received', color='b', fontsize=12)
    ax2.set_ylabel('Bytes Received', color='r', fontsize=12)
    ax1.tick_params(axis='y', labelcolor='b')
    ax2.tick_params(axis='y', labelcolor='r')
    
    lines = [line1, line2]
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc='upper left')
    plt.title('Datagrams and Bytes Received Over Time', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{output_prefix}_datagrams_bytes.png', dpi=150)
    plt.close()
    
    # Plot 2: Receive Rate (Mbps)
    fig2, ax = plt.subplots(figsize=(10, 6))
    ax.plot(time, stats['receive_rate_mbps'], 'g-', linewidth=2, marker='o', markersize=4)
    ax.set_xlabel('Time (s)', fontsize=12)
    ax.set_ylabel('Receive Rate (Mbps)', fontsize=12)
    ax.set_title('Receive Rate Over Time', fontsize=14)
    ax.fill_between(time, stats['receive_rate_mbps'], alpha=0.3, color='g')
    plt.tight_layout()
    plt.savefig(f'{output_prefix}_receive_rate.png', dpi=150)
    plt.close()
    
    # Plot 3: Freeze Count, Total Freeze Duration
    fig4, ax1 = plt.subplots(figsize=(10, 6))
    ax2 = ax1.twinx()
    
    line1, = ax1.plot(time, stats['freeze_count'], 'b-', label='Freeze Count', linewidth=2, marker='o', markersize=4)
    line2, = ax2.plot(time, stats['freeze_duration'], 'r-', label='Total Freeze Duration (s)', linewidth=2, marker='.', markersize=4)
    
    ax1.set_xlabel('Time (s)', fontsize=12)
    ax1.set_ylabel('Freeze Count', color='b', fontsize=12)
    ax2.set_ylabel('Total Freeze Duration (s)', color='r', fontsize=12)
    ax1.tick_params(axis='y', labelcolor='b')
    ax2.tick_params(axis='y', labelcolor='r')
    
    lines = [line1, line2]
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc='upper left')
    plt.title('Freeze Statistics Over Time', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{output_prefix}_freezes.png', dpi=150)
    plt.close()
    
    # Plot 4: Inter-Frame Delay and difference
    fig5, ax1 = plt.subplots(figsize=(10, 6))
    ax2 = ax1.twinx()
    
    line1, = ax1.plot(time, stats['frames_completed'], 'b-', label='Frames Completed', linewidth=2, marker='o', markersize=4)
    line2, = ax2.plot(time, stats['inter_frame_delay_difference'], 'r-', label='Inter-Frame Delay difference (s)', linewidth=2, marker='.', markersize=4)
    
    ax1.set_xlabel('Time (s)', fontsize=12)
    ax1.set_ylabel('Frames', color='b', fontsize=12)
    ax2.set_ylabel('Inter-Frame Delay difference (s)', color='r', fontsize=12)
    ax1.tick_params(axis='y', labelcolor='b')
    ax2.tick_params(axis='y', labelcolor='r')
    
    lines = [line1, line2]
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc='upper left')
    plt.title('Inter-Frame Delay Statistics Over Time', fontsize=14)
    plt.tight_layout()
    plt.savefig(f'{output_prefix}_interframe_delay.png', dpi=150)
    plt.close()
    
    print(f"Time-series plots saved with prefix '{output_prefix}_*.png'")


def plot_histograms(stats, output_prefix='stats'):
    """Create histogram plots for key metrics."""
    
    plt.style.use('seaborn-v0_8-darkgrid' if 'seaborn-v0_8-darkgrid' in plt.style.available else 'ggplot')
    
    def plot_single_hist(data, title, xlabel, color, filename):
        if not data:
            return
            
        fig, ax = plt.subplots(figsize=(10, 6))
        
        # Calculate mean for the vertical line
        mean_val = sum(data) / len(data)
        
        # Create histogram
        n, bins, patches = ax.hist(data, bins=30, color=color, alpha=0.7, edgecolor='black', linewidth=0.5)
        
        # Add mean line
        ax.axvline(mean_val, color='k', linestyle='dashed', linewidth=1.5, label=f'Mean: {mean_val:.2f}')
        
        ax.set_title(title, fontsize=14)
        ax.set_xlabel(xlabel, fontsize=12)
        ax.set_ylabel('Frequency', fontsize=12)
        ax.legend()
        
        plt.tight_layout()
        plt.xlim(0, 15)
        plt.savefig(filename, dpi=150)
        plt.close()

    # 1. Receive Rate Histogram
    plot_single_hist(
        stats['receive_rate_mbps'],
        'Distribution of Receive Rate',
        'Receive Rate (Mbps)',
        'green',
        f'{output_prefix}_hist_receive_rate.png'
    )

    # 2. Freeze Duration Histogram
    plot_single_hist(
        stats['freeze_duration'],
        'Distribution of Freeze Duration per Interval',
        'Freeze Duration (s)',
        'red',
        f'{output_prefix}_hist_freeze_duration.png'
    )

    # 3. Inter-Frame difference Histogram
    plot_single_hist(
        stats['inter_frame_delay_difference'],
        'Distribution of Inter-Frame Delay difference',
        'difference (s)',
        'purple',
        f'{output_prefix}_hist_difference.png'
    )
    
    print(f"Histogram plots saved with prefix '{output_prefix}_hist_*.png'")


def plot_all_in_one(stats, output_filename='stats_combined.png'):
    """Create a single figure with all plots as subplots."""
    
    time = stats['time']
    
    fig, axes = plt.subplots(3, 2, figsize=(14, 12))
    fig.suptitle('Receiver Statistics Over Time', fontsize=16, fontweight='bold')
    
    # Plot 1: Datagrams and Bytes (top-left)
    ax1 = axes[0, 0]
    ax1_twin = ax1.twinx()
    ax1.plot(time, stats['datagrams_received'], 'b-', label='Datagrams', linewidth=2)
    ax1_twin.plot(time, stats['bytes_received'], 'r-', label='Bytes', linewidth=2)
    ax1.set_ylabel('Datagrams', color='b')
    ax1_twin.set_ylabel('Bytes', color='r')
    ax1.set_title('Datagrams & Bytes Received')
    ax1.legend(loc='upper left')
    
    # Plot 2: Receive Rate (top-right)
    ax2 = axes[0, 1]
    ax2.plot(time, stats['receive_rate_mbps'], 'g-', linewidth=2)
    ax2.fill_between(time, stats['receive_rate_mbps'], alpha=0.3, color='g')
    ax2.set_ylabel('Mbps')
    ax2.set_title('Receive Rate')
    
    # Plot 3: Freezes (middle-right)
    ax4 = axes[1, 1]
    ax4_twin = ax4.twinx()
    ax4.plot(time, stats['freeze_count'], 'b-', label='Count', linewidth=2)
    ax4_twin.plot(time, stats['freeze_duration'], 'r-', label='Duration', linewidth=2)
    ax4.set_ylabel('Freeze Count', color='b')
    ax4_twin.set_ylabel('Duration (s)', color='r')
    ax4.set_title('Freeze Statistics')
    
    # Plot 4: Inter-frame delay (bottom-left) *use frames rendered instead, move inter-frame delay to different plot
    ax5 = axes[2, 0]
    ax5_twin = ax5.twinx()
    ax5.plot(time, stats['frames_completed'], 'b-', label='Frames Completed', linewidth=2)
    ax5_twin.plot(time, stats['inter_frame_delay_difference'], 'r-', label='difference', linewidth=2)
    ax5.set_xlabel('Time (s)')
    ax5.set_ylabel('Frames', color='b')
    ax5_twin.set_ylabel('difference (s)', color='r')
    ax5.set_title('Inter-Frame Delay Statistics')
    
    # Hide unused subplot (bottom-right)
    axes[2, 1].axis('off')
    
    plt.tight_layout()
    plt.savefig(output_filename, dpi=150)
    plt.close()
    print(f"Combined plot saved as '{output_filename}'")


def main():
    parser = argparse.ArgumentParser(description='Parse and plot receiver statistics.')
    parser.add_argument('input_file', help='Input .txt file with stats')
    parser.add_argument('-o', '--output', default='stats', help='Output prefix for plot files')
    parser.add_argument('-c', '--combined', action='store_true', help='Also generate combined plot')
    
    args = parser.parse_args()
    
    print(f"Parsing {args.input_file}...")
    stats = parse_stats_file(args.input_file)
    
    print(f"Found {len(stats['time'])} data points")
    
    # Generate time series plots
    plot_stats(stats, args.output)
    
    # Generate histogram plots
    plot_histograms(stats, args.output)
    
    # Generate combined plot if requested
    if args.combined:
        plot_all_in_one(stats, f'{args.output}_combined.png')


if __name__ == '__main__':
    main()