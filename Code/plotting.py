import matplotlib.pyplot as plt
import networkx as nx
import osmnx as ox
import matplotlib.patches as mpatches


def plot_road_classification(G_bike, edge_colours):
    fig, ax = ox.plot_graph(G_bike, node_size=0, edge_color=edge_colours, edge_linewidth=0.5, show=False, close=False)
    # Create legend patches
    legend_elements = [
        mpatches.Patch(color='green', label='Safe'),
        mpatches.Patch(color='yellow', label='Moderate'),
        mpatches.Patch(color='orange', label='Caution'),
        mpatches.Patch(color='red', label='Dangerous'),
        mpatches.Patch(color='brown', label='Unsuitable'),
        mpatches.Patch(color='gray', label='Unclassified')
    ]

    ax.legend(handles=legend_elements, loc='upper left', bbox_to_anchor=(1, 1))
    plt.tight_layout()
    plt.show()