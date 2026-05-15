import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


def _format_columns(df):
    df = df.copy()
    df.columns = [str(col).replace("_", " ").title() for col in df.columns]
    return df


def _plot_heatmap(
    df,
    *,
    title,
    xlabel,
    ylabel,
    figsize=(12, 6),
    cmap="managua_r",
    annot=True,
    fmt=".2f",
    linewidths=0.5,
):
    fig, ax = plt.subplots(figsize=figsize)
    sns.heatmap(
        df,
        annot=annot,
        fmt=fmt,
        cmap=cmap,
        linewidths=linewidths,
        ax=ax,
    )
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.tick_params(axis="x", rotation=45)
    for label in ax.get_xticklabels():
        label.set_ha("right")
    fig.tight_layout()
    return fig, ax


def plot_outward_purpose_shares_by_dest_region(
    outward_purpose_shares_by_dest_region,
    **kwargs,
):
    df = _format_columns(pd.DataFrame(outward_purpose_shares_by_dest_region).T)
    fig, ax = _plot_heatmap(
        df,
        title="Outward Trip Purpose Shares by Destination Region",
        xlabel="Trip Purpose",
        ylabel="Destination Region",
        **kwargs,
    )
    return fig, ax, df


def plot_dest_region_given_origin(
    dest_region_given_origin,
    **kwargs,
):
    df = _format_columns(pd.DataFrame(dest_region_given_origin).T)
    fig, ax = _plot_heatmap(
        df,
        title="Regional Origin-Destination Probabilities",
        xlabel="Destination Region",
        ylabel="Origin Region",
        **kwargs,
    )
    return fig, ax, df


def plot_od_sampling_heatmaps(
    outward_purpose_shares_by_dest_region,
    dest_region_given_origin,
    *,
    print_purpose_table=True,
    show=True,
    **kwargs,
):
    purpose_fig, purpose_ax, purpose_df = plot_outward_purpose_shares_by_dest_region(
        outward_purpose_shares_by_dest_region,
        **kwargs,
    )

    if print_purpose_table:
        print(purpose_df)

    region_fig, region_ax, region_df = plot_dest_region_given_origin(
        dest_region_given_origin,
        **kwargs,
    )

    if show:
        plt.show()

    return (purpose_fig, purpose_ax, purpose_df), (region_fig, region_ax, region_df)
