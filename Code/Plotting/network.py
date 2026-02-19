import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from constants import SafetyClass
from Plotting.renderer import draw_graph, PlotSettings
from typing import Unpack

def plot_categorical_attr(
    G,
    attr: str,
    mapping: dict,
    default_color: str = "gray",
    title: str | None = None,
    legend_title: str | None = None,
    **kwargs: Unpack[PlotSettings]
):
    """
    Generalized plotter for categorical edge attributes.
    
    :param G: The graph.
    :param attr: The edge attribute key (e.g., "safety" or "highway").
    :param mapping: Dict mapping attribute values to colors.
    :param default_color: Color to use if attribute is missing or not in mapping.
    :param title: Plot title.
    :param legend_title: Title for the color legend.
    :param kwargs: Visual settings passed to draw_graph (node_size, fig_size, etc.).
    """
    
    # 1. Generate edge colors based on the mapping
    edge_colors = [
        mapping.get(d.get(attr), default_color)
        for _, _, d in G.edges(data=True)
    ]

    # 2. Use our existing draw_graph helper
    fig, ax = draw_graph(G, edge_color=edge_colors, **kwargs)

    # 3. Build the Legend
    legend_elements = [
        mpatches.Patch(
            color=color, 
            label=str(val).replace("_", " ").title() if hasattr(val, 'name') else str(val).title()
        )
        for val, color in mapping.items()
    ]
    
    ax.legend(
        handles=legend_elements, 
        title=legend_title or attr.replace("_", " ").title(),
        loc="best"
    )

    if title:
        ax.set_title(title)
        
    ax.axis("off")
    fig.tight_layout()
    plt.show()


def plot_boolean_attribute(G, attribute):
    color_map = {True: "green", False: "red"}

    edge_colors = [
        color_map.get(d.get(attribute), "gray")
        for _, _, d in G.edges(data=True)
    ]
    edge_widths = [
        1.2 if d.get(attribute) else 0.5
        for _, _, d in G.edges(data=True)
    ]

    fig, ax = draw_graph(
        G,
        edge_color=edge_colors,
        edge_linewidth=edge_widths,
    )

    legend = [
        mpatches.Patch(color="green", label="True"),
        mpatches.Patch(color="red", label="False"),
    ]
    ax.legend(handles=legend, title=attribute)

    ax.set_title(f"Edge attribute: {attribute}")
    ax.axis("off")
    fig.tight_layout()
    plt.show()
