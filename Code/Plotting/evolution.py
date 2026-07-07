import copy
from pathlib import Path

import geopandas as gpd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib.patches as mpatches
from matplotlib.colors import to_rgba
from shapely.geometry import LineString, MultiLineString
from shapely.ops import unary_union
import GraphUtil as graph_util

from Plotting import renderer
from Plotting.renderer import PlotSettings

from constants import SafetyClass

_VIDEO_OUTPUT_SUFFIXES = {".mp4", ".m4v", ".mov", ".webm"}

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
    return (
        isinstance(value, (tuple, list))
        and len(value) >= 3
        and not isinstance(value[0], (tuple, list, dict))
    )


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


def _frame_event_counts(num_events, iteration_step, include_initial=True):
    iteration_step = int(iteration_step)
    if iteration_step < 1:
        raise ValueError("iteration_step must be at least 1.")

    if num_events == 0:
        return [0]

    start = 0 if include_initial else min(iteration_step, num_events)
    frame_counts = list(range(start, num_events + 1, iteration_step))

    if frame_counts[-1] != num_events:
        frame_counts.append(num_events)

    return frame_counts


def _frame_iteration_label(events, event_count):
    if event_count <= 0:
        return 0

    event = events[event_count - 1]
    if isinstance(event, dict) and event.get("iteration") is not None:
        return event["iteration"]

    return event_count


def _hold_frame_repeats(hold_seconds, fps):
    hold_seconds = float(hold_seconds)
    if hold_seconds < 0:
        raise ValueError("hold seconds must be greater than or equal to 0.")

    if hold_seconds == 0:
        return 1

    return max(1, int(round(hold_seconds * fps)))


def _resolve_animation_writer(output_path, fps, writer=None, metadata=None):
    metadata = metadata or {}

    if writer is not None and not isinstance(writer, str):
        return writer

    writer_name = writer
    if writer_name is None:
        suffix = Path(output_path).suffix.lower()
        if suffix == ".gif":
            writer_name = "pillow"
        elif suffix in _VIDEO_OUTPUT_SUFFIXES:
            writer_name = "ffmpeg"
        else:
            raise ValueError(
                "output_path must end in .gif, .mp4, .m4v, .mov, or .webm "
                "unless a Matplotlib writer instance is provided."
            )

    if writer_name == "pillow":
        return animation.PillowWriter(fps=fps, metadata=metadata)

    if writer_name == "ffmpeg" and not animation.writers.is_available(writer_name):
        _configure_bundled_ffmpeg()

    if not animation.writers.is_available(writer_name):
        if writer_name == "ffmpeg":
            raise RuntimeError(
                "Saving MP4/MOV/WEBM needs ffmpeg available to Matplotlib. "
                "Install imageio-ffmpeg or system ffmpeg, then restart the notebook kernel."
            )
        raise RuntimeError(f"Matplotlib writer {writer_name!r} is not available.")

    return animation.writers[writer_name](fps=fps, metadata=metadata)


def _configure_bundled_ffmpeg():
    try:
        import imageio_ffmpeg
    except ImportError:
        return False

    try:
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    except RuntimeError:
        return False

    plt.rcParams["animation.ffmpeg_path"] = ffmpeg_path
    return True


def _normalise_video_output_path(output_path):
    output_path = Path(output_path)
    suffix = output_path.suffix.lower()

    if not suffix or suffix == ".gif":
        return output_path.with_suffix(".mp4")

    if suffix not in _VIDEO_OUTPUT_SUFFIXES:
        valid_suffixes = ", ".join(sorted(_VIDEO_OUTPUT_SUFFIXES))
        raise ValueError(f"output_path must end in one of {valid_suffixes} for video output.")

    return output_path


def _reject_gif_writer(writer):
    if isinstance(writer, str) and writer.lower() == "pillow":
        raise ValueError("Pillow writes GIF animations; use ffmpeg or another video writer.")

    if isinstance(writer, animation.PillowWriter):
        raise ValueError("PillowWriter writes GIF animations; use a video writer instead.")


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
        return []

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
        return []

    return graph_util.reallocate_segment_dedicated(
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


def _edge_geometry(G, u, v, data):
    geom = data.get("geometry")
    if geom is not None:
        return geom

    return LineString(
        [
            (G.nodes[u]["x"], G.nodes[u]["y"]),
            (G.nodes[v]["x"], G.nodes[v]["y"]),
        ]
    )


def _iter_line_geometries(geom):
    if geom is None or geom.is_empty:
        return

    if geom.geom_type in {"LineString", "LinearRing"}:
        if geom.length > 0:
            yield geom
        return

    if geom.geom_type == "MultiLineString":
        for line in geom.geoms:
            if line.length > 0:
                yield line
        return

    for part in getattr(geom, "geoms", []):
        yield from _iter_line_geometries(part)


def _as_line_geometry(geom):
    lines = list(_iter_line_geometries(geom))
    if not lines:
        return None

    if len(lines) == 1:
        return lines[0]

    return MultiLineString(lines)


def _resolve_polygon_path(polygon_path):
    path = Path(polygon_path)
    candidates = [path]

    if not path.is_absolute():
        candidates.extend(
            [
                Path.cwd() / path,
                Path(__file__).resolve().parents[1] / path,
                Path(__file__).resolve().parents[2] / path,
            ]
        )

    for candidate in candidates:
        if candidate.exists():
            return candidate

    searched = ", ".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(f"Could not find polygon file {polygon_path!r}. Searched: {searched}")


def _load_polygon(polygon_path, target_crs):
    polygon_gdf = gpd.read_file(_resolve_polygon_path(polygon_path))
    polygon_gdf = polygon_gdf[polygon_gdf.geometry.notna()]

    if polygon_gdf.empty:
        raise ValueError(f"Polygon file {polygon_path!r} contains no geometries.")

    if polygon_gdf.crs is None:
        polygon_gdf = polygon_gdf.set_crs("EPSG:4326")

    if target_crs is not None:
        polygon_gdf = polygon_gdf.to_crs(target_crs)

    polygon = unary_union(polygon_gdf.geometry)
    if polygon.is_empty:
        raise ValueError(f"Polygon file {polygon_path!r} contains only empty geometries.")

    return polygon


def _clip_graph_to_polygon(G, polygon):
    edge_geometries = {}

    for u, v, k, data in G.edges(keys=True, data=True):
        geom = _edge_geometry(G, u, v, data)
        if not geom.intersects(polygon):
            continue

        clipped = _as_line_geometry(geom.intersection(polygon))
        if clipped is not None:
            edge_geometries[(u, v, k)] = clipped

    G_clipped = G.edge_subgraph(edge_geometries.keys()).copy()

    for (u, v, k), geom in edge_geometries.items():
        G_clipped[u][v][k]["geometry"] = geom

    return G_clipped


def _plot_edge_geometry(ax, G, edge, *, color, linewidth, alpha=1.0, zorder=3):
    u, v, k = edge
    if not G.has_edge(u, v, k):
        return

    data = G[u][v][k]
    geom = _edge_geometry(G, u, v, data)

    for line in _iter_line_geometries(geom):
        x, y = line.xy
        ax.plot(x, y, color=color, linewidth=linewidth, alpha=alpha, zorder=zorder)


def plot_proposed_cycling_network(
    G_master,
    G_optimised,
    *,
    initial_safety_classes=None,
    initial_color="#7BC87A",        # light green — existing cycling
    proposed_color="#1A6B2F",       # dark green — new additions
    initial_fixed_color="#DBB3A1",  # light orange-red — fixed existing
    newly_fixed_color="#C0242A",    # strong red — newly fixed
    other_color="#CDC8C2",         
    initial_linewidth=1.5,
    proposed_linewidth=2,
    initial_fixed_linewidth=0.5,
    newly_fixed_linewidth=1,
    other_linewidth=0.5,
    initial_alpha=0.95,
    proposed_alpha=1.0,
    initial_fixed_alpha=0.8,
    newly_fixed_alpha=1.0,
    other_alpha=0.7,
    region=None,
    polygon_path=None,
    title="",
    legend=True,
    show=True,
    ax=None,
    close=None,
    **kwargs: PlotSettings,
):
    """
    Plot the original cycling network, newly proposed cycling infrastructure,
    fixed non-reallocatable road edges, and all other network edges.

    Newly proposed infrastructure is inferred by set difference:
    cycling edges in G_optimised minus cycling edges in G_master.

    Fixed edges are road edges marked ``reallocatable=False``. Initial fixed
    edges were already fixed in G_master. Newly fixed edges were reallocatable
    in G_master but are fixed in G_optimised.

    By default, cycling edges follow this project's protected subgraph
    convention: SafetyClass.PROTECTED and SafetyClass.PAINTED.
    Pass initial_safety_classes=(SafetyClass.PROTECTED,) for strictly protected
    infrastructure only.

    Pass region="Northern Harbour" to plot only edges intersecting that region.
    Pass polygon_path="my_area.geojson" to clip the plot to a custom polygon.
    """
    if region is not None:
        G_master = graph_util.make_region_subgraph(G_master, region)
        G_optimised = graph_util.make_region_subgraph(G_optimised, region)

    clip_polygon = None
    if polygon_path is not None:
        clip_polygon = _load_polygon(polygon_path, G_optimised.graph.get("crs"))
        G_master = _clip_graph_to_polygon(G_master, clip_polygon)
        G_optimised = _clip_graph_to_polygon(G_optimised, clip_polygon)

        if len(G_optimised.edges) == 0:
            raise ValueError(f"No optimised graph edges intersect polygon {polygon_path!r}.")

    if initial_safety_classes is None:
        initial_safety_classes = {SafetyClass.PROTECTED, SafetyClass.PAINTED}
    else:
        initial_safety_classes = {
            _normalise_safety(cls)
            for cls in initial_safety_classes
        }

    master_cycling_edges = {
        (u, v, k)
        for u, v, k, d in G_master.edges(keys=True, data=True)
        if _normalise_safety(d.get("safety")) in initial_safety_classes
    }

    optimised_cycling_edges = {
        (u, v, k)
        for u, v, k, d in G_optimised.edges(keys=True, data=True)
        if _normalise_safety(d.get("safety")) in initial_safety_classes
    }

    optimised_edge_keys = set(G_optimised.edges(keys=True))
    initial_edges = master_cycling_edges & optimised_edge_keys
    proposed_edges = optimised_cycling_edges - master_cycling_edges

    master_fixed_edges = {
        (u, v, k)
        for u, v, k, d in G_master.edges(keys=True, data=True)
        if d.get("reallocatable") is False and d.get("highway") != "cycleway"
    }
    master_reallocatable_edges = {
        (u, v, k)
        for u, v, k, d in G_master.edges(keys=True, data=True)
        if d.get("reallocatable") is True and d.get("highway") != "cycleway"
    }
    optimised_fixed_edges = {
        (u, v, k)
        for u, v, k, d in G_optimised.edges(keys=True, data=True)
        if d.get("reallocatable") is False and d.get("highway") != "cycleway"
    }

    initial_fixed_edges = master_fixed_edges & optimised_fixed_edges
    newly_fixed_edges = master_reallocatable_edges & optimised_fixed_edges

    draw_kwargs = dict(kwargs)
    draw_kwargs.setdefault("node_size", 0)
    draw_kwargs["edge_color"] = to_rgba(other_color, other_alpha)
    draw_kwargs["edge_linewidth"] = other_linewidth
    if clip_polygon is not None:
        draw_kwargs.setdefault("bbox", clip_polygon.bounds)

    created_figure = ax is None
    fig, ax = renderer.draw_graph(G_optimised, ax=ax, **draw_kwargs)

    for edge in initial_fixed_edges:
        _plot_edge_geometry(
            ax,
            G_optimised,
            edge,
            color=initial_fixed_color,
            linewidth=initial_fixed_linewidth,
            alpha=initial_fixed_alpha,
            zorder=2,
        )

    for edge in newly_fixed_edges:
        _plot_edge_geometry(
            ax,
            G_optimised,
            edge,
            color=newly_fixed_color,
            linewidth=newly_fixed_linewidth,
            alpha=newly_fixed_alpha,
            zorder=3,
        )

    for edge in initial_edges:
        _plot_edge_geometry(
            ax,
            G_optimised,
            edge,
            color=initial_color,
            linewidth=initial_linewidth,
            alpha=initial_alpha,
            zorder=4,
        )

    for edge in proposed_edges:
        _plot_edge_geometry(
            ax,
            G_optimised,
            edge,
            color=proposed_color,
            linewidth=proposed_linewidth,
            alpha=proposed_alpha,
            zorder=5,
        )

    if title:
        ax.set_title(title, fontsize=24)

    if legend:
        legend_elements = [
            mpatches.Patch(color=initial_color, label="Initial cycling network"),
            mpatches.Patch(color=proposed_color, label="Proposed cycling infrastructure"),
            mpatches.Patch(color=initial_fixed_color, label="Initial fixed non-reallocatable roads"),
            mpatches.Patch(color=newly_fixed_color, label="Newly fixed non-reallocatable roads"),
            mpatches.Patch(color=other_color, label="Other network"),
        ]
        ax.legend(handles=legend_elements, loc="upper right", fontsize=12)

    ax.set_axis_off()
    fig.tight_layout()

    should_close = close if close is not None else created_figure
    if show:
        plt.show()
    elif should_close:
        plt.close(fig)

    return fig, ax


def save_proposed_network_evolution_video(
    G_master,
    diff_log,
    output_path,
    *,
    fps=8,
    iteration_step=1,
    include_initial=True,
    initial_hold_seconds=1.5,
    final_hold_seconds=2.5,
    legend=True,
    title=None,
    title_template="Iteration {iteration}",
    writer=None,
    metadata=None,
    **plot_kwargs,
):
    """
    Save an animation of the proposed cycling network as optimizer events replay.

    Parameters
    ----------
    fps : int | float
        Playback speed. Higher values make the saved animation faster.
    iteration_step : int
        Number of logged optimizer events to advance between frames. Use 1 to
        draw every event, or a larger value to skip ahead and render faster.
    include_initial : bool
        Include the untouched master graph as the first frame.
    initial_hold_seconds : int | float
        Approximate time to hold the first frame in the saved video.
    final_hold_seconds : int | float
        Approximate time to hold the final frame in the saved video.
    legend : bool
        Draw the same legend used by ``plot_proposed_cycling_network``.
    title_template : str
        Format string for the visible iteration label. Available fields are
        iteration, event_count, total_events, frame, and total_frames.
    output_path : str | pathlib.Path
        Video file path. Missing extensions and ``.gif`` paths are saved as
        ``.mp4``.

    Remaining keyword arguments are forwarded to
    ``plot_proposed_cycling_network``.
    """
    fps = float(fps)
    if fps <= 0:
        raise ValueError("fps must be greater than 0.")
    initial_repeats = _hold_frame_repeats(initial_hold_seconds, fps)
    final_repeats = _hold_frame_repeats(final_hold_seconds, fps)

    events = _normalise_diff_log(diff_log)
    frame_counts = _frame_event_counts(
        len(events),
        iteration_step=iteration_step,
        include_initial=include_initial,
    )

    output_path = _normalise_video_output_path(output_path)
    _reject_gif_writer(writer)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    plot_kwargs = dict(plot_kwargs)
    base_title = plot_kwargs.pop("title", title)
    plot_kwargs.pop("show", None)
    plot_kwargs.pop("ax", None)
    plot_kwargs.pop("close", None)

    fig_size = plot_kwargs.get("fig_size", (12, 12))
    dpi = plot_kwargs.get("dpi", renderer.DEFAULTS["dpi"])
    movie_writer = _resolve_animation_writer(
        output_path,
        fps=fps,
        writer=writer,
        metadata=metadata,
    )

    G_working = copy.deepcopy(G_master)
    segment_inventory = graph_util.build_segment_inventory(G_working)
    _, seg_to_arcs = graph_util.build_arc_to_segment_map(G_working)

    fig, ax = plt.subplots(figsize=fig_size, dpi=dpi)
    previous_event_count = 0

    with movie_writer.saving(fig, str(output_path), dpi=dpi):
        for frame_index, event_count in enumerate(frame_counts, start=1):
            for event in events[previous_event_count:event_count]:
                _apply_snapshot_event(
                    G_working,
                    event,
                    segment_inventory,
                    seg_to_arcs,
                )
            previous_event_count = event_count

            iteration_label = _frame_iteration_label(events, event_count)
            frame_title = title_template.format(
                iteration=iteration_label,
                event_count=event_count,
                total_events=len(events),
                frame=frame_index,
                total_frames=len(frame_counts),
            )
            if base_title:
                frame_title = f"{base_title}\n{frame_title}"

            ax.clear()
            plot_proposed_cycling_network(
                G_master,
                G_working,
                title=frame_title,
                legend=legend,
                show=False,
                ax=ax,
                close=False,
                **plot_kwargs,
            )
            if len(frame_counts) == 1:
                repeat_count = max(initial_repeats, final_repeats)
            elif frame_index == 1:
                repeat_count = initial_repeats
            elif frame_index == len(frame_counts):
                repeat_count = final_repeats
            else:
                repeat_count = 1

            for _ in range(repeat_count):
                movie_writer.grab_frame()

    plt.close(fig)
    return output_path


def plot_network_evolution(G_master, diff_log, **kwargs:PlotSettings):
    """Plot incremental reallocations over time, colored by iteration."""
    events = _normalise_diff_log(diff_log)
    
    # Merge defaults with overrides
    settings = renderer.DEFAULTS | kwargs

    fig, ax = renderer.draw_graph(
        G_master,
        **settings
    )

    cmap = plt.cm.plasma
    norm = plt.Normalize(0, max(1, len(events)))

    for i, event in enumerate(events):
        if (
            isinstance(event, dict)
            and event.get("event_type") == "marked_segment_not_reallocatable"
        ):
            continue

        edge = _coerce_event_segment(event)
        if edge is None:
            continue

        u, v, k = edge
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
