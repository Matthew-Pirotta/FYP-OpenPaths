from networkx import MultiDiGraph
import osmnx as ox
import networkx as nx
import numpy as np

from  . import clean_input_data as clean_input_data

def simplify_multidigraph_in_place(G):
    """Merge same-direction parallel edges in a MultiDiGraph while keeping it a MultiDiGraph."""
    merged_edges = []

    # Iterate over each directed node pair that has multiple edges
    edges_to_process = list(G.edges())
    for u, v in edges_to_process:
        if not G.has_edge(u, v):
            continue

        data_dict = G[u][v]
        if len(data_dict) <= 1:
            continue  # only one edge → nothing to merge

        # gather all edge data
        edges = list(data_dict.values())

        agg = {}

        # attributes to aggregate
        numeric_attrs = ["length", "grade"]
        summed_attrs  = ["car_lanes", "bike_lanes"]
        bool_attrs    = ["car_allowed", "bike_allowed"]
        categorical_attrs = ["highway", "safety", "cycleway", "region", "geometry"]

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
                    agg[attr] = min(vals, key=lambda x: clean_input_data.safety_to_risk_factor_map.get(x, 99))
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