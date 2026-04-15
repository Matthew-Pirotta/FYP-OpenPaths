import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
from Demand import ODConstants
import matplotlib.ticker as mticker

def plot_metrics(df):
    x = df["iteration"] if "iteration" in df.columns else range(len(df))

    # ── helpers ──────────────────────────────────────────────────────────────

    def _plot_single(ax, col, label, color, linestyle="-", transform=None):
        if col not in df.columns:
            return
        data = df[col] if transform is None else transform(df[col])
        ax.plot(x, data, label=label, color=color, linewidth=2, linestyle=linestyle)

    def _shared_axis(ax, bike_col, car_col, title, transform=None):
        """Same axis – comparable scales (e.g. num_components, directness)."""
        _plot_single(ax, bike_col, "Bike", "tab:green", transform=transform)
        _plot_single(ax, car_col, "Car", "tab:orange", linestyle="--", transform=transform)
        if bike_col in df.columns or car_col in df.columns:
            ax.legend(fontsize=8)
        ax.set_title(title)
        ax.grid(alpha=0.3)

    def _dual_axis(ax, bike_col, car_col, title, transform=None):
        """Twin y-axes for very different scales (e.g. LCC length, coverage)."""
        t = transform or (lambda s: s)
        ax.set_title(title)
        ax.grid(alpha=0.3)
        lines = []
        if bike_col in df.columns:
            l1, = ax.plot(x, t(df[bike_col]), color="tab:green", linewidth=2, label="Bike")
            ax.set_ylabel("Bike", color="tab:green", fontsize=8)
            ax.tick_params(axis="y", labelcolor="tab:green", labelsize=7)
            lines.append(l1)
        if car_col in df.columns:
            ax2 = ax.twinx()
            l2, = ax2.plot(x, t(df[car_col]), color="tab:orange", linewidth=2, linestyle="--", label="Car")
            ax2.set_ylabel("Car", color="tab:orange", fontsize=8)
            ax2.tick_params(axis="y", labelcolor="tab:orange", labelsize=7)
            lines.append(l2)
        if lines:
            ax.legend(lines, [l.get_label() for l in lines], fontsize=8)

    # ── Figure 1: Structural ─────────────────────────────────────────────────
    fig1, axs1 = plt.subplots(2, 2, figsize=(12, 8))
    fig1.suptitle("Structural metrics", fontsize=13, fontweight="bold")

    _shared_axis(axs1[0, 0],
        bike_col="protected_num_components", car_col="",
        title="Connected components (bike protected)")

    _dual_axis(axs1[0, 1],
        bike_col="protected_lcc_length", car_col="car_lcc_length",
        title="LCC length (km)",
        transform=lambda s: s / 1000)

    _dual_axis(axs1[1, 0],
        bike_col="protected_coverage_area_km2", car_col="car_coverage_area_km2",
        title="Coverage area (km^2)")

    _shared_axis(axs1[1, 1],
        bike_col="protected_mean_node_closeness", car_col="car_mean_node_closeness",
        title="Mean node closeness")

    fig1.tight_layout()

    # ── Figure 2: OD / Travel Cost ───────────────────────────────────────────
    fig2, axs2 = plt.subplots(2, 2, figsize=(12, 8))
    fig2.suptitle("OD / travel-cost metrics", fontsize=13, fontweight="bold")

    _dual_axis(axs2[0, 0],
        bike_col="full_od_total_bike_cost", car_col="car_od_total_car_cost",
        title="Total OD cost")

    _dual_axis(axs2[0, 1],
        bike_col="full_od_mean_bike_cost", car_col="car_od_mean_car_cost",
        title="Mean OD cost")

    _shared_axis(axs2[1, 0],
        bike_col="full_od_bike_cost_covered_demand", car_col="car_od_car_cost_covered_demand",
        title="Covered demand")

    _shared_axis(axs2[1, 1],
        bike_col="full_od_bike_cost_missing_demand", car_col="",
        title="Missing demand (bike)")

    fig2.tight_layout()

    # ── Figure 3: Performance / Comparative ─────────────────────────────────
    fig3, axs3 = plt.subplots(1, 3, figsize=(15, 4))
    fig3.suptitle("Comparative metrics", fontsize=13, fontweight="bold")

    _shared_axis(axs3[0],
        bike_col="full_od_directness_mean", car_col="",
        title="OD directness (bike vs drive)")

    _shared_axis(axs3[1],
        bike_col="mean_edge_betweenness", car_col="car_mean_edge_betweenness",
        title="Mean edge betweenness")

    _shared_axis(axs3[2],
        bike_col="bike_gain_vs_baseline", car_col="car_harm_vs_baseline",
        title="delta vs baseline")

    fig3.tight_layout()
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

