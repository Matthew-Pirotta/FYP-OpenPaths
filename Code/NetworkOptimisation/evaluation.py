import random
from concurrent.futures import ThreadPoolExecutor
from networkx import MultiDiGraph, display
from sympy import centroid
import graph_util as graph_util
import osmnx as ox
import networkx as nx
import numpy as np
import geopandas as gpd
from shapely.geometry import Point
from shapely.ops import unary_union
from collections.abc import Mapping
from Demand import paths_util
import nx_parallel

#TODO THIS SHOULD BE IN THE MAIN CLASS?
SEED = 12


#TODO this doesnt need to saty but whatev
def _iter_od_triples(od_data):
    if isinstance(od_data, Mapping):
        rows = ((o, d, w) for (o, d), w in od_data.items())
    else:
        rows = od_data

    for row in rows:
        try:
            row_vals = tuple(row)
            if len(row_vals) == 3:
                o, d, w = row_vals
            elif len(row_vals) == 2:
                (o, d), w = row_vals
            else:
                raise ValueError("row has invalid length")
        except Exception as exc:
            raise TypeError(
                "od_data must be Mapping[(o,d)->w], Iterable[(o,d,w)], or Iterable[((o,d),w)]."
            ) from exc
        yield int(o), int(d), float(w)


def largest_by_length(G):
    #NOTE strongly connected true since roads cycle infrastructure is directional
    components = (G.subgraph(c).copy() for c in nx.strongly_connected_components(G))
    return max(components, key=lambda H: sum(d.get("length",0) for _,_,d in H.edges(data=True)))

# Connectedness - describing whether the network forms a single, navigable system or remains fragmented into multiple component 
def calc_connectedness(G:MultiDiGraph, G_lcc:MultiDiGraph) -> dict:
    num_components = nx.number_strongly_connected_components(G)
    total_length = float(sum(d.get("length", 0) for _, _, d in G.edges(data=True)))
    lcc_length = float(sum(d.get("length", 0) for _, _, d in G_lcc.edges(data=True)))
    lcc_length_share = (lcc_length / total_length) if total_length > 0 else 0.0

    return {
        "num_components": num_components,
        "lcc_length": lcc_length,
        "lcc_length_share": lcc_length_share,
    }


def compute_od_costs(G: MultiDiGraph, OD_list, weight: str = "length") -> dict:
    """
    Returns {(o, d): path_cost} for reachable OD pairs.
    Unreachable or invalid pairs are omitted.
    """
    costs = {}
    nodes = set(G.nodes())

    for o, d, w in _iter_od_triples(OD_list):
        if w <= 0 or o == d:
            continue
        if o not in nodes or d not in nodes:
            continue

        try:
            c = nx.shortest_path_length(G, source=o, target=d, weight=weight)
            costs[(o, d)] = float(c)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue

    return costs

#TODO idk so many thoughts
# is missing_demand and covered demand extra?
# Technically could keep the whole bike network, and not just the largest protected bike?
def calc_directness_from_costs( bike_costs: dict, drive_costs: dict, OD_list,) -> dict:
    weighted_sum = 0.0
    covered_demand = 0.0
    num_pairs = 0

    for o, d, w in _iter_od_triples(OD_list):

        L_bike = bike_costs.get((o, d))
        L_drive = drive_costs.get((o, d))

        if L_bike is None or L_drive is None:
            continue
        if L_bike <= 0 or L_drive <= 0:
            continue

        directness_od = L_drive / L_bike
        weighted_sum += w * directness_od
        covered_demand += w
        num_pairs += 1

    mean_directness = weighted_sum / covered_demand if covered_demand > 0 else 0.0

    return {
        "od_directness_mean": float(mean_directness),
        "od_directness_num_pairs": int(num_pairs),
    }


def calc_centrality(G_lcc:MultiDiGraph, k_sample=None, seed = SEED, weight = "length") -> dict:
    """Calculate comprehensive centrality metrics for cycling network assessment"""

    #closeness_centrality - how close all other nodes are
    #TODO temp just taking way too long
    """
    node_close_cent = nx.closeness_centrality(G_lcc, distance=weight )
    mean_node_close_cent = float(np.mean(list(node_close_cent.values())))

    degrees = [d for _, d in G_lcc.degree()]
    mean_degree = float(np.mean(degrees))
        
    return {
        "mean_node_closeness": mean_node_close_cent,
        "mean_degree": mean_degree,
    }
    """
    return {
        "mean_node_closeness": 0,
        "mean_degree": 0,
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

def calc_total_cost_from_costs(costs_dict: dict, OD_list, cost_name: str = "bike",) -> dict:
    total_cost = 0.0
    covered_demand = 0.0
    missing_demand = 0.0
    num_pairs = 0

    for o, d, w in _iter_od_triples(OD_list):
        if w <= 0 or o == d:
            continue

        c_val = costs_dict.get((o, d))
        if c_val is None or c_val < 0:
            missing_demand += w
            continue

        total_cost += w * c_val
        covered_demand += w
        num_pairs += 1

    mean_cost = total_cost / covered_demand if covered_demand > 0 else 0.0

    return {
        f"od_total_{cost_name}_cost": float(total_cost),
        f"od_mean_{cost_name}_cost": float(mean_cost),
        f"od_{cost_name}_cost_covered_demand": float(covered_demand),
        f"od_{cost_name}_cost_missing_demand": float(missing_demand),
        f"od_{cost_name}_cost_num_pairs": int(num_pairs),
    }


def _evaluate_structure_metrics( G_target: MultiDiGraph, k_sample=None, prefix: str = "", include_union_geom: bool = True,) -> dict:
    metric_names = [ "num_components", "lcc_length", "mean_node_closeness", "mean_degree", "coverage_area_m2", "coverage_area_km2",]

    #TODO this if condition seems like it should never be hit
    if G_target.number_of_nodes() == 0 or G_target.number_of_edges() == 0:
        results = {f"{prefix}{name}": 0.0 for name in metric_names}
        results[f"{prefix}num_components"] = 0
        if include_union_geom:
            results[f"{prefix}union_geom"] = None
        return results

    G_lcc = largest_by_length(G_target)
    connectedness = calc_connectedness(G_target, G_lcc)
    centrality = calc_centrality(G_lcc, k_sample=k_sample)
    coverage = calc_coverage(G_target)

    results = {**connectedness, **centrality, **coverage}
    if not include_union_geom:
        results.pop("union_geom", None)

    return {f"{prefix}{k}": v for k, v in results.items()}

def network_evaluation(
    G_bike_protected: MultiDiGraph,
    G_bike_full: MultiDiGraph,
    G_drive: MultiDiGraph,
    OD_pairs,
    k_sample=None,
    parallel_od_costs: bool = True,
) -> dict:

    # Precompute OD costs once
    if parallel_od_costs:
        with ThreadPoolExecutor(max_workers=3) as executor:
            drive_future = executor.submit(compute_od_costs, G_drive, OD_pairs, "length")
            full_bike_future = executor.submit(compute_od_costs, G_bike_full, OD_pairs, "bike_cost_penalty")
            protected_bike_future = executor.submit(compute_od_costs, G_bike_protected, OD_pairs, "bike_cost_penalty")
            drive_costs = drive_future.result()
            full_bike_costs = full_bike_future.result()
            protected_bike_costs = protected_bike_future.result()
    else:
        drive_costs = compute_od_costs(G_drive, OD_pairs, weight="length")
        full_bike_costs = compute_od_costs(G_bike_full, OD_pairs, weight="bike_cost_penalty")
        protected_bike_costs = compute_od_costs(G_bike_protected, OD_pairs, weight="bike_cost_penalty")

    # 1. Protected topology only
    protected_structure = _evaluate_structure_metrics(
        G_bike_protected,
        k_sample=k_sample,
        prefix="protected_",
        include_union_geom=True,
    )

    # 2. Main OD performance (Figure 1 metrics)
    protected_directness = calc_directness_from_costs(protected_bike_costs, drive_costs, OD_pairs)
    protected_bike_od = calc_total_cost_from_costs(protected_bike_costs, OD_pairs, cost_name="protected")
    protected_total_demand = (
        protected_bike_od["od_protected_cost_covered_demand"]
        + protected_bike_od["od_protected_cost_missing_demand"]
    )
    protected_reachable_share = (
        protected_bike_od["od_protected_cost_covered_demand"] / protected_total_demand
        if protected_total_demand > 0
        else 0.0
    )
    main_od = {
        "main_od_directness_weighted": float(protected_directness["od_directness_mean"]),
        "main_od_directness_num_pairs": int(protected_directness["od_directness_num_pairs"]),
        "main_od_protected_reachable_share": float(protected_reachable_share),
        "main_od_protected_reachable_demand": float(protected_bike_od["od_protected_cost_covered_demand"]),
        "main_od_total_demand": float(protected_total_demand),
    }

    # 3. Full bike OD only (kept for baseline trade-off metrics)
    full_bike_od = {
        **calc_directness_from_costs(full_bike_costs, drive_costs, OD_pairs),
        **calc_total_cost_from_costs(full_bike_costs, OD_pairs, cost_name="bike"),
    }
    full_bike_od = {f"full_{k}": v for k, v in full_bike_od.items()}

    # 4. Full car evaluation
    car_structure = _evaluate_structure_metrics(
        G_drive,
        k_sample=k_sample,
        prefix="car_",
        include_union_geom=False,
    )

    car_od = calc_total_cost_from_costs(drive_costs, OD_pairs, cost_name="car")
    car_od = {f"car_{k}": v for k, v in car_od.items()}

    return {
        **protected_structure, **car_structure,
        **main_od,
        **full_bike_od, **car_od,
    }
