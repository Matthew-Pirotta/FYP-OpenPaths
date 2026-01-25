import matplotlib.pyplot as plt
import osmnx as ox

_DEFAULT_FIGSIZE = (12, 12)

def draw_graph(G, ax=None, node_size=0, node_color="white", edge_color="black", edge_linewidth=0.5, bgcolor="white", figsize=None):
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize or _DEFAULT_FIGSIZE)
    else:
        fig = ax.figure 

    ox.plot_graph(
        G,
        ax=ax,
        node_size=node_size,
        node_color=node_color,
        edge_color=edge_color,
        edge_linewidth=edge_linewidth,
        bgcolor=bgcolor,
        show=False,
        close=False,
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
):
    """
    Generic edge-attribute map plot.

    If `norm` is provided, manual matplotlib normalization is used.
    Otherwise, OSMnx automatic normalization is used.
    """

    edge_colors = ox.plot.get_edge_colors_by_attr(
        G,
        attr=attr,
        cmap=cmap,
        num_bins=num_bins,
        equal_size=equal_size,
        na_color=na_color,
    )

    fig, ax = draw_graph(G, edge_color=edge_colors)

    # Colorbar
    if normalize_colorbar:
        # Normalized colorbar (explicit or implicit)
        sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    else:
        # Absolute colorbar: infer range directly from data
        values = [
            d.get(attr)
            for _, _, _, d in G.edges(keys=True, data=True)
            if d.get(attr) is not None
        ]
        sm = plt.cm.ScalarMappable(
            norm=plt.Normalize(vmin=min(values), vmax=max(values)),
            cmap=cmap,
        )

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
