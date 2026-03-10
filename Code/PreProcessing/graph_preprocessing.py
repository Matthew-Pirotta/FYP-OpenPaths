from networkx import MultiDiGraph
import osmnx as ox
import networkx as nx
import numpy as np

from . import clean_input_data, enrich_attributes, graph_structure
from NetworkOptimisation import impedance_calculator
import graph_util
import constants

def __create_master_graph(G_bike, G_drive) -> MultiDiGraph:
        """Combine bike and drive networks into one multimodal master graph."""
        print("creating master graph network...")
        #NOTE attributes from G_bike take precedent
        G_master = nx.compose(G_drive, G_bike)
        G_master = ox.truncate.largest_component(G_master, strongly=False) # NOTE we kept all the disconnected networks in the subgraphs but the master network will only contain the lcc, since we cant add roads and only change they will never be reachable

        # tag drive edges
        for u, v, k, d in G_drive.edges(keys=True, data=True):
            if not G_master.has_edge(u,v, k):
                continue
            G_master[u][v][k]["car_allowed"] = True
        
        # tag bike edges
        for u, v, k, d in G_bike.edges(keys=True, data=True):
            if not G_master.has_edge(u,v, k):
                continue
            G_master[u][v][k]["bike_allowed"] = True

        return G_master

def load_network(location) -> MultiDiGraph:
        print(f"Loading OSM networks for {location}...")
        G_bike = ox.graph_from_place(location, network_type="bike", simplify=True, retain_all=False)
        nx.set_edge_attributes(G_bike,True,"bike_allowed")
        #TODO further processing and setting of false

        #TODO should be drive_service?
        G_drive = ox.graph_from_place(location, network_type="drive", simplify=True, retain_all=False)
        G_drive = ox.truncate.largest_component(G_drive, strongly=True)
        nx.set_edge_attributes(G_drive,True,"car_allowed")
        #TODO edge attributes code is being dupplicated in the __create_master graph. Also didnt set False values:

        G_master = __create_master_graph(G_bike, G_drive)

        return G_master


def audit_elevation_and_grade(G, label=""):
    import numpy as np
    from collections import Counter

    missing_nodes = [
        n for n, d in G.nodes(data=True)
        if d.get("elevation") is None or (isinstance(d.get("elevation"), (int, float)) and np.isnan(d.get("elevation")))
    ]

    bad_edges = []
    for u, v, k, d in G.edges(keys=True, data=True):
        if d.get("grade") is None or (isinstance(d.get("grade"), (int, float)) and np.isnan(d.get("grade"))):
            bad_edges.append((u, v, k, G.nodes[u].get("elevation"), G.nodes[v].get("elevation"), d.get("length")))

    grade_counts = Counter()
    for _, _, _, d in G.edges(keys=True, data=True):
        g = d.get("grade")
        if not isinstance(g, (int, float)):
            grade_counts[g] += 1

    print(f"\n--- AUDIT: {label} ---")
    print("nodes:", G.number_of_nodes(), "edges:", G.number_of_edges())
    print("missing elevation nodes:", len(missing_nodes))
    print("grade None/NaN edges:", len(bad_edges))
    print("non-numeric grade counts:", grade_counts.most_common(5))
    if bad_edges:
        print("sample bad edges:", bad_edges[:10])


def clean_graph(G:MultiDiGraph, place_name):
    """Merges semantically equivalent road tags and collapses road tag lists into just the most prominent one. Also projects the graph to have length in meters"""

    # --------------------
    clean_input_data.remove_self_loops(G)
    G = clean_input_data.add_elevation_data(G)
    G = clean_input_data.impute_missing_elevation(G)

    clean_input_data.merge_semantically_equivalent_road_tags(G)
    clean_input_data.collapse_road_tag_lists(G)
    G = clean_input_data.add_max_speed(G)
    clean_input_data.standardise_edge_atr(G)
    clean_input_data.ensure_edge_geometries(G)
    clean_input_data.ensure_bidirectional_bike(G)

    # simplify topology (may change geometries), then recompute accurate lengths
    graph_structure.simplify_multidigraph_in_place(G)
    
    # ensures accurate 'length' in meters
    G = ox.project_graph(G) 


    #G = ox.distance.add_edge_lengths(G) # This is reprojecting the lenghts after already projecting
    G = clean_input_data.add_grades(G)

    enrich_attributes.bike_safety_classification(G)
    impedance_calculator.update_bike_costs(G)
    impedance_calculator.update_car_costs(G)
    enrich_attributes.tag_reallocatable_edges(G, verbose=True)
    gdf_regions_proj, gdf_local_proj = enrich_attributes.load_and_clean_localities(G, place_name, constants.LOCALITY_TO_REGION)
    #NOTE imp to project before assigning regions due to using x and y co-ordinates
    G = enrich_attributes.assign_spatial_context(G, gdf_regions_proj, gdf_local_proj)

    return G, gdf_regions_proj, gdf_local_proj