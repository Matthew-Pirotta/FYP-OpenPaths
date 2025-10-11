import matplotlib.pyplot as plt
import networkx as nx
import osmnx as ox
import matplotlib.patches as mpatches


def plot_road_classification(G_bike:nx.MultiDiGraph):
    safety_to_color_map = {
    "very_safe": "magenta",
    "safe": "green",
    "moderate": "yellow",
    "caution": "orange",
    "dangerous": "red",
    "unsuitable": "brown",
    "unclassified": "gray"
    }

    edge_colors = []
    for _, _, _, data in G_bike.edges(keys=True, data=True):
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