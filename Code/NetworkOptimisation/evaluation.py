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


#TODO this should be over the OD matrix instead
def calc_directness(Gb_lcc:MultiDiGraph, G_drive:MultiDiGraph, k_sample=None, seed=SEED):
    bike_nodes = list(Gb_lcc.nodes())
    drive_nodes = set(G_drive.nodes()) 

    # Choose sampled origins/destinations
    if k_sample is None:
        origins = bike_nodes
        dests = bike_nodes
    else:
        rng = random.Random(seed)
        k_eff = min(k_sample, len(bike_nodes))
        origins = rng.sample(bike_nodes, k_eff)
        dests = rng.sample(bike_nodes, k_eff)

    ratios = []
    for o in origins:
        for d in dests:
            if o == d:
                continue

            # Ensure the drive network also includes the pair
            if o not in drive_nodes or d not in drive_nodes:
                continue

            try:
                L_bike = nx.shortest_path_length(Gb_lcc, source=o, target=d, weight="length")
                L_drive = nx.shortest_path_length(G_drive, source=o, target=d, weight="length")
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue

            if L_drive > 0:
                ratios.append(L_bike / L_drive)

    if len(ratios) == 0:
        return {
            "mean_directness": 0,
        }

    return {
        "mean_directness": float(np.mean(ratios)),
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

    bike_nodes = set(G_bike.nodes())
    drive_nodes = set(G_drive.nodes())

    for o, d, w in OD:
        if w <= 0:
            continue

        if o == d:
            continue

        if o not in bike_nodes or d not in bike_nodes or o not in drive_nodes or d not in drive_nodes:
            missing_demand += w
            continue

        try:
            L_bike = nx.shortest_path_length(G_bike, source=o, target=d, weight=bike_weight)
            L_drive = nx.shortest_path_length(G_drive, source=o, target=d, weight=drive_weight)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            missing_demand += w
            continue

        if L_bike <= 0 or L_drive <= 0:
            missing_demand += w
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
    #NOTE full centrality is O(n^3), k is instead used to approximate
    if k_sample is not None:
        num_nodes = len(G_lcc.nodes)
        k_eff = min(k_sample, num_nodes)
    else:
        k_eff = k_sample
    
    # Edge betweenness centrality - connectors for network resilience
    edge_between_cent = nx.edge_betweenness_centrality(G_lcc, weight=weight, normalized=True, k=k_eff, seed = seed, backend="parallel")
    mean_edge_between_cent = float(np.mean(list(edge_between_cent.values())))

    #closeness_centrality - how close all other nodes are
    node_close_cent = nx.closeness_centrality(G_lcc, distance=weight, backend="parallel")
    mean_node_close_cent = float(np.mean(list(node_close_cent.values())))

    degrees = [d for _, d in G_lcc.degree()]
    mean_degree = float(np.mean(degrees))
        
    return {
        "mean_edge_betweenness": mean_edge_between_cent,
        "mean_node_betweenness": 1,
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


def _evaluate_network_metrics(
    G_target: MultiDiGraph,
    G_drive_reference: MultiDiGraph,
    *,
    k_sample=None,
    prefix: str = "",
    include_union_geom: bool = True,
) -> dict:
    """Evaluate graph-level metrics and prefix result keys when requested."""
    metric_names = [
        "num_components",
        "lcc_length",
        "mean_edge_betweenness",
        "mean_node_betweenness",
        "mean_node_closeness",
        "mean_degree",
        "mean_directness",
        "coverage_area_m2",
        "coverage_area_km2",
    ]

    if G_target.number_of_nodes() == 0 or G_target.number_of_edges() == 0:
        results = {f"{prefix}{name}": 0.0 for name in metric_names}
        results[f"{prefix}num_components"] = 0
        if include_union_geom:
            results[f"{prefix}union_geom"] = None
        return results

    G_lcc = largest_by_length(G_target)
    connectedness = calc_connectedness(G_target, G_lcc)
    centrality = calc_centrality(G_lcc, k_sample=k_sample)
    directness = calc_directness(G_target, G_drive_reference, k_sample=k_sample)
    coverage = calc_coverage(G_target)

    results = {**connectedness, **centrality, **directness, **coverage}
    if not include_union_geom:
        results.pop("union_geom", None)

    return {f"{prefix}{k}": v for k, v in results.items()}


def network_evaluation(G_protected:MultiDiGraph, G_drive:MultiDiGraph, k_sample=None) -> dict:
    bike_results = _evaluate_network_metrics(
        G_protected,
        G_drive,
        k_sample=k_sample,
        prefix="",
        include_union_geom=True,
    )
    car_results = _evaluate_network_metrics(
        G_drive,
        G_drive,
        k_sample=k_sample,
        prefix="car_",
        include_union_geom=False,
    )
    return {**bike_results, **car_results}