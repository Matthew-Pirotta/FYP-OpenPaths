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


def build_od_allowed_arcs(
    G: MultiDiGraph,
    G_seg: MultiDiGraph,
    OD_list: list[tuple[int, int, float]],
    seg_to_arcs: dict[Seg, list[Arc]],
    arc_to_seg: dict[Arc, Seg],
    *,
    # weights for baseline paths
    car_weight: str = "car_cost_current",
    bike_weight_prefer: str = "bike_cost_current",   # will fallback to bike_cost_penalty if missing
    # corridor controls
    corridor_hops: int = 2,
    min_arcs_per_od: int = 300,
    max_arcs_per_od: Optional[int] = None,
    # toggles
    include_car_path: bool = True,
    include_bike_path: bool = True,
    # single-key assumption
    key: int = 0,
) -> dict[int, set[Arc]]:
    """
    Build per-OD allowed arcs for spatial relaxation (Wiedemann-style).

    Assumptions (as requested)
    --------------------------
    - There is effectively only one key in the directed graph and segment graph (default k=0).
    - Segments are represented as (u, v, k) where u=min(node ids), v=max(node ids), k=0.

    Method
    ------
    For each OD index p:
      1) compute baseline car shortest path (optional)
      2) compute baseline bike shortest path (optional)
      3) convert those paths to seed segments (u,v,k) using arc_to_seg
      4) expand seed segments by corridor_hops using the segment graph G_seg
      5) map corridor segments back to directed arcs using seg_to_arcs

    Returns
    -------
    dict
      od_allowed_arcs[p] = set of allowed directed arcs (u,v,k) for OD p
    """
    od_allowed: dict[int, set[Arc]] = {}

    # Determine which bike weight exists on edges
    bike_weight = bike_weight_prefer
    # check one edge quickly
    #TODO remove this at some point?
    for _, _, _, d in G.edges(keys=True, data=True):
        if bike_weight_prefer not in d:
            bike_weight = "bike_cost_penalty"
        break

    for p, (o, d, w) in enumerate(OD_list):
        seed_segs: set[Seg] = set()

        # --- Car baseline ---
        if include_car_path:
            try:
                car_path_nodes = nx.shortest_path(G, o, d, weight=car_weight)
                car_arcs = _path_to_arcs(car_path_nodes)
                for a in car_arcs:
                    seg = arc_to_seg.get(a)
                    if seg is not None:
                        seed_segs.add(seg)
            except nx.NetworkXNoPath:
                pass

        # --- Bike baseline ---
        if include_bike_path:
            try:
                bike_path_nodes = nx.shortest_path(G, o, d, weight=bike_weight)
                bike_arcs = _path_to_arcs(bike_path_nodes)
                for a in bike_arcs:
                    seg = arc_to_seg.get(a)
                    if seg is not None:
                        seed_segs.add(seg)
            except nx.NetworkXNoPath:
                pass

        # No seeds => no corridor (keep empty; solver should skip OD or handle)
        if not seed_segs:
            od_allowed[p] = set()
            continue

        # Expand corridor; if too small, widen hops up to a cap
        hops = corridor_hops
        segs_corr = _k_hop_segment_corridor(G_seg, seed_segs, hops, arc_to_seg)

        def segs_to_arcs_set(segs: set[Seg]) -> set[Arc]:
            arcs: set[Arc] = set()
            for seg in segs:
                arcs.update(seg_to_arcs.get(seg, []))
            return arcs

        arcs_corr = segs_to_arcs_set(segs_corr)

        # Soft fallback: widen corridor if it's too small
        while len(arcs_corr) < min_arcs_per_od and hops < corridor_hops + 6:
            hops += 1
            segs_corr = _k_hop_segment_corridor(G_seg, seed_segs, hops, arc_to_seg)
            arcs_corr = segs_to_arcs_set(segs_corr)

        # Optional hard cap
        if max_arcs_per_od is not None and len(arcs_corr) > max_arcs_per_od:
            # Keep segments in BFS expansion order until arc budget filled
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
                        seg2 = arc_to_seg[(x, y, key)]
                        if seg2 not in visited:
                            visited.add(seg2)
                            q.append((seg2, depth + 1))

            trimmed: set[Arc] = set()
            for seg in ordered_segs:
                trimmed.update(seg_to_arcs.get(seg, []))
                if len(trimmed) >= max_arcs_per_od:
                    break

            # enforce the cap exactly
            arcs_corr = set(list(trimmed)[:max_arcs_per_od])

        od_allowed[p] = arcs_corr

    return od_allowed