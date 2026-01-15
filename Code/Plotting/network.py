import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from constants import SafetyClass
from Plotting.renderer import draw_graph


def plot_safety(G):
    safety_colors = {
        SafetyClass.VERY_SAFE: "magenta",
        SafetyClass.SAFE: "green",
        SafetyClass.MODERATE: "orange",
        SafetyClass.CAUTION: "red",
        SafetyClass.DANGEROUS: "darkred",
        SafetyClass.UNCLASSIFIED: "gray",
    }

    edge_colors = [
        safety_colors.get(d.get("safety"), "gray")
        for _, _, d in G.edges(data=True)
    ]

    fig, ax = draw_graph(G, edge_color=edge_colors)

    legend = [
        mpatches.Patch(
            color=color,
            label=cls.name.replace("_", " ").title()
        )
        for cls, color in safety_colors.items()
    ]
    ax.legend(handles=legend, title="Road Safety Classification")

    ax.set_title("Road Safety Classification")
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
