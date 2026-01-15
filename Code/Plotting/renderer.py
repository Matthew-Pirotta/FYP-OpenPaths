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