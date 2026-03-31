import numpy as np
import geopandas as gpd
from shapely.geometry import Point
import random
import pandas as pd
import osmnx as ox
from collections import Counter
from collections.abc import Mapping
from constants import OD, ODPair
from typing import Any, Optional
import networkx as nx
import constants



DEFAULT_BETA = 0.0002

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

def prepare_region_sampling(gdf_regions):
    """Weighted by area"""
    valid = gdf_regions[
        gdf_regions.geometry.notnull() &
        ~gdf_regions.geometry.is_empty
    ]

    geoms = list(valid.geometry)
    areas = np.array([geom.area for geom in geoms], dtype=float)
    probs = areas / areas.sum()

    return geoms, probs
#endregion

#TODO do the trips but also in reverse?
#TODO allow for residential to residentail trips?
#region sampling Destination

def prepare_destinations(gdf):
    gdf = gdf.copy()

    if not all(gdf.geometry.geom_type == "Point"):
        gdf["geometry"] = gdf.geometry.centroid

    gdf["dest_type"] = gdf.apply(infer_destination_type, axis=1)

    return gdf[["geometry", "dest_type"]]

def infer_destination_type(row):
    office = row.get("office")
    shop = row.get("shop")
    amenity = row.get("amenity")

    # --- Office → work ---
    if pd.notna(office):
        return "work"

    # --- Shop → shopping ---
    if pd.notna(shop):
        return "shop"

    # --- Amenity → mapped ---
    if pd.notna(amenity):
        if amenity in constants.AMENITY_KEEP:
            return amenity
        else:
            return "other"

def sample_trip_purpose(rng, purpose_shares):
    purposes = np.array(list(purpose_shares.keys()))
    probs = np.array(list(purpose_shares.values()), dtype=float)
    probs /= probs.sum()
    idx = rng.choice(len(purposes), p=probs)
    return purposes[idx]

def filter_destinations_for_purpose(destinations, purpose, mapping):
    allowed = mapping[purpose]

    if "*" in allowed:
        return destinations

    return destinations[destinations["dest_type"].isin(allowed)]


def sample_destination_for_purpose( origin:Point, destinations:gpd.GeoDataFrame, purpose, purpose_to_subtypes, rng ,beta:float=DEFAULT_BETA, max_dist:float|None=None,):
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

    candidates = filter_destinations_for_purpose(
            destinations, purpose, purpose_to_subtypes
        )

    if len(candidates) == 0:
        raise ValueError(f"No destinations for purpose={purpose}")

    distances = candidates.geometry.distance(origin)

    if max_dist is not None:
        mask = distances <= max_dist
        candidates = candidates[mask]
        distances = distances[mask]

        if len(candidates) == 0:
            raise ValueError(f"No destinations within max_dist for {purpose}")

    weights = np.exp(-beta * distances.to_numpy())

    probs = weights / weights.sum()
    idx = rng.choice(len(candidates), p=probs)

    return candidates.iloc[idx].geometry


#region TAZ mapping and region-level OD counters
def build_region_od_table(
    G: nx.MultiDiGraph,
    od_counts,
    *,
    micro_attr: str = "locality",
    locality_to_region: dict[str, str] | None = None,
) -> pd.DataFrame:
    """
    Build an OD matrix table aggregated by region or locality.

    Parameters
    ----------
    G
        Graph whose nodes contain locality attributes.
    od_counts
        Either:
          - dict {(origin_node, destination_node): weight}
          - list [(origin_node, destination_node, weight)]
    micro_attr
        Node attribute storing locality.
    locality_to_region
        Optional mapping {locality -> region}.
        If provided, aggregation happens at region level.

    Returns
    -------
    DataFrame
        OD matrix where rows = origin region/locality
        and columns = destination region/locality
    """
    flows = {}

    if isinstance(od_counts, Mapping):
        iterator = ((o, d, w) for (o, d), w in od_counts.items())
    else:
        iterator = od_counts

    for o, d, w in iterator:

        o_local = G.nodes[int(o)].get(micro_attr)
        d_local = G.nodes[int(d)].get(micro_attr)

        if o_local is None or d_local is None:
            continue

        if locality_to_region is not None:
            o_region = locality_to_region.get(o_local)
            d_region = locality_to_region.get(d_local)
        else:
            o_region = o_local
            d_region = d_local

        if o_region is None or d_region is None:
            continue

        key = (o_region, d_region)

        flows[key] = flows.get(key, 0.0) + float(w)

    df = pd.DataFrame(
        [(o, d, w) for (o, d), w in flows.items()],
        columns=["origin", "destination", "flow"],
    )

    od_table = df.pivot_table(
        index="origin",
        columns="destination",
        values="flow",
        aggfunc="sum",
        fill_value=0,
    )

    if locality_to_region is not None:
        od_table = od_table.reindex(
            index=constants.REGION_ORDER,
            columns=constants.REGION_ORDER,
            fill_value=0,
        )
    else:
        # Keep locality-level labels when no region mapping is requested.
        locality_order = sorted(
            set(od_table.index.to_list()) | set(od_table.columns.to_list())
        )
        od_table = od_table.reindex(
            index=locality_order,
            columns=locality_order,
            fill_value=0,
        )

    return od_table



def build_region_od_tables_from_timeline(
    timeline,
    G,
    *,
    micro_attr: str = "locality",
    locality_to_region: dict[str, str] | None = None,
):
    """
    Build a list of OD matrices from a timeline structure.

    Parameters
    ----------
    timeline : list[dict]
        Output from gen_od_trips_timeline()
    G : nx.MultiDiGraph
    micro_attr : str
        Node attribute storing locality
    locality_to_region : dict | None
        Optional mapping for aggregation

    Returns
    -------
    list of dicts
        [
            {
                "begin": int,
                "end": int,
                "od_table": DataFrame
            },
            ...
        ]
    """

    results = []

    for interval in timeline:

        od_table = build_region_od_table(
            G,
            interval["ods"],
            micro_attr=micro_attr,
            locality_to_region=locality_to_region,
        )

        results.append({
            "begin": interval["begin"],
            "end": interval["end"],
            "od_table": od_table
        })

    return results

def build_total_region_od_table(
    timeline,
    G,
    *,
    micro_attr="locality",
    locality_to_region=None,
):

    all_ods = []

    for interval in timeline:
        all_ods.extend(interval["ods"])

    return build_region_od_table(
        G,
        all_ods,
        micro_attr=micro_attr,
        locality_to_region=locality_to_region,
    )

#endregion

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

#TODO i can def optimise this code
def gen_demand_OD_counter(
    G,
    gdf_residential,
    gdf_destinations,
    rng,
    n_trips: int = 50,
    beta: float = DEFAULT_BETA,
    max_dist: float | None = None,
):
    od_counts = Counter()

    residential_geoms, residential_probs = prepare_region_sampling(gdf_residential)

    poly_idxs = rng.choice(
        len(residential_geoms),
        size=n_trips,
        p=residential_probs
    )

    origin_pts = [sample_point_in_polygon(residential_geoms[i], rng) for i in poly_idxs]

    dest_pts = []

    for origin_pt in origin_pts:
        purpose = sample_trip_purpose(rng, constants.PURPOSE_SHARES)

        dest_pt = sample_destination_for_purpose(
            origin=origin_pt,
            destinations=gdf_destinations,
            purpose=purpose,
            rng=rng,
            purpose_to_subtypes=constants.PURPOSE_TO_TYPES,
            beta=beta,
            max_dist=max_dist,
        )
        dest_pts.append(dest_pt)


    if not dest_pts:
        return od_counts

    origin_nodes = ox.distance.nearest_nodes(
        G,
        [p.x for p in origin_pts[:len(dest_pts)]],
        [p.y for p in origin_pts[:len(dest_pts)]],
    )

    dest_nodes = ox.distance.nearest_nodes(
        G,
        [p.x for p in dest_pts],
        [p.y for p in dest_pts],
    )

    # Casting from numpy ints to normal python ints as there were some compatability issues
    origin_nodes = [int(n) for n in origin_nodes]
    dest_nodes = [int(n) for n in dest_nodes]

    for o, d in zip(origin_nodes, dest_nodes):
        if o != d:
            od_counts[(o, d)] += 1

    return od_counts

#TODO im running the exact same od matrix for both cars and bikes and thus they are in the same quantity, idk if this is a problem tbh.
#TODO seperate edge importance for cars and bikes? (i swear i had done this but idk)
def gen_OD_trips(
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


def gen_od_trips_timeline(
    list_total_trips_per_hour: list[int],
    G,
    gdf_residential,
    gdf_destinations,
    rng,
    random_frac: float = 0.0,
    beta: float = DEFAULT_BETA,
    max_dist: float | None = None,
    min_random_dist: float = 3000,
):
    """
    Generate OD trips across multiple hours.

    Returns
    -------
    list of dicts:
        [
            {
                "begin": int,
                "end": int,
                "ods": [(o,d,w), ...]
            },
            ...
        ]
    """

    intervals = []
    for hour, n_trips in enumerate(list_total_trips_per_hour):

        begin = hour * 3600
        end = (hour + 1) * 3600

        ods = gen_OD_trips(
            G,
            gdf_residential,
            gdf_destinations,
            rng,
            n_trips=n_trips,
            random_frac=random_frac,
            beta=beta,
            max_dist=max_dist,
            min_random_dist=min_random_dist,
        )

        intervals.append({
            "begin": begin,
            "end": end,
            "ods": ods
        })

    return intervals


def aggregate_timeline_ods(timeline):
    """
    Sum all OD flows across intervals.

    Returns
    -------
    Counter[(origin,destination)] -> total trips
    """

    total_counter = Counter()

    for interval in timeline:
        for origin, dest, trips in interval["ods"]:
            total_counter[(origin, dest)] += trips

    return total_counter



def scale_OD_pairs(ods_counts, bike_share: float = 0.1) -> list[ODPair]:
    """
    Returns a normalized list of ODPair objects for the flow solver.
    """
    # 1. Generate raw ODPairs
    raw_od = [
        ODPair(
            origin=o, 
            destination=d, 
            bike_weight=float(w) * bike_share, 
            car_weight=float(w) * (1.0 - bike_share), 
            is_auxiliary=False
        )
        for o, d, w in ods_counts
    ]

    # 2. Calculate scaling factor (normalize by mean total weight)
    total_weights = [p.bike_weight + p.car_weight for p in raw_od if (p.bike_weight + p.car_weight) > 0]
    
    if not total_weights:
        return raw_od

    scale = len(total_weights) / sum(total_weights)

    # 3. Return scaled NamedTuples
    return [
        ODPair(
            p.origin, 
            p.destination, 
            p.bike_weight * scale, 
            p.car_weight * scale, 
            p.is_auxiliary
        )
        for p in raw_od
    ]


def append_auxiliary_chain_od_pairs(
    OD_demand: OD,
    rng,
    nodes: list[int],
    shuffle_nodes: bool = True,
) -> OD:
    """
    Augment demand OD with chained auxiliary OD pairs:
      (v1,v2), (v2,v3), ..., (v{n-1},vn), (vn,v1)

    Auxiliary pairs are assigned zero objective weights:
      bike_weight = 0.0, car_weight = 0.0, is_auxiliary = True

    Notes
    -----
    - Duplicates (o,d) already present in OD_demand are not added again.
    - If fewer than 2 nodes are provided, input OD is returned unchanged.
    """
    od_aug: OD = list(OD_demand)
    unique_nodes = list(dict.fromkeys(nodes))
    if len(unique_nodes) < 2:
        return od_aug

    if shuffle_nodes:
        rng.shuffle(unique_nodes)

    existing_pairs = {(od.origin, od.destination) for od in od_aug}

    for i in range(len(unique_nodes) - 1):
        o = int(unique_nodes[i])
        d = int(unique_nodes[i + 1])
        if (o, d) in existing_pairs:
            continue
        od_aug.append(
            ODPair(
                origin=o,
                destination=d,
                bike_weight=0.0,
                car_weight=0.0,
                is_auxiliary=True,
            )
        )
        existing_pairs.add((o, d))

    # Close the chain with (vn, v1)
    o = int(unique_nodes[-1])
    d = int(unique_nodes[0])
    if (o, d) not in existing_pairs:
        od_aug.append(
            ODPair(
                origin=o,
                destination=d,
                bike_weight=0.0,
                car_weight=0.0,
                is_auxiliary=True,
            )
        )

    return od_aug
