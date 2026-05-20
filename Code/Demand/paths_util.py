import networkx as nx
from typing import Literal
from collections import Counter
from collections.abc import Mapping
from constants import Arc, OD, Seg
from networkx import MultiDiGraph
import GraphUtil as graph_util

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

ODKey = tuple[int, int]

def make_od_key(od) -> ODKey:
    if isinstance(od, tuple) and len(od) >= 2:
        return int(od[0]), int(od[1])
    raise TypeError("od must be a tuple-like row containing origin and destination.")
