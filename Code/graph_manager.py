from networkx import MultiDiGraph

import networkx as nx
import osmnx as ox
import copy
import numpy as np
from collections import Counter


import graph_preprocessing

class GraphManager:
    def __init__(self, location: str):
        self.location = location
        self.G_master = self.load_network()
        self.G_master = graph_preprocessing.clean_graph(self.G_master)


    def __create_master_graph(self, G_bike, G_drive) -> MultiDiGraph:
        """Combine bike and drive networks into one multimodal master graph."""
        #NOTE attributes from G_bike take precedent
        G_master = nx.compose(G_drive, G_bike)

        # Step 1: tag drive edges
        for u, v, k, d in G_drive.edges(keys=True, data=True):
            G_master[u][v][k]["car_allowed"] = True
        
        # Step 2: tag bike edges
        for u, v, k, d in G_bike.edges(keys=True, data=True):
            G_master[u][v][k]["bike_allowed"] = True

        return G_master
    
    def load_network(self) -> MultiDiGraph:
        print(f"Loading OSM networks for {self.location}...")
        G_bike = ox.graph_from_place(self.location, network_type="bike", simplify=True, retain_all=True)
        G_drive = ox.graph_from_place(self.location, network_type="drive", simplify=True, retain_all=True)

        G_master = self.__create_master_graph(G_bike, G_drive)

        return G_master


    # region Subgraph generators
    def make_drive_subgraph(self):
        return self._filter_edges(lambda d: d.get("car_allowed", False))

    def make_bikeable_subgraph(self):
        return self._filter_edges(lambda d: d.get("bike_allowed", False))

    def make_protected_subgraph(self):
        return self._filter_edges(lambda d: d.get("safety") in ["safe", "very_safe"])
    
    def _filter_edges(self, condition):
        edges = [(u, v, k) 
                 for u, v, k, d in self.G_master.edges(keys=True, data=True) 
                 if condition(d)]
        return self.G_master.edge_subgraph(edges).copy()    
    #endregion


    
    def summarise_road_type_stats(self, G:MultiDiGraph):
        print("hi")
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

