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
    
    print(highway_list)
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


def clean_graph(G:MultiDiGraph) -> MultiDiGraph:
    """Merges semantically equivalent road tags and collapses road tag lists into just the most prominent one. Also projects the graph to have length in meters"""
    merge_semantically_equivalent_road_tags(G)
    collapse_road_tag_lists(G)
    bike_safety_classification(G)

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
        elif cycleway in {"shared", "lane"}:
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

        #print(f"highway: {highway},\t\t bicycle: {bicycle},\t\t cycleway: {cycleway}") 


#region Grade
def add_elevation_data(G:MultiDiGraph, batch_size = 100, pause = 5) -> MultiDiGraph:
    ox.settings.elevation_url_template = (
    "https://api.opentopodata.org/v1/eudem25m?locations={locations}"
    )

    G = ox.add_node_elevations_google(G, batch_size=batch_size, pause=pause)
    G = ox.elevation.add_edge_grades(G, add_absolute=True)

    return G

def impute_missing_elevation(G:MultiDiGraph, max_iter=10) -> MultiDiGraph:
    """Nodes with missing elevation take the median of their neighbours. This is repeated multiple times in the case where elevationless nodes are completely surrounded with nodes that are also missing elevation data"""
    for it in range(max_iter):
        changed = 0
        for node, data in G.nodes(data=True):
            elev = data.get("elevation")
            if np.isnan(elev):
                print(elev,type(elev),",", f"is elev none {elev is None}", ",",f"is np.isnan(elev):{np.isnan(elev)}")
                neigh_elevs = [
                    G.nodes[n].get("elevation")
                    for n in G.neighbors(node)
                    if G.nodes[n].get("elevation") is not None #.get() returns None if node doesnt have elevation 
                    and not np.isnan(G.nodes[n]["elevation"])
                ]

                """                
                for n in G.neighbors(node):
                n_elev = G.nodes[n].get("elevation")
                print(n_elev,type(n_elev),",", f"is n_elev none {n_elev is None}", ",",f"is np.isnan(n_elev):{np.isnan(n_elev)}")"""

                if neigh_elevs:
                    data["elevation"] = np.median(neigh_elevs)
                    changed += 1
    
        print(f"Iteration {it+1}: imputed {changed} nodes")
        if changed == 0:
            break

    #Recalculate grades and clamp to reasonable values
    G = ox.elevation.add_edge_grades(G, add_absolute=True)

    for _,_, data in G.edges(data=True):
        data["grade"] = float(np.clip(data["grade"], -0.2, 0.2))
        data["grade_abs"] = float(min(data["grade_abs"], 0.2))

    return G

#endregion