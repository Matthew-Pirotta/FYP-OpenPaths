import networkx as nx
from typing import Literal, Optional
from collections import Counter, deque
from collections.abc import Mapping
from constants import Arc, OD, Seg
from networkx import MultiDiGraph
import GraphUtil as graph_util
import nx_parallel

def _best_edge_key(G, u, v, weight_attr):
    edges = G[u][v]

    k = min(
        edges,
        key=lambda key: edges[key].get(weight_attr, float("inf"))
    )

    if weight_attr not in edges[k]:
        raise ValueError(
            f"No valid '{weight_attr}' found on any edge between {u} and {v}."
        )

    return k

def total_cost_from_paths(G, paths, weight_attr):
    total = 0.0

    for (o, d, w), path in paths.items():
        cost = 0.0

        for u, v in zip(path[:-1], path[1:]):
            k = _best_edge_key(G, u, v, weight_attr)
            cost += G[u][v][k][weight_attr]

        total += w * cost

    return total

def _iter_od_triples(od_data):
    if isinstance(od_data, Mapping):
        rows = ((o, d, w) for (o, d), w in od_data.items())
    else:
        rows = od_data

    for row in rows:
        try:
            row_vals = tuple(row)
            if len(row_vals) == 3:
                o, d, w = row_vals
            elif len(row_vals) == 2:
                (o, d), w = row_vals
            else:
                raise ValueError("row has invalid length")
        except Exception as exc:
            raise TypeError(
                "od_data must be Mapping[(o,d)->w], Iterable[(o,d,w)], or Iterable[((o,d),w)]."
            ) from exc
        yield int(o), int(d), float(w)


def compute_candidate_paths(G, OD_list, path_weight_metric:Literal["car_cost_current", "bike_cost_penalty", "length"]):
    """
    Compute a single shortest path for each OD pair in a counter-like OD demand.
    """
    paths = {}

    for o, d, w in _iter_od_triples(OD_list):
        try:
            length, path = nx.bidirectional_dijkstra(G, o, d, weight=path_weight_metric)
            paths[(o, d, w)] = path
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue

    return paths

def calculate_path_metrics(G, od_trips, weight_attr="length"):
    """
    Returns weighted average path cost for OD demand.
    """
    # 1. Compute paths
    paths = compute_candidate_paths(G, od_trips, weight_attr)
    
    # 2. Calculate total cost (weighted by trip counts)
    total_cost = total_cost_from_paths(G, paths, weight_attr)
    
    # 3. Normalize by total OD weight
    total_relevant_trips = sum(w for _, _, w in _iter_od_triples(od_trips))
    
    if total_relevant_trips == 0:
        return 0.0
        
    return total_cost / total_relevant_trips

def compute_edge_importance(G, paths, weight_attr = "length"):
    """
    Compute weighted edge importance from OD shortest paths.

    For each consecutive node pair in each path, the function assigns
    the OD weight to the lowest-cost parallel edge according to weight_attr.

    Parameters
    ----------
    G : networkx.MultiDiGraph
    paths : dict
        {(o, d, w): [n0, n1, ..., nk]}
    weight_attr : str
        Edge attribute used to choose among parallel edges.

    Returns
    -------
    dict
        {(u, v, k): importance}
    """
    edge_importance = Counter()

    for (o, d, w), path in paths.items():
        for u, v in zip(path[:-1], path[1:]):
            k = _best_edge_key(G, u, v, weight_attr)
            edge_importance[(u, v, k)] += w

    return edge_importance

#NOTE Use G_seg (undirected segment graph) for corridor expansion because it approximates “nearby streets” without directionality headaches
def _path_to_arcs(path: list[int]) -> list[Arc]:
    """
    Converts an ordered list of nodes into a list of directed arcs.

    Example:
        >>> _path_to_arcs([1, 2, 3])
        [(1, 2, 0), (2, 3, 0)]
    """
    return [(u, v, 0) for u, v in zip(path[:-1], path[1:])]

#region build_od_allowed_arcs
def _k_hop_arc_corridor(G_seg: MultiDiGraph, seed_segs: set[Seg], hops: int) -> set[Arc]:
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
            for x, y, k in G_seg.edges(endpoint, keys=True):
                seg2 = x,y,k
                if seg2 not in visited:
                    visited.add(seg2)
                    q.append((seg2, depth + 1))

    return visited

def _collect_path_seed_arcs( G: MultiDiGraph, o: int, d: int, weight_attr: str) -> set[Arc]:
    """Shortest path -> arcs -> mapped seed segments."""
    try:
        path_nodes = nx.shortest_path(G, o, d, weight=weight_attr)
    except nx.NetworkXNoPath:
        return set()

    path_arcs = _path_to_arcs(path_nodes)
    seed_arcs = set(path_arcs)
    return seed_arcs

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
            _collect_path_seed_arcs(G, o, d, car_weight)
        )

    if include_bike_path:
        seed_segs.update(
            _collect_path_seed_arcs(G, o, d, bike_weight)
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

def _expand_corridor(
    G_seg: MultiDiGraph,
    seed_segs: set[Seg],
    arc_to_seg: dict[Arc, Seg],
    seg_to_arcs: dict[Seg, list[Arc]],
    *,
    corridor_hops: int,
) -> set[Arc]:
    
    segs_corr = _k_hop_arc_corridor(G_seg, seed_segs, corridor_hops)
    arcs_corr = _segments_to_arcs_set(segs_corr, seg_to_arcs)
    return arcs_corr

ODKey = tuple[int, int]


def make_od_key(od) -> ODKey:
    if isinstance(od, tuple) and len(od) >= 2:
        return int(od[0]), int(od[1])
    raise TypeError("od must be a tuple-like row containing origin and destination.")
