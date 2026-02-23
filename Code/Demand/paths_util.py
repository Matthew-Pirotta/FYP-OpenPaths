import networkx as nx
from typing import Literal, Optional
from collections import Counter, deque
from constants import Arc, OD, Seg
from networkx import MultiDiGraph
import graph_util

def total_cost_from_paths(G, paths, weight_attr):
    total = 0.0
    for (o, d, w), path in paths.items():
        cost = 0.0
        for u, v in zip(path[:-1], path[1:]):
            cost += G[u][v][0][weight_attr]
        total += w * cost
    return total

def compute_candidate_paths(G, OD, path_weight_metric:Literal["car_cost_current", "bike_cost_penalty"]):
    """
    Compute a single shortest (bike-optimal) path for each OD pair.
    
    Parameters
    ----------
    G : networkx graph
        Network with 'bike_cost_penalty' edge weights.
    OD : iterable of (origin, destination)
    path_weight_metric: which attribute to use as edge weight for shortest path
    Returns
    -------
    dict
        {(origin, destination): path}
    """
    paths = {}

    for o, d, w in OD:

        try:
            path = nx.shortest_path(G, o, d, weight=path_weight_metric)
            paths[(o, d, w)] = path
        except nx.NetworkXNoPath:
            continue

    return paths


def compute_edge_importance(G, paths):
    """
    Compute weighted edge importance from OD shortest paths.

    Parameters
    ----------
    G : networkx.MultiDiGraph
    paths : dict
        {(o, d, w): [n0, n1, ..., nk]}

    Returns
    -------
    dict
        {(u, v, k): importance}
    """
    edge_importance = Counter()

    for (o, d, w), path in paths.items():
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            k = 0

            edge_importance[(u, v, k)] += w

    return edge_importance


#NOTE Use G_seg (undirected segment graph) for corridor expansion because it approximates “nearby streets” without directionality headaches
#TODO can remove?
def _path_to_arcs(path: list[int]) -> list[Arc]:
    return [(u, v, 0) for u, v in zip(path[:-1], path[1:])]


def _k_hop_segment_corridor(G_seg: MultiDiGraph, seed_segs: set[Seg], hops: int, arc_to_seg:dict[Arc, Seg]) -> set[Seg]:
    """Expand a set of undirected segments by k hops in the undirected segment graph."""
    if hops <= 0:
        return set(seed_segs)

    visited: set[Seg] = set(seed_segs)
    q = deque([(seg, 0) for seg in seed_segs])

    # In a segment graph, each edge is a segment between two nodes.
    # Two segments are "neighbors" if they share a node (endpoint).
    while q:
        seg, depth = q.popleft()
        if depth >= hops:
            continue

        a, b, _= seg
        for endpoint in (a, b):
            for x, y, kk in G_seg.edges(endpoint, keys=True):
                seg2 =  arc_to_seg[(x, y, 0)]
                if seg2 not in visited:
                    visited.add(seg2)
                    q.append((seg2, depth + 1))

    return visited


#region build_od_allowed_arcs
def _collect_path_seed_segments(
    G: MultiDiGraph,
    o: int,
    d: int,
    weight_attr: str,
    arc_to_seg: dict[Arc, Seg],
) -> set[Seg]:
    """Shortest path -> arcs -> mapped seed segments."""
    try:
        path_nodes = nx.shortest_path(G, o, d, weight=weight_attr)
    except nx.NetworkXNoPath:
        return set()

    seed_segs: set[Seg] = set()
    for arc in _path_to_arcs(path_nodes):
        seg = arc_to_seg.get(arc)
        if seg is not None:
            seed_segs.add(seg)
    return seed_segs

def _collect_seed_segments_for_od(
    G: MultiDiGraph,
    o: int,
    d: int,
    arc_to_seg: dict[Arc, Seg],
    *,
    include_car_path: bool,
    include_bike_path: bool,
    car_weight: str,
    bike_weight: str,
) -> set[Seg]:
    """Collect seed segments from enabled baseline paths."""
    seed_segs: set[Seg] = set()

    if include_car_path:
        seed_segs.update(
            _collect_path_seed_segments(G, o, d, car_weight, arc_to_seg)
        )

    if include_bike_path:
        seed_segs.update(
            _collect_path_seed_segments(G, o, d, bike_weight, arc_to_seg)
        )

    return seed_segs

def _segments_to_arcs_set(
    segs: set[Seg],
    seg_to_arcs: dict[Seg, list[Arc]],
) -> set[Arc]:
    
    arcs: set[Arc] = set()
    for seg in segs:
        arcs.update(seg_to_arcs.get(seg, []))
    return arcs


def _expand_corridor_with_soft_fallback(
    G_seg: MultiDiGraph,
    seed_segs: set[Seg],
    arc_to_seg: dict[Arc, Seg],
    seg_to_arcs: dict[Seg, list[Arc]],
    *,
    corridor_hops: int,
    min_arcs_per_od: int,
    max_extra_hops: int = 6,
) -> tuple[set[Seg], set[Arc], int]:
    """
    Build k-hop segment corridor and widen if arc count is below min_arcs_per_od.
    Returns (segments, arcs, final_hops).
    """
    hops = corridor_hops
    segs_corr = _k_hop_segment_corridor(G_seg, seed_segs, hops, arc_to_seg)
    arcs_corr = _segments_to_arcs_set(segs_corr, seg_to_arcs)

    while len(arcs_corr) < min_arcs_per_od and hops < corridor_hops + max_extra_hops:
        hops += 1
        segs_corr = _k_hop_segment_corridor(G_seg, seed_segs, hops, arc_to_seg)
        arcs_corr = _segments_to_arcs_set(segs_corr, seg_to_arcs)

    return segs_corr, arcs_corr, hops

def _ordered_segments_bfs(
    G_seg: MultiDiGraph,
    seed_segs: set[Seg],
    arc_to_seg: dict[Arc, Seg],
    *,
    hops: int,
    key: int,
) -> list[Seg]:
    """BFS segment expansion order from seeds up to hop depth."""
    visited = set(seed_segs)
    q = deque([(seg, 0) for seg in seed_segs])
    ordered_segs: list[Seg] = []

    while q:
        seg, depth = q.popleft()
        ordered_segs.append(seg)

        if depth >= hops:
            continue

        a, b, _ = seg
        for endpoint in (a, b):
            for x, y, kk in G_seg.edges(endpoint, keys=True):
                if kk != key:
                    continue
                seg2 = arc_to_seg.get((x, y, key))
                if seg2 is None or seg2 in visited:
                    continue
                visited.add(seg2)
                q.append((seg2, depth + 1))

    return ordered_segs

def _trim_arcs_with_hard_cap(
    ordered_segs: list[Seg],
    seg_to_arcs: dict[Seg, list[Arc]],
    max_arcs_per_od: int,
) -> set[Arc]:
    """Accumulate arcs by segment order and enforce exact cap."""
    trimmed: set[Arc] = set()
    for seg in ordered_segs:
        trimmed.update(seg_to_arcs.get(seg, []))
        if len(trimmed) >= max_arcs_per_od:
            break

    if len(trimmed) <= max_arcs_per_od:
        return trimmed

    return set(list(trimmed)[:max_arcs_per_od])

def build_od_allowed_arcs(
    G: MultiDiGraph,
    G_seg: MultiDiGraph,
    OD_list: list[tuple[int, int, float]],
    seg_to_arcs: dict[Seg, list[Arc]],
    arc_to_seg: dict[Arc, Seg],
    *,
    car_weight: str = "car_cost_current",
    bike_weight: str = "bike_cost_current",
    corridor_hops: int = 2,
    min_arcs_per_od: int = 300,
    max_arcs_per_od: Optional[int] = None,
    include_car_path: bool = True,
    include_bike_path: bool = True,
    key: int = 0,
) -> dict[int, set[Arc]]:
    """
    Build per-OD allowed arcs for spatial relaxation (Wiedemann-style).
    """
    od_allowed: dict[int, set[Arc]] = {}

    for p, (o, d, _) in enumerate(OD_list):
        seed_segs = _collect_seed_segments_for_od(
            G,
            o,
            d,
            arc_to_seg,
            include_car_path=include_car_path,
            include_bike_path=include_bike_path,
            car_weight=car_weight,
            bike_weight=bike_weight,
        )

        if not seed_segs:
            od_allowed[p] = set()
            continue

        _, arcs_corr, hops = _expand_corridor_with_soft_fallback(
            G_seg,
            seed_segs,
            arc_to_seg,
            seg_to_arcs,
            corridor_hops=corridor_hops,
            min_arcs_per_od=min_arcs_per_od,
        )

        if max_arcs_per_od is not None and len(arcs_corr) > max_arcs_per_od:
            ordered_segs = _ordered_segments_bfs(
                G_seg,
                seed_segs,
                arc_to_seg,
                hops=hops,
                key=key,
            )
            arcs_corr = _trim_arcs_with_hard_cap(
                ordered_segs,
                seg_to_arcs,
                max_arcs_per_od,
            )

        od_allowed[p] = arcs_corr

    return od_allowed

#endregion