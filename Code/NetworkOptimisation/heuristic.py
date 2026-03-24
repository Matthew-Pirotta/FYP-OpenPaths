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

#TODO THIS SHOULD BE IN THE MAIN CLASS?
SEED = 12

def largest_by_length(G):
    #NOTE strongly connected true since roads cycle infrastructure is directional
    components = (G.subgraph(c).copy() for c in nx.strongly_connected_components(G))
    return max(components, key=lambda H: sum(d.get("length",0) for _,_,d in H.edges(data=True)))


# Connectedness - describing whether the network forms a single, navigable system or remains fragmented into multiple component
def calc_connectedness(G:MultiDiGraph, G_lcc:MultiDiGraph) -> dict:
    num_components = nx.number_strongly_connected_components(G)
    lcc_length = float(sum(d.get("length", 0) for _, _, d in G_lcc.edges(data=True)))

    return {
        "num_components": num_components,
        "lcc_length": lcc_length,
    }


def calc_directness(Gb_lcc:MultiDiGraph, G_drive:MultiDiGraph, k_sample=None, seed=SEED):
    bike_nodes = list(Gb_lcc.nodes())
    drive_nodes = set(G_drive.nodes()) 

    # Choose sampled origins/destinations
    if k_sample is None:
        origins = bike_nodes
        dests = bike_nodes
    else:
        rng = random.Random(seed)
        k_eff = min(k_sample, len(bike_nodes))
        origins = rng.sample(bike_nodes, k_eff)
        dests = rng.sample(bike_nodes, k_eff)

    ratios = []
    for o in origins:
        for d in dests:
            if o == d:
                continue

            # Ensure the drive network also includes the pair
            if o not in drive_nodes or d not in drive_nodes:
                continue

            try:
                L_bike = nx.shortest_path_length(Gb_lcc, source=o, target=d, weight="length")
                L_drive = nx.shortest_path_length(G_drive, source=o, target=d, weight="length")
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue

            if L_drive > 0:
                ratios.append(L_bike / L_drive)

    if len(ratios) == 0:
        return {
            "mean_directness": 0,
        }

    return {
        "mean_directness": float(np.mean(ratios)),
    }

def calc_centrality(G_lcc:MultiDiGraph, k_sample=None, seed = SEED) -> dict:
    """Calculate comprehensive centrality metrics for cycling network assessment"""
    #NOTE full centrality is O(n^3), k is instead used to approximate
    if k_sample is not None:
        num_nodes = len(G_lcc.nodes)
        k_eff = min(k_sample, num_nodes)
    else:
        k_eff = k_sample
    
    # Edge betweenness centrality - connectors for network resilience
    edge_between_cent = nx.edge_betweenness_centrality(G_lcc, weight="length", normalized=True, k=k_eff, seed = seed)
    mean_edge_between_cent = float(np.mean(list(edge_between_cent.values())))

    #closeness_centrality - how close all other nodes are
    node_close_cent = nx.closeness_centrality(G_lcc, distance="length")
    mean_node_close_cent = float(np.mean(list(node_close_cent.values())))

    degrees = [d for _, d in G_lcc.degree()]
    mean_degree = float(np.mean(degrees))
        
    return {
        "mean_edge_betweenness": mean_edge_between_cent,
        "mean_node_betweenness": 1,
        "mean_node_closeness": mean_node_close_cent,
        "mean_degree": mean_degree,
    }


def _evaluate_network_metrics(
    G_target: MultiDiGraph,
    G_drive_reference: MultiDiGraph,
    *,
    k_sample=None,
    prefix: str = "",
    include_union_geom: bool = True,
) -> dict:
    """Evaluate graph-level metrics and prefix result keys when requested."""
    metric_names = [
        "num_components",
        "lcc_length",
        "mean_edge_betweenness",
        "mean_node_betweenness",
        "mean_node_closeness",
        "mean_degree",
        "mean_directness",
        "coverage_area_m2",
        "coverage_area_km2",
    ]

    if G_target.number_of_nodes() == 0 or G_target.number_of_edges() == 0:
        results = {f"{prefix}{name}": 0.0 for name in metric_names}
        results[f"{prefix}num_components"] = 0
        if include_union_geom:
            results[f"{prefix}union_geom"] = None
        return results

    G_lcc = largest_by_length(G_target)
    connectedness = { "num_components": 0, "lcc_length": 0,} #TODO NOTE TEMP #calc_connectedness(G_target, G_lcc)
    centrality = calc_centrality(G_lcc, k_sample=k_sample)
    directness = calc_directness(G_target, G_drive_reference, k_sample=k_sample)
    coverage = calc_coverage(G_target)

    results = {**connectedness, **centrality, **directness, **coverage}
    if not include_union_geom:
        results.pop("union_geom", None)

    return {f"{prefix}{k}": v for k, v in results.items()}


def network_evaluation(G_protected:MultiDiGraph, G_drive:MultiDiGraph, k_sample=None) -> dict:
    bike_results = _evaluate_network_metrics(
        G_protected,
        G_drive,
        k_sample=k_sample,
        prefix="",
        include_union_geom=True,
    )
    car_results = _evaluate_network_metrics(
        G_drive,
        G_drive,
        k_sample=k_sample,
        prefix="car_",
        include_union_geom=False,
    )
    return {**bike_results, **car_results}

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

    edges_between_cent = nx.edge_betweenness_centrality(G_bikeable, weight="length", normalized=True, k=k_sample, seed=seed)

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
    node_close = nx.closeness_centrality(G_bikeable, distance="length")

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

def heuristic_random(G_master: MultiDiGraph, G_drive: MultiDiGraph, G_bikeable: MultiDiGraph, G_realloc: MultiDiGraph, G_protected:MultiDiGraph,) -> tuple:
    #TODO set seed?

    edges = list(G_realloc.edges)
    random_edge = random.choice(edges)
    return random_edge

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

def calc_coverage(G, buffer_m=500):
    """
    Compute Szell-style coverage: union of ε-buffer around all nodes and edges.
    Requires G to be projected (meters).
    """

    # --- 1. Collect node geometries ---
    node_geoms = []
    for _, data in G.nodes(data=True):
        if "x" in data and "y" in data:
            node_geoms.append(Point(data["x"], data["y"]))

    # --- 2. Collect edge geometries ---
    edge_geoms = []
    for u, v, data in G.edges(data=True):
        geom = data.get("geometry")
        edge_geoms.append(geom)

    # Convert to GeoSeries for fast buffer + union
    all_geoms = gpd.GeoSeries(node_geoms + edge_geoms, crs=G.graph["crs"])

    # --- 3. Buffer all elements ---
    buffered = all_geoms.buffer(buffer_m)

    # --- 4. Unary union: compute merged area ---
    union_geom = unary_union(buffered)

    # --- 5. Compute area in km² ---
    area_m2 = union_geom.area
    area_km2 = area_m2 / 1e6

    return {
        "coverage_area_m2": area_m2,
        "coverage_area_km2": area_km2,
        "union_geom": union_geom  # useful for debugging/plotting
    }

def _calc_network_centroid(G:MultiDiGraph, nodes:set)-> np.ndarray:
    coords = np.array([[G.nodes[n]["x"], G.nodes[n]["y"]] for n in nodes])
    centroid = coords.mean(axis=0)
    return centroid
