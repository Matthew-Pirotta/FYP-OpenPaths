from networkx import MultiDiGraph
import osmnx as ox
import networkx as nx
import numpy as np
from constants import SafetyClass
from . import tag_utils
from shapely.geometry import LineString
import constants


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
    for _, _, data in G.edges(data=True):

        data["highway"] = select_primary_label(
            data.get("highway"), tag_utils.HIGHWAY_PRIORITY
        )

        data["bicycle"] = select_primary_label(
            data.get("bicycle"), tag_utils.BICYCLE_PRIORITY
        )

        data["cycleway"] = select_primary_label(
            data.get("cycleway"), tag_utils.CYCLEWAY_PRIORITY
        )

def collapse_lanes_list(G):
    pass
#endregion


def remove_self_loops(G:MultiDiGraph):
    """Self loops need to be removed as they have a lenght of 0, and are not meaningful NOTE (roundabouts are currently represted by multiple nodes)"""
    loops = list(nx.selfloop_edges(G))
    print(f"removed {len(loops)} self loops")
    G.remove_edges_from(loops)

    return G


def add_max_speed(G):
    """
    Add the following attributes the edges,
    The original speed kph
    and the current kph if there are any reallocations, this is initialised to the original kph.
    """

    hwy_speeds:dict[str,int] = {
        "trunk": 70,         # Fastest: Major arterial / high-capacity road
        "primary": 60,       # Main city connectors
        "secondary": 60,     # Main local routes
        "tertiary": 50,      # Collector roads between neighborhoods
        "residential": 30,   # Local neighborhood streets
        "service": 30,       # Alleyways, parking lot access, etc.
    }

    #TODO use the road type as fallback instead
    G = ox.add_edge_speeds(G, hwy_speeds=hwy_speeds, fallback=constants.DEFUALT_MAXIUM_SPEED_KMH)

    for u, v, _, d in G.edges(keys=True, data=True):
        #Renames 'speed_kph' to 'speed_kph_original'
        d["speed_kph_original"] = d.get("speed_kph")
        d["speed_kph_current"] = d["speed_kph_original"]

        # remove old 'speed_kph' tag
        if "lanes" in d:
            del d["speed_kph"]

    
    from collections import Counter

    speeds = [d.get("speed_kph_current") for _, _, _, d in G.edges(keys=True, data=True) if d.get("speed_kph_current") is not None]
    speed_counts = Counter(speeds)

    for spd, cnt in sorted(speed_counts.items()):
        print(f"{spd:>5} kph : {cnt}")

    return G

#TODO need to do a better job, example car_allowed and bike_allowed
def standardise_edge_atr(G):

    #NOTE unfortunatly some streets are not tagged with a lane count, these are assumed to be single lanes
    def clean_lanes(unclean_lane):
        # Normalize to a single numeric value
        if isinstance(unclean_lane, list):
            # Summing list elements: e.g., ['2', '1'] becomes 3
            unclean_lane = sum(int(x) for x in unclean_lane if str(x).isdigit())
        elif isinstance(unclean_lane, str):
            # simple case: "2"
            unclean_lane = int(unclean_lane) if unclean_lane.isdigit() else 1

        return unclean_lane

    for u, v, _, d in G.edges(keys=True, data=True):

        #Renames 'lanes' to 'car_lanes, and set to 1 as default
        car_lanes = 1
        if d.get("car_allowed", False):
            car_lanes = d.get("lanes", 1)
            car_lanes = clean_lanes(car_lanes)
        d["car_lanes"] = car_lanes

        #TODO idk if this is correct
        bike_lanes = 1
        if d.get("bike_allowed", False):
            bike_lanes = d.get("lanes", 1)
            bike_lanes = clean_lanes(bike_lanes)
        d["bike_lanes"] = bike_lanes
        #TODO IDK d["bike_lanes"] = 2 if d.get("safety") == SafetyClass.VERY_SAFE else 0

        # remove old 'lanes' tag
        if "lanes" in d:
            del d["lanes"]

def ensure_edge_geometries(G:MultiDiGraph):
    for u, v, k, d in G.edges(keys=True, data=True):
        geom = d.get("geometry")
        if geom is None:
            geom = LineString([
                (G.nodes[u]["x"], G.nodes[u]["y"]),
                (G.nodes[v]["x"], G.nodes[v]["y"])
            ])
            d["geometry"] = geom



#region Grade
def add_elevation_data(G:MultiDiGraph, batch_size = 100, pause = 5) -> MultiDiGraph:
    print("Adding elevation data.....")
    ox.settings.elevation_url_template = (
    "https://api.opentopodata.org/v1/eudem25m?locations={locations}"
    )

    G = ox.add_node_elevations_google(G, batch_size=batch_size, pause=pause)

    return G

def impute_missing_elevation(G:MultiDiGraph, max_iter=10) -> MultiDiGraph:
    """Nodes with missing elevation take the median of their neighbours. This is repeated multiple times in the case where elevationless nodes are completely surrounded with nodes that are also missing elevation data"""
    print("Imputing missing elevation values")
    UG = G.to_undirected(as_view=True)
    for it in range(max_iter):
        changed = 0
        for node, data in G.nodes(data=True):
            elev = data.get("elevation")
            if elev is None or np.isnan(elev):

                neigh_elevs = []
                for n in UG.neighbors(node):
                    e = G.nodes[n].get("elevation")
                    if e is not None and not np.isnan(e):
                        neigh_elevs.append(e)

                if neigh_elevs:
                    data["elevation"] = np.median(neigh_elevs)
                    changed += 1
    
        print(f"Iteration {it+1}: imputed {changed} nodes")
        if changed == 0:
            break
      
    #TODO idk why man :Sob:
    """         
    print("node elevation",G.nodes[9068823240].get("elevation"), type(G.nodes[9068823240].get("elevation")))
    full_elevation = [d["elevation"] for _,d in G.nodes(data=True) 
                      if (d["elevation"] is not None) and (not np.isnan(d["elevation"])) ]
    median_elevation = np.median(full_elevation)
    for node, data in G.nodes(data=True):
            elev = data.get("elevation")
            if np.isnan(elev) or elev is None:
                print(f"NOde{node} elevation is problematic :/")
                data["elevation"] = float(median_elevation)

    print("node elevation", G.nodes[9068823240].get("elevation"), type(G.nodes[9068823240].get("elevation")))"""
    
    return G


def add_grades(G:MultiDiGraph):
    """
    Calculate grades and clamp to reasonable values
    """
    G = ox.elevation.add_edge_grades(G, add_absolute=True)

    for _,_, data in G.edges(data=True):
        data["grade"] = float(np.clip(data["grade"], -0.2, 0.2))
        data["grade_abs"] = float(min(data["grade_abs"], 0.2))

    return G
#endregion


#TODO this is gonna cuase problems for sumo
def ensure_bidirectional_bike(G_drive: MultiDiGraph):
    """
    Create a synthetic edge for bikes allowing for bidrectional flow
    """
    #NOTE This is not creating artifical lanes because the lane counts are set to 0
    # Wiedmann did not have this issue as their ground source thruth was an undirected graph, and created a directed graph from there
    new_edges = []
    reallocated = []

    for u, v, _, d in G_drive.edges(keys=True, data=True):
        # Only process if it's the reverse doesn't exist
        if not G_drive.has_edge(v, u):
            attrs = d.copy()
            attrs["bike_allowed"] = d.get("bike_allowed")
            attrs["car_allowed"] = False  # no car traffic on this synthetic link
            attrs["bike_lanes"] = 0
            attrs["car_lanes"] = 0
            
            attrs["geometry"] = d["geometry"]
            #attrs["grade"] = -d["grade"]
            
            # Set specific bike-safety attributes
            attrs["risk_factor"] = d.get("risk_factor")
            attrs["reallocatable"] = False
            attrs["infra_type"] = d.get("infra_type")
            attrs["safety"] =  d.get("safety")
            attrs["speed_kph_current"] = d.get("speed_kph_current")
            
            # Map cost logic
            attrs["car_cost_current"] = d.get("car_cost_if_fietsstraat", 0)

            # Store to add after iteration to avoid 'dictionary changed size during iteration'
            new_edges.append((v, u, attrs))

    # Add the newly created edges to the Graph
    for v, u, attrs in new_edges:
        G_drive.add_edge(v, u, **attrs)
        # If adding a new first edge in that direction, the key is 0
        reallocated.append((v, u, 0))

    return reallocated


#region others

#Although sumo internally checks for roundabouts as oneway during graph creation https://github.com/gboeing/osmnx/blob/main/osmnx/graph.py#L783#
# This is only being used internally and not being set within the edge, <- NVM not true it actually is being set L850, but actually it wasnt being set when running the sumo sim cos of the settings.all_oneway
# BUt if i need any of this depends if i keep sumo
# TODO set the default oneway value to true?
def set_roundabouts_oneway(G:MultiDiGraph):
    """This is done to prevent a lane being counterflow in roundabouts during the sumo simulation"""
    for u, v, k, d in G.edges(keys=True, data=True):
        # Check if the edge is part of a roundabout
        if d.get("junction") == "roundabout":
            # Force it to be one-way
            d["oneway"] = True 
    
    return G

#endregion