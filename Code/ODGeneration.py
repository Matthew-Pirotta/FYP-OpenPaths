import numpy as np
import geopandas as gpd
from shapely.geometry import Point
import random

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


#region sampling Destinatiob
AMENITY_WEIGHTS = {
    # High-importance destinations
    "hospital": 5.0,
    "school": 5.0,
    "university": 5.0,

    # Medium-importance destinations
    "cafe": 2.0,
    "fast_food": 2.0,
    "pub": 2.0,
    "restaurant": 2.0,

    # Low-importance / default
    "rest": 1.0
}



def prepare_amenities_with_weights(gdf_amenities, amenity_weights):
    """
    Ensure amenities are points and assign attractiveness weights. 
    All amenities were converted to point destinations using centroids; original OSM element types were discarded.
    """
    gdf = gdf_amenities.copy()

    # Convert geometries to points if needed
    if not all(gdf.geometry.geom_type == "Point"):
        gdf["geometry"] = gdf.geometry.centroid

    # Assign weights
    def get_weight(row):
        amenity = row.get("amenity")
        return amenity_weights.get(amenity, amenity_weights["rest"])

    gdf["weight"] = gdf.apply(get_weight, axis=1)

    gdf = gdf[["geometry", "amenity", "weight"]]

    return gdf



def sample_amenity_destination(
    origin: Point,
    amenities: gpd.GeoDataFrame,
    beta: float = 0.001,
    max_dist: float | None = None,
):
    """
    Sample an amenity destination using an exponential gravity model.

    Parameters
    ----------
    origin : Point
        Origin point (projected CRS)
    gdf_amenities : GeoDataFrame
        Amenity locations (points or polygons)
    beta : float
        Distance decay parameter (1/meters)
    max_dist : float, optional
        Hard cutoff distance in meters

    Returns
    -------
    shapely.geometry.Point
    """

    # Compute distances
    distances = amenities.geometry.distance(origin)

    if max_dist is not None:
        mask = distances <= max_dist
        amenities = amenities[mask]
        distances = distances[mask]

        if len(amenities) == 0:
            raise ValueError("No amenities within max_dist")

    # Gravity weights
    weights = np.exp(-beta * distances.values)

    # Normalize
    probs = weights / weights.sum()

    # Sample
    idx = np.random.choice(len(amenities), p=probs)
    return amenities.iloc[idx].geometry