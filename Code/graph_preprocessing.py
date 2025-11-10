from math import isnan
from pickle import NONE
from networkx import DiGraph, MultiDiGraph
import osmnx as ox
import networkx as nx
import copy
import numpy as np
from constants import SafetyClass

#TODO very safe?
safety_to_risk_factor_map = {
    "safe": 1,
    "moderate": 1.5,
    "caution": 2 ,#NOTE Cyclists perceive travel on car-dominated lanes as twice as costly
    "dangerous": 4, #TODO highway twice as costly ig?
    "unsuitable": 2,
    "unclassified": 2,
}

def merge_semantically_equivalent_road_tags(G:MultiDiGraph):
    highway_equivalence = {
    # Merging link types
    "motorway_link": "motorway",
    "trunk_link": "trunk",
    "primary_link": "primary",
    "secondary_link": "secondary",
    "tertiary_link": "tertiary",
    
    # Local road equivalences
    "living_street": "residential",
    "unclassified": "residential",
    
    """# Access / minor roads
    "track": "service",""" #TODO
    
    # Non-motorised
    "footway": "non_motorised",
    "pedestrian": "non_motorised",
    "path": "non_motorised",
    "busway": "non_motorised"  # often bus-priority corridor #TODO?
    }

    cycle_equivalence = {
        "shared_lane" #TODO????
    }
    
    for _,_, data in G.edges(data=True):
        highway = data.get("highway")

        if isinstance(highway, list):
            updated_highway = []
            for entry in highway:
                if entry in highway_equivalence:
                    updated_highway.append(highway_equivalence[entry])
                else:
                    updated_highway.append(entry)
            data["highway"] = updated_highway
            continue

        if highway in highway_equivalence:
            data["highway"] = highway_equivalence[highway]

def select_primary_label(highway_list:list[str]|str, priority_order:list) -> str:
    """Select the highest priority highway type from a list."""
    if not isinstance(highway_list, list):
        return highway_list
    
    #print(highway_list)
    # Find highest priority highway type
    best_highway = highway_list[0]  # fallback
    best_priority = -1
    
    for highway in highway_list:
        try:
            priority = priority_order.index(highway)
            if priority > best_priority:
                best_priority = priority
                best_highway = highway
        except ValueError:
            # Highway type not in priority list, use as fallback
            continue
    
    return best_highway

def collapse_road_tag_lists(G):
    highway_priority = [          
        "service", # Lowest priority - often just access roads
        "residential",
        "pedestrian"
        "tertiary",
        "secondary",
        "primary",
        "trunk",
        "track"
        "cycleway"         # Highest priority - dedicated cycling infrastructure
    ]

    bicycle_priority = [
        # Lowest priority
        'None',
        'permissive'
        'yes',
        'private'
        'designated',
        # Highest priority
    ]

    cycleway_priority = [
        'None',
        'no',
        'crossing',
        'shared',
        'shared_lane', # cycling along side cars
        'lane', # lies within the roadway 
        'track', # separated by buffer
    ]

    for _, _, data in G.edges(data=True):
        highway = data.get("highway")
        #NOTE that some entries have a list of labels, and the safest option is taken for classification

        highway = select_primary_label(highway, highway_priority)
        data["highway"] = highway

        # Defines legal access — whether bicycles may use the way.
        bicycle = data.get("bicycle")
        bicycle = select_primary_label(bicycle, bicycle_priority)
        data['bicycle'] = bicycle

        #Describes infrastructure type — if and how a bike facility exists
        cycleway = data.get("cycleway")
        cycleway = select_primary_label(cycleway, cycleway_priority)
        data["cycleway"] = cycleway


def set_edge_attributes(G):
    for _, _, _, d in G.edges(keys=True, data=True):

        #Renames 'lanes' to 'lanes_car, and set to 1 as default
        d["car_lanes"] = (d.get("lanes",1))
        if d.get("lanes"):
         del d["lanes"]

        d["bike_lanes"] = 2 if d.get("safety") == SafetyClass.VERY_SAFE else 0

def clean_graph(G:MultiDiGraph) -> MultiDiGraph:
    """Merges semantically equivalent road tags and collapses road tag lists into just the most prominent one. Also projects the graph to have length in meters"""
    merge_semantically_equivalent_road_tags(G)
    collapse_road_tag_lists(G)
    bike_safety_classification(G)
    set_edge_attributes(G)

    # ensures accurate 'length' in meters
    G = ox.project_graph(G)           
    G = ox.distance.add_edge_lengths(G)
    return G

#TODO
def bike_safety_classification(G_bike:MultiDiGraph):
    for _, _, data in G_bike.edges(data=True):
        #TODO although im filtering based on road priority for classification, i still need to see the seperate bike and car lanes
        # and in reality they should be 2 seperate graphs? but currently the bike can cycle over the car network
        # ig in reality i just need to see how these connections are being stored

        highway = data.get("highway")
        # Defines legal access — whether bicycles may use the way.
        bicycle = data.get("bicycle")
        #Describes infrastructure type — if and how a bike facility exists
        cycleway = data.get("cycleway")

        #Separated 
        if cycleway == 'track' or highway == "cycleway" or bicycle == "designated":
            classification = SafetyClass.VERY_SAFE
        #Demarcated Shared
        #NOTE shared_lane is not considered safe as the cyclist is travelling on the same road with no markings
        elif cycleway in {"shared", "lane",}:
            classification = SafetyClass.SAFE

        # MODERATE - Cyclist-friendly streets  
        elif highway in {"non_motorised", "residential"}:
            classification = SafetyClass.MODERATE

        # CAUTION - Mixed traffic but manageable
        elif highway == "service":
            classification = SafetyClass.CAUTION
        
        # Dangerous - active traffic
        elif highway in {"trunk", "secondary","primary", "tertiary"}:
            classification = SafetyClass.DANGEROUS

        #Country roads not suitable for urban transport
        elif highway == "track":
            #NOTE was "unsuitable" and has been changed to "moderate"
            classification = SafetyClass.MODERATE
        else:
            classification = SafetyClass.UNCLASSIFIED

        data["safety"] = classification
        data["risk_factor"] = safety_to_risk_factor_map.get(data.get("safety",-1))

        if classification == SafetyClass.DANGEROUS:
            data["bike_allowed"] = False
        #print(f"highway: {highway},\t\t bicycle: {bicycle},\t\t cycleway: {cycleway}") 


#region Grade
def add_elevation_data(G:MultiDiGraph, batch_size = 100, pause = 5) -> MultiDiGraph:
    print("Adding elevation data.....")
    ox.settings.elevation_url_template = (
    "https://api.opentopodata.org/v1/eudem25m?locations={locations}"
    )

    G = ox.add_node_elevations_google(G, batch_size=batch_size, pause=pause)
    G = ox.elevation.add_edge_grades(G, add_absolute=True)

    return G

def impute_missing_elevation(G:MultiDiGraph, max_iter=10) -> MultiDiGraph:
    """Nodes with missing elevation take the median of their neighbours. This is repeated multiple times in the case where elevationless nodes are completely surrounded with nodes that are also missing elevation data"""
    print("Imputing missing elevation values")
    for it in range(max_iter):
        changed = 0
        for node, data in G.nodes(data=True):
            elev = data.get("elevation")
            if np.isnan(elev) or elev is None:
                neigh_elevs = [
                    G.nodes[n].get("elevation")
                    for n in G.neighbors(node)
                    if G.nodes[n].get("elevation") is not None #.get() returns None if node doesnt have elevation 
                    and not np.isnan(G.nodes[n]["elevation"])
                ]

                if neigh_elevs:
                    data["elevation"] = np.median(neigh_elevs)
                    changed += 1
    
        print(f"Iteration {it+1}: imputed {changed} nodes")
        if changed == 0:
            break

    #TODO idk why man :Sob:
    print("node elevation",G.nodes[9068823240].get("elevation"), type(G.nodes[9068823240].get("elevation")))
    full_elevation = [d["elevation"] for _,d in G.nodes(data=True) 
                      if (d["elevation"] is not None) and (not np.isnan(d["elevation"])) ]
    median_elevation = np.median(full_elevation)
    for node, data in G.nodes(data=True):
            elev = data.get("elevation")
            if np.isnan(elev) or elev is None:
                print(f"NOde{node} elevation is problematic :/")
                data["elevation"] = float(median_elevation)

    print("node elevation", G.nodes[9068823240].get("elevation"), type(G.nodes[9068823240].get("elevation")))

    #Recalculate grades and clamp to reasonable values
    G = ox.elevation.add_edge_grades(G, add_absolute=True)

    for _,_, data in G.edges(data=True):
        data["grade"] = float(np.clip(data["grade"], -0.2, 0.2))
        data["grade_abs"] = float(min(data["grade_abs"], 0.2))

    return G

#endregion
def simplify_multidigraph_in_place(G):
    """Merge same-direction parallel edges in a MultiDiGraph while keeping it a MultiDiGraph."""
    merged_edges = []

    # Iterate over each directed node pair that has multiple edges
    edges_to_process = list(G.edges())
    for u, v in edges_to_process:
        if not G.has_edge(u, v):
            continue  # it may have been removed already

        data_dict = G[u][v]
        if len(data_dict) <= 1:
            continue  # only one edge → nothing to merge

        # gather all edge data
        edges = list(data_dict.values())

        agg = {}

        # attributes to aggregate
        numeric_attrs = ["length", "grade"]
        summed_attrs  = ["lanes_car", "lanes_bike"]
        bool_attrs    = ["car_allowed", "bike_allowed"]
        categorical_attrs = ["highway", "safety", "cycleway"]

        # average numeric values
        for attr in numeric_attrs:
            vals = [d.get(attr) for d in edges if d.get(attr) is not None]
            if vals:
                agg[attr] = float(np.mean(vals))

        # sum lane counts
        for attr in summed_attrs:
            vals = [d.get(attr) for d in edges if d.get(attr) is not None]
            if vals:
                agg[attr] = int(np.sum(vals))

        # boolean OR
        for attr in bool_attrs:
            agg[attr] = any(d.get(attr, False) for d in edges)

        # pick most bike-friendly safety class if available
        #TODO Nuh
        for attr in categorical_attrs:
            vals = [d.get(attr) for d in edges if d.get(attr) not in (None, "", np.nan)]
            if vals:
                if attr == "safety" and "safety_to_risk_factor_map" in globals():
                    agg[attr] = min(vals, key=lambda x: safety_to_risk_factor_map.get(x, 99))
                else:
                    agg[attr] = vals[0]
            else:
                agg[attr] = None

        merged_edges.append((u, v, agg))

        # remove the old parallel edges
        for key in list(data_dict.keys()):
            G.remove_edge(u, v, key)

    # add back one merged edge per direction
    for u, v, attrs in merged_edges:
        G.add_edge(u, v, **attrs)

    return G