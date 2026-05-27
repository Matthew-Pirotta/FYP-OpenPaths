import random
from networkx import MultiDiGraph, display
from sympy import centroid
import GraphUtil as graph_util
import osmnx as ox
import networkx as nx
import numpy as np
import geopandas as gpd
from shapely.geometry import Point
from shapely.ops import unary_union
from Demand import paths_util
import nx_parallel
from collections import defaultdict

SEED = 12


def get_candidate_segments(
    G_realloc: MultiDiGraph,
    arc_to_seg: dict | None = None,
    seg_to_arcs: dict | None = None,
):
    """
    Return currently candidate segment ids from the current reallocatable graph.

    If precomputed maps are provided, reuse them and just filter to segments that
    still have at least one arc present in G_realloc.
    """
    if arc_to_seg is None or seg_to_arcs is None:
        arc_to_seg, seg_to_arcs = graph_util.build_arc_to_segment_map(G_realloc)
        return list(seg_to_arcs.keys()), arc_to_seg, seg_to_arcs

    candidate_segments = [
        seg_id
        for seg_id, arcs in seg_to_arcs.items()
        if any(G_realloc.has_edge(u, v, k) for u, v, k in arcs)
    ]
    return candidate_segments, arc_to_seg, seg_to_arcs

def heuristic_od_segment_betweenness(
    G_working: MultiDiGraph,
    G_drive: MultiDiGraph,
    G_bikeable: MultiDiGraph,
    G_realloc: MultiDiGraph,
    G_protected: MultiDiGraph,
    bike_paths,
    car_paths,
    beta: float = 1.0,
    arc_to_seg: dict | None = None,
    seg_to_arcs: dict | None = None,
    bike_edge_importance: dict | None = None,
    car_edge_importance: dict | None = None,
    candidate_actions: dict | None = None,
):
    if candidate_actions is None:
        candidate_segments, arc_to_seg, seg_to_arcs = get_candidate_segments(
            G_realloc,
            arc_to_seg=arc_to_seg,
            seg_to_arcs=seg_to_arcs,
        )
    else:
        candidate_segments = list(candidate_actions)

    if not candidate_segments:
        return None

    if bike_edge_importance is None:
        bike_edge_importance = paths_util.compute_edge_importance(G_bikeable, bike_paths, "bike_cost_penalty", )
    if car_edge_importance is None:
        car_edge_importance = paths_util.compute_edge_importance(G_drive, car_paths, "car_cost_current",)

    seg_scores = {}
    for seg_id in candidate_segments:
        if candidate_actions is None:
            bike_arcs = seg_to_arcs[seg_id]
            lost_car_arcs = seg_to_arcs[seg_id]
        else:
            action = candidate_actions[seg_id]
            bike_arcs = action.bike_arcs
            lost_car_arcs = action.lost_car_arcs

        bike_score = sum(bike_edge_importance.get(arc, 0.0) for arc in bike_arcs)
        car_score = sum(car_edge_importance.get(arc, 0.0) for arc in lost_car_arcs)
        seg_scores[seg_id] = bike_score - beta * car_score

    return max(seg_scores, key=seg_scores.get)


def heuristic_segment_betweenness_centrality(
    G_master: MultiDiGraph,
    G_drive: MultiDiGraph,
    G_bikeable: MultiDiGraph,
    G_realloc: MultiDiGraph,
    G_protected: MultiDiGraph,
    k_sample=None,
    seed=SEED,
    arc_to_seg: dict | None = None,
    seg_to_arcs: dict | None = None,
    edge_betweenness_scores: dict | None = None,
    candidate_actions: dict | None = None,
):
    if candidate_actions is None:
        candidate_segments, arc_to_seg, seg_to_arcs = get_candidate_segments(
            G_realloc,
            arc_to_seg=arc_to_seg,
            seg_to_arcs=seg_to_arcs,
        )
    else:
        candidate_segments = list(candidate_actions)

    if not candidate_segments:
        return None

    if k_sample is not None:
        k_sample = min(G_bikeable.number_of_nodes(), k_sample)

    if edge_betweenness_scores is None:
        edge_betweenness_scores = nx.edge_betweenness_centrality(
            G_bikeable,
            weight="bike_cost_penalty",
            normalized=True,
            k=k_sample,
            seed=seed,
            backend="parallel",
        )

    seg_scores = defaultdict(float)

    if candidate_actions is None:
        candidate_set = set(candidate_segments)
        for arc, score in edge_betweenness_scores.items():
            seg = arc_to_seg.get(arc)
            if seg in candidate_set:
                seg_scores[seg] += score
    else:
        for seg_id, action in candidate_actions.items():
            for arc in action.bike_arcs:
                seg_scores[seg_id] += edge_betweenness_scores.get(arc, 0.0)

    return max(seg_scores, key=seg_scores.get) if seg_scores else None

def heuristic_random(
    G_master: MultiDiGraph,
    G_drive: MultiDiGraph,
    G_bikeable: MultiDiGraph,
    G_realloc: MultiDiGraph,
    G_protected: MultiDiGraph,
    arc_to_seg: dict | None = None,
    seg_to_arcs: dict | None = None,
    candidate_actions: dict | None = None,
    rng=None,
):
    if candidate_actions is None:
        candidate_segments, _, _ = get_candidate_segments(
            G_realloc,
            arc_to_seg=arc_to_seg,
            seg_to_arcs=seg_to_arcs,
        )
    else:
        candidate_segments = list(candidate_actions)

    if not candidate_segments:
        return None

    random_source = rng if rng is not None else random
    return random_source.choice(candidate_segments)


#region Component Heuristics
def _euclidean_distance(G: MultiDiGraph, u, v) -> float:
    dx = G.nodes[u]["x"] - G.nodes[v]["x"]
    dy = G.nodes[u]["y"] - G.nodes[v]["y"]
    return (dx * dx + dy * dy) ** 0.5


def _find_bridge_path(
    G_master: MultiDiGraph,
    comp_a: set,
    comp_b: set,
    max_pairs: int = 5,
) -> tuple[list | None, float]:
    """
    Approximate bridge path:
    1. Rank component node pairs by straight-line distance.
    2. Run network shortest path only for the closest max_pairs pairs.
    3. Return the cheapest actual network path among those attempts.
    """
    if not comp_a or not comp_b:
        return None, float("inf")

    # Step 1: compute straight-line distances between component node pairs
    candidate_pairs = []

    for a in comp_a:
        if a not in G_master:
            continue

        for b in comp_b:
            if b not in G_master:
                continue

            dist = _euclidean_distance(G_master, a, b)
            candidate_pairs.append((dist, a, b))

    if not candidate_pairs:
        return None, float("inf")

    # Step 2: try only the closest pairs
    candidate_pairs.sort(key=lambda item: item[0])
    candidate_pairs = candidate_pairs[:max_pairs]

    best_path = None
    best_cost = float("inf")

    for _, a, b in candidate_pairs:
        try:
            path = nx.shortest_path(
                G_master,
                source=a,
                target=b,
                weight="length",
            )
            cost = nx.path_weight(
                G_master,
                path,
                weight="length",
            )

            if cost < best_cost:
                best_cost = cost
                best_path = path

        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue

    return best_path, best_cost


def _components_by_distance(G: MultiDiGraph, source_component: set, target_components: list[set]):
    source_centroid = _calc_network_centroid(G, source_component)
    distances = []

    for comp in target_components:
        comp_centroid = _calc_network_centroid(G, comp)
        dist = np.linalg.norm(source_centroid - comp_centroid)
        distances.append((dist, comp))

    return [comp for _, comp in sorted(distances, key=lambda item: item[0])]


def _select_bridge_segment(
    G_master: MultiDiGraph,
    path: list,
    candidate_segments: set,
    arc_to_seg: dict,
    source_comp: set,
    target_comp: set,
):
    """
    Pick the first reallocatable segment on the bridge path that is outside both
    selected components. If none exists, fall back to the first reallocatable
    segment on the path.
    """
    component_nodes = set(source_comp) | set(target_comp)
    first_reallocatable = None

    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        candidate_arcs = [(u, v, k) for k in G_master[u][v].keys()] if G_master.has_edge(u, v) else []
        for arc in candidate_arcs:
            seg = arc_to_seg.get(arc)
            if seg is None or seg not in candidate_segments:
                continue

            if first_reallocatable is None:
                first_reallocatable = seg

            if u not in component_nodes and v not in component_nodes:
                return seg

    return first_reallocatable

def _connect_nearest_feasible_component(
    G_master: MultiDiGraph,
    G_distance: MultiDiGraph,
    G_realloc: MultiDiGraph,
    source_comp: set,
    target_components: list[set],
    label: str,
    arc_to_seg: dict | None = None,
    seg_to_arcs: dict | None = None,
):
    candidate_segments, arc_to_seg, seg_to_arcs = get_candidate_segments(
        G_realloc,
        arc_to_seg=arc_to_seg,
        seg_to_arcs=seg_to_arcs,
    )
    if not candidate_segments:
        print(f"[{label}] No reallocatable segments available.")
        return None

    candidate_segments = set(candidate_segments)

    for target_comp in _components_by_distance(G_distance, source_comp, target_components):
        path, cost = _find_bridge_path(G_master, source_comp, target_comp)
        if not path or len(path) < 2:
            continue

        seg = _select_bridge_segment(
            G_master,
            path,
            candidate_segments,
            arc_to_seg,
            source_comp,
            target_comp,
        )
        if seg is not None:
            return seg

    print(f"[{label}] No bridge path with a reallocatable segment found.")
    return None


def fallback_edge(G_bikeable, G_realloc, candidate_actions: dict | None = None):
    """
    Fallback for when protected network is too small.
    Keeps previous behaviour: use betweenness-based fallback.
    """
    seg = heuristic_segment_betweenness_centrality(
        None,
        None,
        G_bikeable,
        G_realloc,
        None,
        k_sample=50,
        candidate_actions=candidate_actions,
    )
    return seg


def heuristic_L2C(
    G_master: MultiDiGraph,
    G_drive: MultiDiGraph,
    G_bikeable: MultiDiGraph,
    G_realloc: MultiDiGraph,
    G_protected: MultiDiGraph,
    arc_to_seg: dict | None = None,
    seg_to_arcs: dict | None = None,
    candidate_actions: dict | None = None,
):
    if G_protected.number_of_edges() < 3:
        return fallback_edge(G_bikeable, G_realloc, candidate_actions=candidate_actions)

    components = sorted(nx.strongly_connected_components(G_protected), key=len, reverse=True)
    if len(components) < 2:
        print("Already connected")
        return None

    largest = components[0]
    others = components[1:]

    return _connect_nearest_feasible_component(
        G_master,
        G_bikeable,
        G_realloc,
        largest,
        others,
        "L2C",
        arc_to_seg=arc_to_seg,
        seg_to_arcs=seg_to_arcs,
    )

def _calc_network_centroid(G: MultiDiGraph, nodes: set) -> np.ndarray:
    coords = np.array([[G.nodes[n]["x"], G.nodes[n]["y"]] for n in nodes])
    centroid = coords.mean(axis=0)
    return centroid
#endregion
