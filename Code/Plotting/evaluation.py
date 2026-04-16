import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from Demand import ODConstants
import matplotlib.ticker as mticker


def plot_metrics(df):
    x = df["iteration"] if "iteration" in df.columns else range(len(df))

    def _pick(*cols):
        for col in cols:
            if col and col in df.columns:
                return col
        return None

    def _plot_if_exists(ax, col, *, label, color, linestyle="-", scale=1.0):
        if col is None:
            return
        ax.plot(x, df[col] * scale, label=label, color=color, linewidth=2, linestyle=linestyle)

    # Figure 1: Main OD performance
    fig1, axs1 = plt.subplots(1, 2, figsize=(12, 4.5))
    fig1.suptitle("Figure 1: Main OD performance", fontsize=13, fontweight="bold")

    directness_col = _pick("main_od_directness_weighted", "full_od_directness_mean")
    _plot_if_exists(axs1[0], directness_col, label="Demand-weighted directness", color="tab:green")
    axs1[0].set_title("Demand-weighted directness")
    axs1[0].set_xlabel("Iteration")
    axs1[0].set_ylabel("Directness (drive/bike)")
    axs1[0].grid(alpha=0.3)
    if directness_col:
        axs1[0].legend(fontsize=8)

    reachable_share_col = _pick("main_od_protected_reachable_share")
    _plot_if_exists(
        axs1[1],
        reachable_share_col,
        label="Protected reachable demand share",
        color="tab:blue",
        scale=100.0,
    )
    axs1[1].set_title("Share of demand reachable on protected network")
    axs1[1].set_xlabel("Iteration")
    axs1[1].set_ylabel("Reachable demand (%)")
    axs1[1].yaxis.set_major_formatter(mticker.PercentFormatter())
    axs1[1].grid(alpha=0.3)
    if reachable_share_col:
        axs1[1].legend(fontsize=8)

    fig1.tight_layout()

    # Figure 2: Bike-car trade-off
    fig2, axs2 = plt.subplots(1, 3, figsize=(16, 4.5))
    fig2.suptitle("Figure 2: Bike-car trade-off", fontsize=13, fontweight="bold")

    bike_gain_col = _pick("bike_gain_vs_baseline")
    car_harm_col = _pick("car_harm_vs_baseline")

    _plot_if_exists(axs2[0], bike_gain_col, label="Bike gain vs baseline", color="tab:green", scale=100.0)
    axs2[0].set_title("Bike gain vs baseline")
    axs2[0].set_xlabel("Iteration")
    axs2[0].set_ylabel("Gain (%)")
    axs2[0].yaxis.set_major_formatter(mticker.PercentFormatter())
    axs2[0].grid(alpha=0.3)
    if bike_gain_col:
        axs2[0].legend(fontsize=8)

    _plot_if_exists(axs2[1], car_harm_col, label="Car harm vs baseline", color="tab:red", scale=100.0)
    axs2[1].set_title("Car harm vs baseline")
    axs2[1].set_xlabel("Iteration")
    axs2[1].set_ylabel("Harm (%)")
    axs2[1].yaxis.set_major_formatter(mticker.PercentFormatter())
    axs2[1].grid(alpha=0.3)
    if car_harm_col:
        axs2[1].legend(fontsize=8)

    axs2[2].set_title("Gain vs harm (scatter)")
    axs2[2].set_xlabel("Bike gain vs baseline (%)")
    axs2[2].set_ylabel("Car harm vs baseline (%)")
    axs2[2].grid(alpha=0.3)
    if bike_gain_col and car_harm_col:
        gain = df[bike_gain_col] * 100.0
        harm = df[car_harm_col] * 100.0
        axs2[2].plot(gain, harm, color="gray", alpha=0.35, linewidth=1)
        sc = axs2[2].scatter(gain, harm, c=np.arange(len(df)), cmap="viridis", s=24)
        cbar = fig2.colorbar(sc, ax=axs2[2])
        cbar.set_label("Iteration index")

    fig2.tight_layout()

    # Figure 3: Structural diagnostics
    fig3, axs3 = plt.subplots(1, 3, figsize=(16, 4.5))
    fig3.suptitle("Figure 3: Structural diagnostics", fontsize=13, fontweight="bold")

    protected_lcc_share_col = _pick("protected_lcc_length_share")
    car_lcc_share_col = _pick("car_lcc_length_share")
    _plot_if_exists(axs3[0], protected_lcc_share_col, label="Protected", color="tab:green", scale=100.0)
    _plot_if_exists(axs3[0], car_lcc_share_col, label="Car", color="tab:orange", linestyle="--", scale=100.0)
    axs3[0].set_title("LCC length share")
    axs3[0].set_xlabel("Iteration")
    axs3[0].set_ylabel("LCC share (%)")
    axs3[0].yaxis.set_major_formatter(mticker.PercentFormatter())
    axs3[0].grid(alpha=0.3)
    if protected_lcc_share_col or car_lcc_share_col:
        axs3[0].legend(fontsize=8)

    protected_cov_col = _pick("protected_coverage_area_km2")
    car_cov_col = _pick("car_coverage_area_km2")
    _plot_if_exists(axs3[1], protected_cov_col, label="Protected", color="tab:green")
    _plot_if_exists(axs3[1], car_cov_col, label="Car", color="tab:orange", linestyle="--")
    axs3[1].set_title("Coverage area")
    axs3[1].set_xlabel("Iteration")
    axs3[1].set_ylabel("Area (km^2)")
    axs3[1].grid(alpha=0.3)
    if protected_cov_col or car_cov_col:
        axs3[1].legend(fontsize=8)

    protected_comp_col = _pick("protected_num_components")
    car_comp_col = _pick("car_num_components")
    _plot_if_exists(axs3[2], protected_comp_col, label="Protected", color="tab:green")
    _plot_if_exists(axs3[2], car_comp_col, label="Car", color="tab:orange", linestyle="--")
    axs3[2].set_title("Number of components (diagnostic)")
    axs3[2].set_xlabel("Iteration")
    axs3[2].set_ylabel("Components")
    axs3[2].grid(alpha=0.3)
    if protected_comp_col or car_comp_col:
        axs3[2].legend(fontsize=8)

    fig3.tight_layout()
    plt.show()


def plot_od_investigation(df_sweep, random_avg_length, random_abs_error, best_beta, best_avg_m, title=""):
    fig, ax1 = plt.subplots(figsize=(10, 6))

    # Primary Y-Axis: Absolute Error
    color_err = "tab:red"
    ax1.set_xlabel("Beta Value (Log Scale)", fontsize=12)
    ax1.set_ylabel("Abs Avg Distance Error (m)", color=color_err, fontsize=12)
    ax1.plot(df_sweep["beta"], df_sweep["abs_avg_m_error"], marker="o", color=color_err, label="Abs Error")
    ax1.axhline(y=random_abs_error, color=color_err, linestyle=":", alpha=0.5, label="Random Baseline Error")
    ax1.tick_params(axis="y", labelcolor=color_err)

    # Secondary Y-Axis: Avg Length
    ax2 = ax1.twinx()
    color_len = "tab:blue"
    ax2.set_ylabel("Avg Path Length (m)", color=color_len, fontsize=12)
    ax2.plot(df_sweep["beta"], df_sweep["avg_length"], marker="s", color=color_len, label="Avg Length", alpha=0.7)
    ax2.axhline(y=random_avg_length, color=color_len, linestyle=":", alpha=0.5, label="Random Baseline Length")
    ax2.axhline(y=ODConstants.TARGET_AVG_DISTANCE, color="green", linestyle="-", alpha=0.4, label="Target Avg Distance")
    ax2.tick_params(axis="y", labelcolor=color_len)

    # Optimal Beta
    best_error = df_sweep.loc[df_sweep["beta"] == best_beta, "abs_avg_m_error"].values[0]
    plt.axvline(x=best_beta, color="green", linestyle="--", linewidth=2, label=f"Optimal Beta ({best_beta:.2e})")
    ax1.plot(best_beta, best_error, "ko", markersize=10, fillstyle="none")
    ax2.plot(best_beta, best_avg_m, "ks", markersize=10, fillstyle="none")

    ax1.annotate(
        f"Avg Length: {best_avg_m/1000:.2f}km\nError: {best_error:.0f}m",
        xy=(best_beta, best_error),
        xytext=(best_beta * 1.5, best_error * 1.1),
        arrowprops=dict(arrowstyle="->", color="black"),
        fontweight="bold",
        color="green",
    )

    plt.title(title or "Beta Sweep: Distance Error vs Avg Path Length", fontsize=14)
    ax1.set_xscale("log")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=3)
    plt.tight_layout()
    plt.show()


def plot_od_matrix_error(error, title=None):
    plt.figure(figsize=(6, 5))
    sns.heatmap(error, annot=True, cmap="coolwarm", center=0)
    if title:
        plt.title(title)
    plt.show()
