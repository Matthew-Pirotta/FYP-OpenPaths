import networkx as nx
from typing import Literal
from collections import Counter

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
