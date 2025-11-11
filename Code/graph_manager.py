from networkx import MultiDiGraph

import networkx as nx
import osmnx as ox
import copy
import numpy as np
from collections import Counter


from constants import SafetyClass
import graph_preprocessing

class GraphManager:
    def __init__(self, location: str):
        self.location = location

        self.G_master = self.load_network()
        self.G_master = graph_preprocessing.add_elevation_data(self.G_master)
        self.G_master = graph_preprocessing.impute_missing_elevation(self.G_master)
        self.G_master = graph_preprocessing.clean_graph(self.G_master)
        self.G_master = graph_preprocessing.simplify_multidigraph_in_place(self.G_master)

    #region loading and creating Graphs
    def __create_master_graph(self, G_bike, G_drive) -> MultiDiGraph:
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
    
    def load_network(self) -> MultiDiGraph:
        print(f"Loading OSM networks for {self.location}...")
        G_bike = ox.graph_from_place(self.location, network_type="bike", simplify=True, retain_all=True)
        nx.set_edge_attributes(G_bike,True,"bike_allowed")
        #TODO further processing and setting of false

        G_drive = ox.graph_from_place(self.location, network_type="drive", simplify=True, retain_all=True)
        nx.set_edge_attributes(G_drive,True,"car_allowed")

        G_master = self.__create_master_graph(G_bike, G_drive)

        return G_master
    #endregion

    # region Subgraph generators
    def make_drive_subgraph(self, G:MultiDiGraph):
        return self._filter_edges(G, lambda d: d.get("car_allowed", False))

    #TODO need to set dangerous roads and bridges as not bikeable
    def make_bikeable_subgraph(self, G:MultiDiGraph):
        return self._filter_edges(G, lambda d: d.get("bike_allowed", False))

    def make_protected_subgraph(self, G:MultiDiGraph):
        return self._filter_edges(G, lambda d: d.get("safety") in ["safe", "very_safe"])
    
    def _filter_edges(self, G:MultiDiGraph, condition):
        #NOTE subgraph is view and read-only
        edges = [(u, v, k) 
                 for u, v, k, d in G.edges(keys=True, data=True) 
                 if condition(d)]
        return G.edge_subgraph(edges)
    #endregion

    def reallocate_edge(self, G:MultiDiGraph, edge_id, new_safety=SafetyClass.SAFE):
        """Simulate reallocating a road edge to bike use."""
        u,v,k = edge_id
        #NOTE Since the 'MultiGraph' has only one edge per direction, k will always be 0
        d = G[u][v][k] 
        d["car_lanes"] = max(d["car_lanes"]-1,0)
        if d["car_lanes"] == 0:
            d["car_allowed"] = False

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
            G.add_edge(v, u, **attrs)
    
    def summarise_road_type_stats(self, G:MultiDiGraph):
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

    