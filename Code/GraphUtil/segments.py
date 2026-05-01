from collections import defaultdict

from networkx import MultiDiGraph
import osmnx as ox


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def _as_lane_count(value, default: int = 1) -> int:
    if value is None:
        return default
    if isinstance(value, (list, tuple)):
        return sum(_as_lane_count(v, default=0) for v in value) or default
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return default
        if ";" in value:
            return sum(_as_lane_count(v, default=0) for v in value.split(";")) or default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def build_segment_inventory(G_directed: MultiDiGraph) -> dict:
    """
    Build authoritative segment inventory from OSMnx undirected graph.

    Returns
    -------
    dict[seg_id -> dict]
        seg_id is (u, v, k) in undirected graph space.
        Each entry contains authoritative physical lane supply and metadata.
    """
    Gu = ox.convert.to_undirected(G_directed)

    inventory = {}
    for u, v, k, d in Gu.edges(keys=True, data=True):
        lanes = _as_lane_count(d.get("car_lanes", d.get("lanes", 1)))

        inventory[(u, v, k)] = {
            "lanes_total": lanes,
            "lanes_remaining": lanes,
            "reallocatable": _as_bool(d.get("reallocatable", False)),
            "geometry": d.get("geometry"),
            "osmid": d.get("osmid"),
            "highway": d.get("highway"),
        }
    return inventory


def _canonical_geometry_key(data):
    """Return a direction-invariant geometry key."""
    geom = data["geometry"]
    coords = list(geom.coords)

    forward = tuple(coords)
    backward = tuple(reversed(coords))
    return min(forward, backward)


def build_arc_to_segment_map(G_directed: MultiDiGraph) -> tuple[dict, dict]:
    """
    Map each directed arc to exactly one authoritative undirected segment.

    Returns
    -------
    arc_to_seg : dict[(u,v,k) -> seg_id]
    seg_to_arcs : dict[seg_id -> list[(u,v,k)]]
    """
    Gu = ox.convert.to_undirected(G_directed)

    undirected_lookup = {}
    for u, v, k, d in Gu.edges(keys=True, data=True):
        node_pair = tuple(sorted((u, v)))
        geom_key = _canonical_geometry_key(d)
        undirected_lookup[(node_pair, geom_key)] = (u, v, k)

    arc_to_seg = {}
    seg_to_arcs = defaultdict(list)

    for u, v, k, d in G_directed.edges(keys=True, data=True):
        node_pair = tuple(sorted((u, v)))
        geom_key = _canonical_geometry_key(d)

        seg_id = undirected_lookup.get((node_pair, geom_key))
        if seg_id is None:
            raise KeyError(
                f"Could not map directed edge {(u, v, k)} "
                f"with node_pair={node_pair}"
            )

        arc_to_seg[(u, v, k)] = seg_id
        seg_to_arcs[seg_id].append((u, v, k))

    return arc_to_seg, seg_to_arcs


def refresh_segment_reallocatable_flags(
    G: MultiDiGraph,
    segment_inventory: dict,
    seg_to_arcs: dict,
):
    """Keep directed graph reallocatable flags synchronized with segment supply."""
    for seg_id, arcs in seg_to_arcs.items():
        remaining = segment_inventory[seg_id]["lanes_remaining"]
        can_reallocate = remaining > 0 and segment_inventory[seg_id].get(
            "reallocatable",
            True,
        )

        for u, v, k in arcs:
            if not G.has_edge(u, v, k):
                continue
            d = G[u][v][k]
            if d.get("highway") == "cycleway":
                d["reallocatable"] = False
            else:
                d["reallocatable"] = bool(d.get("car_allowed", False) and can_reallocate)
