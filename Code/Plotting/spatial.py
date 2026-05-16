import matplotlib.pyplot as plt
import geopandas as gpd
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
from shapely.geometry import LineString
from shapely.ops import unary_union
import numpy as np

from Plotting.utils import assign_adjacent_colors
from Plotting.renderer import draw_graph

#region Optimisation
def plot_gdf_and_overlay(gdf, G=None, title=None, annotate=False, show=True):
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

    if show:
        plt.show()

    return fig, ax, gdf_colored


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
    silhouette=None,
    silhouette_color="0.95",
    silhouette_edgecolor="none",
    silhouette_alpha=1.0,
    legend_loc="upper right",
    legend_fontsize=None,
    legend_markerscale=1.0,
    show = True,
):
    fig, ax = plt.subplots(figsize=figsize)

    if silhouette is not None:
        plot_silhouette(
            silhouette,
            ax=ax,
            crs=G.graph.get("crs"),
            color=silhouette_color,
            edgecolor=silhouette_edgecolor,
            alpha=silhouette_alpha,
        )

    fig, ax = draw_graph(G, ax=ax, node_size=0, edge_color="gray", edge_linewidth=0.5)

    legend_handles = []

    if gdf_residential is not None:
        gdf_residential.plot(ax=ax, facecolor="lightblue", edgecolor="none", alpha=0.6)
        legend_handles.append(
            mpatches.Patch(facecolor="lightblue", alpha=0.6, label="Residential areas")
        )

    if gdf_destinations is not None:
        gdf_destinations.plot(ax=ax, color="orange", markersize=6, alpha=0.7)
        legend_handles.append(
            mlines.Line2D(
                [],
                [],
                color="orange",
                marker="o",
                linestyle="None",
                markersize=8,
                label="Destination opportunities",
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
        ax.legend(
            handles=legend_handles,
            loc=legend_loc,
            fontsize=legend_fontsize,
            markerscale=legend_markerscale,
        )

    if title:
        ax.set_title(title)

    ax.axis("off")
    fig.tight_layout()
    if show:
        plt.show()
    else:
        plt.close(fig)

    return fig, ax

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
    silhouette=None,
    silhouette_color="0.95",
    silhouette_edgecolor="none",
    silhouette_alpha=1.0,
    show_graph=True,
    graph_edge_color="lightgray",
    graph_edge_linewidth=0.5,
    show = True,
):
    """
    Plot straight-line OD pairs over the network.
    """
    fig, ax = plt.subplots(figsize=figsize)

    if silhouette is not None:
        plot_silhouette(
            silhouette,
            ax=ax,
            crs=G.graph.get("crs"),
            color=silhouette_color,
            edgecolor=silhouette_edgecolor,
            alpha=silhouette_alpha,
        )

    if show_graph:
        fig, ax = draw_graph(
            G,
            ax=ax,
            node_size=0,
            edge_color=graph_edge_color,
            edge_linewidth=graph_edge_linewidth,
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

    if show:
        plt.show()
    else:
        plt.close(fig)

    return fig, ax, gdf_od


def plot_silhouette(
    silhouette,
    *,
    ax,
    crs=None,
    color="0.92",
    edgecolor="none",
    alpha=1.0,
):
    """Plot a dissolved polygon silhouette from a geometry, GeoSeries, or GeoDataFrame."""
    if isinstance(silhouette, gpd.GeoDataFrame):
        source_crs = silhouette.crs
        geoms = silhouette.geometry.dropna().tolist()
    elif isinstance(silhouette, gpd.GeoSeries):
        source_crs = silhouette.crs
        geoms = silhouette.dropna().tolist()
    else:
        source_crs = crs
        geoms = [silhouette]

    geom = unary_union(geoms)
    gdf = gpd.GeoDataFrame(geometry=[geom], crs=source_crs)

    if crs is not None and gdf.crs is not None and gdf.crs != crs:
        gdf = gdf.to_crs(crs)

    gdf.plot(
        ax=ax,
        color=color,
        edgecolor=edgecolor,
        alpha=alpha,
        zorder=0,
    )
    return ax


import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm

from Plotting.utils import assign_adjacent_colors
from Plotting.renderer import draw_graph


def plot_population_heatmap_with_regions_and_roads(
    gdf_residential,
    gdf_localities,
    G=None,
    *,
    value_col="raw_weight",
    use_density=False,
    show_region_fill=True,
    show_region_boundaries=True,
    show_region_names=True,
    show_roads=True,
    cmap="OrRd",
    figsize=(12, 12),
    title=None,
    use_log=True,
    road_edge_color="black",
    road_edge_linewidth=0.4,
    road_alpha=0.5,
    cbar_label="Allocated population weight",
    silhouette=None,
    silhouette_color="0.95",
    silhouette_edgecolor="none",
    silhouette_alpha=1.0,
    show_plot = True
):
    res = gdf_residential.copy()
    loc = gdf_localities.copy()

    if res.crs != loc.crs:
        loc = loc.to_crs(res.crs)

    if use_density:
        plot_col = f"{value_col}_density"
        res[plot_col] = res[value_col] / res.geometry.area
    else:
        plot_col = value_col

    loc_colored = assign_adjacent_colors(loc)

    fig, ax = plt.subplots(figsize=figsize)

    # 1) faint locality silhouette underneath
    if show_region_fill:
        plot_silhouette(
            silhouette if silhouette is not None else loc,
            ax=ax,
            crs=res.crs,
            color=silhouette_color,
            edgecolor=silhouette_edgecolor,
            alpha=silhouette_alpha,
        )

    # 2) residential heatmap
    vals = res[plot_col].replace(0, float("nan")).dropna()
    norm = None
    if use_log and len(vals) > 0 and (vals > 0).all():
        norm = LogNorm(vmin=vals.min(), vmax=vals.max())

    res.plot(
        column=plot_col,
        ax=ax,
        cmap=cmap,
        edgecolor="none",
        linewidth=0.1,
        alpha=0.85,
        legend=True,
        norm=norm,
        legend_kwds={"label": cbar_label, "shrink": 0.7},
        zorder=2,
    )

    # 3) locality boundaries
    if show_region_boundaries:
        loc_colored.boundary.plot(
            ax=ax,
            color="black",
            linewidth=0.6,
            alpha=0.7,
            zorder=3,
        )

    # 4) road edges
    if show_roads and G is not None:
        before = set(ax.collections)

        fig, ax = draw_graph(
            G,
            ax=ax,
            node_size=0,
            edge_color=road_edge_color,
            edge_linewidth=road_edge_linewidth,
            # if draw_graph is osmnx.plot_graph or supports this:
            edge_alpha=road_alpha,
        )

        # fallback: force styling on newly added road collections
        new_collections = [c for c in ax.collections if c not in before]

        for c in new_collections:
            c.set_alpha(road_alpha)
            c.set_linewidth(road_edge_linewidth)
            c.set_color(road_edge_color)
            c.set_rasterized(True)   # important for PDF appearance

    # 5) region names
    if show_region_names and "name" in loc_colored.columns:
        for _, row in loc_colored.iterrows():
            pt = row.geometry.representative_point()
            ax.text(
                pt.x,
                pt.y,
                row["name"],
                fontsize=7,
                ha="center",
                va="center",
                color="black",
                bbox=dict(facecolor="white", alpha=0.65, edgecolor="none", pad=1),
                zorder=5,
            )

    ax.set_title(title)
    ax.axis("off")
    plt.tight_layout()
    if show_plot:
        plt.show()
    else:
        plt.close(fig)

    return fig, ax


import matplotlib.pyplot as plt
import geopandas as gpd
from matplotlib.colors import LogNorm

from Plotting.utils import assign_adjacent_colors
from Plotting.renderer import draw_graph


def plot_locality_population(
    gdf_localities,
    locality_to_population,
    G=None,
    *,
    locality_name_col="name",
    cmap="OrRd",
    figsize=(12, 12),
    title="Locality population",
    use_log=True,
    show_region_boundaries=True,
    show_region_names=True,
    show_roads=True,
    road_edge_color="black",
    road_edge_linewidth=0.4,
):
    loc = gdf_localities.copy()

    # attach locality population
    loc["population"] = loc[locality_name_col].map(locality_to_population)

    missing = loc[loc["population"].isna()]
    if len(missing) > 0:
        print("Warning: missing population for localities:")
        print(sorted(missing[locality_name_col].dropna().unique().tolist()))

    loc = loc[loc["population"].notna()].copy()

    vals = loc["population"].replace(0, float("nan")).dropna()
    norm = None
    if use_log and len(vals) > 0 and (vals > 0).all():
        norm = LogNorm(vmin=vals.min(), vmax=vals.max())

    fig, ax = plt.subplots(figsize=figsize)

    # locality polygons colored by full locality population
    loc.plot(
        column="population",
        ax=ax,
        cmap=cmap,
        edgecolor="black" if show_region_boundaries else "none",
        linewidth=0.6 if show_region_boundaries else 0,
        alpha=0.9,
        legend=True,
        norm=norm,
        legend_kwds={"label": "Population", "shrink": 0.7},
        zorder=2,
    )

    if show_roads and G is not None:
        fig, ax = draw_graph(
            G,
            ax=ax,
            node_size=0,
            edge_color=road_edge_color,
            edge_linewidth=road_edge_linewidth,
        )

    if show_region_names:
        for _, row in loc.iterrows():
            pt = row.geometry.representative_point()
            ax.text(
                pt.x,
                pt.y,
                row[locality_name_col],
                fontsize=7,
                ha="center",
                va="center",
                color="black",
                bbox=dict(facecolor="white", alpha=0.65, edgecolor="none", pad=1),
                zorder=5,
            )

    ax.set_title(title)
    ax.axis("off")
    plt.tight_layout()
    plt.show()

    return fig, ax, loc
