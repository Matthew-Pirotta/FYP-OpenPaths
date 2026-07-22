import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter, MultipleLocator
from Plotting.evaluation import MODEL_STYLE_BY_LABEL, MODEL_STYLES
from pathlib import Path


hour_formatter = FuncFormatter(lambda x, pos: f"{x / 3600:.1f}")
hour_locator = MultipleLocator(3600)


def get_model_style(label, idx):
    if label in MODEL_STYLE_BY_LABEL:
        return MODEL_STYLE_BY_LABEL[label].copy()

    return MODEL_STYLES[idx % len(MODEL_STYLES)][1].copy()


def get_result_df(data, *keys):
    """
    Return the first DataFrame found for the given keys.

    Avoids using `or` on pandas DataFrames, which raises:
    ValueError: The truth value of a DataFrame is ambiguous.
    """
    for key in keys:
        df = data.get(key)
        if df is not None:
            return df
    return None


def plot_compare_summary(
    results,
    metric,
    ylabel,
    title,
    scale=1.0,
    *,
    min_value=None,
    xlabel="Time (h)",
    output_dir="Output/Plots/SumoEvaluation",
):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8, 5))
    plotted = False

    for idx, (name, data) in enumerate(results.items()):
        df = get_result_df(data, "summary", "summary_df")

        if df is None:
            print(f"Skipping {name}: no summary dataframe")
            continue

        if metric not in df.columns:
            print(f"Skipping {name}: summary has no column '{metric}'")
            continue

        if "time" not in df.columns:
            print(f"Skipping {name}: summary has no 'time' column")
            continue

        style = get_model_style(name, idx)

        y = df[metric].copy()

        if min_value is not None:
            y = y.where(y >= min_value)

        if not y.notna().any():
            print(f"Skipping {name}: '{metric}' contains no valid values")
            continue

        ax.plot(
            df["time"],
            y * scale,
            label=name,
            linewidth=2,
            markersize=4,
            markevery=max(1, len(df) // 12),
            **style,
        )

        plotted = True

    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.xaxis.set_major_formatter(hour_formatter)
    ax.xaxis.set_major_locator(hour_locator)
    ax.grid(True)

    if plotted:
        ax.legend(title="Model", fontsize=9)

    fig.tight_layout()
    fig.savefig(
        output_dir / f"{title}.svg",
        format="svg",
        bbox_inches="tight",
    )

    plt.show()

    return fig, ax


def plot_compare_mode(
    results,
    mode,
    metric,
    ylabel,
    title,
    scale=1.0,
    *,
    min_value=None,
    xlabel="Time (h)",
    output_dir="Output/Plots/SumoEvaluation",
):
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8, 5))
    plotted = False

    for idx, (name, data) in enumerate(results.items()):
        df = get_result_df(data, mode)

        if df is None:
            print(f"Skipping {name}: no '{mode}' dataframe")
            continue

        if metric not in df.columns:
            print(f"Skipping {name}: {mode} has no column '{metric}'")
            continue

        if "time" not in df.columns:
            print(f"Skipping {name}: {mode} has no 'time' column")
            continue

        style = get_model_style(name, idx)

        y = df[metric].copy()

        if min_value is not None:
            y = y.where(y >= min_value)

        if not y.notna().any():
            print(f"Skipping {name}: '{metric}' contains no valid values")
            continue

        ax.plot(
            df["time"],
            y * scale,
            label=name,
            linewidth=2,
            markersize=4,
            markevery=max(1, len(df) // 12),
            **style,
        )

        plotted = True

    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.xaxis.set_major_formatter(hour_formatter)
    ax.xaxis.set_major_locator(hour_locator)
    ax.grid(True)

    if plotted:
        ax.legend(title="Model", fontsize=9)

    fig.tight_layout()
    plt.show()

    fig.savefig(
        output_dir / f"{title}.pdf",
        format="pdf",
        bbox_inches="tight",
    )

    return fig, ax


def plot_mean_perceived_bike_trip_length(
    results,
    *,
    result_key="bike_perceived",
    metric="perceived_length_m",
    scale=1 / 1000,
    ylabel="Mean perceived bike trip length (km)",
    title="Mean Perceived Bike Trip Length",
    output_dir="Output/Plots/SumoEvaluation",
):
    """Compare the mean perceived bicycle trip length between scenarios.

    Parameters
    ----------
    results : mapping
        The same nested results mapping accepted by ``plot_compare_summary``
        and ``plot_compare_mode``. Each scenario must contain a DataFrame under
        ``result_key``.
    result_key : str
        Key containing the per-bike perceived trip-length DataFrame.
    metric : str
        Column containing the perceived trip cost. By default this is the
        metre-equivalent cost loaded from the bicycle route file.
    scale : float
        Applied after calculating each scenario mean. The default converts
        metres to kilometres.

    Returns
    -------
    (pandas.DataFrame, matplotlib.axes.Axes)
        The plotted scenario summary and axes. ``trip_count`` is included so
        the number of bicycle trips behind every mean remains visible.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    colors = []

    for idx, (scenario, data) in enumerate(results.items()):
        df = get_result_df(data, result_key)

        if df is None:
            print(f"Skipping {scenario}: no '{result_key}' dataframe")
            continue

        if metric not in df.columns:
            print(
                f"Skipping {scenario}: {result_key} has no column '{metric}'"
            )
            continue

        values = pd.to_numeric(df[metric], errors="coerce").dropna()
        if values.empty:
            print(f"Skipping {scenario}: '{metric}' contains no valid values")
            continue

        mean_m = values.mean()
        rows.append({
            "scenario": str(scenario),
            "trip_count": len(values),
            "mean_perceived_length_m": mean_m,
            "mean_perceived_length_km": mean_m / 1000,
            "plotted_mean": mean_m * scale,
        })
        colors.append(get_model_style(scenario, idx).get("color", f"C{idx % 10}"))

    summary = pd.DataFrame(rows)
    if summary.empty:
        raise ValueError(
            f"No valid '{metric}' data was found under result key "
            f"'{result_key}'"
        )

    fig, ax = plt.subplots(figsize=(max(6, 1.4 * len(summary)), 4.5))

    bars = ax.bar(
        summary["scenario"],
        summary["plotted_mean"],
        color=colors,
    )
    ax.bar_label(bars, fmt="%.2f", padding=3)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Scenario")
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.25)
    ax.tick_params(axis="x", rotation=15)
    fig.tight_layout()
    fig.savefig(
        output_dir / f"{title}.pdf",
        format="pdf",
        bbox_inches="tight",
    )
    plt.show()

    return summary, ax