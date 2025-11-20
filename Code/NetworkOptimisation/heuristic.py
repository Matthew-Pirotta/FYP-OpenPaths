import random
from networkx import MultiDiGraph
from sympy import centroid
import graph_util as graph_util
import osmnx as ox
import networkx as nx
import numpy as np

#TODO THIS SHOULD BE IN THE MAIN CLASS?
SEED = 12

# Connectedness - describing whether the network forms a single, navigable system or remains fragmented into multiple component
def calc_connectedness(G:MultiDiGraph, G_lcc:MultiDiGraph) -> dict:
    num_components = nx.number_strongly_connected_components(G)
    lcc_length = float(sum(d.get("length", 0) for _, _, d in G_lcc.edges(data=True)))

    return {
        "num_components": num_components,
        "lcc_length": lcc_length,
    }


"""def calc_directness(Gb_lcc:MultiDiGraph, G_drive:MultiDiGraph, k = SAMPLE_K, seed=SEED):
    #TODO update when I actually have OD matrix data
    rng = random.Random(seed)

    nodes_b = list(Gb_lcc.nodes())
    if len(nodes_b) < 2:
        raise ValueError("Bike LCC has fewer than 2 nodes.")
    K_eff = min(k, len(nodes_b) * 5)  # keep reasonable number of pairs
    rng.seed(seed)
    ods = []
    while len(ods) < K_eff:
        o = rng.choice(nodes_b)
        d = rng.choice(nodes_b)
        if o != d:
            ods.append((o, d))
            
    pass"""

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

    # node betweenness centrality - measures how frequently a node lies on the shortest paths between all node pair
    node_between_cent = nx.betweenness_centrality(G_lcc, weight="length", normalized=True, k=k_eff, seed = seed)
    mean_node_between_cent = float(np.mean(list(node_between_cent.values())))

    #closeness_centrality - how close all other nodes are
    #TODO
    #node_close_cent = nx.closeness_centrality(G_lcc, distance="length")
    #mean_node_close_cent = float(np.mean(list(node_close_cent.values())))

    degrees = [d for _, d in G_lcc.degree()]
    mean_degree = float(np.mean(degrees))
        
    return {
        "mean_edge_betweenness": mean_edge_between_cent,
        "mean_node_betweenness": mean_node_between_cent,
        "mean_node_closeness": 1,
        "mean_degree": mean_degree,
    }


def network_evaluation(G:MultiDiGraph, k_sample=None) -> dict:
    G_lcc = ox.truncate.largest_component(G, strongly=True) #NOTE strongly connected true since roads cycle infrastructure is directional

    connectedness = calc_connectedness(G, G_lcc)
    centrality  = calc_centrality(G_lcc, k_sample=k_sample)
    results = {**connectedness, **centrality}
    return results


def heuristic_edge_betweenness_centrality(G_drive:MultiDiGraph, k_sample=None, seed=SEED) -> tuple:
    if k_sample is not None:
        k_sample = min(G_drive.number_of_nodes(),k_sample) #ensure we dont sample more nodes than exist
    
    edges_between_cent = nx.edge_betweenness_centrality(G_drive, weight="length", normalized=True, k=k_sample, seed=seed)
    max_between_cent_edge = max(edges_between_cent, key=edges_between_cent.get)
    print(max_between_cent_edge)    
    return max_between_cent_edge

def heuristic_random(G_drive:MultiDiGraph) -> tuple:
    edges = list(G_drive.edges)
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

def heuristic_L2S(G: MultiDiGraph) -> tuple:
    """Largest-to-Second: Connects the two largest components."""
    comps = sorted(nx.strongly_connected_components(G), key=len, reverse=True)
    if len(comps) < 2:
        print("Already connected")
        return None
    edge_to_reallocate = _connect_components(G, comps[0], comps[1], "L2S") 
    return edge_to_reallocate


def heuristic_L2C(G_drive:MultiDiGraph):
    components = sorted(nx.strongly_connected_components(G_drive), key=len, reverse=True)
    if len(components) < 2:
        print("Already connected")
        return None
    
    largest = components[0]
    others = components[1:]

    closest_component, _ = _find_closest_component(G_drive, largest, others)

    edge_to_reallocate = _connect_components(G_drive, largest,closest_component, "L2C")
    return edge_to_reallocate

def heuristic_R2C(G_drive:MultiDiGraph):
    components = list(nx.strongly_connected_components(G_drive))
    if len(components) < 2:
        print("Already connected")
        return None
    
    random.shuffle(components)
    
    random_component = components[0]
    other_components = components[1:]

    closest_component, _ = _find_closest_component(G_drive, random_component, other_components)

    edge_to_reallocate = _connect_components(G_drive, random_component,closest_component, "R2C")
    return edge_to_reallocate

def heuristic_CC(G_drive:MultiDiGraph):
    components = list(nx.strongly_connected_components(G_drive))
    if len(components) < 2:
        print("Already connected")
        return None
    
    min_dist = float("inf")
    best_pair = (None, None)

    for i, comp in enumerate(components):
        other_components = components[i + 1:]
        closest_component, dist = _find_closest_component(G_drive, comp, other_components)
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