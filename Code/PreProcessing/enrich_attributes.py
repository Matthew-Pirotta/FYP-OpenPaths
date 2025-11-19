from geopandas import GeoDataFrame
from networkx import MultiDiGraph

import osmnx as ox
import networkx as nx
import numpy as np
from constants import SafetyClass

safety_to_risk_factor_map = {
    SafetyClass.VERY_SAFE: 0.5, 
    SafetyClass.SAFE: 1,
    SafetyClass.MODERATE: 1.5,
    SafetyClass.CAUTION: 2,#NOTE Cyclists perceive travel on car-dominated lanes as twice as costly
    SafetyClass.DANGEROUS: 4,#TODO highway twice as costly ig?
    SafetyClass.UNSUITABLE: 2,
    SafetyClass.UNCLASSIFIED:2,
}

#TODO
def bike_safety_classification(G_bike:MultiDiGraph) -> MultiDiGraph:
    for _, _, data in G_bike.edges(data=True):
        #TODO although im filtering based on road priority for classification, i still need to see the seperate bike and car lanes
        # and in reality they should be 2 seperate graphs? but currently the bike can cycle over the car network
        # ig in reality i just need to see how these connections are being stored

        highway = data.get("highway")
        # Defines legal access — whether bicycles may use the way.
        bicycle = data.get("bicycle")
        #Describes infrastructure type — if and how a bike facility exists
        cycleway = data.get("cycleway")

        #Separated 
        if cycleway == 'track' or highway == "cycleway" or bicycle == "designated":
            classification = SafetyClass.VERY_SAFE
        #Demarcated Shared
        #NOTE shared_lane is not considered safe as the cyclist is travelling on the same road with no markings
        elif cycleway in {"shared", "lane",}:
            classification = SafetyClass.SAFE

        # MODERATE - Cyclist-friendly streets  
        elif highway in {"non_motorised", "residential"}:
            classification = SafetyClass.MODERATE

        # CAUTION - Mixed traffic but manageable
        elif highway == "service":
            classification = SafetyClass.CAUTION
        
        # Dangerous - active traffic
        elif highway in {"trunk", "secondary","primary", "tertiary"}:
            classification = SafetyClass.DANGEROUS

        #Country roads not suitable for urban transport
        elif highway == "track":
            #NOTE was "unsuitable" and has been changed to "moderate"
            classification = SafetyClass.MODERATE
        else:
            classification = SafetyClass.UNCLASSIFIED

        data["safety"] = classification
        data["risk_factor"] = float(safety_to_risk_factor_map.get(classification))

        if classification == SafetyClass.DANGEROUS:
            data["bike_allowed"] = False
        #print(f"highway: {highway},\t\t bicycle: {bicycle},\t\t cycleway: {cycleway}") 
    
    return G_bike

#TODO move to clean_input data?
def load_and_clean_localities(G) -> tuple[GeoDataFrame, GeoDataFrame]:
    """
    Fetch and clean administrative boundaries for both level 7 (regions) and level 8 (localities) in Malta. Returns a unified GeoDataFrame projected to the graph CRS.
    """
    #TODO malta is hardcoded
    gdf_localities = ox.features.features_from_place(
        "Malta (Island)",
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

