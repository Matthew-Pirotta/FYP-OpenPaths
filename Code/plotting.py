import matplotlib.pyplot as plt
import networkx as nx
import osmnx as ox
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.ticker import PercentFormatter
import numpy as np
import osmnx as ox

from constants import SafetyClass

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
    axs[0,0].plot(df.index, df["num_components"], label="Number of Components", color="red")
    axs[0,0].set_xlabel("Iteration")
    axs[0,0].set_ylabel("Components")
    axs[0,0].set_title("Network Fragmentation Over Time")
    axs[0,0].legend()
    axs[0,0].grid(True, alpha=0.3)


    #-- Plot LCC growth ---
    axs[0,1].plot(df.index, df["lcc_length"]/1000, label="LCC length (km)", color="green")
    axs[0,1].set_xlabel("Iteration")
    axs[0,1].set_ylabel("Length (km)")
    axs[0,1].set_title("Largest Connected Component Length Over Time")
    axs[0,1].legend()
    axs[0,1].grid(True, alpha=0.3)


    # --- Plot centrality metrics ---
    df[["mean_edge_betweenness", "mean_node_betweenness", "mean_node_closeness"]].plot(
        ax=axs[1,0],
        linewidth=2
    )
    axs[1,0].set_xlabel("Iteration")
    axs[1,0].set_ylabel("Average Centrality Value")
    axs[1,0].set_title("Network Centrality Metrics During Simulation")
    axs[1,0].grid(True, alpha=0.3)

    # hide unused bottom-right subplot
    axs[1,1].axis("off")

    fig.tight_layout()
    plt.show()