from networkx import MultiDiGraph
import networkx as nx
import osmnx as ox
import copy
import numpy as np
from collections import Counter, defaultdict

import constants
from constants import SafetyClass
from PreProcessing import enrich_attributes
from typing import Literal
from NetworkOptimisation import impedance_calculator
from shapely.geometry import LineString

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
    return _filter_edges(G, lambda d: d.get("safety") in [SafetyClass.SAFE, SafetyClass.VERY_SAFE])

def make_region_subgraph(G: MultiDiGraph, region: str) -> MultiDiGraph:
    """
    Subgraph containing all edges that intersect the given region.
    Boundary edges are included.
    """
    return _filter_edges(G, lambda d: region in d.get("regions"))

def make_locality_subgraph(G:MultiDiGraph, locality) -> MultiDiGraph:
    return _filter_edges(G, lambda d: locality in d.get("localities"))

def make_highway_subgraph(G:MultiDiGraph,
                           road_type:Literal["primary", "residential", "service", "track", "tertiary", "secondary"]) -> MultiDiGraph:
    return _filter_edges(G, lambda d: d.get("highway") == road_type)



def _filter_edges(G:MultiDiGraph, condition) -> MultiDiGraph:
    #NOTE subgraph is view and read-only
    #NOTE TODO made copy so its not read-only lol
    # NOTE TODO use nx.subgraph_view if they are just views
    edges = [(u, v, k) 
                for u, v, k, d in G.edges(keys=True, data=True) 
                if condition(d)]
    return G.edge_subgraph(edges).copy()
#endregion

#region reallocation
def check_edge_reallocateability(G_drive:MultiDiGraph, edge_id) -> bool:
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


def _create_bike_edge(G, u, v, base_data):
    """
    Create a new bike-only edge parallel to (u, v).
    Returns (u, v, new_key)
    """
    new_data = copy.deepcopy(base_data)

    # Mode permissions
    new_data["car_allowed"] = False
    new_data["bike_allowed"] = True

    # Infrastructure classification
    new_data["highway"] = "cycleway"
    new_data["bicycle"] = "designated"
    new_data["infra_type"] = "dedicated_bike_lane"

    # Ensure safe defaults
    new_data["bike_lanes"] = new_data.get("bike_lanes", 0) + 1

    # Safety
    new_data["safety"] = SafetyClass.VERY_SAFE
    new_data["risk_factor"] = float(
        enrich_attributes.safety_to_risk_factor_map[SafetyClass.VERY_SAFE]
    )

    # Prevent reallocation loops
    new_data["reallocatable"] = False

    # Add as a new parallel edge
    new_key = G.add_edge(u, v, **new_data)

    return (u, v, new_key)

def _has_dedicated_bike_edge(G, u, v):
    if not G.has_edge(u, v):
        return False

    for k, d in G[u][v].items():
        if d.get("highway") == "cycleway":
            return True
    return False

#TODO this is all useless idk
def reallocate_edge_dedicated(G: MultiDiGraph, edge_id: tuple,) -> list[tuple]:
    """
    Create dedicated bike edges instead of modifying existing ones. Changes are made inplace
    """
    u, v, k = edge_id
    d = G[u][v][k]

    reallocated = []

    d["car_lanes"] = max(0, d.get("car_lanes", 1) - 1)

    # Prevent repeated reallocations
    d["reallocatable"] = False

    # --- 2. Create forward bike edge if missing ---
    if not _has_dedicated_bike_edge(G, u, v):
        new_edge = _create_bike_edge(G, u, v, d)
        reallocated.append(new_edge)

    # --- 3. Handle reverse direction ---
    if not _has_dedicated_bike_edge(G, v, u):
        # use reverse edge as template
        d_rev = copy.deepcopy(d)
        d_rev["grade"] = -d_rev.get("grade",0)
        d_rev["geometry"] = LineString(d_rev.get("geometry").coords[::-1])

        new_edge_rev = _create_bike_edge(G, v, u, d_rev)
        reallocated.append(new_edge_rev)

        # also lock original reverse edge
        d_rev["reallocatable"] = False

    # --- 4. Recompute costs only for new bike edges ---
    #TODO
    #enrich_attributes.update_bike_costs(G, reallocated)

    return reallocated


#endregion

def summarise_road_type_stats(G):
    # Map the edge attribute key to the label you want to print
    categories = {
        "highway": "Highway type counts",
        "bicycle": "Bikeway classification type counts",
        "cycleway": "Cycleway type counts",
        "tunnel": "Tunnel counts",
        "junction": "Juntion type counts",
        "turns": "turn type counts",
    }
    
    # Initialize counters for each category
    stats = {key: Counter() for key in categories}

    # Single pass over the edges
    for _, _, data in G.edges(data=True):
        for key in categories:
            stats[key][data.get(key)] += 1
    
    # Print the results
    for key, label in categories.items():
        print(f"{label}:")
        for val, count in stats[key].most_common():
            print(f"{val}: {count}")
        print("-" * 10)


def set_edge_attribute(G:MultiDiGraph, edge:tuple, attribute_name:str, value) -> MultiDiGraph:
    u,v,k = edge
    data = G[u][v][k]
    data[attribute_name] = value
    return G


#TODO check if i want to keep the deep copy or not
def recombine_subgraphs_into_master(
    G_master: MultiDiGraph,
    subgraphs: dict[str, MultiDiGraph],
) -> MultiDiGraph:
    """
    Recombine locality subgraphs back into a master graph.

    Rule:
      - If an edge is reallocated in at least one subgraph,
        it is reallocated in the master graph.
      - Reallocation is monotonic and irreversible.
    """

    G_new = copy.deepcopy(G_master)

    # Helper: detect whether an edge is reallocated
    def is_reallocated(d):
        return (
            d.get("infra_type") == "fietsstraat"
            or d.get("safety") == SafetyClass.SAFE
            or d.get("safety") == SafetyClass.VERY_SAFE
        )

    # Iterate over all subgraphs
    for loc_name, G_sub in subgraphs.items():
        for u, v, k, d_sub in G_sub.edges(keys=True, data=True):

            d_master = G_new[u][v][k]

            # If subgraph edge is reallocated and master is not yet
            if is_reallocated(d_sub) and not is_reallocated(d_master):
                # Apply reallocation in master
                # IMPORTANT: call the same canonical logic
                reallocate_edge_dedicated(G_new, (u, v, k))

    return G_new


#region simpligfied and unsimplified mapping
def apply_reallocation_to_unsimplified(G_simplified: MultiDiGraph,G_unsimplified: MultiDiGraph,reallocated_edges: list[tuple],) -> MultiDiGraph:
    """
    Projects reallocations from simplified graph onto unsimplified graph.
    """

    G_processed_unsimplified = copy.deepcopy(G_unsimplified)

    processed = set()
    for u, v, k in reallocated_edges:
        d_s = G_simplified[u][v][k]

        merged = d_s.get("merged_edges", [])
        if not merged:
            continue

        for (u0, v0) in merged:

            # avoid double application
            if (u0, v0) in processed:
                continue
            processed.add((u0, v0))
        
            edge_id_unsimplified = (u0, v0, 0)
            reallocate_edge_dedicated(G_processed_unsimplified, edge_id_unsimplified)

    return G_processed_unsimplified
            
#endregion

#region segment logic
# Applying steet segment level reallocation logic to formulation
# u,v and v,u are combined
def build_segment_arc_map(G:MultiDiGraph):
    """
    Groups directed edges into undirected segments.

    :param G: A NetworkX MultiDiGraph.
    :return: Dict mapping (min_node, max_node, key) to a list of (u, v, key) edges.
    """
    seg_to_arcs = defaultdict(list)

    for u, v, k in G.edges(keys=True):
        seg = (min(u, v), max(u, v), 0)
        seg_to_arcs[seg].append((u, v, k))
    return seg_to_arcs


def build_segment_coef(G,G_sub_reallocatable, eligible_edges, paths_bike, paths_car, gamma: float):
    """
    Build per-edge objective coefficients for the solver. The benefit and harm of edges are summed into their segements, as the solver will reallocate them in one go.

    coef[seg] = bike_benefit[e] - gamma * car_harm[e]

    Parameters
    ----------
    G : MultiDiGraph
        Authoritative graph (current state).
    G_sub_reallocatable : MultiDiGraph
        Sub graph which is filtered on teallocatable edges.
    eligible_edges : set[(u,v,k)]
        Edges allowed to be reallocated this iteration.
    paths_bike : dict[(o,d,w) -> list[node]]
        Current shortest bike paths.
    paths_car : dict[(o,d,w) -> list[node]]
        Current shortest car paths.
    gamma : float
        Weight of car harm relative to bike benefit.

    Returns
    -------
    dict[(u,v,k) -> float]
        Objective coefficient per eligible edge.
    """

    seg_to_arcs = build_segment_arc_map(G_sub_reallocatable)  
    arc_to_seg = {arc: seg for seg, arcs in seg_to_arcs.items() for arc in arcs}


    bike_benefit_seg = defaultdict(float)
    car_harm_seg = defaultdict(float)


    # --- Bike benefit aggregation ---
    for (o, d, w), path in paths_bike.items():
        for u, v in zip(path[:-1], path[1:]):
            e = (u, v, 0)
            seg = arc_to_seg.get(e)
            if seg not in seg_to_arcs: 
                continue
 
            edge = G[u][v][0]
            # Δb​(e)=bike cost before upgrade − bike cost after upgrade
            delta_bike = (edge["bike_cost_penalty"] - edge["bike_cost_base"])
            bike_benefit_seg[seg] += w * delta_bike

    # --- Car harm aggregation ---
    for (o, d, w), path in paths_car.items():
        for u, v in zip(path[:-1], path[1:]):
            e = (u, v, 0)
            seg = arc_to_seg.get(e)
            if seg not in seg_to_arcs: 
                continue

            edge = G[u][v][0]
            # Δc​(e)=car cost after upgrade − car cost before upgrade
            delta_car = (edge["car_cost_if_fietsstraat"] - edge["car_cost_current"])
            car_harm_seg[seg] += w * delta_car

    # --- Combine ---
    """
    If coef[e] > 0: upgrading is beneficial overall
    If coef[e] < 0: car harm outweighs bike benefit
    gamma controls how much you care about car harm relative to bike benefit
    """
    coef_seg = {}
    for seg, arcs in seg_to_arcs.items():
        # This explicitly calculates the balance for every eligible segment
        benefit = bike_benefit_seg[seg]
        harm = car_harm_seg[seg]
        coef_seg[seg] = benefit - (gamma * harm)

    return coef_seg, bike_benefit_seg, car_harm_seg
#endregion