import matplotlib.pyplot as plt
import seaborn as sns
from Demand import ODConstants
import matplotlib.ticker as mticker


MODEL_STYLES = (
    ("Model A", {"color": "tab:blue", "linestyle": "-", "marker": "o"}),
    ("Model B", {"color": "tab:orange", "linestyle": "--", "marker": "s"}),
    ("Model C", {"color": "tab:green", "linestyle": ":", "marker": "^"}),
    ("Model D", {"color": "tab:red", "linestyle": "-.", "marker": "D"}),
)
MODEL_STYLE_BY_LABEL = dict(MODEL_STYLES)


def plot_metrics(df):
    model_col = _pick_col(df, "model", "heuristic")
    groups = _metric_groups(df, model_col)

    bike_gain_col = _pick_col(df, "bike_gain_vs_baseline")
    car_harm_col = _pick_col(df, "car_harm_vs_baseline")
    directness_col = _pick_col(df, "main_od_directness_weighted", "full_od_directness_mean")
    coverage_col = _pick_col(
        df,
        "protected_coverage_area_km2",
        "coverage_area_km2",
        "protected_coverage_area_m2",
        "coverage_area_m2",
    )
    protected_lcc_col = _pick_col(df, "protected_lcc_length", "lcc_length")

    # Figure 1: Bike-car trade-off scatter.
    fig1, ax1 = plt.subplots(figsize=(7.5, 5.5))
    ax1.set_title("Bike gain vs car harm")
    ax1.set_xlabel("Car harm vs baseline (%)")
    ax1.set_ylabel("Bike gain vs baseline (%)")
    ax1.axhline(0, color="0.75", linewidth=1)
    ax1.axvline(0, color="0.75", linewidth=1)
    ax1.xaxis.set_major_formatter(mticker.PercentFormatter())
    ax1.yaxis.set_major_formatter(mticker.PercentFormatter())
    ax1.grid(alpha=0.3)

    if bike_gain_col and car_harm_col:
        for label, run, style in groups:
            ax1.plot(
                run[car_harm_col] * 100.0,
                run[bike_gain_col] * 100.0,
                label=label,
                linewidth=2,
                markersize=6,
                **style,
            )
        ax1.legend(title="Model", fontsize=9)
    else:
        _show_missing_metric(ax1)
    fig1.tight_layout()

    # Figure 2: Demand-weighted directness over iterations.
    fig2, ax2 = plt.subplots(figsize=(7.5, 4.8))
    _plot_metric_over_iterations(
        ax2,
        groups,
        directness_col,
        title="Demand-weighted directness",
        ylabel="Directness (drive/bike)",
    )
    fig2.tight_layout()

    # Figure 3: Protected coverage over iterations.
    fig3, ax3 = plt.subplots(figsize=(7.5, 4.8))
    coverage_scale = 1.0
    coverage_ylabel = "Coverage area (km^2)"
    if coverage_col and coverage_col.endswith("_m2"):
        coverage_scale = 1.0 / 1_000_000.0

    _plot_metric_over_iterations(
        ax3,
        groups,
        coverage_col,
        title="Coverage",
        ylabel=coverage_ylabel,
        scale=coverage_scale,
    )
    fig3.tight_layout()

    # Figure 4: Protected LCC length over iterations.
    fig4, ax4 = plt.subplots(figsize=(7.5, 4.8))
    _plot_metric_over_iterations(
        ax4,
        groups,
        protected_lcc_col,
        title="Protected LCC length",
        ylabel="Protected LCC length (km)",
        scale=1.0 / 1000.0,
    )
    fig4.tight_layout()

    plt.show()


def _pick_col(df, *cols):
    for col in cols:
        if col and col in df.columns:
            return col
    return None


def _metric_groups(df, model_col):
    if model_col is None:
        return [("Run", _sort_metric_run(df), MODEL_STYLES[0][1])]

    model_values = list(dict.fromkeys(df[model_col].dropna()))

    if not model_values:
        return [("Run", _sort_metric_run(df), MODEL_STYLES[0][1])]

    if len(model_values) > len(MODEL_STYLES):
        raise ValueError(
            f"plot_metrics supports up to {len(MODEL_STYLES)} models, "
            f"but received {len(model_values)}."
        )

    groups = []

    for idx, model_value in enumerate(model_values):
        _, style = MODEL_STYLES[idx]
        run = df[df[model_col] == model_value]
        groups.append((str(model_value), _sort_metric_run(run), style))

    return groups

def _sort_metric_run(run):
    if "iteration" in run.columns:
        return run.sort_values("iteration")
    return run.reset_index(drop=True)


def _plot_metric_over_iterations(
    ax,
    groups,
    metric_col,
    *,
    title,
    ylabel,
    scale=1.0,
):
    ax.set_title(title)
    ax.set_xlabel("Iteration")
    ax.set_ylabel(ylabel)
    ax.grid(alpha=0.3)

    if metric_col is None:
        _show_missing_metric(ax)
        return

    for label, run, style in groups:
        x = run["iteration"] if "iteration" in run.columns else range(len(run))
        ax.plot(
            x,
            run[metric_col] * scale,
            label=label,
            linewidth=2,
            markersize=5,
            **style,
        )

    ax.legend(title="Model", fontsize=9)


def _show_missing_metric(ax):
    ax.text(
        0.5,
        0.5,
        "Metric not available",
        ha="center",
        va="center",
        transform=ax.transAxes,
        color="0.4",
    )


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
