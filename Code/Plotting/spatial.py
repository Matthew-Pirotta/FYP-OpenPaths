import matplotlib.pyplot as plt
import geopandas as gpd
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
from shapely.geometry import LineString
import numpy as np

from Plotting.utils import assign_adjacent_colors
from Plotting.renderer import draw_graph

#region Optimisation
def plot_gdf_and_overlay(gdf, G=None, title=None, annotate=False):
    """Plot the location and the region outlines, and the transport network if passed"""
    fig, ax = plt.subplots(figsize=(10, 10))

    gdf_colored = assign_adjacent_colors(gdf)
    gdf_colored.plot(ax=ax, color=gdf_colored["color"], edgecolor="black", alpha=0.7)

    if G is not None:
        fig, ax = draw_graph(G, ax=ax, edge_color="black")

    if annotate and "name" in gdf_colored.columns:
        for _, row in gdf_colored.iterrows():
            c = row.geometry.centroid
            ax.text(c.x, c.y, row["name"], fontsize=6, ha="center")

    if title:
        ax.set_title(title)

    ax.axis("off")
    fig.tight_layout()
    plt.show()

    return gdf_colored


#region Metrics
def plot_coverage(G_master, union_geom, title="Coverage Area"):
    """Dispalys a green area in which locations are rechable throhg the transport network given a certain radius"""
    fig, ax = plt.subplots(figsize=(10, 10))

    gpd.GeoSeries([union_geom], crs=G_master.graph["crs"]).plot(
        ax=ax,
        alpha=0.3,
        color="green",
        edgecolor="none",
    )

    fig, ax = draw_graph(
        G_master,
        ax=ax,
        node_size=0,
        edge_color="black",
        edge_linewidth=0.6,
    )

    ax.set_title(title)
    ax.axis("off")
    fig.tight_layout()
    plt.show()


# region OD spatial
def plot_OD_points(
    G,
    gdf_residential=None,
    gdf_destinations=None,
    *,
    destination_size_col=None,
    origin_point=None,
    destination_point=None,
    figsize=(14, 14),
    title=None,
):
    fig, ax = plt.subplots(figsize=figsize)

    fig, ax = draw_graph(G, ax=ax, node_size=0, edge_color="gray", edge_linewidth=0.5)

    legend_handles = []

    if gdf_residential is not None:
        gdf_residential.plot(ax=ax, facecolor="lightblue", edgecolor="none", alpha=0.6)
        legend_handles.append(
            mpatches.Patch(facecolor="lightblue", alpha=0.6, label="Residential Areas")
        )

    if gdf_destinations is not None:
        sizes = (
            gdf_destinations[destination_size_col] * 4
            if destination_size_col and destination_size_col in gdf_destinations.columns
            else 6
        )
        gdf_destinations.plot(ax=ax, color="orange", markersize=sizes, alpha=0.7)
        legend_handles.append(
            mlines.Line2D(
                [],
                [],
                color="orange",
                marker="o",
                linestyle="None",
                markersize=8,
                label="Destinations",
            )
        )

    if origin_point is not None:
        ax.plot(origin_point.x, origin_point.y, marker="*", color="red", markersize=20)
        legend_handles.append(
            mlines.Line2D(
                [],
                [],
                color="red",
                marker="*",
                linestyle="None",
                markersize=15,
                label="Origin",
            )
        )

    if destination_point is not None:
        ax.plot(
            destination_point.x,
            destination_point.y,
            marker="*",
            color="blue",
            markersize=20,
        )
        legend_handles.append(
            mlines.Line2D(
                [],
                [],
                color="blue",
                marker="*",
                linestyle="None",
                markersize=15,
                label="Destination",
            )
        )

    if legend_handles:
        ax.legend(handles=legend_handles, loc="upper right")

    if title:
        ax.set_title(title)

    ax.axis("off")
    fig.tight_layout()
    plt.show()

def build_OD_lines_gdf(G, OD, *, use_weights=True):
    """
    Build a GeoDataFrame of straight OD lines.

    Parameters
    ----------
    G : networkx graph
    OD : iterable of (origin_node, destination_node, weight)
    use_weights : bool
        If True, store OD weight for plotting (alpha/linewidth)

    Returns
    -------
    GeoDataFrame with geometry = LineString
    """
    lines = []
    weights = []

    #TODO
    #for o, d, w in OD:
    for (o, d), w in OD.items():
        xo, yo = G.nodes[o]["x"], G.nodes[o]["y"]
        xd, yd = G.nodes[d]["x"], G.nodes[d]["y"]

        lines.append(LineString([(xo, yo), (xd, yd)]))
        weights.append(w if use_weights else 1)

    gdf = gpd.GeoDataFrame(
        {"weight": weights},
        geometry=lines,
        crs=G.graph["crs"],
    )

    return gdf


def plot_OD_lines(
    G,
    OD,
    *,
    alpha=0.05,
    linewidth=1.0,
    figsize=(14, 14),
    title=None,
):
    """
    Plot straight-line OD pairs over the network.
    """
    fig, ax = plt.subplots(figsize=figsize)

    # Base graph
    fig, ax = draw_graph(
        G,
        ax=ax,
        node_size=0,
        edge_color="lightgray",
        edge_linewidth=0.5,
    )

    # Build OD lines
    gdf_od = build_OD_lines_gdf(G, OD)

    # Optional: scale linewidth or alpha by weight
    if "weight" in gdf_od.columns:
        lw = np.clip(gdf_od["weight"] / gdf_od["weight"].max(), 0.1, 1.0) * linewidth
    else:
        lw = linewidth

    gdf_od.plot(
        ax=ax,
        color="red",
        linewidth=lw,
        alpha=alpha,
    )

    if title:
        ax.set_title(title)

    ax.axis("off")
    fig.tight_layout()
    plt.show()

    return gdf_od
