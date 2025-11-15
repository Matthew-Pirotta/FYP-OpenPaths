from networkx import MultiDiGraph
import osmnx as ox
import networkx as nx
import numpy as np
from constants import SafetyClass

#region road tags
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

def collapse_lanes_list(G):
    pass
#endregion

def standardise_edge_atr(G):
    for u, v, _, d in G.edges(keys=True, data=True):

        #Renames 'lanes' to 'car_lanes, and set to 1 as default
        lanes_val = d.get("lanes", 1)
        # Normalize to a single numeric value
        if isinstance(lanes_val, list):
            # sometimes it's ['2', '3']; assume these are all separate lanes
            #print(f"edge {u}->{v} has lanes as a list")
            #print(f"{d}")
            lanes_val = sum(int(x) for x in lanes_val if str(x).isdigit())
        elif isinstance(lanes_val, str):
            # simple case: "2"
            lanes_val = int(lanes_val) if lanes_val.isdigit() else 1

        d["car_lanes"] = int(lanes_val)

        # remove old 'lanes' tag
        if "lanes" in d:
            del d["lanes"]

        d["bike_lanes"] = 2 if d.get("safety") == SafetyClass.VERY_SAFE else 0


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