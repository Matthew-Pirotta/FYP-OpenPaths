import random
from networkx import MultiDiGraph, display
from sympy import centroid
import graph_util as graph_util
import osmnx as ox
import networkx as nx
import numpy as np
import geopandas as gpd
from shapely.geometry import Point
from shapely.ops import unary_union
from Demand import paths_util
import nx_parallel

#TODO THIS SHOULD BE IN THE MAIN CLASS?
SEED = 12

def largest_by_length(G):
    #NOTE strongly connected true since roads cycle infrastructure is directional
    components = (G.subgraph(c).copy() for c in nx.strongly_connected_components(G))
    return max(components, key=lambda H: sum(d.get("length",0) for _,_,d in H.edges(data=True)))

# Connectedness - describing whether the network forms a single, navigable system or remains fragmented into multiple component 
def calc_connectedness(G:MultiDiGraph, G_lcc:MultiDiGraph) -> dict:
    num_components = nx.number_strongly_connected_components(G)
    lcc_length = float(sum(d.get("length", 0) for _, _, d in G_lcc.edges(data=True)))

    return {
        "num_components": num_components,
        "lcc_length": lcc_length,
    }

#TODO idk so many thoughts
# is missing_demand and covered demand extra?
# Technically could keep the whole bike network, and not just the largest protected bike?
# TODO dribe_weight length
def calc_directness_od( G_bike: MultiDiGraph, G_drive: MultiDiGraph, OD,
                        bike_weight: str = "bike_cost_penalty", drive_weight: str = "length",) -> dict:
    """
    Compute OD-weighted bike-vs-drive directness.

    Parameters
    ----------
    G_bike : MultiDiGraph
        Bike network to evaluate.
    G_drive : MultiDiGraph
        Drive reference network.
    OD : iterable
        Iterable of (origin, destination, weight).
    bike_weight : str
        Edge attribute used for bike shortest paths.
        Use "length" for geometric directness, or "bike_cost_penalty"
        for generalized-cost directness.
    drive_weight : str
        Edge attribute used for drive shortest paths.
        Usually "length" for geometric directness or "car_cost_current"
        for generalized-cost comparison.

    Returns
    -------
    dict
        {
            "od_directness_mean": float,
            "od_directness_num_pairs": int,
        }

    Notes
    -----
    Directness for an OD pair is defined as:

        directness_od = L_drive / L_bike

    where higher is better.
    If no bike path or no drive path exists, that OD pair is excluded from
    the mean but counted in missing demand.
    """
    weighted_sum = 0.0
    covered_demand = 0.0

    bike_nodes = set(G_bike.nodes())
    drive_nodes = set(G_drive.nodes())

    for o, d, w in OD:
        if w <= 0:
            continue

        if o == d:
            continue

        if o not in bike_nodes or d not in bike_nodes or o not in drive_nodes or d not in drive_nodes:
            continue

        try:
            L_bike = nx.shortest_path_length(G_bike, source=o, target=d, weight=bike_weight)
            L_drive = nx.shortest_path_length(G_drive, source=o, target=d, weight=drive_weight)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue

        if L_bike <= 0 or L_drive <= 0:
            continue

        directness_od = L_drive / L_bike

        weighted_sum += w * directness_od
        covered_demand += w

    mean_directness = weighted_sum / covered_demand if covered_demand > 0 else 0.0

    return {
        "od_directness_mean": float(mean_directness),
    }

def calc_centrality(G_lcc:MultiDiGraph, k_sample=None, seed = SEED, weight = "length") -> dict:
    """Calculate comprehensive centrality metrics for cycling network assessment"""

    #closeness_centrality - how close all other nodes are
    node_close_cent = nx.closeness_centrality(G_lcc, distance=weight, backend="parallel")
    mean_node_close_cent = float(np.mean(list(node_close_cent.values())))

    degrees = [d for _, d in G_lcc.degree()]
    mean_degree = float(np.mean(degrees))
        
    return {
        "mean_node_closeness": mean_node_close_cent,
        "mean_degree": mean_degree,
    }


def calc_coverage(G, buffer_m=500):
    """
    Compute Szell-style coverage: union of ε-buffer around all nodes and edges.
    Requires G to be projected (meters).
    """

    # --- 1. Collect node geometries ---
    node_geoms = []
    for _, data in G.nodes(data=True):
        if "x" in data and "y" in data:
            node_geoms.append(Point(data["x"], data["y"]))

    # --- 2. Collect edge geometries ---
    edge_geoms = []
    for u, v, data in G.edges(data=True):
        geom = data.get("geometry")
        edge_geoms.append(geom)

    # Convert to GeoSeries for fast buffer + union
    all_geoms = gpd.GeoSeries(node_geoms + edge_geoms, crs=G.graph["crs"])

    # --- 3. Buffer all elements ---
    buffered = all_geoms.buffer(buffer_m)

    # --- 4. Unary union: compute merged area ---
    union_geom = unary_union(buffered)

    # --- 5. Compute area in km² ---
    area_m2 = union_geom.area
    area_km2 = area_m2 / 1e6

    return {
        "coverage_area_m2": area_m2,
        "coverage_area_km2": area_km2,
        "union_geom": union_geom  # useful for debugging/plotting
    }

def calc_total_cost_od(
    G_bike: MultiDiGraph,
    OD,
    weight: str = "bike_cost_penalty",
) -> dict:
    """
    Compute total and mean OD-weighted bike generalized cost.
    """
    total_cost = 0.0
    covered_demand = 0.0
    missing_demand = 0.0
    num_pairs = 0

    bike_nodes = set(G_bike.nodes())

    for o, d, w in OD:
        if w <= 0 or o == d:
            continue

        if o not in bike_nodes or d not in bike_nodes:
            missing_demand += w
            continue

        try:
            c_bike = nx.shortest_path_length(G_bike, source=o, target=d, weight=weight)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            missing_demand += w
            continue

        if c_bike < 0:
            missing_demand += w
            continue

        total_cost += w * c_bike
        covered_demand += w
        num_pairs += 1

    mean_cost = total_cost / covered_demand if covered_demand > 0 else 0.0

    return {
        "od_total_bike_cost": float(total_cost),
        "od_mean_bike_cost": float(mean_cost),
        "od_bike_cost_covered_demand": float(covered_demand),
        "od_bike_cost_missing_demand": float(missing_demand),
        "od_bike_cost_num_pairs": int(num_pairs),
    }



def _evaluate_network_metrics(
    G_target: MultiDiGraph,
    G_drive_reference: MultiDiGraph,
    OD_pairs,
    *,
    k_sample=None,
    prefix: str = "",
    include_union_geom: bool = True,
) -> dict:
    """Evaluate graph-level metrics and prefix result keys when requested."""
    metric_names = [
            "num_components", "lcc_length", "mean_node_closeness", 
            "mean_degree", "od_directness_mean", "coverage_area_m2", 
            "coverage_area_km2", "od_total_bike_cost", "od_mean_bike_cost"]

    if G_target.number_of_nodes() == 0 or G_target.number_of_edges() == 0:
        results = {f"{prefix}{name}": 0.0 for name in metric_names}
        results[f"{prefix}num_components"] = 0
        if include_union_geom:
            results[f"{prefix}union_geom"] = None
        return results

    G_lcc = largest_by_length(G_target)
    connectedness = calc_connectedness(G_target, G_lcc)
    centrality = calc_centrality(G_lcc, k_sample=k_sample)
    directness = calc_directness_od(G_target, G_drive_reference, OD_pairs)
    costs = calc_total_cost_od(G_target, OD_pairs)
    coverage = calc_coverage(G_target)

    results = {**connectedness, **centrality, **directness, **costs, **coverage}
    if not include_union_geom:
        results.pop("union_geom", None)

    return {f"{prefix}{k}": v for k, v in results.items()}


def network_evaluation(G_protected:MultiDiGraph, G_drive:MultiDiGraph, k_sample=None, OD_pairs) -> dict:
    bike_results = _evaluate_network_metrics(
        G_protected,
        G_drive,
        k_sample=k_sample,
        prefix="",
        OD_pairs=OD_pairs,
        include_union_geom=True,
    )
    car_results = _evaluate_network_metrics(
        G_drive,
        G_drive,
        k_sample=k_sample,
        prefix="car_",
        OD_pairs=OD_pairs,
        include_union_geom=False,
    )
    return {**bike_results, **car_results}