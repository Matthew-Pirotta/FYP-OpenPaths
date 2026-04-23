#TODO pass Gu instead of rebuilding it multiple times.
from networkx import MultiDiGraph
import networkx as nx
import osmnx as ox
import copy
import numpy as np
from collections import Counter, defaultdict

import constants
from constants import SafetyClass
from PreProcessing import enrich_attributes
from typing import Literal
from NetworkOptimisation import impedance_calculator
from shapely.geometry import LineString

# region Subgraph generators
def make_drive_subgraph(G:MultiDiGraph) -> MultiDiGraph:
    return _filter_edges(G, lambda d: d.get("car_allowed", False))

#TODO need to set dangerous roads and bridges as not bikeable
def make_bikeable_subgraph(G:MultiDiGraph)-> MultiDiGraph:
    return _filter_edges(G, lambda d: d.get("bike_allowed", False))

def make_reallocatable_subgraph(G:MultiDiGraph)-> MultiDiGraph:
    #concern might have car_lanes = 0, car_allowed = false, but somehow reallocatable = True?
    return _filter_edges(G, lambda d: d.get("reallocatable") == True)

def make_protected_subgraph(G:MultiDiGraph)-> MultiDiGraph:
    return _filter_edges(G, lambda d: d.get("safety") in [SafetyClass.PAINTED, SafetyClass.PROTECTED])

def make_region_subgraph(G: MultiDiGraph, region: str) -> MultiDiGraph:
    """
    Subgraph containing all edges that intersect the given region.
    Boundary edges are included.
    """
    return _filter_edges(G, lambda d: region in d.get("regions"))

def make_locality_subgraph(G:MultiDiGraph, locality) -> MultiDiGraph:
    return _filter_edges(G, lambda d: locality in d.get("localities"))

def make_highway_subgraph(G:MultiDiGraph,
                           road_type:Literal["primary", "residential", "service", "track", "tertiary", "secondary"]) -> MultiDiGraph:
    return _filter_edges(G, lambda d: d.get("highway") == road_type)



def _filter_edges(G:MultiDiGraph, condition) -> MultiDiGraph:
    #NOTE subgraph is view and read-only
    #NOTE TODO made copy so its not read-only lol
    # NOTE TODO use nx.subgraph_view if they are just views
    #NOTE nvm creating a view will actually take more time, as every time a NetworkX algorithm checks an edge in a View, it has to execute your Python lambda function.
    edges = [(u, v, k) 
                for u, v, k, d in G.edges(keys=True, data=True) 
                if condition(d)]
    return G.edge_subgraph(edges).copy()
#endregion

#region reallocation
def _segment_is_oneway(
    G: MultiDiGraph,
    seg_id,
    seg_to_arcs: dict,
) -> bool:
    arcs = seg_to_arcs[seg_id]

    for u, v, k in arcs:
        d = G[u][v][k]
        if d.get("highway") == "cycleway":
            continue
        return d.get("oneway", True)

    return True


def check_segment_reallocatable(
    G_drive: MultiDiGraph,
    seg_id,
    segment_inventory: dict,
    seg_to_arcs: dict,
    arc_scores: dict,
) -> bool:
    G_test = copy.deepcopy(G_drive)

    total = segment_inventory[seg_id]["lanes_remaining"]
    if total <= 0:
        return False

    remaining_total = total - 1
    is_oneway = _segment_is_oneway(G_test, seg_id, seg_to_arcs)

    keep_arc = None
    if (not is_oneway) and remaining_total == 1:
        keep_arc = choose_keep_arc_for_segment(seg_id, seg_to_arcs, arc_scores, G_test)

    _apply_segment_capacity_to_arcs(
        G_test,
        seg_id,
        seg_to_arcs=seg_to_arcs,
        remaining_total=remaining_total,
        keep_arc=keep_arc,
    )

    G_drive_test = make_drive_subgraph(G_test)
    return G_drive_test.number_of_edges() > 0 and nx.is_strongly_connected(G_drive_test)


def _create_bike_edge(G, u, v, base_data):
    """
    Create a new bike-only edge parallel to (u, v).
    Returns (u, v, new_key)
    """
    new_data = copy.deepcopy(base_data)

    # Mode permissions
    new_data["car_allowed"] = False
    new_data["bike_allowed"] = True

    # Infrastructure classification
    new_data["highway"] = "cycleway"
    new_data["bicycle"] = "designated"
    new_data["infra_type"] = "dedicated_bike_lane"

    # Ensure safe defaults
    new_data["bike_lanes"] = new_data.get("bike_lanes", 0) + 1

    # Safety
    new_data["safety"] = SafetyClass.PROTECTED
    new_data["risk_factor"] = float(
        enrich_attributes.safety_to_risk_factor_map[SafetyClass.PROTECTED]
    )

    # Prevent reallocation loops
    new_data["reallocatable"] = False

    # Add as a new parallel edge
    new_key = G.add_edge(u, v, **new_data)

    impedance_calculator.update_bike_costs(G, [(u,v,new_key)])

    return (u, v, new_key)

def _has_dedicated_bike_edge(G, u, v):
    if not G.has_edge(u, v):
        return False

    for k, d in G[u][v].items():
        if d.get("highway") == "cycleway":
            return True
    return False

def reallocate_segment_dedicated(
    G: MultiDiGraph,
    seg_id,
    segment_inventory: dict,
    seg_to_arcs: dict,
    keep_arc: tuple | None = None,
) -> list[tuple]:
    """
    Reallocate one authoritative car lane from a segment.
    If the segment becomes one-lane two-way, keep_arc determines which direction survives for cars.
    """
    created_edges = []
    arcs = seg_to_arcs[seg_id]

    old_total = segment_inventory[seg_id]["lanes_remaining"]
    new_total = max(0, old_total - 1)
    segment_inventory[seg_id]["lanes_remaining"] = new_total

    _apply_segment_capacity_to_arcs(
        G,
        seg_id,
        seg_to_arcs=seg_to_arcs,
        remaining_total=new_total,
        keep_arc=keep_arc,
    )

    for u, v, k in arcs:
        d = G[u][v][k]
        if d.get("highway") == "cycleway":
            continue
        if not _has_dedicated_bike_edge(G, u, v):
            created_edges.append(_create_bike_edge(G, u, v, d))

    refresh_segment_reallocatable_flags(G, segment_inventory, seg_to_arcs)
    return created_edges

def _apply_segment_capacity_to_arcs(
    G: MultiDiGraph,
    seg_id,
    seg_to_arcs: dict,
    remaining_total: int | float,
    keep_arc: tuple | None = None,
):
    arcs = seg_to_arcs[seg_id]

    drive_arcs = [
        (u, v, k)
        for (u, v, k) in arcs
        if G[u][v][k].get("highway") != "cycleway"
    ]

    if not drive_arcs:
        return

    # representative arc per direction
    dir_to_arc = {arc[:2]: arc for arc in drive_arcs}
    unique_arcs = list(dir_to_arc.values())

    is_oneway = _segment_is_oneway(G, seg_id, seg_to_arcs)

    # -------------------------
    # ONEWAY SEGMENT
    # -------------------------
    if is_oneway:
        # choose one representative driving arc
        # if multiple parallel one-way arcs exist, you may later want finer handling
        u, v, k = unique_arcs[0]

        G[u][v][k]["car_lanes"] = max(remaining_total, 0)
        G[u][v][k]["car_allowed"] = remaining_total > 0
        G[u][v][k]["reallocatable"] = remaining_total > 0

        # any other parallel same-direction arcs:
        for uu, vv, kk in unique_arcs[1:]:
            G[uu][vv][kk]["car_lanes"] = max(remaining_total, 0)
            G[uu][vv][kk]["car_allowed"] = remaining_total > 0
            G[uu][vv][kk]["reallocatable"] = remaining_total > 0

        return

    # -------------------------
    # TWOWAY SEGMENT
    # -------------------------
    if remaining_total >= 2:
        for u, v, k in unique_arcs:
            G[u][v][k]["car_lanes"] = remaining_total
            G[u][v][k]["car_allowed"] = True
            G[u][v][k]["reallocatable"] = True
        return

    if remaining_total == 1:
        if keep_arc is None:
            raise ValueError(
                f"keep_arc is required when two-way segment {seg_id} is reduced to one remaining car lane"
            )

        keep_dir = keep_arc[:2]
        for u, v, k in unique_arcs:
            keep = (u, v) == keep_dir
            G[u][v][k]["car_lanes"] = 1 if keep else 0
            G[u][v][k]["car_allowed"] = keep
            G[u][v][k]["reallocatable"] = keep
        return

    # remaining_total == 0
    for u, v, k in unique_arcs:
        G[u][v][k]["car_lanes"] = 0
        G[u][v][k]["car_allowed"] = False
        G[u][v][k]["reallocatable"] = False

def choose_keep_arc_for_segment(
    seg_id,
    seg_to_arcs: dict,
    arc_scores: dict,
    G: MultiDiGraph,
) -> tuple | None:
    """
    For a two-way segment with only 1 remaining car lane, choose which directed arc to keep.
    """
    if _segment_is_oneway(G, seg_id, seg_to_arcs):
        return None

    arcs = seg_to_arcs[seg_id]

    drive_arcs = [
        arc for arc in arcs
        if G[arc[0]][arc[1]][arc[2]].get("highway") != "cycleway"
    ]

    if not drive_arcs:
        return None

    dir_to_arc = {arc[:2]: arc for arc in drive_arcs}
    unique_arcs = list(dir_to_arc.values())

    if len(unique_arcs) == 1:
        return unique_arcs[0]

    return max(unique_arcs, key=lambda arc: arc_scores.get(arc, float("-inf")))

#endregion

def summarise_road_type_stats(G):
    # Map the edge attribute key to the label you want to print
    categories = {
        "highway": "Highway type counts",
        "bicycle": "Bikeway classification type counts",
        "cycleway": "Cycleway type counts",
        "tunnel": "Tunnel counts",
        "junction": "Juntion type counts",
        "turns": "turn type counts",
        "oneway": "Oneway or twoway"
    }
    
    # Initialize counters for each category
    stats = {key: Counter() for key in categories}

    # Single pass over the edges
    for _, _, data in G.edges(data=True):
        for key in categories:
            stats[key][data.get(key)] += 1
    
    # Print the results
    for key, label in categories.items():
        print(f"{label}:")
        for val, count in stats[key].most_common():
            print(f"{val}: {count}")
        print("-" * 10)


def set_edge_attribute(G:MultiDiGraph, edge:tuple, attribute_name:str, value) -> MultiDiGraph:
    u,v,k = edge
    data = G[u][v][k]
    data[attribute_name] = value
    return G

#region new segment logic
def build_segment_inventory(G_directed: MultiDiGraph) -> dict:
    """
    Build authoritative segment inventory from OSMnx undirected graph.

    Returns
    -------
    dict[seg_id -> dict]
        seg_id is (u, v, k) in undirected graph space.
        Each entry contains authoritative physical lane supply and metadata.
    """
    Gu = ox.convert.to_undirected(G_directed)

    inventory = {}
    for u, v, k, d in Gu.edges(keys=True, data=True):
        
        lanes = d.get("lanes", 1)

        inventory[(u, v, k)] = {
            "lanes_total": lanes,
            "lanes_remaining": lanes,
            "geometry": d.get("geometry"),
            "osmid": d.get("osmid"),
            "highway": d.get("highway"),
        }
    return inventory


#TODO idk if i should keep the hex key, i.e. maintain a multiGraph or just a graph
# should I keep (min(u, v), max(u, v), 0)?
def _canonical_geometry_key(data):
    """
    Return a direction-invariant geometry key.
    Assumes every edge has valid geometry.
    """
    geom = data["geometry"]
    coords = list(geom.coords)

    forward = tuple(coords)
    backward = tuple(reversed(coords))

    # make A->B and B->A map to same key
    return min(forward, backward)


def build_arc_to_segment_map(G_directed: MultiDiGraph) -> tuple[dict, dict]:
    """
    Map each directed arc to exactly one authoritative undirected segment.

    Returns
    -------
    arc_to_seg : dict[(u,v,k) -> seg_id]
    seg_to_arcs : dict[seg_id -> list[(u,v,k)]]
    """
    Gu = ox.convert.to_undirected(G_directed)

    undirected_lookup = {}
    for u, v, k, d in Gu.edges(keys=True, data=True):
        node_pair = tuple(sorted((u, v)))
        geom_key = _canonical_geometry_key(d)
        undirected_lookup[(node_pair, geom_key)] = (u, v, k)

    arc_to_seg = {}
    seg_to_arcs = defaultdict(list)

    for u, v, k, d in G_directed.edges(keys=True, data=True):
        node_pair = tuple(sorted((u, v)))
        geom_key = _canonical_geometry_key(d)

        seg_id = undirected_lookup.get((node_pair, geom_key))
        if seg_id is None:
            raise KeyError(
                f"Could not map directed edge {(u, v, k)} "
                f"with node_pair={node_pair}"
            )

        arc_to_seg[(u, v, k)] = seg_id
        seg_to_arcs[seg_id].append((u, v, k))

    return arc_to_seg, seg_to_arcs

def refresh_segment_reallocatable_flags(G: MultiDiGraph, segment_inventory: dict, seg_to_arcs: dict):
    """
    Keep directed graph reallocatable flags synchronized with authoritative segment supply.
    """
    for seg_id, arcs in seg_to_arcs.items():
        remaining = segment_inventory[seg_id]["lanes_remaining"]
        can_reallocate = remaining > 0

        for u, v, k in arcs:
            d = G[u][v][k]
            if d.get("highway") == "cycleway":
                d["reallocatable"] = False
            else:
                d["reallocatable"] = bool(d.get("car_allowed", False) and can_reallocate)


#endregion

#region segment logic
def build_segment_coef(
    G,
    eligible_segments,
    seg_to_arcs,
    arc_to_seg,
    paths_bike,
    paths_car,
    gamma: float,
):
    bike_benefit_seg = defaultdict(float)
    car_harm_seg = defaultdict(float)

    for (o, d, w), path in paths_bike.items():
        for u, v in zip(path[:-1], path[1:]):
            candidate_arcs = [(u, v, k) for k in G[u][v].keys()] if G.has_edge(u, v) else []
            for arc in candidate_arcs:
                seg = arc_to_seg.get(arc)
                if seg not in eligible_segments:
                    continue
                edge = G[arc[0]][arc[1]][arc[2]]
                delta_bike = edge["bike_cost_penalty"] - edge["bike_cost_base"]
                bike_benefit_seg[seg] += w * delta_bike

    for (o, d, w), path in paths_car.items():
        for u, v in zip(path[:-1], path[1:]):
            candidate_arcs = [(u, v, k) for k in G[u][v].keys()] if G.has_edge(u, v) else []
            for arc in candidate_arcs:
                seg = arc_to_seg.get(arc)
                if seg not in eligible_segments:
                    continue
                edge = G[arc[0]][arc[1]][arc[2]]
                delta_car = edge["car_cost_if_fietsstraat"] - edge["car_cost_current"]
                car_harm_seg[seg] += w * delta_car

    coef_seg = {}
    for seg in eligible_segments:
        coef_seg[seg] = bike_benefit_seg[seg] - gamma * car_harm_seg[seg]

    return coef_seg, bike_benefit_seg, car_harm_seg
#endregion

