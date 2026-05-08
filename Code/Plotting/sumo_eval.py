import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MultipleLocator
from Plotting.evaluation import MODEL_STYLE_BY_LABEL, MODEL_STYLES


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
):
    fig, ax = plt.subplots(figsize=(10, 7))
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
):
    fig, ax = plt.subplots(figsize=(10, 7))
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

    return fig, ax