from geopandas import GeoDataFrame
from networkx import MultiDiGraph
from shapely.geometry import LineString

import osmnx as ox
import networkx as nx
import numpy as np
from constants import SafetyClass


#TODO very safe?
safety_to_risk_factor_map = {
    "safe": 1,
    "moderate": 1.5,
    "caution": 2 ,#NOTE Cyclists perceive travel on car-dominated lanes as twice as costly
    "dangerous": 4, #TODO highway twice as costly ig?
    "unsuitable": 2,
    "unclassified": 2,
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
        data["risk_factor"] = safety_to_risk_factor_map.get(data.get("safety",-1))

        if classification == SafetyClass.DANGEROUS:
            data["bike_allowed"] = False
        #print(f"highway: {highway},\t\t bicycle: {bicycle},\t\t cycleway: {cycleway}") 
    
    return G_bike

#TODO move to clean_input data?
def load_and_clean_localities(G) -> GeoDataFrame:
    #Get boundary GeoDataFrame for localities (e.g., admin_level = 8)
    #TODO malta is hardcoded
    gdf_localities = ox.features.features_from_place(
        "Malta (Island)",
        tags={"boundary": "administrative", "admin_level": "8"}
    )

    #Data cleaning
    gdf_localities = gdf_localities[["name", "admin_level","geometry"]]
    gdf_localities = gdf_localities[gdf_localities['admin_level'] == "8"]
    gdf_localities = gdf_localities.dropna()
    gdf_localities = gdf_localities.drop_duplicates(subset=['name'])

    # Merge multipolygons
    for idx, row in gdf_localities.iterrows():
        if row.geometry.geom_type == "MultiPolygon":
            largest_poly  = max(row.geometry.geoms, key=lambda g: g.area)  # keep largest component
            gdf_localities.at[idx, "geometry"] = largest_poly 

    gdf_localities_proj = gdf_localities.to_crs(G.graph["crs"])

    # Inspect results
    print("Number of localities:", len(gdf_localities))
    return gdf_localities_proj


def assign_edge_regions(G, gdf_localities) -> MultiDiGraph:
    """Assign each edge a region based on centroid of geometry (fallback to nearest region)."""
    sindex = gdf_localities.sindex

    for u, v, k, d in G.edges(keys=True, data=True):
        # 1️⃣ Get geometry or reconstruct from node coordinates
        geom = d.get("geometry")
        if geom is None:
            geom = LineString([
                (G.nodes[u]["x"], G.nodes[u]["y"]),
                (G.nodes[v]["x"], G.nodes[v]["y"])
            ])
        centroid = geom.centroid
        

        # 2️⃣ Try containment first (fast exact match)
        matches = list(sindex.intersection(centroid.bounds))
        region_found = False
        for idx in matches:
            poly = gdf_localities.iloc[idx].geometry
            if poly.contains(centroid):
                d["region"] = gdf_localities.iloc[idx]["name"]
                region_found = True
                break

        # 3️⃣ Fallback: assign to closest polygon (if no containment match)
        if not region_found:
            min_dist = float("inf")
            nearest_name = None
            for idx, row in gdf_localities.iterrows():
                dist = centroid.distance(row.geometry)
                if dist < min_dist:
                    min_dist = dist
                    nearest_name = row["name"]
            d["region"] = nearest_name

    return G
