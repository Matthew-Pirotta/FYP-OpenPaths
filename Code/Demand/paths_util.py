import networkx as nx
from typing import Literal, Optional
from collections import Counter, deque
from collections.abc import Mapping
from constants import Arc, OD, Seg
from networkx import MultiDiGraph
import graph_util
import nx_parallel


#TODO depricated
def total_cost_from_paths(G, paths, weight_attr):
    total = 0.0
    for (o, d, w), path in paths.items():
        cost = 0.0
        for u, v in zip(path[:-1], path[1:]):
            # Pick the minimum-weight edge among all parallel edges
            edge_data = G[u][v]
            cost += min(
                data[weight_attr]
                for data in edge_data.values()
            )
        total += w * cost
    return total

#TODO these generated paths do not provide the K key, there are two solutions
#1. k = min(edges, key=lambda x: edges[x].get(weight_attr, float('inf')))
#2. convert to digraph, extra benefit of being able to use cupgraph, nvm that wont really work
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
            path = nx.bidirectional_dijkstra(G, o, d, weight=path_weight_metric)
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


#TODO this should be on the actual k
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


#TODO wiedmann might be building it differently from me....
#TODO maybe it should be segment level idk
def build_od_allowed_arcs(
    G_drive:MultiDiGraph,
    G_bike:MultiDiGraph,
    OD_list: OD,
    car_weight: str = "car_cost_current",
    bike_weight: str = "bike_cost_penalty",
    corridor_hops: int = 2,
) -> tuple[dict[ODKey, set[Arc]], dict[ODKey, set[Arc]]]:
    """
    Build per-OD allowed arcs separately for car and bike.

    Returns
    -------
    od_allowed_car, od_allowed_bike
        Dictionaries keyed by ODKey from make_od_key(od).
    """
    od_allowed_car: dict[ODKey, set[Arc]] = {}
    od_allowed_bike: dict[ODKey, set[Arc]] = {}

    for o, d, _ in _iter_od_triples(OD_list):
        od_key = (o, d)
        if od_key in od_allowed_car and od_key in od_allowed_bike:
            continue

        car_seed_segs: set[Seg] = set()
        bike_seed_segs: set[Seg] = set()

        car_seed_segs = _collect_path_seed_arcs(G_drive, o, d, car_weight)
        bike_seed_segs = _collect_path_seed_arcs(G_bike, o, d, bike_weight)

        car_arcs = _k_hop_arc_corridor(G_drive, car_seed_segs, corridor_hops)
        bike_arcs = _k_hop_arc_corridor(G_bike, bike_seed_segs, corridor_hops)

        od_allowed_car[od_key] = car_arcs
        od_allowed_bike[od_key] = bike_arcs

    return od_allowed_car, od_allowed_bike
#endregion
