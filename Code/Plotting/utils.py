import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import networkx as nx
import libpysal

def color_hist(ax, values, bins, cmap, norm, title, xlabel, ylabel="Frequency", log=False):
    n, bins, patches = ax.hist(values, bins=bins, edgecolor="black", alpha=0.8, log=log)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", alpha=0.3)

    for left, right, patch in zip(bins[:-1], bins[1:], patches):
        patch.set_facecolor(cmap(norm(0.5 * (left + right))))


def assign_adjacent_colors(gdf, cmap_name="tab20"):
    w = libpysal.weights.Rook.from_dataframe(gdf, ids=gdf.index)
    G = nx.Graph(w.neighbors)
    coloring = nx.coloring.greedy_color(G, strategy="largest_first")

    gdf = gdf.copy()
    gdf["color_id"] = gdf.index.map(coloring)
    cmap = plt.cm.get_cmap(cmap_name, gdf["color_id"].max() + 1)
    gdf["color"] = gdf["color_id"].apply(lambda i: mcolors.to_hex(cmap(i)))

    return gdf
