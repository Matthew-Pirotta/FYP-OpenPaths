from networkx import MultiDiGraph
import osmnx as ox
import networkx as nx
import numpy as np

from . import clean_input_data
from . import enrich_attributes
from . import graph_structure

def __create_master_graph(G_bike, G_drive) -> MultiDiGraph:
        """Combine bike and drive networks into one multimodal master graph."""
        print("creating master graph network...")
        #NOTE attributes from G_bike take precedent
        G_master = nx.compose(G_drive, G_bike)
        G_master = ox.truncate.largest_component(G_master, strongly=False) # NOTE we kept all the disconnected networks in the subgraphs but the master network will only contain the lcc, since we cant add roads and only change they will never be reachable

        # tag drive edges
        for u, v, k, d in G_drive.edges(keys=True, data=True):
            if not G_master.has_edge(u,v):
                continue
            G_master[u][v][k]["car_allowed"] = True
        
        # tag bike edges
        for u, v, k, d in G_bike.edges(keys=True, data=True):
            if not G_master.has_edge(u,v):
                continue
            G_master[u][v][k]["bike_allowed"] = True

        return G_master

def load_network(location) -> MultiDiGraph:
        print(f"Loading OSM networks for {location}...")
        G_bike = ox.graph_from_place(location, network_type="bike", simplify=True, retain_all=True)
        nx.set_edge_attributes(G_bike,True,"bike_allowed")
        #TODO further processing and setting of false

        G_drive = ox.graph_from_place(location, network_type="drive", simplify=True, retain_all=True)
        nx.set_edge_attributes(G_drive,True,"car_allowed")

        G_master = __create_master_graph(G_bike, G_drive)

        return G_master

def clean_graph(G:MultiDiGraph):
    """Merges semantically equivalent road tags and collapses road tag lists into just the most prominent one. Also projects the graph to have length in meters"""

    # --------------------
    clean_input_data.add_elevation_data(G)
    clean_input_data.impute_missing_elevation(G)
    clean_input_data.merge_semantically_equivalent_road_tags(G)
    clean_input_data.collapse_road_tag_lists(G)
    clean_input_data.standardise_edge_atr(G)

    # ensures accurate 'length' in meters
    G = ox.project_graph(G)           
    G = ox.distance.add_edge_lengths(G)

    enrich_attributes.bike_safety_classification(G)
    gdf_localities_proj = enrich_attributes.load_and_clean_localities(G)
    #NOTE imp to project before assigning regions due to using x and y co-ordinates
    G = enrich_attributes.assign_edge_regions(G, gdf_localities_proj)


    graph_structure.simplify_multidigraph_in_place(G)
    return G, gdf_localities_proj