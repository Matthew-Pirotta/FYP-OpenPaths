import matplotlib.pyplot as plt
import osmnx as ox

_DEFAULT_FIGSIZE = (12, 12)

from typing import TypedDict, Unpack

class PlotSettings(TypedDict, total=False):
    """Schema for graph plotting parameters."""
    node_size: int
    node_color: str
    edge_linewidth: float
    fig_size: tuple[int, int]
    bgcolor: str
    alpha: float
    edge_color: str
    dpi: int  

DEFAULTS: PlotSettings = {
    "node_size": 0,
    "node_color": "black",
    "edge_linewidth": 0.5,
    "bgcolor": "white",
    "edge_color": "black",
    "dpi": 100,
}

def draw_graph(G, ax=None, **kwargs: PlotSettings):
    # The | operator merges dicts. kwargs overrides DEFAULTS.
    settings: dict = DEFAULTS | kwargs
    # Pull out the one thing that doesn't go into plot_graph
    fig_size = settings.pop("fig_size", _DEFAULT_FIGSIZE)
    dpi = settings.pop("dpi") 

    if ax is None:
        fig, ax = plt.subplots(figsize=fig_size, dpi=dpi)
    else:
        fig = ax.figure 

    ox.plot_graph(
        G,
        ax=ax,
        show=False,
        close=False,
        **settings,
    )
    return fig, ax


def plot_graph_by_edge_attr(
    G,
    attr: str | None = None,
    cmap="managua_r",
    num_bins=None,
    equal_size=False,
    na_color="#dddddd",
    norm=None,
    normalize_colorbar=False,
    title=None,
    label = None,
    **kwargs: Unpack[PlotSettings]
):
    """
    Generic edge-attribute map plot.

    If `norm` is provided, manual matplotlib normalization is used.
    Otherwise, OSMnx automatic normalization is used.
    """

    cmap_obj = plt.get_cmap(cmap)
    values = [
        d.get(attr)
        for _, _, _, d in G.edges(keys=True, data=True)
        if d.get(attr) is not None
    ]

    if norm is not None:
        # Apply fixed/manual normalization directly to edges.
        edge_colors = [
            na_color if d.get(attr) is None else cmap_obj(norm(d.get(attr)))
            for _, _, _, d in G.edges(keys=True, data=True)
        ]
    else:
        edge_colors = ox.plot.get_edge_colors_by_attr(
            G,
            attr=attr,
            cmap=cmap,
            num_bins=num_bins,
            equal_size=equal_size,
            na_color=na_color,
        )

    fig, ax = draw_graph(G, edge_color=edge_colors, **kwargs)

    if norm is not None:
        cbar_norm = norm
    elif normalize_colorbar:
        cbar_norm = plt.Normalize(vmin=0, vmax=1)
    elif values:
        cbar_norm = plt.Normalize(vmin=min(values), vmax=max(values))
    else:
        cbar_norm = plt.Normalize(vmin=0, vmax=1)

    sm = plt.cm.ScalarMappable(norm=cbar_norm, cmap=cmap_obj)
    sm.set_array([])


    # Colorbar
    cbar = fig.colorbar(sm, ax=ax, fraction=0.03, pad=0.01)

    if label:
        cbar.set_label(label)
    if title:
        ax.set_title(title)

    ax.axis("off")
    fig.tight_layout()
    return fig, ax
