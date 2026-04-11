import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
from Demand import ODConstants


def plot_metrics(df):
    fig, axs = plt.subplots(4, 2, figsize=(12, 12))
    x = df["iteration"] if "iteration" in df.columns else range(len(df))

    def plot_pair(ax, bike_col, car_col, title, transform=None):
        if transform is None:
            transform = lambda s: s

        if bike_col in df.columns:
            ax.plot(x, transform(df[bike_col]), label="Bike", color="tab:green", linewidth=2)
        if car_col in df.columns:
            ax.plot(
                x,
                transform(df[car_col]),
                label="Car",
                color="tab:orange",
                linewidth=2,
                linestyle="--",
            )

        if bike_col in df.columns and car_col in df.columns:
            ax.legend()
        ax.set_title(title)
        ax.grid(alpha=0.3)

    plot_pair(
        axs[0, 0],
        bike_col="protected_num_components",
        car_col="",
        title="Network Fragmentation",
    )

    plot_pair(
        axs[0, 1],
        bike_col="protected_lcc_length",
        car_col="car_lcc_length",
        title="Largest Connected Component (km)",
        transform=lambda s: s / 1000,
    )

    plot_pair(
        axs[1, 0],
        bike_col="mean_edge_betweenness",
        car_col="car_mean_edge_betweenness",
        title="Edge Betweenness",
    )

    plot_pair(
        axs[1, 1],
        bike_col="protected_mean_node_closeness",
        car_col="car_mean_node_closeness",
        title="Node Closeness",
    )

    plot_pair(
        axs[2, 0],
        bike_col="full_od_directness_mean",
        car_col="car_mean_directness",
        title="Directness",
    )

    plot_pair(
        axs[2, 1],
        bike_col="protected_coverage_area_km2",
        car_col="car_coverage_area_km2",
        title="Coverage (km^2)",
    )

    plot_pair(
        axs[3, 0],
        bike_col="full_od_total_bike_cost",
        car_col="car_od_total_car_cost",
        title="od total cost by type",
    )

    plot_pair(
        axs[3, 1],
        bike_col="bike_gain_vs_baseline",
        car_col="car_harm_vs_baseline",
        title="vs baseline",
    )

    fig.tight_layout()
    plt.show()


def plot_od_investigation(df_sweep, random_avg_length, random_abs_error, best_beta, best_avg_m, title=""):
    fig, ax1 = plt.subplots(figsize=(10, 6))

    # --- Primary Y-Axis: Absolute Error ---
    color_err = 'tab:red'
    ax1.set_xlabel('Beta Value (Log Scale)', fontsize=12)
    ax1.set_ylabel('Abs Avg Distance Error (m)', color=color_err, fontsize=12)
    ax1.plot(df_sweep['beta'], df_sweep['abs_avg_m_error'], marker='o', color=color_err, label='Abs Error')
    ax1.axhline(y=random_abs_error, color=color_err, linestyle=':', alpha=0.5, label='Random Baseline Error')
    ax1.tick_params(axis='y', labelcolor=color_err)

    # --- Secondary Y-Axis: Avg Length ---
    ax2 = ax1.twinx()
    color_len = 'tab:blue'
    ax2.set_ylabel('Avg Path Length (m)', color=color_len, fontsize=12)
    ax2.plot(df_sweep['beta'], df_sweep['avg_length'], marker='s', color=color_len, label='Avg Length', alpha=0.7)
    ax2.axhline(y=random_avg_length, color=color_len, linestyle=':', alpha=0.5, label='Random Baseline Length')
    ax2.axhline(y=ODConstants.TARGET_AVG_DISTANCE, color='green', linestyle='-', alpha=0.4, label='Target Avg Distance')
    ax2.tick_params(axis='y', labelcolor=color_len)

    # --- Optimal Beta ---
    best_error = df_sweep.loc[df_sweep['beta'] == best_beta, 'abs_avg_m_error'].values[0]
    plt.axvline(x=best_beta, color='green', linestyle='--', linewidth=2, label=f'Optimal Beta ({best_beta:.2e})')
    ax1.plot(best_beta, best_error, 'ko', markersize=10, fillstyle='none')
    ax2.plot(best_beta, best_avg_m, 'ks', markersize=10, fillstyle='none')

    ax1.annotate(f'Avg Length: {best_avg_m/1000:.2f}km\nError: {best_error:.0f}m',
                 xy=(best_beta, best_error),
                 xytext=(best_beta * 1.5, best_error * 1.1),
                 arrowprops=dict(arrowstyle='->', color='black'),
                 fontweight='bold', color='green')

    plt.title(title or "Beta Sweep: Distance Error vs Avg Path Length", fontsize=14)
    ax1.set_xscale('log')

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper center', bbox_to_anchor=(0.5, -0.15), ncol=3)
    plt.tight_layout()
    plt.show()

def plot_od_matrix_error(error, title=None):
    plt.figure(figsize=(6,5))
    sns.heatmap(error, annot=True, cmap="coolwarm", center=0)
    if title:
        plt.title(title)
    plt.show()

