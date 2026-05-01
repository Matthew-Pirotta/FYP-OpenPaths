import copy

from networkx import MultiDiGraph

from constants import SafetyClass
from PreProcessing import enrich_attributes

from .segments import _as_lane_count, _canonical_geometry_key


def _is_arc_like(value) -> bool:
    return (
        isinstance(value, (tuple, list))
        and len(value) >= 3
        and not isinstance(value[0], (tuple, list, dict))
    )


def _as_arc(value) -> tuple | None:
    if value is None:
        return None
    if not _is_arc_like(value):
        return None
    return tuple(value[:3])


def _normalise_reallocation_events(diff_log) -> list:
    if diff_log is None:
        return []

    if hasattr(diff_log, "explode") and hasattr(diff_log, "dropna"):
        diff_log = diff_log.explode().dropna().tolist()

    events = []
    for item in diff_log:
        if item is None:
            continue
        if isinstance(item, list) and not _is_arc_like(item):
            events.extend(entry for entry in item if entry is not None)
        else:
            events.append(item)

    return events


def _existing_edges_between(G: MultiDiGraph, u, v) -> list[tuple]:
    if not G.has_edge(u, v):
        return []
    return [(u, v, k) for k in G[u][v].keys()]


def _unsimplified_segment_key(G: MultiDiGraph, edge: tuple):
    u, v, k = edge
    d = G[u][v][k]
    node_pair = tuple(sorted((u, v)))

    geom = d.get("geometry")
    if geom is None:
        return node_pair, None

    return node_pair, _canonical_geometry_key(d)


def _simplified_segment_arcs(G_simplified: MultiDiGraph, segment: tuple) -> list[tuple]:
    segment = _as_arc(segment)
    if segment is None:
        return []

    u, v, k = segment
    arcs = []
    if G_simplified.has_edge(u, v, k):
        arcs.append((u, v, k))
    if G_simplified.has_edge(v, u, k):
        arcs.append((v, u, k))

    return arcs


def _simplified_arcs_to_unsimplified_edges(
    G_simplified: MultiDiGraph,
    G_unsimplified: MultiDiGraph,
    arcs,
) -> list[tuple]:
    edges = []
    seen = set()

    for arc in arcs:
        u, v, k = arc
        if not G_simplified.has_edge(u, v, k):
            continue

        d_s = G_simplified[u][v][k]
        targets = d_s.get("merged_edges") or [(u, v)]

        for target in targets:
            u0, v0 = target[:2]
            for edge in _existing_edges_between(G_unsimplified, u0, v0):
                if edge in seen:
                    continue
                seen.add(edge)
                edges.append(edge)

    return edges


def _build_unsimplified_sumo_segment_state(G_unsimplified: MultiDiGraph) -> dict:
    """
    Group SUMO-facing one-way arcs back into directionless physical segments.

    The authoritative lane supply is the maximum lane tag across reciprocal arcs,
    not the sum. OSMnx often stores the same OSM way lane count on both directed
    copies of a two-way road; summing here would double-count the physical supply.
    """
    state = {}

    for edge in G_unsimplified.edges(keys=True):
        u, v, k = edge
        d = G_unsimplified[u][v][k]
        if d.get("highway") == "cycleway":
            continue

        seg_key = _unsimplified_segment_key(G_unsimplified, edge)
        lanes = _as_lane_count(d.get("car_lanes", d.get("lanes", 1)))
        entry = state.setdefault(
            seg_key,
            {
                "lanes_total": 0,
                "lanes_remaining": 0,
                "arcs": [],
            },
        )
        entry["lanes_total"] = max(entry["lanes_total"], lanes)
        entry["lanes_remaining"] = max(entry["lanes_remaining"], lanes)
        entry["arcs"].append(edge)

    return state


def _set_sumo_projection_attrs(G: MultiDiGraph, edge: tuple, car_lanes: int):
    u, v, k = edge
    d = G[u][v][k]

    car_lanes = max(0, int(car_lanes))
    d["car_lanes"] = car_lanes
    d["car_allowed"] = car_lanes > 0

    d["bike_allowed"] = True
    d["bike_lanes"] = max(1, _as_lane_count(d.get("bike_lanes", 0), default=0))
    d["bicycle"] = "designated"
    d["cycleway"] = "lane"
    d["safety"] = SafetyClass.PROTECTED
    d["risk_factor"] = float(
        enrich_attributes.safety_to_risk_factor_map[SafetyClass.PROTECTED]
    )

    if car_lanes == 0:
        d["highway"] = "cycleway"
        d["cycleway"] = "track"

    # SUMO/netconvert reads the OSM "lanes" tag. The reallocation removes one
    # car lane and records the cycle lane with OSM bike tags.
    d["lanes"] = max(car_lanes, 1)


def _reallocated_event_segment(event):
    if isinstance(event, dict):
        if event.get("event_type", "reallocated_segment") != "reallocated_segment":
            return None
        return _as_arc(event.get("segment", event.get("edge")))

    return _as_arc(event)


def apply_reallocation_events_to_unsimplified(
    G_simplified: MultiDiGraph,
    G_unsimplified: MultiDiGraph,
    diff_log,
    return_stats: bool = False,
):
    """
    Project simplified-graph reallocation events onto the unsimplified SUMO graph.

    SUMO/netconvert works with one-way edges, but the optimiser reallocates
    physical segments. For each segment event, decrement the segment lane supply
    once and then write that remaining lane count plus cycle-lane tags onto all
    unsimplified one-way edges belonging to the segment.
    """
    G_projected = copy.deepcopy(G_unsimplified)
    segment_state = _build_unsimplified_sumo_segment_state(G_projected)
    events = _normalise_reallocation_events(diff_log)

    stats = {
        "events_seen": len(events),
        "events_applied": 0,
        "segments_touched": 0,
        "missing_simplified_segments": [],
        "missing_unsimplified_segments": [],
    }

    for event in events:
        segment = _reallocated_event_segment(event)
        if segment is None:
            continue

        simplified_arcs = _simplified_segment_arcs(G_simplified, segment)
        if not simplified_arcs:
            stats["missing_simplified_segments"].append(segment)
            continue

        targets = _simplified_arcs_to_unsimplified_edges(
            G_simplified,
            G_projected,
            simplified_arcs,
        )
        touched_segment_keys = {
            _unsimplified_segment_key(G_projected, edge)
            for edge in targets
        }
        if not touched_segment_keys:
            stats["missing_unsimplified_segments"].append(segment)
            continue

        for seg_key in touched_segment_keys:
            entry = segment_state.get(seg_key)
            if entry is None:
                stats["missing_unsimplified_segments"].append(seg_key)
                continue

            entry["lanes_remaining"] = max(0, int(entry["lanes_remaining"]) - 1)

            for edge in entry["arcs"]:
                _set_sumo_projection_attrs(
                    G_projected,
                    edge,
                    car_lanes=entry["lanes_remaining"],
                )

        stats["events_applied"] += 1
        stats["segments_touched"] += len(touched_segment_keys)

    if return_stats:
        return G_projected, stats
    return G_projected
