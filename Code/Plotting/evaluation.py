import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt


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
        bike_col="num_components",
        car_col="car_num_components",
        title="Network Fragmentation",
    )

    plot_pair(
        axs[0, 1],
        bike_col="lcc_length",
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
        bike_col="mean_node_closeness",
        car_col="car_mean_node_closeness",
        title="Node Closeness",
    )

    plot_pair(
        axs[2, 0],
        bike_col="mean_directness",
        car_col="car_mean_directness",
        title="Directness",
    )

    plot_pair(
        axs[2, 1],
        bike_col="coverage_area_km2",
        car_col="car_coverage_area_km2",
        title="Coverage (km^2)",
    )

    plot_pair(
        axs[3, 0],
        bike_col="bike_od_total_cost",
        car_col="car_od_total_cost",
        title="od total cost by type",
    )

    fig.tight_layout()
    plt.show()


def plot_od_investigation(df_sweep, random_rmse, avg_random_lengths_km, best_beta, best_len, best_rmse, title ="" ):
    fig, ax1 = plt.subplots(figsize=(10, 6))

    # --- Primary Y-Axis: RMSE ---
    color_rmse = 'tab:red'
    ax1.set_xlabel('Beta Value (Log Scale)', fontsize=12)
    ax1.set_ylim(0.05, 0.2)
    ax1.set_ylabel('RMSE (Error)', color=color_rmse, fontsize=12)
    line1 = ax1.plot(df_sweep['beta'], df_sweep['rmse'], marker='o', color=color_rmse, label='Model RMSE')
    ax1.tick_params(axis='y', labelcolor=color_rmse)

    # RMSE Baseline
    ax1.axhline(y=random_rmse, color=color_rmse, linestyle=':', alpha=0.5, label='Random RMSE Baseline')

    # --- Secondary Y-Axis: Path Length ---
    ax2 = ax1.twinx()
    color_len = 'tab:blue'
    ax2.set_ylabel('Avg Path Length (km)', color=color_len, fontsize=12)
    line2 = ax2.plot(df_sweep['beta'], df_sweep['avg_length'], marker='s', color=color_len, label='Model Avg Length')
    ax2.tick_params(axis='y', labelcolor=color_len)

    # Distance Baseline (Note: using the scalar average)
    ax2.axhline(y=avg_random_lengths_km, color=color_len, linestyle=':', alpha=0.5, label='Random Distance Baseline')

    # --- Target Value Indicators ---
    # Vertical line showing the "Sweet Spot"
    plt.axvline(x=best_beta, color='green', linestyle='--', linewidth=2, label=f'Optimal Beta ({best_beta:.2e})')

    # Highlight the specific points on the lines
    ax1.plot(best_beta, best_rmse, 'ko', markersize=10, fillstyle='none') # Circle on RMSE
    ax2.plot(best_beta, best_len, 'ks', markersize=10, fillstyle='none')  # Square on Length

    # Text annotation
    ax1.annotate(f'Avg Length: {best_len:.2f}km', 
                xy=(best_beta, best_rmse), 
                xytext=(best_beta * 1.5, best_rmse + 0.01),
                arrowprops=dict(arrowstyle='->', color='black'),
                fontweight='bold', color='green')

    # --- Final Touches ---
    plt.title("Beta Parameter Sweep: Finding the Optimal Fit for Malta", fontsize=14)
    ax1.set_xscale('log')

    # Combine legends from both axes
    lines, labels = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines + lines2, labels + labels2, loc='upper center', bbox_to_anchor=(0.5, -0.15), ncol=2)

    plt.tight_layout()
    plt.show()


def plot_od_matrix_error(error, title=None):
    plt.figure(figsize=(6,5))
    sns.heatmap(error, annot=True, cmap="coolwarm", center=0)
    if title:
        plt.title(title)
    plt.show()

