import copy
import matplotlib.pyplot as plt
import networkx as nx
from networkx import MultiDiGraph
import osmnx as ox
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.ticker import PercentFormatter
import numpy as np
import osmnx as ox
import pandas as pd
import libpysal
from pandas import Series
from shapely import LineString
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrow, Patch



import graph_util
from constants import SafetyClass

#TODO Clean the living hell out of this abomination of a script

def plot_road_classification(G_bike):
    safety_to_color_map = {
    SafetyClass.VERY_SAFE: "magenta",
    SafetyClass.SAFE: "green",
    SafetyClass.MODERATE: "yellow",
    SafetyClass.CAUTION: "orange",
    SafetyClass.DANGEROUS: "red",
    SafetyClass.UNSUITABLE: "brown",
    SafetyClass.UNCLASSIFIED: "gray"
    }

    edge_colors = []
    for _, _, data in G_bike.edges(data=True):
        color = safety_to_color_map.get(data.get("safety"), "gray")
        edge_colors.append(color)


    fig, ax = ox.plot_graph(G_bike, node_size=0, edge_color=edge_colors, edge_linewidth=0.5, show=False, close=False)
    # Create legend patches#
    legend_elements = [
    mpatches.Patch(color=color, label=label.replace("_", " ").title())
    for label, color in safety_to_color_map.items()
    ]

    ax.legend(handles=legend_elements, title="Road Safety Classification")
    plt.tight_layout()
    plt.show()


def plot_bool_atr(G_bike, attribute):
    allocability_to_colour = {
    True: "green",
    False: "red",
    }

    edge_colors = []
    for _, _, data in G_bike.edges(data=True):
        color = allocability_to_colour.get(data.get(attribute), "gray")
        edge_colors.append(color)

    edge_linewidth = [
        1 if d.get(attribute, False) else 0.5
        for _, _, d in G_bike.edges(data=True)
    ]



    fig, ax = ox.plot_graph(G_bike, node_size=0, edge_color=edge_colors, edge_linewidth=edge_linewidth, show=False, close=False)
    # Create legend patches#
    legend_elements = [
        mpatches.Patch(color=allocability_to_colour[True], label="True"),
        mpatches.Patch(color=allocability_to_colour[False], label="False"),
    ]
    ax.legend(handles=legend_elements, title=f"is {attribute}")
    plt.tight_layout()
    plt.show()

def plot_directionality(G):
    fig, ax = plt.subplots(figsize=(12, 12))

    # Prepare containers
    car_twoway = []
    car_oneway = []
    bike_twoway = []
    bike_oneway = []

    # Find forward/backward edges
    car_edges = {(u, v) for u, v, k, d in G.edges(keys=True, data=True) if d.get("car_allowed")}
    bike_edges = {(u, v) for u, v, k, d in G.edges(keys=True, data=True) if d.get("bike_allowed")}

    # -------- CAR TWO-WAY --------
    for u, v in car_edges:
        if (v, u) in car_edges:
            car_twoway.append((u, v))
        else:
            car_oneway.append((u, v))

    # -------- BIKE TWO-WAY --------
    for u, v in bike_edges:
        if (v, u) in bike_edges:
            bike_twoway.append((u, v))
        else:
            bike_oneway.append((u, v))

    def draw_arrowhead_mid(ax, geom, color="black", size=12):
        """
        Draw ONLY an arrowhead marker in the middle of a LineString.
        """
        xs, ys = geom.xy

        # Find midpoint index
        mid_idx = len(xs) // 2

        # Midpoint coordinates
        x_mid, y_mid = xs[mid_idx], ys[mid_idx]

        # A second point for direction (slightly before midpoint)
        if mid_idx == 0:
            x_prev, y_prev = xs[1], ys[1]
        else:
            x_prev, y_prev = xs[mid_idx - 1], ys[mid_idx - 1]

        ax.annotate(
            "",
            xy=(x_mid, y_mid),
            xytext=(x_prev, y_prev),
            arrowprops=dict(
                arrowstyle="-|>",   # head only
                color=color,        # black arrowhead
                mutation_scale=size,
                lw=0.0              # no tail line
            )
        )

    def draw_edges(edge_list, color, linewidth=1, arrows=False):
        for u, v in edge_list:
            data = G.get_edge_data(u, v)
            if data is None:
                continue
            d = data[list(data.keys())[0]]

            geom = d.get("geometry")
            if geom is None:
                geom = LineString([
                    (G.nodes[u]["x"], G.nodes[u]["y"]),
                    (G.nodes[v]["x"], G.nodes[v]["y"])
                ])

            xs, ys = geom.xy

            # Draw the line normally
            ax.plot(xs, ys, color=color, linewidth=linewidth)

            if arrows:
                draw_arrowhead_mid(ax, geom, color="black", size=12)

    def add_directionality_legend(ax):

        car_line = Line2D([0], [0], color="red", lw=2, label="Car - two-way")
        car_one  = Line2D([0], [0], color="red", lw=2, label="Car - one-way")

        bike_line = Line2D([0], [0], color="blue", lw=2, label="Bike - two-way")
        bike_one  = Line2D([0], [0], color="blue", lw=2, label="Bike - one-way")

        # Arrowhead marker only (triangle-like arrowhead)
        arrow_head = Line2D(
            [0], [0],
            color="black",
            marker="4",             # arrowhead marker
            markersize=14,
            linestyle="None",
            label="Direction"
        )

        handles = [
            car_line,
            car_one,
            bike_line,
            bike_one,
            arrow_head
        ]

        ax.legend(
            handles=handles,
            title="Road Directionality",
            loc="upper left",
            fontsize=8
        )


    # ---- DRAW EVERYTHING ----
    draw_edges(car_twoway, "red", linewidth=1.2)
    draw_edges(car_oneway, "red", linewidth=1.0, arrows=True)

    draw_edges(bike_twoway, "blue", linewidth=1.2)
    draw_edges(bike_oneway, "blue", linewidth=1.0, arrows=True)

    add_directionality_legend(ax)

    ax.set_title("Directionality of Car (Red) and Bike (Blue) Network")
    ax.set_axis_off()
    plt.show()



def color_hist(ax, values, bins, cmap, norm, title, xlabel, ylabel="Frequency", log=False):
    """Utility to draw a colored histogram with consistent style."""
    n, bins, patches = ax.hist(values, bins=bins, color='grey', alpha=0.7,
                               edgecolor='black', log=log)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(axis='y', alpha=0.4)
    ax.xaxis.set_major_formatter(PercentFormatter(xmax=1.0))
    if log:
        ax.set_yscale("log")

    # Color each bar by its bin center
    for left, right, patch in zip(bins[:-1], bins[1:], patches):
        color = cmap(norm(0.5 * (left + right)))
        patch.set_facecolor(color)

def plot_elevation(G):
    """Visualize elevation and grade distributions for a graph."""

    # -------------------------------
    # Elevation distribution
    # -------------------------------
    elevations = [d.get("elevation") for _, d in G.nodes(data=True) if d.get("elevation") is not None]

    for node, d in G.nodes(data=True):
        elevation = d.get("elevation") 
        if elevation is None:
            print(f"node {node} has elevation:{elevation} of type:{type(elevation)}")

    print(f"Fetched elevations for {len(elevations)} / {G.number_of_nodes()} nodes")

    plt.hist(elevations, bins=40, color='purple', edgecolor='black', alpha=0.8)
    plt.title("Node Elevation Distribution")
    plt.xlabel("Elevation (m)")
    plt.ylabel("Frequency")
    plt.grid(True, alpha=0.3)
    plt.show()

    #Elevation Map 
    cmap = plt.cm.plasma
    norm = mcolors.Normalize(vmin=min(elevations), vmax=max(elevations))

    nc = ox.plot.get_node_colors_by_attr(G, "elevation", cmap="plasma")
    fig, ax = ox.plot.plot_graph(G, node_color=nc, node_size=5, edge_color="#333333", bgcolor="k", show=False,close=False)
    
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    cbar = fig.colorbar(sm, ax=ax, fraction=0.03, pad=0.01)
    cbar.set_label("Elevation (m)")
    plt.show()



def plot_grades(G):
    cmap = plt.cm.coolwarm
    norm = mcolors.Normalize(vmin=-0.1, vmax=0.1, clip=False)

    # -------------------------------
    # Grade distribution
    # -------------------------------
    grade_values = [
        data["grade"] for _, _, _, data in G.edges(keys=True, data=True)
        if data.get("grade") is not None
    ]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    color_hist(ax1, grade_values, bins=16, cmap=cmap, norm=norm,
               title="Grade Frequency (log scale)", xlabel="Grade (%)", log=True)

    # Focused view on typical grades
    typical = [g for g in grade_values if -0.2 < g < 0.2]
    color_hist(ax2, typical, bins=40, cmap=cmap, norm=norm,
               title="Distribution of Typical Road Grades", xlabel="Grade (%)")
    plt.tight_layout()
    plt.show()

    """    
    print(f"Avg grade: {np.mean(grade_values):.3f}")
    print(f"Max grade: {np.max(grade_values):.2f}")
    print(f"Edges with grade > 50%: {sum(g > 0.5 for g in grade_values)}")"""

    # -------------------------------
    # Spatial grade visualization
    # -------------------------------
    edge_colors = [
        cmap(norm(d.get("grade", 0))) for _, _, _, d in G.edges(keys=True, data=True)
    ]

    fig, ax = ox.plot.plot_graph(
        G,
        edge_color=edge_colors,
        edge_linewidth=0.5,
        node_size=0,
        bgcolor="k",
        show=False,
        close=False
    )

    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    cbar = fig.colorbar(sm, ax=ax, fraction=0.03, pad=0.01,
                        extend='both', format=PercentFormatter(xmax=1.0, decimals=0))
    cbar.set_label("Edge Grade (%)")
    plt.show()

def plot_evaluation(df):
    fig, axs = plt.subplots(2,2, figsize=(12, 8))

    # --- Plot connectedness ---
    axs[0,0].plot(df["iteration"], df["num_components"], label="Number of Components", color="red")
    axs[0,0].set_xlabel("Iteration")
    axs[0,0].set_ylabel("Components")
    axs[0,0].set_title("Network Fragmentation Over Time")
    axs[0,0].legend()
    axs[0,0].grid(True, alpha=0.3)


    #-- Plot LCC growth ---
    axs[0,1].plot(df["iteration"], df["lcc_length"]/1000, label="LCC length (km)", color="green")
    axs[0,1].set_xlabel("Iteration")
    axs[0,1].set_ylabel("Length (km)")
    axs[0,1].set_title("Largest Connected Component Length Over Time")
    axs[0,1].legend()
    axs[0,1].grid(True, alpha=0.3)


    # --- Plot centrality metrics ---
   
    cols = ["mean_edge_betweenness", "mean_node_betweenness", ] #"mean_node_closeness"
    df_plot = df.sort_values("iteration")  # ensure correct order
    df_plot.plot(x="iteration", y=cols, ax=axs[1,0], linewidth=2)
    axs[1,0].set_xlabel("Iteration")
    axs[1,0].set_ylabel("Average Centrality Value")
    axs[1,0].set_title("Network Centrality Metrics During Simulation")
    axs[1,0].grid(True, alpha=0.3)

    # hide unused bottom-right subplot
    axs[1,1].axis("off")

    fig.tight_layout()
    plt.show()

def plot_network_evolution2(G_master, diff_log_series: pd.Series):
    diff_log = list(diff_log_series.explode())

    fig, ax = ox.plot_graph(
        G_master,
        node_size=0,
        edge_color="lightgray",
        edge_linewidth=0.3,
        show=False,
        close=False
    )

    cmap = plt.cm.plasma
    norm = plt.Normalize(0, len(diff_log))

    for i, diff_data in enumerate(diff_log):
        color = cmap(norm(i))
        diff_type = diff_data.get("type")
        u,v,k = diff_data.get("edge")
        if G_master.has_edge(u, v, k) and diff_type == "realloc":
            data = G_master[u][v][k]
            geom = data.get("geometry")
            if geom is None:
                # Fallback to straight line between node coords
                x1, y1 = G_master.nodes[u]["x"], G_master.nodes[u]["y"]
                x2, y2 = G_master.nodes[v]["x"], G_master.nodes[v]["y"]
                ax.plot([x1, x2], [y1, y2], color=color, linewidth=1.2)
            else:
                x, y = geom.xy
                ax.plot(x, y, color=color, linewidth=1.2)

    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    fig.colorbar(sm, ax=ax, label="Iteration")
    ax.set_title("Incremental Reallocations Over Time")
    plt.show()


def plot_snapshots(
    G_master:MultiDiGraph,
    diff_log_series: pd.Series,
    num_snapshots = 4,
    show_classification=True
):
    """Plot network snapshots at given iterations with optional safety classification coloring."""
    # Flatten nested list of diffs
    diff_log = list(diff_log_series.explode())
    snapshot_iters = np.linspace(0,len(diff_log), num_snapshots, dtype=int)

    fig, axs = plt.subplots(1, len(snapshot_iters), figsize=(4 * len(snapshot_iters), 6))
    G_temp = copy.deepcopy(G_master)


    # Define safety color map
    safety_to_color_map = {
        SafetyClass.VERY_SAFE: "magenta",
        SafetyClass.SAFE: "green",
        SafetyClass.MODERATE: "yellow",
        SafetyClass.CAUTION: "orange",
        SafetyClass.DANGEROUS: "red",
        SafetyClass.UNSUITABLE: "brown",
        SafetyClass.UNCLASSIFIED: "gray",
    }

    for ax, it in zip(axs, snapshot_iters):
        # Apply reallocations up to this iteration
        for diff_data in diff_log[:it]:
            diff_type = diff_data.get("type")
            edge = diff_data.get("edge")
            if diff_type == "fixed":
                graph_util.set_edge_attribute(G_temp, edge, "reallocatable", False)

            elif diff_type == "realloc":
                graph_util.reallocate_edge(G_temp, edge)


        # Choose coloring scheme
        if show_classification:
            edge_colors = [
                safety_to_color_map.get(d.get("safety"), "gray")
                for _, _, d in G_temp.edges(data=True)
            ]
        else:
            edge_colors = []
            for _, _, d in G_temp.edges(data=True):
                if d.get("safety") == SafetyClass.VERY_SAFE:
                    edge_colors.append("green")
                elif d.get("reallocatable") == False:
                    edge_colors.append("red")
                else:
                    edge_colors.append("gray")

        edge_linewidth = [
            1.2 if d.get("safety") == SafetyClass.VERY_SAFE else 0.5
            for _, _, d in G_temp.edges(data=True)
        ]

        ox.plot_graph(
            G_temp,
            node_size=0,
            edge_color=edge_colors,
            edge_linewidth=edge_linewidth,
            ax=ax,
            bgcolor="k",
            show=False,
            close=False,
        )

        ax.set_facecolor("k")        # ensure black background
        ax.figure.set_facecolor("k") # prevent white padding
        ax.set_title(f"Iteration {it}", color="white")

    # Add one shared legend for all subplots
    if show_classification:
        legend_elements = [
            mpatches.Patch(color=color, label=label.replace("_", " ").title())
            for label, color in safety_to_color_map.items()
        ]
        axs[-1].legend(
            handles=legend_elements,
            title="Road Safety Classification",
            loc="lower right",
            fontsize=8,
        )
    else:
        legend_elements = [
            mpatches.Patch(color="green", label="Bike infrastructure"),
            mpatches.Patch(color="red", label="Fixed Car lane"),
            mpatches.Patch(color="gray", label="Other"),
        ]
        axs[-1].legend(
            handles=legend_elements,
            title="Legend",
            loc="lower right",
            fontsize=8,
        )


    plt.tight_layout()
    plt.show()


def assign_adjacent_colors(gdf, cmap_name="tab20"):
    """Assign non-repeating colors to adjacent polygons using PySAL + NetworkX."""
    # Build adjacency
    w = libpysal.weights.Rook.from_dataframe(gdf, ids=gdf.index)

    # Greedy coloring
    G_adj = nx.Graph(w.neighbors)
    coloring = nx.coloring.greedy_color(G_adj, strategy="largest_first")

    # Attach color ids + map to hex
    gdf = gdf.copy()
    gdf["color_id"] = gdf.index.map(coloring)
    cmap = plt.cm.get_cmap(cmap_name, gdf["color_id"].max() + 1)
    gdf["color"] = gdf["color_id"].apply(lambda i: mcolors.to_hex(cmap(i)))

    return gdf

def plot_colored_polygons(
    gdf,
    G=None,
    figsize=(10, 10),
    alpha=0.7,
    edgecolor="black",
    linewidth=0.5,
    title=None,
    annotate=True,
):
    """Plot colored polygons, optionally overlaying an OSMnx graph."""
    
    # CRS check: if graph provided, match CRS
    if G is not None:
        gdf = gdf.to_crs(G.graph["crs"])

    fig, ax = plt.subplots(figsize=figsize)

    # --- Base layer: polygons ---
    gdf.plot(
        ax=ax,
        color=gdf["color"],
        alpha=alpha,
        edgecolor=edgecolor,
        linewidth=linewidth,
    )

    # --- Optional layer: OSMnx graph ---
    if G is not None:
        ox.plot_graph(
            G,
            ax=ax,
            node_size=0,
            edge_color="black",
            edge_linewidth=0.6,
            bgcolor="white",
            show=False,
            close=False,
        )

    # --- Optional annotation ---
    if annotate and "name" in gdf.columns:
        for _, row in gdf.iterrows():
            centroid = row.geometry.centroid
            ax.text(
                centroid.x,
                centroid.y,
                row["name"],
                fontsize=6,
                ha="center",
                va="center",
                color="black",
            )

    if title:
        ax.set_title(title, fontsize=14)

    ax.set_axis_off()
    plt.tight_layout()
    plt.show()



def plot_gdf_and_overlay(gdf, polygons_title, G=None, cmap_name="tab20", annotate=False):
    """
    Plot polygons with distinct colors, optionally overlaying an OSMnx graph.
    """
    gdf_colored = assign_adjacent_colors(gdf, cmap_name=cmap_name)

    plot_colored_polygons(
        gdf_colored,
        G=G,
        annotate=annotate,
        title=polygons_title,
    )

    return gdf_colored