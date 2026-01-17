import numpy as np
import geopandas as gpd
from shapely.geometry import Point
import random
import pandas as pd

#region sampling Origin
def sample_point_in_polygon(polygon, max_tries=100):
    """
    Uniformly sample a point inside a (Multi)Polygon using rejection sampling.
    """
    minx, miny, maxx, maxy = polygon.bounds

    for _ in range(max_tries):
        p = Point(
            random.uniform(minx, maxx),
            random.uniform(miny, maxy),
        )
        if polygon.contains(p):
            return p

    raise RuntimeError("Failed to sample point inside polygon")

def sample_point_from_regions_weighted(gdf_regions):
    """
    Sample a random point from regions, weighted by polygon area.
    """
    valid = gdf_regions[
        gdf_regions.geometry.notnull() & 
        ~gdf_regions.geometry.is_empty
    ].copy()

    valid["area"] = valid.geometry.area
    probs = valid["area"] / valid["area"].sum()

    row = valid.sample(1, weights=probs).iloc[0]
    geom = row.geometry

    if geom.geom_type == "MultiPolygon":
        geom = random.choice(list(geom.geoms))

    return sample_point_in_polygon(geom)


#region sampling Destination

DESTINATION_WEIGHTS = {
    # --- High-importance (anchor trips) ---
    "hospital": 5.0,
    "school": 5.0,
    "university": 5.0,

    # --- Work-related ---
    "government": 4.0,

    # --- Retail & services ---
    "supermarket": 3.0,
    "mall": 3.0,
    "shop": 3.0,

    # --- Food / social ---
    "restaurant": 2.0,
    "convenience":2.0,
    "cafe": 2.0,
    "fast_food": 2.0,
    "pub": 2.0,
    "bar":2.0,

    # --- Low-priority / fallback ---
    "default": 1.0
}


def infer_destination_type_and_subtype(row):
    if pd.notna(row.get("office")):
        return "office", row.get("office")
    if pd.notna(row.get("shop")):
        return "shop", row.get("shop")
    if pd.notna(row.get("amenity")):
        return "amenity", row.get("amenity")
    return "other", None


def prepare_destinations_with_weights(gdf, weight_map):
    """
    Prepare a canonical destination layer for OD generation.

    Output columns:
        - geometry (Point)
        - dest_type (amenity | shop | office | other)
        - dest_subtype (e.g. cafe, school, office)
        - weight (float)
    """
    gdf = gdf.copy()

    # Ensure point geometry
    if not all(gdf.geometry.geom_type == "Point"):
        gdf["geometry"] = gdf.geometry.centroid

    # Infer destination type and subtype
    inferred = gdf.apply(infer_destination_type_and_subtype, axis=1)
    gdf["dest_type"] = inferred.apply(lambda x: x[0])
    gdf["dest_subtype"] = inferred.apply(lambda x: x[1])

    # Assign weights
    def get_weight(row):
        subtype = row["dest_subtype"]
        return weight_map.get(subtype, weight_map["default"])

    gdf["weight"] = gdf.apply(get_weight, axis=1)

    return gdf[["geometry", "dest_type", "dest_subtype", "weight"]]

def sample_destination(
    origin: Point,
    destinations: gpd.GeoDataFrame,
    beta: float = 0.001,
    max_dist: float | None = None,
):
    """
    Sample an destinatio using an exponential gravity model.

    Parameters
    ----------
    origin : Point
        Origin point (projected CRS)
    gdf_destinations : GeoDataFrame
        Destination locations (points or polygons)
    beta : float
        Distance decay parameter (1/meters)
    max_dist : float, optional
        Hard cutoff distance in meters

    Returns
    -------
    shapely.geometry.Point
    """

    # Compute distances
    distances = destinations.geometry.distance(origin)

    if max_dist is not None:
        mask = distances <= max_dist
        destinations = destinations[mask]
        distances = distances[mask]

        if len(destinations) == 0:
            raise ValueError("No destinations within max_dist")

    # Gravity weights
    weights = np.exp(-beta * distances.values)

    # Normalize
    probs = weights / weights.sum()

    # Sample
    idx = np.random.choice(len(destinations), p=probs)
    return destinations.iloc[idx].geometry