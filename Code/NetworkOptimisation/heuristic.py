from networkx import MultiDiGraph
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

def _find_bridge_path(G_drive:MultiDiGraph, comp_a:MultiDiGraph, comp_b:MultiDiGraph) -> tuple[list,float]:
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


def heuristic_L2S(G_drive:MultiDiGraph) -> tuple:
    components = sorted(nx.strongly_connected_components(G_drive), key=len, reverse=True)
    if len(components) < 2:
        print("Already connected")
        return None
    
    largest = components[0]
    second_largest = components[1]

    path, cost = _find_bridge_path(G_drive, largest, second_largest)
    if not path or len(path) < 2:
        print("No bridge path found.")
        return None

    print(f"Best Path {path}")
    u, v = path[0], path[1]
    edge_to_reallocate = (u,v,0)
    return edge_to_reallocate