import argparse
import os
import sys

try:
    import pandas as pd
    import matplotlib
    matplotlib.use('Agg')  
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
    import numpy as np
except ImportError as e:
    print(f"[ERROR] Missing dependency: {e}")
    print("Install with: pip3 install pandas matplotlib numpy")
    sys.exit(1)


def parse_args():
    parser = argparse.ArgumentParser(
        description='Generate performance plots from benchmark results')
    parser.add_argument('--input', required=True,
                        help='Path to benchmark_results.csv')
    parser.add_argument('--output-dir', required=True,
                        help='Directory to save plot images')
    return parser.parse_args()


def setup_style():
    """Configure matplotlib for publication-quality plots."""
    plt.style.use('seaborn-v0_8-darkgrid')
    plt.rcParams.update({
        'figure.figsize': (10, 7),
        'figure.dpi': 150,
        'font.family': 'sans-serif',
        'font.size': 12,
        'axes.titlesize': 16,
        'axes.titleweight': 'bold',
        'axes.labelsize': 13,
        'legend.fontsize': 11,
        'lines.linewidth': 2.5,
        'lines.markersize': 8,
    })


def format_size(size_bytes):
    """Convert bytes to human-readable string."""
    if size_bytes >= 1024 * 1024 * 1024:
        return f"{size_bytes / (1024**3):.1f} GB"
    elif size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024**2):.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


def plot_execution_time(df_grouped, output_dir):
    """Plot 1: Execution time vs. number of processes."""
    fig, ax = plt.subplots()

    colors = ['#2196F3', '#4CAF50', '#FF9800', '#E91E63', '#9C27B0']
    markers = ['o', 's', '^', 'D', 'v']

    for idx, (fsize, group) in enumerate(df_grouped):
        color = colors[idx % len(colors)]
        marker = markers[idx % len(markers)]
        label = format_size(fsize)

        ax.errorbar(group['num_procs'], group['mean_time'],
                     yerr=group['std_time'],
                     label=label, color=color, marker=marker,
                     capsize=5, capthick=1.5, elinewidth=1.5,
                     markeredgecolor='white', markeredgewidth=1)

    ax.set_xlabel('Number of MPI Processes')
    ax.set_ylabel('Execution Time (seconds)')
    ax.set_title('Execution Time vs. Process Count')
    ax.legend(title='File Size', framealpha=0.9)
    ax.set_xticks(sorted(df_grouped.obj['num_procs'].unique()))

    plt.tight_layout()
    path = os.path.join(output_dir, 'execution_time.png')
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved {path}")


def plot_speedup(df_grouped, output_dir):
    """Plot 2: Speedup relative to minimum process count."""
    fig, ax = plt.subplots()

    colors = ['#2196F3', '#4CAF50', '#FF9800', '#E91E63', '#9C27B0']
    markers = ['o', 's', '^', 'D', 'v']

    all_procs = sorted(df_grouped.obj['num_procs'].unique())
    min_procs = all_procs[0]

    for idx, (fsize, group) in enumerate(df_grouped):
        color = colors[idx % len(colors)]
        marker = markers[idx % len(markers)]
        label = format_size(fsize)

        baseline = group.loc[group['num_procs'] == min_procs, 'mean_time']
        if baseline.empty:
            continue
        baseline_time = baseline.values[0]

        speedup = baseline_time / group['mean_time']
        ax.plot(group['num_procs'], speedup,
                label=label, color=color, marker=marker,
                markeredgecolor='white', markeredgewidth=1)

    # Ideal speedup line (relative to min_procs)
    ax.plot(all_procs, [p / min_procs for p in all_procs],
            '--', color='gray', alpha=0.6, label='Ideal (linear)')

    ax.set_xlabel('Number of MPI Processes')
    ax.set_ylabel(f'Speedup (relative to {min_procs} processes)')
    ax.set_title('Parallel Speedup')
    ax.legend(title='File Size', framealpha=0.9)
    ax.set_xticks(all_procs)

    plt.tight_layout()
    path = os.path.join(output_dir, 'speedup.png')
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved {path}")





def main():
    args = parse_args()
    os.makedirs(args.output_dir, exist_ok=True)
    setup_style()

    # Read CSV
    df = pd.read_csv(args.input)

    # Filter out failed runs
    df = df[df['elapsed_time_sec'] > 0]

    if df.empty:
        print("[WARN] No valid data in benchmark results. Skipping plots.")
        return

    # Compute mean and standard deviation per (num_procs, file_size_bytes)
    summary = df.groupby(['file_size_bytes', 'num_procs']).agg(
        mean_time=('elapsed_time_sec', 'mean'),
        std_time=('elapsed_time_sec', 'std'),
        mean_matches=('total_matches', 'mean'),
    ).reset_index()

    summary['std_time'] = summary['std_time'].fillna(0)

    grouped = summary.groupby('file_size_bytes')

    print("Generating plots...")
    plot_execution_time(grouped, args.output_dir)
    plot_speedup(grouped, args.output_dir)
    print("Plot generation complete.")


if __name__ == '__main__':
    main()
