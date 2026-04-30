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

    def _plot_if_exists(ax, col, *, label, color, linestyle="-", scale=1.0, marker="o"):
        if col is None:
            return
        ax.plot(x, df[col] * scale, label=label, color=color, linewidth=2, linestyle=linestyle, marker=marker, markersize=4)

    # Figure 1: Main OD performance
    fig1, axs1 = plt.subplots(1, 3, figsize=(12, 4.5))
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

    full_od_directness_col = _pick("full_od_directness_mean")
    _plot_if_exists(
        axs1[1],
        full_od_directness_col,
        label="Bikeable reachable demand share",
        color="tab:blue",
        scale=100.0,
    )
    axs1[2].set_title("Share of demand reachable on bikeable network")
    axs1[2].set_xlabel("Iteration")
    axs1[2].set_ylabel("Reachable demand (%)")
    axs1[2].yaxis.set_major_formatter(mticker.PercentFormatter())
    axs1[2].grid(alpha=0.3)
    if full_od_directness_col:
        axs1[2].legend(fontsize=8)


    

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


def plot_od_investigation(
    df_sweep,
    random_avg_length=None,
    random_abs_error=None,
    best_beta=None,
    best_avg_m=None,
    title="",
    show_error_diagnostic=False,
):
    df = df_sweep.sort_values("beta").copy()

    # Pick best beta from df if not explicitly supplied
    if best_beta is None:
        best_idx = df["abs_avg_m_error"].idxmin()
        best_beta = df.loc[best_idx, "beta"]
    else:
        # Avoid exact float equality issues
        best_idx = (df["beta"] - best_beta).abs().idxmin()

    best_error = df.loc[best_idx, "abs_avg_m_error"]

    if best_avg_m is None:
        best_avg_m = df.loc[best_idx, "avg_length"]

    target_km = ODConstants.TARGET_AVG_DISTANCE / 1000.0

    # Detect whether optimum is at sweep boundary
    best_at_edge = best_idx in [df.index[0], df.index[-1]]

    fig, ax = plt.subplots(figsize=(10, 6))

    # Main line: average path length
    ax.plot(
        df["beta"],
        df["avg_length"] / 1000.0,
        marker="o",
        linewidth=2,
        label="Simulated avg path length",
    )

    # Target line
    ax.axhline(
        y=target_km,
        linestyle="-",
        linewidth=2,
        alpha=0.6,
        label=f"Target avg distance ({target_km:.2f} km)",
    )

    # Optional random baseline
    if random_avg_length is not None:
        ax.axhline(
            y=random_avg_length / 1000.0,
            linestyle=":",
            linewidth=2,
            alpha=0.7,
            label=f"Random baseline ({random_avg_length / 1000.0:.2f} km)",
        )

    # Best beta marker
    ax.axvline(
        x=best_beta,
        linestyle="--",
        linewidth=2,
        label=f"Selected beta ({best_beta:.2e})",
    )

    ax.plot(
        best_beta,
        best_avg_m / 1000.0,
        marker="o",
        markersize=10,
        fillstyle="none",
        color="black",
    )

    annotation = (
        f"β = {best_beta:.2e}\n"
        f"Avg length = {best_avg_m / 1000.0:.2f} km\n"
        f"Error = {best_error:.0f} m"
    )

    if best_at_edge:
        annotation += "\nBest is at sweep edge"

    ax.annotate(
        annotation,
        xy=(best_beta, best_avg_m / 1000.0),
        xytext=(15, 15),
        textcoords="offset points",
        arrowprops=dict(arrowstyle="->"),
        fontweight="bold",
    )

    ax.set_title(title or "Beta Sweep: Avg Path Length Calibration", fontsize=14)
    ax.set_xlabel("Beta value", fontsize=12)
    ax.set_ylabel("Avg path length (km)", fontsize=12)
    ax.set_xscale("log")

    ax.grid(True, which="both", alpha=0.25)
    ax.legend(loc="best")
    plt.tight_layout()
    plt.show()

    # Optional separate diagnostic plot: error only
    if show_error_diagnostic:
        fig, ax = plt.subplots(figsize=(10, 4))

        ax.plot(
            df["beta"],
            df["abs_avg_m_error"],
            marker="o",
            linewidth=2,
            label="Absolute error",
        )

        if random_abs_error is not None:
            ax.axhline(
                y=random_abs_error,
                linestyle=":",
                linewidth=2,
                alpha=0.7,
                label=f"Random baseline error ({random_abs_error:.0f} m)",
            )

        ax.axvline(
            x=best_beta,
            linestyle="--",
            linewidth=2,
            label=f"Selected beta ({best_beta:.2e})",
        )

        ax.plot(
            best_beta,
            best_error,
            marker="o",
            markersize=10,
            fillstyle="none",
            color="black",
        )

        ax.set_title("Beta Sweep Diagnostic: Absolute Error", fontsize=14)
        ax.set_xlabel("Beta value", fontsize=12)
        ax.set_ylabel("Absolute avg distance error (m)", fontsize=12)
        ax.set_xscale("log")

        ax.grid(True, which="both", alpha=0.25)
        ax.legend(loc="best")
        plt.tight_layout()
        plt.show()


def plot_od_matrix_error(error, title=None):
    plt.figure(figsize=(6, 5))
    sns.heatmap(error, annot=True, cmap="coolwarm", center=0)
    if title:
        plt.title(title)
    plt.show()
