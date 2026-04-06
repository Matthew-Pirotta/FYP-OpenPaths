import random
from networkx import MultiDiGraph, display
from sympy import centroid
import graph_util as graph_util
import osmnx as ox
import networkx as nx
import numpy as np
import geopandas as gpd
from shapely.geometry import Point
from shapely.ops import unary_union
from Demand import paths_util
import nx_parallel

#TODO THIS SHOULD BE IN THE MAIN CLASS?
SEED = 12

# TODO NOTE (i.e write in writeup) routing model differs cars route on one graph with one cost function, bikes route on another graph with bike_cost_penalty, network connectivity and route concentration can differ a lot.
# That means one mode can naturally produce more dispersed flows or more concentrated flows, So a bike importance value of 50 and a car importance value of 50 do not necessarily mean equal strategic importance.
# Since the networks are of different sizes, it is only fair to normalise on the the candidate edges, as the importance can be difused/concentrated
def normalize_edge_importance_on_candidates(
    candidate_edges, 
    edge_importance,
):
    """
    Normalize a single importance dictionary over the current candidate set.

    Parameters
    ----------
    candidate_edges : iterable of (u, v, k)
        Edges currently eligible for reallocation.
    edge_importance : dict[(u, v, k), float]
        Raw edge importance values.

    Returns
    -------
    dict[(u, v, k), float]
        Importance normalized to [0, 1] over candidate_edges.
    """
    vals = {e: edge_importance.get(e, 0.0) for e in candidate_edges}
    max_val = max(vals.values(), default=0.0)

    if max_val <= 0.0:
        return {e: 0.0 for e in candidate_edges}

    return {e: vals[e] / max_val for e in candidate_edges}

def build_balanced_edge_scores(
    candidate_edges,
    bike_edge_importance,
    car_edge_importance,
    gamma: float = 1.0,
):
    """
    Build balanced candidate scores from normalized bike and car importance.

    Score:
        alpha * normalized_bike_importance
      - beta  * normalized_car_importance

    Parameters
    ----------
    candidate_edges : iterable of (u, v, k)
    bike_edge_importance : dict[(u, v, k), float]
    car_edge_importance : dict[(u, v, k), float]
    alpha : float
        Weight for bike importance.
    beta : float
        Weight for car importance penalty.

    Returns
    -------
    dict[(u, v, k), float]
        Combined score for each candidate edge.
    """
    bike_norm = normalize_edge_importance_on_candidates(
        candidate_edges=candidate_edges,
        edge_importance=bike_edge_importance,
    )
    car_norm = normalize_edge_importance_on_candidates(
        candidate_edges=candidate_edges,
        edge_importance=car_edge_importance,
    )

    scores = {}
    for e in candidate_edges:
        scores[e] = bike_norm[e] - gamma * car_norm[e]

    return scores

#TODO is this just flow?
def heuristic_od_edge_betweenness(
    G_working: MultiDiGraph,
    G_drive: MultiDiGraph,
    G_bikeable: MultiDiGraph,
    G_realloc: MultiDiGraph,
    G_protected: MultiDiGraph,
    bike_paths,
    car_paths,
    beta: float = 1.0,
):
    """
    Select the reallocatable edge with the best balanced score.

    Notes
    -----
    - Bike importance is computed from shortest bike paths using bike_cost_penalty.
    - Car importance is computed from shortest car paths using length.
    - Importances are normalized only over currently reallocatable edges,
      since the decision is made only among that feasible set.
    """
    reallocatable_edges = list(G_realloc.edges(keys=True))
    if not reallocatable_edges:
        return None

    bike_edge_importance = paths_util.compute_edge_importance(G_bikeable, bike_paths,)
    car_edge_importance = paths_util.compute_edge_importance(G_drive, car_paths,)

    realloc_scores = build_balanced_edge_scores(
        candidate_edges=reallocatable_edges,
        bike_edge_importance=bike_edge_importance,
        car_edge_importance=car_edge_importance,
        gamma=beta,
    )

    if not realloc_scores:
        return None

    best_edge = max(realloc_scores, key=realloc_scores.get)
    return best_edge


#region topological heuristics
def heuristic_edge_betweenness_centrality(
        G_master:MultiDiGraph,
        G_drive:MultiDiGraph,
        G_bikeable:MultiDiGraph,
        G_realloc:MultiDiGraph,
        G_protected:MultiDiGraph,
        k_sample=None, seed=SEED) -> tuple:
    
    reallocatable_edges = set(G_realloc.edges(keys=True))

    if k_sample is not None:
        k_sample = min(G_bikeable.number_of_nodes(),k_sample) #ensure we dont sample more nodes than exist

    edges_between_cent = nx.edge_betweenness_centrality(G_bikeable, weight="bike_cost_penalty", normalized=True, k=k_sample, seed=seed, backend="parallel")

    reallocatable_edges_between_cent = {k: v for k, v in edges_between_cent.items() if k in reallocatable_edges}
    #Some sort of intersection on the edge_between centrality

    #print(f"edges_between_cent: {edges_between_cent}")
    #print(f"reallocatable_edges:  {reallocatable_edges}")
    #print(f"G_reallocatable.number_of_edges() IN DA FUNCTION: {G_realloc.number_of_edges()}")
    #print(f"reallocatable_edges_between_cent: {reallocatable_edges_between_cent}")

    max_between_cent_edge = max(reallocatable_edges_between_cent, key=reallocatable_edges_between_cent.get)
    print(max_between_cent_edge)    
    return max_between_cent_edge

def heuristic_edge_closeness_centrality(
    G_master: MultiDiGraph,
    G_drive: MultiDiGraph,
    G_bikeable: MultiDiGraph,
    G_realloc: MultiDiGraph,
    G_protected:MultiDiGraph,
    k_sample=None,seed=SEED) -> tuple:

    # 1. Get reallocatable edges
    reallocatable_edges = set(G_realloc.edges(keys=True))

    # 2. Compute *node* closeness on the bikeable network
    node_close = nx.closeness_centrality(G_bikeable, distance="length", backend="parallel")

    # 3. Convert node closeness → edge closeness
    edge_scores = {}
    for (u, v, k) in reallocatable_edges:
        cu = node_close.get(u, 0)
        cv = node_close.get(v, 0)
        edge_scores[(u, v, k)] = (cu + cv) / 2   # average of endpoints

    # 4. Select the best edge
    best_edge = max(edge_scores, key=edge_scores.get)
    print("Selected edge:", best_edge, "score:", edge_scores[best_edge])
    return best_edge
#endregion

def heuristic_random(G_master: MultiDiGraph, G_drive: MultiDiGraph, G_bikeable: MultiDiGraph, G_realloc: MultiDiGraph, G_protected:MultiDiGraph,) -> tuple:
    #TODO set seed?

    edges = list(G_realloc.edges)
    random_edge = random.choice(edges)
    return random_edge

#region Component Heuristics
def _find_bridge_path(G_drive:MultiDiGraph, comp_a:set, comp_b:set) -> tuple[list,float]:
    best_path, best_cost = None, float("inf")
    for a in comp_a:
        for b in comp_b:
            try:
                path = nx.shortest_path(G_drive, a, b, weight="length")
                cost = nx.path_weight(G_drive, path, weight="length")
                #print(f"trying {path}, for a cost of {cost}")
                if cost < best_cost:
                    best_cost, best_path = cost, path
            except nx.NetworkXNoPath:
                continue
    return best_path, best_cost

def _find_closest_component(G:MultiDiGraph, main_component:set, other_components:list[set]):
    main_centroid = _calc_network_centroid(G, main_component)
    
    min_dist = float("inf")
    closest_component = None
    for comp in other_components:
        comp_centroid = _calc_network_centroid(G, comp)
        dist = np.linalg.norm(main_centroid - comp_centroid)

        if dist < min_dist:
            min_dist = dist
            closest_component = comp
    
    return closest_component, min_dist

def _select_bridge_edge(G: MultiDiGraph, comp_a: set, path: list) -> tuple:
    """Find the first edge that leaves component A."""
    for i in range(len(path) - 1):
        if path[i] in comp_a and path[i + 1] not in comp_a:
            return (path[i], path[i + 1], 0)
    return (path[0], path[1], 0)

def _connect_components(G: MultiDiGraph, source_comp: set, target_comp: set, label: str):
    path, cost = _find_bridge_path(G, source_comp, target_comp)
    if not path or len(path) < 2:
        print(f"[{label}] No bridge path found.")
        return None
    #print(f"[{label}] Best path: {path}, cost={cost:.2f}")
    edge = _select_bridge_edge(G, source_comp, path)
    return edge

def fallback_edge(G_bikeable, G_realloc):
    """fallback_if_protected_empty, using edge betweenness centrality"""
    # Fallback: pick highest-betweenness reallocatable edge
    #TODO hard coded k_sample
    edge = heuristic_edge_betweenness_centrality(None,None,G_bikeable,G_realloc,None, k_sample=50)
    #TODO handle if none?
    print(f"fallback found edge {edge}")
    return edge

def heuristic_L2S(
        G_master:MultiDiGraph,
        G_drive:MultiDiGraph,
        G_bikeable:MultiDiGraph,
        G_realloc:MultiDiGraph,
        G_protected:MultiDiGraph,) -> tuple:
    """Largest-to-Second: Connects the two largest components."""

    #print(f"G_protected.number_of_edges(): {G_protected.number_of_edges()}, cond:{G_protected.number_of_edges() < 2}" )
    if G_protected.number_of_edges() < 3:
        return fallback_edge(G_bikeable,G_realloc)

    comps = sorted(nx.strongly_connected_components(G_protected), key=len, reverse=True)
    #print(f"the comps are: {comps}")
    if len(comps) < 2:
        print("Already connected")
        return None
    
    #NOTE it is done through G_drive, as the bike network may be disconnected
    edge_to_reallocate = _connect_components(G_drive, comps[0], comps[1], "L2S") 
    return edge_to_reallocate

def heuristic_L2C(
        G_master:MultiDiGraph,
        G_drive:MultiDiGraph,
        G_bikeable:MultiDiGraph,
        G_realloc:MultiDiGraph,
        G_protected:MultiDiGraph,):
    
    if G_protected.number_of_edges() < 3:
        return fallback_edge(G_bikeable,G_realloc)
    
    components = sorted(nx.strongly_connected_components(G_protected), key=len, reverse=True)
    if len(components) < 2:
        print("Already connected")
        return None
    
    largest = components[0]
    others = components[1:]

    closest_component, _ = _find_closest_component(G_bikeable, largest, others)

    edge_to_reallocate = _connect_components(G_drive, largest,closest_component, "L2C")
    return edge_to_reallocate

def heuristic_R2C(
        G_master:MultiDiGraph,
        G_drive:MultiDiGraph,
        G_bikeable:MultiDiGraph,
        G_realloc:MultiDiGraph,
        G_protected:MultiDiGraph,):
    
    if G_protected.number_of_edges() < 3:
        return fallback_edge(G_bikeable,G_realloc)

    components = list(nx.strongly_connected_components(G_protected))
    if len(components) < 2:
        print("Already connected")
        return None
    
    random.shuffle(components)
    
    random_component = components[0]
    other_components = components[1:]

    closest_component, _ = _find_closest_component(G_bikeable, random_component, other_components)

    edge_to_reallocate = _connect_components(G_drive, random_component,closest_component, "R2C")
    return edge_to_reallocate

def heuristic_CC(
        G_master:MultiDiGraph,
        G_drive:MultiDiGraph,
        G_bikeable:MultiDiGraph,
        G_realloc:MultiDiGraph,
        G_protected:MultiDiGraph,):
    
    if G_protected.number_of_edges() < 3:
        return fallback_edge(G_bikeable,G_realloc)

    components = list(nx.strongly_connected_components(G_protected))
    if len(components) < 2:
        print("Already connected")
        return None
    
    min_dist = float("inf")
    best_pair = (None, None)

    for i, comp in enumerate(components):
        other_components = components[i + 1:]
        closest_component, dist = _find_closest_component(G_bikeable, comp, other_components)
        if closest_component and dist < min_dist:
                min_dist = dist
                best_pair = (comp, closest_component)

    comp_a, comp_b = best_pair
    edge_to_reallocate = _connect_components(G_drive, comp_a, comp_b, "CC")
    return edge_to_reallocate

def _calc_network_centroid(G:MultiDiGraph, nodes:set)-> np.ndarray:
    coords = np.array([[G.nodes[n]["x"], G.nodes[n]["y"]] for n in nodes])
    centroid = coords.mean(axis=0)
    return centroid
#endregion
