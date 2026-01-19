import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.ticker import PercentFormatter

import osmnx as ox
from Plotting.utils import color_hist
from Plotting.renderer import draw_graph


def plot_elevation(G):
    elevations = [d["elevation"] for _, d in G.nodes(data=True) if d.get("elevation") is not None]

    # --- Elevation histogram ---
    plt.hist(elevations, bins=40, edgecolor="black", alpha=0.8)
    plt.xlabel("Elevation (m)")
    plt.ylabel("Frequency")
    plt.title("Node Elevation Distribution")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.show()

    # --- Spatial elevation map ---
    cmap_name = "managua_r"
    norm = mcolors.Normalize(vmin=min(elevations), vmax=max(elevations))

    node_colors = ox.plot.get_node_colors_by_attr(G, "elevation", cmap=cmap_name)

    fig, ax = draw_graph(G, node_color=node_colors, node_size=10)

    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap_name)
    fig.colorbar(sm, ax=ax, label="Elevation (m)", fraction=0.03, pad=0.01)

    ax.set_title("Elevation Map")
    ax.axis("off")
    fig.tight_layout()
    plt.show()


def plot_grades(G):
    grades = [d["grade"] for _, _, _, d in G.edges(keys=True, data=True)]

    cmap = plt.cm.managua_r
    norm = mcolors.Normalize(vmin=-0.1, vmax=0.1, clip=True)

    # --- Grade distribution ---
    fig, ax = plt.subplots(figsize=(14, 5))
    color_hist(
        ax,
        grades,
        bins=40,
        cmap=cmap,
        norm=norm,
        title="Road Grades",
        xlabel="Grade",
    )
    ax.xaxis.set_major_formatter(PercentFormatter(xmax=1.0))

    fig.tight_layout()
    plt.show()

    # --- Spatial grade map ---
    edge_colors = [cmap(norm(d.get("grade", 0))) for _, _, _, d in G.edges(keys=True, data=True)]

    fig, ax = draw_graph(G, edge_color=edge_colors, node_size=0)

    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    cbar = fig.colorbar(sm, ax=ax, label="Edge Grade (%)", extend="both" ,fraction=0.03, pad=0.01, format=PercentFormatter(xmax=1.0, decimals=0))
    cbar.set_label("Edge Grade (%)")

    ax.set_title("Spatial Grade Map")
    ax.axis("off")
    fig.tight_layout()
    plt.show()
