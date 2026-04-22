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
from collections import defaultdict

#TODO THIS SHOULD BE IN THE MAIN CLASS?
SEED = 12


def get_candidate_segments(G_realloc: MultiDiGraph):
    arc_to_seg, seg_to_arcs = graph_util.build_arc_to_segment_map(G_realloc)
    candidate_segments = list(seg_to_arcs.keys())
    return candidate_segments, arc_to_seg, seg_to_arcs



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
def heuristic_od_segment_betweenness(
    G_working: MultiDiGraph,
    G_drive: MultiDiGraph,
    G_bikeable: MultiDiGraph,
    G_realloc: MultiDiGraph,
    G_protected: MultiDiGraph,
    bike_paths,
    car_paths,
    beta: float = 1.0,
):
    candidate_segments, arc_to_seg, seg_to_arcs = get_candidate_segments(G_realloc)
    if not candidate_segments:
        return None

    bike_edge_importance = paths_util.compute_edge_importance(G_bikeable, bike_paths)
    car_edge_importance = paths_util.compute_edge_importance(G_drive, car_paths)

    seg_scores = {}
    for seg_id, arcs in seg_to_arcs.items():
        bike_score = sum(bike_edge_importance.get(arc, 0.0) for arc in arcs)
        car_score = sum(car_edge_importance.get(arc, 0.0) for arc in arcs)
        seg_scores[seg_id] = bike_score - beta * car_score

    best_edge = max(seg_scores, key=seg_scores.get)

    return best_edge


#region topological heuristics
def heuristic_segment_betweenness_centrality(
    G_master: MultiDiGraph,
    G_drive: MultiDiGraph,
    G_bikeable: MultiDiGraph,
    G_realloc: MultiDiGraph,
    G_protected: MultiDiGraph,
    k_sample=None,
    seed=SEED
):
    candidate_segments, arc_to_seg, seg_to_arcs = get_candidate_segments(G_realloc)
    if not candidate_segments:
        return None

    if k_sample is not None:
        k_sample = min(G_bikeable.number_of_nodes(), k_sample)

    edges_between_cent = nx.edge_betweenness_centrality(
        G_bikeable,
        weight="bike_cost_penalty",
        normalized=True,
        k=k_sample,
        seed=seed,
        backend="parallel"
    )

    seg_scores = defaultdict(float)
    for arc, score in edges_between_cent.items():
        seg = arc_to_seg.get(arc)
        if seg in seg_to_arcs:
            seg_scores[seg] += score

    max_between_cent_seg = max(seg_scores, key=seg_scores.get) if seg_scores else None
    return max_between_cent_seg

#TODO remove this function
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

def _select_bridge_segment(G: MultiDiGraph, comp_a: set, path: list, arc_to_seg: dict):
    """Find the first edge that leaves component A."""
    for i in range(len(path) - 1):
        if path[i] in comp_a and path[i + 1] not in comp_a:
            u, v = path[i], path[i + 1]
            candidate_arcs = [(u, v, k) for k in G[u][v].keys()] if G.has_edge(u, v) else []
            for arc in candidate_arcs:
                seg = arc_to_seg.get(arc)
                if seg is not None:
                    return seg
    return None

def _connect_components(G: MultiDiGraph, source_comp: set, target_comp: set, label: str):
    path, cost = _find_bridge_path(G, source_comp, target_comp)
    if not path or len(path) < 2:
        print(f"[{label}] No bridge path found.")
        return None
    #print(f"[{label}] Best path: {path}, cost={cost:.2f}")
    seg = _select_bridge_segment(G, source_comp, path)
    return seg

def fallback_edge(G_bikeable, G_realloc):
    """fallback_if_protected_empty, using edge betweenness centrality"""
    # Fallback: pick highest-betweenness reallocatable edge
    #TODO hard coded k_sample
    seg = heuristic_segment_betweenness_centrality(
            None, None, G_bikeable, G_realloc, None, k_sample=50)
    return seg

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

    comps = sorted(nx.weakly_connected_components(G_protected), key=len, reverse=True)
    #print(f"the comps are: {comps}")
    if len(comps) < 2:
        print("Already connected")
        return None
    
    #TODO
    #I want to use Realloc so that the path is fullybuildable but 1.Roundabouts are not reallocatable, 2. the edges in the componenets aren't reallocatable but this is fixable by just temp adding them or something
    #G_bikeable is good because it avoids stuff like tunnels. Possible problem is that bike network may be disconnected
    #G_drive does not containg the protected cycle components

    #I think my main problem is that if the path isnt connenctable for some reason the system wont recover and will try to path the same route. Consider the case where it is bikeable but not realloacatble the route.

    #I could either make use of and filter on a certain tag
    #Or have some sort of retry code/fallback

    #I need to account for 2 components not being connectable and trying a different component?
    #
    edge_to_reallocate = _connect_components(G_master, comps[0], comps[1], "L2S") 
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
