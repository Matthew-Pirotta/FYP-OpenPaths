from networkx import MultiDiGraph
import osmnx as ox
import networkx as nx
import numpy as np
from collections import defaultdict
import operator
from statistics import fmean

from  . import clean_input_data, tag_utils, enrich_attributes

import constants

SIMPLIFY_SPEC = {
    #mean
    "length": fmean,
    "grade": fmean,
    "risk_factor": fmean,
    "speed_kph_original": fmean,
    "speed_kph_current": fmean,

    #sum
    "car_lanes": lambda vs: int(sum(vs)),
    "bike_lanes": lambda vs: int(sum(vs)),

    #boolean
    "car_allowed": any,
    "bike_allowed": any,

    #categorical, select through priority
    "highway": lambda values: tag_utils.select_primary_label(values, tag_utils.HIGHWAY_PRIORITY),
    "cycleway": lambda values: tag_utils.select_primary_label(values, tag_utils.CYCLEWAY_PRIORITY),
    "safety": lambda values: min(values, key=lambda x: enrich_attributes.safety_to_risk_factor_map.get(x, float("inf"))), #TODO check if this is functional

    #misc
    "region": lambda vs: list(set(vs)), #TODO no this shoud now be a list of regions. we are no longer restricting to single region. The agg shoukd be the union
    "geometry": operator.itemgetter(0),
}

SEGMENT_SPEC = {
    "car_lanes": lambda vs: int(sum(vs)),
    "length": max,
    "bike_cost_base": fmean,
    "bike_cost_penalty": fmean,
}

#NOTE technically the grade value shouldnt be in the segments, and is not actually meaningful in this context.
#To remedy this create seperate dicts for shared attrbiutes and ones specific for simplify_multidigraph_in_place
SIMPLIFY_AND_SEGMENT_SPEC = {**SIMPLIFY_SPEC,**SEGMENT_SPEC} 

def aggregate_by_key(rows, spec, defaults=None):
    """
    spec: dict[key -> reducer(list_of_values)]
    defaults: dict[key -> default_value]
    """
    defaults = defaults or {}
    out = {}

    for key, reducer in spec.items():
        #print(f"key:{key}, reducer{reducer}")
        vals = [r[key] for r in rows if key in r and r[key] is not None]
        if vals:
            out[key] = reducer(vals)
        elif key in defaults:
            out[key] = defaults[key]

    return out


#region MultdiGraph -> Digraph
def simplify_multidigraph_in_place(G: MultiDiGraph) -> MultiDiGraph:
    """Merge same-direction parallel edges in a MultiDiGraph, in place."""
    merge_jobs = []

    # Snapshot jobs first, then mutate graph
    for u, nbrs in list(G.adj.items()):
        for v, key_dict in list(nbrs.items()):
            if len(key_dict) <= 1:
                continue

            keys = list(key_dict.keys())
            rows = [dict(d) for d in key_dict.values()]
            merge_jobs.append((u, v, keys, rows))

    for u, v, keys, rows in merge_jobs:
        # Keep first edge attrs as base so unlisted attrs are not lost
        merged_attrs = dict(rows[0])
        agg_attrs = aggregate_by_key(rows, SIMPLIFY_SPEC)
        merged_attrs.update(agg_attrs)

        for k in keys:
            if G.has_edge(u, v, k):
                G.remove_edge(u, v, k)

        G.add_edge(u, v, **merged_attrs)

    return G
#endregion

#region Digraph -> undirected graph
#NOTE that all features are calculatedo n the digraph and are then aggregated oto the undirected graph.
def _segment_id(u, v, k = 0):
    """Canonical undirected segment id used across preprocessing and optimization."""
    return (min(u, v), max(u, v), k)


#TODO move to a different class, or move the class
def build_segment_graph(G: MultiDiGraph):
    """
    Build segment maps + undirected segment graph from a clean directed graph.

    Returns
    -------
    tuple
        (seg_to_arcs, arc_to_seg, G_seg)
    """
    seg_rows = defaultdict(list)
    seg_to_arcs = defaultdict(list)
    arc_to_seg = {}

    for u, v, k, d in G.edges(keys=True, data=True):
        seg = _segment_id(u, v, k)
        arc = (u, v, k)

        seg_rows[seg].append(d)
        seg_to_arcs[seg].append(arc)
        arc_to_seg[arc] = seg

    G_seg = nx.MultiGraph()
    G_seg.graph.update(dict(G.graph)) #graph level attr such as crs
    G_seg.add_nodes_from((n, dict(d)) for n, d in G.nodes(data=True))  # keeps x/y and other node attrs

    for seg, rows in seg_rows.items():
        #print(f"seg:{seg}, rows{rows}")
        agg = aggregate_by_key(rows, SIMPLIFY_AND_SEGMENT_SPEC) #Need to reaggrigrate the orignal attributes such a lanes
        a, b, k = seg

        G_seg.add_edge(
            a,
            b,
            key=k,  # always 0
            seg=seg,
            arcs=list(seg_to_arcs[seg]),
            n_arcs=len(rows),
            **agg
        )

    seg_to_arcs = dict(seg_to_arcs)
    arc_to_seg = dict(arc_to_seg)

    return seg_to_arcs, arc_to_seg, G_seg
#endregion