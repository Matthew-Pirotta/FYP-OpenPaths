import copy
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import graph_util

from Plotting import renderer
from Plotting.renderer import PlotSettings

from constants import SafetyClass

SAFETY_TO_COLOR_MAP = {
    SafetyClass.PROTECTED: "magenta",
    SafetyClass.PAINTED: "green",
    SafetyClass.LOW_CAR_FLOW: "orange",
    SafetyClass.CAUTION: "red",
    SafetyClass.HIGH_CAR_FLOW: "darkred",
    SafetyClass.UNSUITABLE: "black",
    SafetyClass.UNCLASSIFIED: "gray",
}


def _is_edge_like(value) -> bool:
    return isinstance(value, (tuple, list)) and len(value) >= 3 and not isinstance(value[0], dict)


def _normalise_diff_log(diff_log) -> list:
    if diff_log is None:
        return []

    if hasattr(diff_log, "explode") and hasattr(diff_log, "dropna"):
        diff_log = diff_log.explode().dropna().tolist()

    events = []
    for item in diff_log:
        if item is None:
            continue

        # Accept a non-exploded dataframe column containing lists of event dicts.
        if isinstance(item, list) and not _is_edge_like(item):
            events.extend(entry for entry in item if entry is not None)
        else:
            events.append(item)

    return events


def _coerce_event_segment(event):
    if isinstance(event, dict):
        segment = event.get("segment", event.get("edge"))
    else:
        segment = event

    if _is_edge_like(segment):
        return tuple(segment[:3])

    return None


def _normalise_safety(value):
    if isinstance(value, SafetyClass):
        return value

    if isinstance(value, str):
        try:
            return SafetyClass(value)
        except ValueError:
            try:
                return SafetyClass[value]
            except KeyError:
                return value

    return value


def _apply_snapshot_event(G, event, segment_inventory, seg_to_arcs):
    segment = _coerce_event_segment(event)
    if segment is None:
        return

    event_type = (
        event.get("event_type", "reallocated_segment")
        if isinstance(event, dict)
        else "reallocated_segment"
    )
    keep_arc = event.get("keep_arc") if isinstance(event, dict) else None
    if keep_arc is not None:
        keep_arc = tuple(keep_arc[:3])

    if segment not in seg_to_arcs:
        raise KeyError(f"Snapshot event references segment {segment}, which is not in the plotted graph.")

    if event_type == "marked_segment_not_reallocatable":
        if segment in segment_inventory:
            segment_inventory[segment]["lanes_remaining"] = 0
        for u, v, k in seg_to_arcs[segment]:
            if G.has_edge(u, v, k):
                G[u][v][k]["reallocatable"] = False
        return

    graph_util.reallocate_segment_dedicated(
        G,
        segment,
        segment_inventory,
        seg_to_arcs,
        keep_arc=keep_arc,
    )


def _edge_safety_colors(G):
    return [
        SAFETY_TO_COLOR_MAP.get(_normalise_safety(d.get("safety")), "gray")
        for _, _, _, d in G.edges(keys=True, data=True)
    ]


def _edge_status_colors(G):
    bike_infra = {SafetyClass.PROTECTED, SafetyClass.PAINTED}
    colors = []
    for _, _, _, d in G.edges(keys=True, data=True):
        safety = _normalise_safety(d.get("safety"))
        if safety in bike_infra:
            colors.append("green")
        elif d.get("reallocatable") is False:
            colors.append("red")
        else:
            colors.append("gray")
    return colors


def _edge_widths(G):
    bike_infra = {SafetyClass.PROTECTED, SafetyClass.PAINTED}
    return [
        1.2 if _normalise_safety(d.get("safety")) in bike_infra else 0.5
        for _, _, _, d in G.edges(keys=True, data=True)
    ]


def plot_snapshots(
    G_master,
    diff_log,
    num_snapshots=4,
    show_classification=True,
    *,
    show=True,
    **kwargs: PlotSettings,
):
    """Plot network snapshots by replaying optimizer segment events."""
    events = _normalise_diff_log(diff_log)
    num_snapshots = max(1, min(int(num_snapshots), len(events) + 1))
    snapshot_iters = np.unique(np.linspace(0, len(events), num_snapshots, dtype=int))

    fig_size = kwargs.pop("fig_size", (4 * len(snapshot_iters), 6))
    dpi = kwargs.get("dpi", renderer.DEFAULTS["dpi"])
    fig, axs = plt.subplots(1, len(snapshot_iters), figsize=fig_size, dpi=dpi)
    axs = np.atleast_1d(axs)

    for ax, it in zip(axs, snapshot_iters):
        G_temp = copy.deepcopy(G_master)
        segment_inventory = graph_util.build_segment_inventory(G_temp)
        _, seg_to_arcs = graph_util.build_arc_to_segment_map(G_temp)

        for event in events[:it]:
            _apply_snapshot_event(G_temp, event, segment_inventory, seg_to_arcs)

        if show_classification:
            edge_colors = _edge_safety_colors(G_temp)
        else:
            edge_colors = _edge_status_colors(G_temp)

        draw_kwargs = dict(kwargs)
        draw_kwargs.setdefault("node_size", 0)
        draw_kwargs["edge_color"] = edge_colors
        draw_kwargs["edge_linewidth"] = _edge_widths(G_temp)

        _, ax = renderer.draw_graph(
            G_temp,
            ax=ax,
            **draw_kwargs,
        )

        ax.set_title(f"Iteration {it}")
        ax.axis("off")

    # Shared legend
    if show_classification:
        legend_elements = [
            mpatches.Patch(color=color, label=cls.name.replace("_", " ").title())
            for cls, color in SAFETY_TO_COLOR_MAP.items()
        ]
    else:
        legend_elements = [
            mpatches.Patch(color="green", label="Bike infrastructure"),
            mpatches.Patch(color="red", label="Not reallocatable"),
            mpatches.Patch(color="gray", label="Other"),
        ]

    axs[-1].legend(
        handles=legend_elements,
        title="Legend",
        loc="lower right",
        fontsize=8,
    )

    fig.tight_layout()
    if show:
        plt.show()

    return fig, axs


def plot_network_evolution(G_master, diff_log, **kwargs:PlotSettings):
    """Plot incremental reallocations over time, colored by iteration."""
    
    # Merge defaults with overrides
    settings = renderer.DEFAULTS | kwargs

    fig, ax = renderer.draw_graph(
        G_master,
        **settings
    )

    cmap = plt.cm.plasma
    norm = plt.Normalize(0, len(diff_log))

    for i, diff_data in enumerate(diff_log):
        u, v, k = diff_data
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

    return fig,ax
