import numpy as np
import geopandas as gpd
from shapely.geometry import Point
import random
import pandas as pd
import osmnx as ox
from collections import Counter


DEFAULT_BETA = 0.001

#region sampling Origin
def sample_point_in_polygon(polygon, rng, max_tries=100):
    """
    Uniformly sample a point inside a (Multi)Polygon using rejection sampling.
    """
    minx, miny, maxx, maxy = polygon.bounds

    for _ in range(max_tries):
        p = Point(
            rng.uniform(minx, maxx),
            rng.uniform(miny, maxy),
        )
        if polygon.contains(p):
            return p

    raise RuntimeError("Failed to sample point inside polygon")

def sample_point_from_regions_weighted(gdf_regions, rng):
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
        geom = geom.geoms[rng.integers(len(geom.geoms))]

    return sample_point_in_polygon(geom, rng)


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

def sample_destination_gravity( origin:Point, destinations:gpd.GeoDataFrame, rng ,beta:float=DEFAULT_BETA, max_dist:float|None=None,):
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
    idx = rng.choice(len(destinations), p=probs)
    return destinations.iloc[idx].geometry

#region gen_OD
def gen_random_OD_counter( G, rng, n_trips, min_euclid_m=3000,):
    nodes = np.array(list(G.nodes))
    xs = np.array([G.nodes[n]["x"] for n in nodes])
    ys = np.array([G.nodes[n]["y"] for n in nodes])

    c = Counter()
    tries = 0

    while sum(c.values()) < n_trips and tries < n_trips * 50:
        i = rng.integers(len(nodes))
        j = rng.integers(len(nodes))
        if i == j:
            tries += 1
            continue

        dx = xs[i] - xs[j]
        dy = ys[i] - ys[j]
        if (dx*dx + dy*dy) ** 0.5 < min_euclid_m:
            tries += 1
            continue

        c[(int(nodes[i]), int(nodes[j]))] += 1
        tries += 1

    return c

def gen_demand_OD_counter(
    G,
    gdf_residential,
    gdf_destinations,
    rng,
    n_trips: int = 50,
    beta: float = DEFAULT_BETA,
    max_dist: float | None = None,
):
    """
    Generate sparse weighted OD list:
        (origin_node, destination_node, weight)

    Weight corresponds to how many times this OD pair
    was sampled (Monte Carlo approximation of demand).
    """
    od_counts = Counter()

    for _ in range(n_trips):
        origin_pt = sample_point_from_regions_weighted(
            gdf_residential, rng
        )

        destination_pt = sample_destination_gravity(
            origin_pt,
            gdf_destinations,
            rng,
            beta=beta,
            max_dist=max_dist,
        )

        origin_node = ox.distance.nearest_nodes(
            G, origin_pt.x, origin_pt.y
        )
        dest_node = ox.distance.nearest_nodes(
            G, destination_pt.x, destination_pt.y
        )

        # Skip trivial OD
        if origin_node == dest_node:
            continue

        od_counts[(origin_node, dest_node)] += 1

    return od_counts


def gen_OD(
    G,
    gdf_residential,
    gdf_destinations,
    rng,
    n_trips: int = 50,
    random_frac: float = 0.0,
    beta: float = DEFAULT_BETA,
    max_dist: float | None = None,
    min_random_dist: float = 3000,
):
    """
    Generate a mixed OD matrix consisting of:
      - demand-driven ODs (gravity-based)
      - random long-distance ODs (structural probing)

    Parameters
    ----------
    n_trips : int
        Number of demand-driven trips
    random_frac : float
        Fraction of random trips relative to demand trips (e.g. 0.1 = 10%)
    """

    if not (0.0 <= random_frac <= 1.0):
        raise ValueError("random_frac must be in [0, 1]")

    # --- Demand ODs ---
    demand_counter = gen_demand_OD_counter(
        G,
        gdf_residential,
        gdf_destinations,
        rng,
        n_trips=n_trips,
        beta=beta,
        max_dist=max_dist,
    )

    # --- Random ODs ---
    n_random = int(random_frac * n_trips)
    if n_random > 0:
        random_counter = gen_random_OD_counter(
            G,
            rng,
            n_trips=n_random,
            min_euclid_m=min_random_dist,
        )
    else:
        random_counter = Counter()

    # --- Combine ---
    od_counts = demand_counter + random_counter

    # --- Convert to weighted list ---
    ods = [(o, d, w) for (o, d), w in od_counts.items()]

    return ods
