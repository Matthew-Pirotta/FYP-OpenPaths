from networkx import MultiDiGraph
import networkx as nx
import osmnx as ox
import copy
import numpy as np
from collections import Counter


from constants import SafetyClass

FIETSSRAAT_MAX_SPEED = 10

# region Subgraph generators
def make_drive_subgraph(G:MultiDiGraph) -> MultiDiGraph:
    return _filter_edges(G, lambda d: d.get("car_allowed", False))

#TODO need to set dangerous roads and bridges as not bikeable
def make_bikeable_subgraph(G:MultiDiGraph)-> MultiDiGraph:
    return _filter_edges(G, lambda d: d.get("bike_allowed", False))

def make_reallocatable_subgraph(G:MultiDiGraph)-> MultiDiGraph:
    #concern might have car_lanes = 0, car_allowed = false, but somehow reallocatable = True?
    return _filter_edges(G, lambda d: d.get("reallocatable") == True)

def make_protected_subgraph(G:MultiDiGraph)-> MultiDiGraph:
    return _filter_edges(G, lambda d: d.get("safety") in ["safe", "very_safe"])

def make_region_subgraph(G:MultiDiGraph, region)-> MultiDiGraph:
    return _filter_edges(G, lambda d: d.get("region") == region)

def make_locality_subgraph(G:MultiDiGraph, locality) -> MultiDiGraph:
    return _filter_edges(G, lambda d: d.get("locality") == locality)

def _filter_edges(G:MultiDiGraph, condition) -> MultiDiGraph:
    #NOTE subgraph is view and read-only
    #NOTE TODO made copy so its not read-only lol
    edges = [(u, v, k) 
                for u, v, k, d in G.edges(keys=True, data=True) 
                if condition(d)]
    return G.edge_subgraph(edges).copy()
#endregion

def check_edge_reallocateability(G_drive:MultiDiGraph, edge_id) -> bool:
    return True
    """Updates the reallocatable attribute in place"""
    # Work on a shallow copy (just edge structure)
    u,v,k = edge_id
    d = G_drive[u][v][k]
    car_lanes = d.get("car_lanes")
    #Reachability is not affected if a lane is removed
    if car_lanes >= 2:
        return True

    G_test = copy.deepcopy(G_drive)
    G_test.remove_edge(u, v, k)
    stays_connected = nx.is_strongly_connected(G_test)

    # Choose strong or weak connectivity depending on road model
    return stays_connected

#TODO currently can reallocate from the main road, big no no, need to set a more restrictive subgraph view
def reallocate_edge(G:MultiDiGraph, edge_id:tuple):
    """Convert an edge into a fietsstraat (bike-priority street)."""
    u, v, k = edge_id
    d = G[u][v][k]

    # 1. Cars still allowed but as guests
    d["car_allowed"] = True
    # No lane reduction: cars share space
    
    # 2. Bikes explicitly allowed
    d["bike_allowed"] = True
    
    # 3. Fietsstraat classification
    d["infra_type"] = "fietsstraat"
    
    # 4. Set safety level appropriate to fietsstraat
    d["safety"] = SafetyClass.SAFE
    #d["risk_factor"] = float(safety_to_risk_factor_map[SafetyClass.SAFE])

    #5.
    d["maxspeed"] = FIETSSRAAT_MAX_SPEED

    # 6. After conversion, edge should not be converted again
    d["reallocatable"] = False

    
    # 7. Directionality preserved:
    # If reverse exists, classify it too (but do NOT create new synthetic edges)
    if G.has_edge(v, u):
        #TODO this 0 indexing could be a problem depending on if i keep the multi digraph
        d_rev = G[v][u][0]
        d_rev["car_allowed"] = True
        d_rev["bike_allowed"] = True
        d_rev["infra_type"] = "fietsstraat"
        d_rev["safety"] = SafetyClass.SAFE
        d_rev["maxspeed"] = FIETSSRAAT_MAX_SPEED
        #d_rev["risk_factor"] = float(safety_to_risk_factor_map[SafetyClass.SAFE])
        G[v][u][0]["reallocatable"] = False

def summarise_road_type_stats(G:MultiDiGraph):
    highway_counts = Counter()
    bikeway_counts = Counter()
    cycleway_counts = Counter()
    tunnel_counts = Counter()


    for u, v, data in G.edges(data=True):
        highway_counts[data.get("highway")] += 1
        bikeway_counts[data.get("bicycle")] += 1
        cycleway_counts[data.get("cycleway")] += 1
        tunnel_counts[data.get("tunnel")] += 1
    
    print("Highway type counts:")
    for highway_type, count in highway_counts.most_common():
        print(f"{highway_type}: {count}")

    print("-------")
    print("bikeway classification type counts:")
    for bikeway_type, count in bikeway_counts.most_common():
        print(f"{bikeway_type}: {count}")

    print("------")
    print("cycleway type counts:")
    for cycleway_type, count in cycleway_counts.most_common():
        print(f"{cycleway_type}: {count}")
    
    print("------")
    print("tunnel counts:")
    for tunnel_type, count in tunnel_counts.most_common():
        print(f"{tunnel_type}: {count}")


def set_edge_attribute(G:MultiDiGraph, edge:tuple, attribute_name:str, value) -> MultiDiGraph:
    u,v,k = edge
    data = G[u][v][k]
    data[attribute_name] = value
    return G