from geopandas import GeoDataFrame
from networkx import MultiDiGraph

import osmnx as ox
import networkx as nx
import numpy as np
from constants import SafetyClass, InfraType

from collections import Counter


safety_to_risk_factor_map = {
    SafetyClass.VERY_SAFE: 0.5, 
    SafetyClass.SAFE: 1,
    SafetyClass.MODERATE: 1.5,
    SafetyClass.CAUTION: 2,#NOTE Cyclists perceive travel on car-dominated lanes as twice as costly
    SafetyClass.DANGEROUS: 4,#TODO highway twice as costly ig?
    SafetyClass.UNCLASSIFIED:2,
}

#TODO
def bike_safety_classification(G: MultiDiGraph) -> MultiDiGraph:
    for _, _, data in G.edges(data=True):

        highway = data.get("highway")
        bicycle = data.get("bicycle")
        cycleway = data.get("cycleway")

        # ==========================================================
        # STEP 1 — Determine infra_type
        # ==========================================================
        if cycleway == "track" or highway == "cycleway" or bicycle == "designated":
            infra_type = "cycle_track"        # physically separated
        elif cycleway in {"lane"}:
            infra_type = "bike_lane"          # painted lane
        elif cycleway in {"shared", "shared_lane"}:
            infra_type = "mixed"              # no markings, shared with cars
        elif highway in {"residential", "living_street"}:
            infra_type = "mixed"              # low-speed streets
        else:
            infra_type = "car"                # default assumption

        # Store inferred type
        data["infra_type"] = infra_type

        # ==========================================================
        # STEP 2 — Safety classification (fietsstraat support)
        # ==========================================================
        if infra_type == "cycle_track":
            classification = SafetyClass.VERY_SAFE

        elif infra_type == "bike_lane":
            classification = SafetyClass.SAFE

        elif infra_type == "mixed":
            # Potentially a good fietsstraat candidate
            if highway in {"residential", "living_street"}:
                classification = SafetyClass.MODERATE
            else:
                classification = SafetyClass.CAUTION

        elif highway in {"primary", "secondary", "trunk", "tertiary"}:
            classification = SafetyClass.DANGEROUS

        elif highway in {"track", "service", "non_motorised"}:
            classification = SafetyClass.MODERATE

        else:
            classification = SafetyClass.UNCLASSIFIED

        # ==========================================================
        # STEP 3 — Update attributes
        # ==========================================================
        data["safety"] = classification
        data["risk_factor"] = float(safety_to_risk_factor_map[classification])

        # Dangerous roads should not be bikeable
        if classification == SafetyClass.DANGEROUS:
            data["bike_allowed"] = False
        else:
            data["bike_allowed"] = True

    return G


#TODO move to clean_input data?
def load_and_clean_localities(G, place_name) -> tuple[GeoDataFrame, GeoDataFrame]:
    """
    Fetch and clean administrative boundaries for both level 7 (regions) and level 8 (localities) in Malta. Returns a unified GeoDataFrame projected to the graph CRS.
    """
    gdf_localities = ox.features.features_from_place(
        place_name,
        tags={"boundary": "administrative", "admin_level": ["7", "8"]}
    )

    #Data cleaning
    gdf_localities = gdf_localities[["name", "admin_level","geometry"]]
    gdf_localities = gdf_localities[gdf_localities["admin_level"].isin(["7", "8"])]
    gdf_localities = gdf_localities.dropna()
    gdf_localities = gdf_localities.drop_duplicates(subset=['name'])

    # Merge multipolygons
    for idx, row in gdf_localities.iterrows():
        if row.geometry.geom_type == "MultiPolygon":
            largest_poly  = max(row.geometry.geoms, key=lambda g: g.area)  # keep largest component
            gdf_localities.at[idx, "geometry"] = largest_poly 

    gdf_localities_proj = gdf_localities.to_crs(G.graph["crs"])

    gdf_regions_proj  = gdf_localities_proj[gdf_localities["admin_level"] == "7"]
    gdf_local_proj = gdf_localities_proj[gdf_localities["admin_level"] == "8"]

    # Inspect results
    print("Number of localities:", len(gdf_localities))
    return gdf_regions_proj, gdf_local_proj



"""def tag_reallocatable_edges(G:MultiDiGraph):
    # mark bridges as not reallocatable
    bridges = set(nx.bridges(G.to_undirected()))
    for u, v, k, d in G.edges(keys=True, data=True):
        if (u, v) in bridges or (v, u) in bridges:
            d["reallocatable"] = False

        #Can only reallocate from car lanes
        elif d.get("car_allowed", False) == False or d.get("car_lanes",0) <= 0:
            d["reallocatable"] = False

        #Can only reallocate from where its bikeable (i.e not tunnels or highways)
        elif d.get("bike_allowed", True) == False:
            d["reallocatable"] = False


        else:
            d["reallocatable"] = True"""

def tag_reallocatable_edges(G:MultiDiGraph, verbose: bool = False) -> Counter:
    """
    Mark edges as reallocatable and return a Counter with how many edges hit each rule.
    Set verbose=True to print a short summary.
    """
    counters = Counter()
    # mark bridges as not reallocatable
    #bridges = set(nx.bridges(G.to_undirected()))
    bridges = {}
    for u, v, k, d in G.edges(keys=True, data=True):
        # default to False until proven otherwise (defensive)
        if (u, v) in bridges or (v, u) in bridges:
            d["reallocatable"] = False
            counters["bridge"] += 1

        # Never touch protected cycle tracks
        elif d.get("infra_type") == InfraType.CYCLE_TRACK:
            d["reallocatable"] = False

        # Can only reallocate from car lanes
        elif d.get("car_allowed", False) == False:
            d["reallocatable"] = False
            counters["no_car_allowed"] += 1
        
        #TODO can remove
        elif d.get("car_lanes", 0) <= 0:
            d["reallocatable"] = False
            counters["no_car_lanes"] += 1

        # Can only reallocate where biking is allowed (i.e. not tunnels/highways)
        elif d.get("bike_allowed", True) == False:
            d["reallocatable"] = False
            counters["no_bike_allowed"] += 1

        else:
            d["reallocatable"] = True
            counters["reallocatable"] += 1

        counters["total"] += 1

    if verbose:
        print("Reallocatability summary:", counters.most_common())

    return counters




def assign_edge_regions(G, gdf_regions_proj, gdf_local_proj) -> MultiDiGraph:
    """
    Assign each edge both a region (admin_level=7) and a locality/town (admin_level=8)
    based on the centroid of its geometry.
    If not contained in any polygon, the nearest polygon of each level is used.
    """
    # Split for convenience
    sindex_regions = gdf_regions_proj.sindex
    sindex_local   = gdf_local_proj.sindex

    for u, v, k, d in G.edges(keys=True, data=True):
        geom = d.get("geometry")
        if geom is None:
            continue
        centroid = geom.centroid

        # ---- Region (level 7) ----
        found_region = None
        for idx in sindex_regions.intersection(centroid.bounds):
            row = gdf_regions_proj.iloc[idx]
            if row.geometry.contains(centroid):
                found_region = row["name"]
                break
        if not found_region:  # fallback nearest
            min_dist, nearest_name = float("inf"), None
            for idx, row in gdf_regions_proj.iterrows():
                dist = centroid.distance(row.geometry)
                if dist < min_dist:
                    min_dist, nearest_name = dist, row["name"]
            found_region = nearest_name

        # ---- Locality (level 8) ----
        found_local = None
        for idx in sindex_local.intersection(centroid.bounds):
            row = gdf_local_proj.iloc[idx]
            if row.geometry.contains(centroid):
                found_local = row["name"]
                break
        if not found_local:  # fallback nearest
            min_dist, nearest_name = float("inf"), None
            for idx, row in gdf_local_proj.iterrows():
                dist = centroid.distance(row.geometry)
                if dist < min_dist:
                    min_dist, nearest_name = dist, row["name"]
            found_local = nearest_name

        # Assign both attributes
        d["region"] = found_region
        d["locality"] = found_local

    return G

# region bike costs

def _compute_bike_costs_from_grade(
    length_m: float,
    grade: float,  # capped in [-0.2, 0.2]
    risk_factor: float,
    base_speed_kmh: float = 18.0,     # typical urban cycling
    min_speed_kmh: float = 6.0,       # avoid absurdly slow speeds
    max_speed_kmh: float = 35.0,      # cap downhill speed
):
    """
    Returns:
      bike_cost_base: physical travel time (seconds)
      bike_cost_penalty: perceived travel time (seconds)
    """

    # Convert fractional grade to percent for interpretability
    grade_pct = 100.0 * max(-0.2, min(0.2, grade))

    # --- Physical speed from grade ---
    # Simple, monotonic speed adjustment:
    # - uphill: speed decreases faster
    # - downhill: speed increases slower (safer/more realistic)
    if grade_pct >= 0:
        # e.g., +10% grade -> noticeable slowdown
        speed_kmh = base_speed_kmh * (1.0 / (1.0 + 0.08 * grade_pct))
    else:
        # e.g., -10% grade -> modest speedup, capped later
        speed_kmh = base_speed_kmh * (1.0 + 0.03 * (-grade_pct))

    # Clamp to keep stable and realistic
    speed_kmh = max(min_speed_kmh, min(max_speed_kmh, speed_kmh))

    # Convert to m/s
    speed_ms = speed_kmh * 1000.0 / 3600.0
    # Base physical time
    bike_cost_base = length_m / speed_ms

    # --- Risk-adjusted perceived cost ---
    bike_cost_penalty = bike_cost_base * risk_factor

    return bike_cost_base, bike_cost_penalty

def update_bike_costs(
    G: MultiDiGraph,
    edges: list[tuple] | None = None,
):
    """
    Recompute bike costs for all edges or a specified subset.

    Parameters
    ----------
    G : MultiDiGraph
    edges : list of (u, v, k), optional
        If None, recompute for all edges.
        If provided, recompute only for these edges.
    """
    if edges is None:
        edges = list(G.edges(keys=True))

    for u, v, k in edges:
        d = G[u][v][k]

        base, penalty = _compute_bike_costs_from_grade(
            length_m=d["length"],
            grade=d.get("grade"),
            risk_factor=d["risk_factor"],
        )

        d["bike_cost_base"] = base
        d["bike_cost_penalty"] = penalty

