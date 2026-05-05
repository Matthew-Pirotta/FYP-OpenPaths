from matplotlib.ticker import FuncFormatter
from matplotlib.ticker import MultipleLocator
import matplotlib.pyplot as plt
import numpy as np
from collections.abc import Mapping
from Plotting import renderer
from Plotting.renderer import  PlotSettings
from Plotting.evaluation import MODEL_STYLES, MODEL_STYLE_BY_LABEL


thousand_formatter = FuncFormatter(lambda x, pos: f"{int(x/1000)}k")
hour_formatter = FuncFormatter(lambda x, pos: f"{int(x/3600)}")
hour_locator = MultipleLocator(3600)


def plot_simulation_results(summary_df=None, tripinfo_df=None, edgedata_df=None, *, results=None):
    runs = _normalise_simulation_runs(summary_df, tripinfo_df, edgedata_df, results)
    figs = []


    # -----------------------------
    # 1. NETWORK MEAN SPEED
    # -----------------------------
    fig, ax = plt.subplots(figsize=(8, 5))
    figs.append(fig)

    for label, run_summary_df, _, _, style in runs:
        _plot_time_series(
            ax,
            run_summary_df,
            "meanSpeed",
            label=label,
            style=style,
            scale=3.6,
            min_value=0,
        )
    ax.set_xlabel("Time (hr)")
    ax.set_ylabel("Mean Speed (km/hr)")
    ax.set_title("Network Mean Speed Over Time")
    ax.xaxis.set_major_formatter(hour_formatter)
    ax.xaxis.set_major_locator(hour_locator)
    ax.grid(True)
    ax.legend(title="Model", fontsize=9)
    fig.tight_layout()
    plt.show()

    # -----------------------------
    # 2. NETWORK RELATIVE MEAN SPEED
    # -----------------------------
    fig, ax = plt.subplots(figsize=(8, 5))
    relative_plotted = False
    for label, run_summary_df, _, _, style in runs:
        relative_plotted = (
            _plot_time_series(
                ax,
                run_summary_df,
                "meanSpeedRelative",
                label=label,
                style=style,
                min_value=0,
            )
            or relative_plotted
        )

    if relative_plotted:
        figs.append(fig)
        ax.set_xlabel("Time (hr)")
        ax.set_ylabel("Mean Speed Relative")
        ax.set_title("Network Mean Speed Relative Over Time")
        ax.xaxis.set_major_formatter(hour_formatter)
        ax.xaxis.set_major_locator(hour_locator)
        ax.grid(True)
        ax.legend(title="Model", fontsize=9)
        fig.tight_layout()
        plt.show()
    else:
        plt.close(fig)

    # -----------------------------
    # 3. VEHICLES RUNNING OVER TIME
    # -----------------------------
    fig, ax = _plot_summary_metric(
        runs,
        "running",
        ylabel="Vehicles in Network",
        title="Vehicles Currently in Simulation Over Time",
    )
    figs.append(fig)
    ax.yaxis.set_major_formatter(thousand_formatter)
    plt.show()

    # -----------------------------
    # 4. CUMULATIVE VEHICLES INSERTED
    # -----------------------------
    fig, ax = _plot_summary_metric(
        runs,
        "inserted",
        ylabel="Cumulative Vehicles",
        title="Cumulative Vehicles Inserted Over Time",
    )
    figs.append(fig)
    ax.yaxis.set_major_formatter(thousand_formatter)
    plt.show()

    # -----------------------------
    # 5. VEHICLES ARRIVED OVER TIME
    # -----------------------------
    fig, ax = _plot_summary_metric(
        runs,
        "arrived",
        ylabel="Arrived Vehicles",
        title="Vehicles Arrived Over Time",
    )
    figs.append(fig)
    ax.yaxis.set_major_formatter(thousand_formatter)
    plt.show()

    # -----------------------------
    # 6. HALTING VEHICLES OVER TIME
    # -----------------------------
    fig, ax = _plot_summary_metric(
        runs,
        "halting",
        ylabel="Halting Vehicles",
        title="Halting Vehicles Over Time",
    )
    figs.append(fig)
    ax.yaxis.set_major_formatter(thousand_formatter)
    plt.show()

    # -----------------------------
    # 7. TRAVEL TIME DISTRIBUTION
    # -----------------------------
    fig, ax = plt.subplots()
    figs.append(fig)
    _plot_histogram(
        ax,
        ((label, run_tripinfo_df, style) for label, _, run_tripinfo_df, _, style in runs),
        "duration",
        bins=30,
    )
    ax.set_xlabel("Travel Time (hr)")
    ax.set_ylabel("Vehicles")
    ax.set_title("Travel Time Distribution")
    ax.xaxis.set_major_formatter(hour_formatter)
    ax.xaxis.set_major_locator(hour_locator)
    ax.legend(title="Model", fontsize=9)
    fig.tight_layout()
    plt.show()

    # -----------------------------
    # 8. EDGE SPEED DISTRIBUTION
    # -----------------------------
    fig, ax = plt.subplots()
    figs.append(fig)
    _plot_histogram(
        ax,
        ((label, run_edgedata_df, style) for label, _, _, run_edgedata_df, style in runs),
        "speed",
        bins=40,
        scale=3.6,
    )
    ax.set_xlabel("Edge Speed (km/hr)")
    ax.set_ylabel("Frequency")
    ax.set_title("Distribution of Edge Speeds")
    ax.legend(title="Model", fontsize=9)
    fig.tight_layout()
    plt.show()


    fig, ax = plt.subplots()
    figs.append(fig)
    _plot_histogram(
        ax,
        ((label, run_edgedata_df, style) for label, _, _, run_edgedata_df, style in runs),
        "entered",
        bins=40,
        value_range=(0, 500),
    )
    ax.set_xlabel("Count Vehicles Entered Edge")
    ax.set_ylabel("Frequency")
    ax.set_title("Distribution of edge use")
    ax.legend(title="Model", fontsize=9)
    fig.tight_layout()
    plt.show()

    return figs


def plot_sumo_edgedata_by_model(edgedata_by_model, *, mode="bike"):
    """
    Plot edge-data comparisons for one SUMO vehicle class across models.

    ``edgedata_by_model`` should match the notebook structure:
    {model: {"all": df, "car": df, "bike": df}}.
    """
    runs = _normalise_edgedata_by_model_runs(edgedata_by_model, mode=mode)
    figs = []
    title_prefix = mode.title()

    fig, ax = plt.subplots(figsize=(8, 5))
    plotted = _plot_edgedata_time_metric(
        ax,
        runs,
        "speed",
        agg="weighted_mean",
        weight_col="entered",
        scale=3.6,
        min_value=0,
    )
    if plotted:
        ax.set_xlabel("Time (hr)")
        ax.set_ylabel(f"{title_prefix} Mean Speed (km/hr)")
        ax.set_title(f"{title_prefix} Mean Edge Speed Over Time")
        ax.xaxis.set_major_formatter(hour_formatter)
        ax.xaxis.set_major_locator(hour_locator)
        ax.grid(True)
        ax.legend(title="Model", fontsize=9)
        fig.tight_layout()
        figs.append(fig)
        plt.show()
    else:
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5))
    plotted = _plot_edgedata_time_metric(ax, runs, "entered", agg="sum")
    if plotted:
        ax.set_xlabel("Time (hr)")
        ax.set_ylabel(f"{title_prefix} Edge Entries")
        ax.set_title(f"{title_prefix} Edge Entries Over Time")
        ax.xaxis.set_major_formatter(hour_formatter)
        ax.xaxis.set_major_locator(hour_locator)
        ax.yaxis.set_major_formatter(thousand_formatter)
        ax.grid(True)
        ax.legend(title="Model", fontsize=9)
        fig.tight_layout()
        figs.append(fig)
        plt.show()
    else:
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5))
    plotted = _plot_edgedata_time_metric(ax, runs, "waitingTime", agg="sum")
    if plotted:
        ax.set_xlabel("Time (hr)")
        ax.set_ylabel(f"{title_prefix} Waiting Time (s)")
        ax.set_title(f"{title_prefix} Waiting Time Over Time")
        ax.xaxis.set_major_formatter(hour_formatter)
        ax.xaxis.set_major_locator(hour_locator)
        ax.grid(True)
        ax.legend(title="Model", fontsize=9)
        fig.tight_layout()
        figs.append(fig)
        plt.show()
    else:
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5))
    _plot_histogram(
        ax,
        runs,
        "speed",
        bins=40,
        scale=3.6,
        min_value=0,
    )
    ax.set_xlabel(f"{title_prefix} Edge Speed (km/hr)")
    ax.set_ylabel("Frequency")
    ax.set_title(f"{title_prefix} Edge Speed Distribution")
    ax.legend(title="Model", fontsize=9)
    fig.tight_layout()
    figs.append(fig)
    plt.show()

    return figs


def _normalise_simulation_runs(summary_df, tripinfo_df, edgedata_df, results):
    if results is not None:
        if not isinstance(results, Mapping):
            raise TypeError("results must be a mapping of model label to simulation data.")
        raw_runs = []
        for label, data in results.items():
            if isinstance(data, Mapping):
                raw_runs.append(
                    (
                        str(label),
                        _first_present(data, "summary_df", "summary"),
                        _first_present(data, "tripinfo_df", "tripinfo"),
                        _first_present(data, "edgedata_df", "edgedata", "edgedata_all"),
                    )
                )
            else:
                run_summary, run_tripinfo, run_edgedata = data
                raw_runs.append((str(label), run_summary, run_tripinfo, run_edgedata))
        return _apply_model_styles(raw_runs)

    if isinstance(summary_df, Mapping):
        raw_runs = []
        for label, run_summary in summary_df.items():
            raw_runs.append(
                (
                    str(label),
                    run_summary,
                    tripinfo_df.get(label) if isinstance(tripinfo_df, Mapping) else None,
                    edgedata_df.get(label) if isinstance(edgedata_df, Mapping) else None,
                )
            )
        return _apply_model_styles(raw_runs)

    return _apply_model_styles([("Run", summary_df, tripinfo_df, edgedata_df)])


def _normalise_edgedata_by_model_runs(edgedata_by_model, *, mode):
    if not isinstance(edgedata_by_model, Mapping):
        raise TypeError("edgedata_by_model must be a mapping of model label to edge-data frames.")

    raw_runs = []
    for label, data in edgedata_by_model.items():
        if isinstance(data, Mapping):
            raw_runs.append((str(label), data.get(mode)))
        else:
            raw_runs.append((str(label), data))

    if len(raw_runs) > len(MODEL_STYLES):
        raise ValueError(
            f"plot_sumo_edgedata_by_model supports up to {len(MODEL_STYLES)} models, "
            f"but received {len(raw_runs)}."
        )

    runs = []
    for idx, (label, df) in enumerate(raw_runs):
        style = MODEL_STYLE_BY_LABEL.get(label, MODEL_STYLES[idx][1]).copy()
        runs.append((label, df, style))
    return runs


def _first_present(data, *keys):
    for key in keys:
        if key in data:
            return data[key]
    return None


def _apply_model_styles(raw_runs):
    if len(raw_runs) > len(MODEL_STYLES):
        raise ValueError(
            f"plot_simulation_results supports up to {len(MODEL_STYLES)} models, "
            f"but received {len(raw_runs)}."
        )

    styled_runs = []
    for idx, (label, run_summary_df, run_tripinfo_df, run_edgedata_df) in enumerate(raw_runs):
        style = MODEL_STYLE_BY_LABEL.get(label, MODEL_STYLES[idx][1]).copy()
        styled_runs.append((label, run_summary_df, run_tripinfo_df, run_edgedata_df, style))
    return styled_runs


def _plot_summary_metric(runs, metric_col, *, ylabel, title):
    fig, ax = plt.subplots()
    for label, run_summary_df, _, _, style in runs:
        _plot_time_series(ax, run_summary_df, metric_col, label=label, style=style)

    ax.set_xlabel("Time (hr)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.xaxis.set_major_formatter(hour_formatter)
    ax.xaxis.set_major_locator(hour_locator)
    ax.grid(True)
    ax.legend(title="Model", fontsize=9)
    fig.tight_layout()
    return fig, ax


def _plot_time_series(ax, df, metric_col, *, label, style, scale=1.0, min_value=None):
    if df is None or metric_col not in df or "time" not in df:
        return False

    y = df[metric_col]
    if min_value is not None:
        y = y.where(y >= min_value)

    if not y.notna().any():
        return False

    ax.plot(
        df["time"],
        y * scale,
        label=label,
        linewidth=2,
        markersize=4,
        markevery=_marker_interval(len(df)),
        **style,
    )
    return True


def _plot_edgedata_time_metric(
    ax,
    runs,
    metric_col,
    *,
    agg,
    scale=1.0,
    weight_col=None,
    min_value=None,
):
    plotted = False
    for label, df, style in runs:
        values = _aggregate_edgedata_time_metric(
            df,
            metric_col,
            agg=agg,
            scale=scale,
            weight_col=weight_col,
            min_value=min_value,
        )
        if values is None:
            continue

        times, y = values
        ax.plot(
            times,
            y,
            label=label,
            linewidth=2,
            markersize=4,
            markevery=_marker_interval(len(times)),
            **style,
        )
        plotted = True
    return plotted


def _aggregate_edgedata_time_metric(
    df,
    metric_col,
    *,
    agg,
    scale=1.0,
    weight_col=None,
    min_value=None,
):
    if df is None or metric_col not in df or "time" not in df:
        return None

    cols = ["time", metric_col]
    if weight_col is not None and weight_col in df:
        cols.append(weight_col)

    data = df[cols].dropna(subset=["time", metric_col]).copy()
    if min_value is not None:
        data = data[data[metric_col] >= min_value]
    if data.empty:
        return None

    times = []
    values = []
    for time, group in data.groupby("time", sort=True):
        if agg == "sum":
            value = group[metric_col].sum()
        elif agg == "mean":
            value = group[metric_col].mean()
        elif agg == "weighted_mean":
            if weight_col is not None and weight_col in group:
                weights = group[weight_col].fillna(0)
                if weights.sum() > 0:
                    value = np.average(group[metric_col], weights=weights)
                else:
                    value = group[metric_col].mean()
            else:
                value = group[metric_col].mean()
        else:
            raise ValueError(f"Unknown aggregation: {agg}")

        times.append(time)
        values.append(value * scale)

    return np.array(times), np.array(values)


def _plot_histogram(ax, runs, metric_col, *, bins, scale=1.0, value_range=None, min_value=None):
    for label, df, style in runs:
        if df is None or metric_col not in df:
            continue
        values = df[metric_col].dropna()
        if min_value is not None:
            values = values[values >= min_value]
        values = (values * scale).to_numpy()
        if len(values) == 0:
            continue
        ax.hist(
            values,
            bins=bins,
            range=value_range,
            histtype="step",
            linewidth=2,
            color=style["color"],
            linestyle=style["linestyle"],
            label=label,
        )


def _marker_interval(n_rows):
    return max(1, n_rows // 12)


def plot_sumo_edges(net, metric_dict=None, title="SUMO Plot", cmap=plt.cm.managua_r, colorbar_label="Value", **kwargs:PlotSettings):
    # Merge defaults with overrides
    settings = renderer.DEFAULTS | kwargs

    fig, ax = plt.subplots(figsize=settings.get("fig_size", (12, 12)))

    fig.patch.set_facecolor(settings["bgcolor"])
    ax.set_facecolor(settings["bgcolor"])

    linewidth = settings["edge_linewidth"]
    alpha = settings.get("alpha", 1.0)

    # --- normalization (only if metric provided) ---
    if metric_dict is not None:
        values = np.array([v for v in metric_dict.values() if not np.isnan(v)])
        norm = plt.Normalize(vmin=values.min(), vmax=values.max())

    # --- plotting ---
    for edge in net.getEdges():
        shape = edge.getShape()
        xs = [p[0] for p in shape]
        ys = [p[1] for p in shape]

        if metric_dict is None:
            color = settings["edge_color"]
        else:
            val = metric_dict.get(edge.getID(), np.nan)
            color = settings["edge_color"] if np.isnan(val) else cmap(norm(val))

        ax.plot(xs, ys, color=color, linewidth=linewidth, alpha=alpha)

    # --- styling ---
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(title)

    # --- colorbar ---
    if metric_dict is not None:
        sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
        sm.set_array([])
        cbar = fig.colorbar(sm, ax=ax, fraction=0.03, pad=0.01)
        cbar.set_label(colorbar_label)

    plt.show()
