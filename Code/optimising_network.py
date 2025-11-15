from networkx import MultiDiGraph
import graph_util as graph_util
import copy
import osmnx as ox
import networkx as nx
import numpy as np
import concurrent.futures
import pandas as pd

#TODO THIS SHOULD BE IN THE MAIN CLASS?
SAMPLE_K = None #NOTE set k to None to use full network
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

def calc_centrality(G_lcc:MultiDiGraph, k=SAMPLE_K, seed = SEED) -> dict:
    """Calculate comprehensive centrality metrics for cycling network assessment"""
    #NOTE full centrality is O(n^3), k is instead used to approximate

    num_nodes = len(G_lcc.nodes)
    k_eff = min(k, num_nodes)
    
    # Edge betweenness centrality - connectors for network resilience
    edge_between_cent = nx.edge_betweenness_centrality(G_lcc, weight="length", normalized=True, k=k_eff, seed = seed)
    mean_edge_between_cent = float(np.mean(list(edge_between_cent.values())))

    # betweenness centrality - measures how frequently a link lies on the shortest paths between all node pair
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


def network_evaluation(G:MultiDiGraph) -> dict:
    G_lcc = ox.truncate.largest_component(G, strongly=True) #NOTE strongly connected true since roads cycle infrastructure is directional

    connectedness = calc_connectedness(G, G_lcc)
    centrality  = calc_centrality(G_lcc)
    results = {**connectedness, **centrality}
    return results


def heuristic(G_master:MultiDiGraph, G_drive:MultiDiGraph, k=SAMPLE_K, seed=SEED):
    k = min(G_drive.number_of_nodes(),k) #ensure we dont sample more nodes than exist
    edges_between_cent = nx.edge_betweenness_centrality(G_drive, weight="length", normalized=True, k=k, seed=seed)
    max_between_cent_edge = max(edges_between_cent, key=edges_between_cent.get)
    print(max_between_cent_edge)
    
    u,v,k = max_between_cent_edge
    #print(f"edge before: {G_master[u][v][k]}")
    graph_util.reallocate_edge(G_master, max_between_cent_edge)
    #print(f"edge after: {G_master[u][v][k]}" )

def run_locality_task(args):
    """Worker function for a single locality."""
    name, G_sub, n_iterations = args

    print(f"🏙️ Starting {name} in process")
    G_working = copy.deepcopy(G_sub)

    for i in range(n_iterations):
        G_drive = graph_util.make_drive_subgraph(G_working)
        heuristic(G_working, G_drive)

    evaluation = network_evaluation(G_working)
    evaluation["locality"] = name
    return evaluation

def run_global_parallel(G_master, subgraphs, n_iterations=10, max_workers=None):
    """Run heuristic on all subgraphs in parallel."""
    tasks = [(name, G_sub_master, n_iterations) for name, G_sub_master in subgraphs.items()]
    results = []

    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor: 
        for result in executor.map(run_locality_task, tasks):
            results.append(result)
    
    """    
    for task in tasks:
        result = run_locality_task(task)
        results.append(result)
    """

    df_results = pd.DataFrame(results)
    df_results.set_index("locality", inplace=True)
    return df_results

def run_global_serial(G_master, subgraphs, n_iterations=10, max_workers=None):
    """Run heuristic on all subgraphs sequentially."""
    tasks = [(name, G_sub_master, n_iterations) for name, G_sub_master in subgraphs.items()]
    results = []
    
    for task in tasks:
        result = run_locality_task(task)
        results.append(result)

    df_results = pd.DataFrame(results)
    df_results.set_index("locality", inplace=True)
    return df_results

if __name__ == "__main__":
    print("hello????")