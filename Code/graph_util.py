from networkx import MultiDiGraph
import networkx as nx
import osmnx as ox
import copy
import numpy as np
from collections import Counter


from constants import SafetyClass

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
def reallocate_edge(G:MultiDiGraph, edge_id, new_safety=SafetyClass.VERY_SAFE):
    """Simulate reallocating a road edge to bike use."""
    u,v,k = edge_id
    #NOTE Since the 'MultiGraph' has only one edge per direction, k will always be 0
    d = G[u][v][k] 
    d["car_lanes"] = max(d["car_lanes"]-1,0)
    if d["car_lanes"] == 0:
        #d["car_allowed"] = False
        d["reallocatable"] = False

    #removing one car lane adds 1 bike lane in each direction
    d["bike_allowed"] = True
    d["bike_lanes"] += 1
    d["safety"] = new_safety

    # --- Reverse direction ---
    if G.has_edge(v, u):
        rev = G[v][u][0]
        rev["bike_allowed"] = True
        rev["bike_lanes"] = rev.get("bike_lanes") + 1
        rev["safety"] = new_safety
    else: #create edge if it doesn't exist
        attrs = d.copy()
        attrs["bike_allowed"] = True
        attrs["bike_lanes"] = 1
        attrs["car_allowed"] = False  # no car traffic on this synthetic link
        attrs["car_lanes"] = 0
        attrs["geometry"] = d["geometry"].reverse() #road shape
        attrs["grade"] = -d["grade"]
        attrs["reallocatable"] = False
        G.add_edge(v, u, **attrs)

def summarise_road_type_stats(G:MultiDiGraph):
    highway_counts = Counter()
    bikeway_counts = Counter()
    cycleway_counts = Counter()

    for u, v, data in G.edges(data=True):
        highway_counts[data.get("highway")] += 1
        bikeway_counts[data.get("bicycle")] += 1
        cycleway_counts[data.get("cycleway")] += 1
    
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


def set_edge_attribute(G:MultiDiGraph, edge:tuple, attribute_name:str, value) -> MultiDiGraph:
    u,v,k = edge
    data = G[u][v][k]
    data[attribute_name] = value
    return G