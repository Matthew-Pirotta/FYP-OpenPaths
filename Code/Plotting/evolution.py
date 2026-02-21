import copy
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import graph_util

from Plotting.renderer import draw_graph
from constants import SafetyClass

#TODO remove diff_type
def plot_snapshots(G_master, diff_log, num_snapshots=4, show_classification=True):
    """Plot network snapshots at given iterations with optional safety classification coloring."""
    snapshot_iters = np.linspace(0, len(diff_log), num_snapshots, dtype=int)

    fig, axs = plt.subplots(1, len(snapshot_iters), figsize=(4 * len(snapshot_iters), 6))

    safety_to_color_map = {
        SafetyClass.VERY_SAFE: "magenta",
        SafetyClass.SAFE: "green",
        SafetyClass.MODERATE: "orange",
        SafetyClass.CAUTION: "red",
        SafetyClass.DANGEROUS: "darkred",
        SafetyClass.UNCLASSIFIED: "gray",
    }

    for ax, it in zip(axs, snapshot_iters):
        # Start from a fresh copy per snapshot
        G_temp = copy.deepcopy(G_master)

        # Apply reallocations up to this iteration
        for diff_data in diff_log[:it]:
            edge = diff_data.get("edge")

            graph_util.reallocate_edge_to_fietsstraat(G_temp, edge)

        # Edge coloring
        if show_classification:
            edge_colors = [
                safety_to_color_map.get(d.get("safety"), "gray")
                for _, _, d in G_temp.edges(data=True)
            ]
        else:
            edge_colors = [
                "green" if d.get("safety") in {SafetyClass.VERY_SAFE, SafetyClass.SAFE}
                else "red" if d.get("reallocatable") is False
                else "gray"
                for _, _, d in G_temp.edges(data=True)
            ]

        edge_linewidth = [
            1.2 if d.get("safety") in {SafetyClass.VERY_SAFE, SafetyClass.SAFE} else 0.5
            for _, _, d in G_temp.edges(data=True)
        ]

        _, ax = draw_graph(
            G_temp,
            ax=ax,
            node_size=0,
            edge_color=edge_colors,
            edge_linewidth=edge_linewidth,
        )

        ax.set_title(f"Iteration {it}")
        ax.axis("off")

    # Shared legend
    if show_classification:
        legend_elements = [
            mpatches.Patch(color=color, label=cls.name.replace("_", " ").title())
            for cls, color in safety_to_color_map.items()
        ]
    else:
        legend_elements = [
            mpatches.Patch(color="green", label="Bike infrastructure"),
            mpatches.Patch(color="gray", label="Other"),
        ]

    axs[-1].legend(
        handles=legend_elements,
        title="Legend",
        loc="lower right",
        fontsize=8,
    )

    fig.tight_layout()
    plt.show()


def plot_network_evolution(G_master, diff_log):
    """Plot incremental reallocations over time, colored by iteration."""

    fig, ax = draw_graph(
        G_master,
        node_size=0,
        edge_linewidth=0.3,
    )

    cmap = plt.cm.plasma
    norm = plt.Normalize(0, len(diff_log))

    for i, diff_data in enumerate(diff_log):
        u, v, k = diff_data.get("edge")
        if not G_master.has_edge(u, v, k):
            continue

        color = cmap(norm(i))
        data = G_master[u][v][k]
        geom = data.get("geometry")

        if geom is None:
            x1, y1 = G_master.nodes[u]["x"], G_master.nodes[u]["y"]
            x2, y2 = G_master.nodes[v]["x"], G_master.nodes[v]["y"]
            ax.plot([x1, x2], [y1, y2], color=color, linewidth=1.2)
        else:
            x, y = geom.xy
            ax.plot(x, y, color=color, linewidth=1.2)

    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    fig.colorbar(
        sm,
        ax=ax,
        label="Iteration",
        fraction=0.03,
        pad=0.01,
    )

    ax.set_title("Incremental Reallocations Over Time")
    ax.axis("off")

    fig.tight_layout()
    plt.show()
