import matplotlib.pyplot as plt
import geopandas as gpd
import matplotlib.patches as mpatches
import matplotlib.lines as mlines

from Plotting.utils import assign_adjacent_colors
from Plotting.renderer import draw_graph


def plot_gdf_and_overlay(gdf, G=None, title=None, annotate=False):
    fig, ax = plt.subplots(figsize=(10, 10))

    if G is not None:
        gdf = gdf.to_crs(G.graph["crs"])

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


def plot_coverage(G_master, union_geom, title="Coverage Area"):
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


def plot_OD_points(
    G,
    gdf_residential=None,
    gdf_amenities=None,
    *,
    amenity_size_col=None,
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

    if gdf_amenities is not None:
        sizes = (
            gdf_amenities[amenity_size_col] * 4
            if amenity_size_col and amenity_size_col in gdf_amenities.columns
            else 6
        )
        gdf_amenities.plot(ax=ax, color="orange", markersize=sizes, alpha=0.7)
        legend_handles.append(
            mlines.Line2D(
                [],
                [],
                color="orange",
                marker="o",
                linestyle="None",
                markersize=8,
                label="Amenities",
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
