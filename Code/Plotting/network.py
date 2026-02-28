import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
from constants import SafetyClass
from Plotting.renderer import draw_graph, PlotSettings
from typing import Unpack
from Demand import paths_util



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


def plot_od_allowed_corridor(
    G,
    G_seg,
    OD_list: list[tuple[int, int, float]],
    od_idx: int,
    seg_to_arcs: dict,
    arc_to_seg: dict,
    *,
    car_weight: str = "car_cost_current",
    bike_weight: str = "bike_cost_penalty",
    corridor_hops: int = 2,
    include_car_path: bool = True,
    include_bike_path: bool = True,
    show_other_edges: bool = True,
    seed_color: str = "darkgreen",
    corridor_color: str = "red",
    other_color: str = "gray",
    seed_width: float = 2.0,
    corridor_width: float = 1.2,
    other_width: float = 0.4,
    title: str | None = None,
    **kwargs: Unpack[PlotSettings],
):
    """
    Plot one OD's:
    - seed segments (mapped to arcs): seed_color
    - expanded corridor arcs: corridor_color
    - optionally all other edges: other_color
    """
    if od_idx < 0 or od_idx >= len(OD_list):
        raise IndexError(f"od_idx={od_idx} out of bounds for {len(OD_list)} ODs")
    o, d, _ = OD_list[od_idx]

    # Your current build_od_allowed_arcs returns (seed_segs, arcs_corr, od_allowed)
    # with seed/corridor corresponding to the processed OD.
    # So call it with a single-OD list.
    od_single = [OD_list[od_idx]]

    #TODO this should be a paramter that is passed
    seed_segs, arcs_corr, _ = paths_util.build_od_allowed_arcs(
        G_master=G,
        G_seg=G_seg,
        OD_list=od_single,
        seg_to_arcs=seg_to_arcs,
        arc_to_seg=arc_to_seg,
        car_weight=car_weight,
        bike_weight=bike_weight,
        corridor_hops=corridor_hops,
        include_car_path=include_car_path,
        include_bike_path=include_bike_path,
    )

    # Build disjoint arc classes at segment level so the same street geometry
    # cannot appear as both seed and corridor (e.g., opposite directions/keys).
    seed_seg_pairs = {(min(a, b), max(a, b)) for a, b, _ in seed_segs}

    corridor_seg_pairs: set[tuple[int, int]] = set()
    for arc in arcs_corr:
        seg = arc_to_seg.get(arc)
        if seg is None:
            continue
        a, b, _ = seg
        corridor_seg_pairs.add((min(a, b), max(a, b)))

    corridor_only_seg_pairs = corridor_seg_pairs - seed_seg_pairs

    seed_arcs: set[tuple[int, int, int]] = set()
    corridor_arcs: set[tuple[int, int, int]] = set()

    for seg, arcs in seg_to_arcs.items():
        a, b, _ = seg
        pair = (min(a, b), max(a, b))
        if pair in seed_seg_pairs:
            seed_arcs.update(arcs)
        elif pair in corridor_only_seg_pairs:
            corridor_arcs.update(arcs)

    # Fallback: include any corridor arcs missing from seg_to_arcs.
    for arc in arcs_corr:
        if arc in seed_arcs:
            continue
        seg = arc_to_seg.get(arc)
        if seg is None:
            corridor_arcs.add(arc)
            continue
        a, b, _ = seg
        if (min(a, b), max(a, b)) in corridor_only_seg_pairs:
            corridor_arcs.add(arc)

    edge_colors: list = []
    edge_widths: list[float] = []

    for u, v, k in G.edges(keys=True):
        arc = (u, v, k)

        if arc in seed_arcs:
            edge_colors.append(seed_color)
            edge_widths.append(seed_width)
        elif arc in corridor_arcs:
            edge_colors.append(corridor_color)
            edge_widths.append(corridor_width)
        elif show_other_edges:
            edge_colors.append(other_color)
            edge_widths.append(other_width)
        else:
            edge_colors.append((0, 0, 0, 0))  # transparent
            edge_widths.append(0.0)

    fig, ax = draw_graph(
        G,
        edge_color=edge_colors,
        edge_linewidth=edge_widths,
        **kwargs,
    )

    endpoint_handles = []
    for node, color, label in ((o, "red", "Start"), (d, "blue", "End")):
        node_data = G.nodes.get(node, {})
        if "x" in node_data and "y" in node_data:
            ax.scatter(
                node_data["x"],
                node_data["y"],
                marker="*",
                s=220,
                c=color,
                edgecolors="black",
                linewidths=0.8,
                zorder=6,
            )
            endpoint_handles.append(
                mlines.Line2D(
                    [],
                    [],
                    color=color,
                    marker="*",
                    markeredgecolor="black",
                    markeredgewidth=0.8,
                    linestyle="None",
                    markersize=12,
                    label=label,
                )
            )

    legend = [
        mpatches.Patch(color=seed_color, label="Seed segments"),
        mpatches.Patch(color=corridor_color, label="Expanded corridor"),
    ]
    if show_other_edges:
        legend.append(mpatches.Patch(color=other_color, label="Other edges"))
    legend.extend(endpoint_handles)

    ax.legend(handles=legend, loc="best")
    if title is None:
        title = f"OD corridor: {o} -> {d}"
    ax.set_title(title)
    ax.axis("off")
    fig.tight_layout()
    return fig, ax
