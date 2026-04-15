import numpy as np
import geopandas as gpd
from shapely.geometry import Point
import random
import pandas as pd
import osmnx as ox
from collections import Counter
from collections.abc import Mapping
from constants import OD
from typing import Any, Optional, Literal
import networkx as nx
import constants

from Demand import ODSampling, ODConstants

#region gen_OD
def gen_random_OD_counter( G, rng, n_trips, min_euclid_m=500,):
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

def gen_home_based_tour_counter(
    G,
    residential_sampling,
    gdf_destinations,
    rng,
    n_tours: int = 50,
    beta: float = ODConstants.DEFAULT_BETA,
    max_dist: float | None = None,
):
    od_counts = Counter()

    residential_geoms = residential_sampling["geoms"]
    residential_probs = residential_sampling["probs"]
    residential_regions = residential_sampling["regions"]

    poly_idxs = rng.choice(len(residential_geoms), size=n_tours, p=residential_probs)

    outward_origins = []
    outward_dests = []
    return_origins = []
    return_dests = []

    for i in poly_idxs:
        home_pt = ODSampling.sample_point_in_polygon(residential_geoms[i], rng)
        origin_region = residential_regions[i]

        dest_region = ODSampling.sample_dest_region_given_origin(
            origin_region,
            ODSampling.DEST_REGION_GIVEN_ORIGIN,
            rng,
        )

        purpose = ODSampling.sample_purpose_given_dest_region(
            dest_region,
            ODSampling.OUTWARD_PURPOSE_SHARES_BY_DEST_REGION,
            rng,
        )

        dest_pt = ODSampling.sample_destination_for_region_and_purpose(
            origin=home_pt,
            destinations=gdf_destinations,
            dest_region=dest_region,
            purpose=purpose,
            purpose_to_subtypes=ODConstants.PURPOSE_TO_TYPES,
            rng=rng,
            beta=beta,
            max_dist=max_dist,
        )

        outward_origins.append(home_pt)
        outward_dests.append(dest_pt)

        # explicit return-home leg
        return_origins.append(dest_pt)
        return_dests.append(home_pt)

    o1 = ox.distance.nearest_nodes(G, [p.x for p in outward_origins], [p.y for p in outward_origins])
    d1 = ox.distance.nearest_nodes(G, [p.x for p in outward_dests], [p.y for p in outward_dests])
    o2 = ox.distance.nearest_nodes(G, [p.x for p in return_origins], [p.y for p in return_origins])
    d2 = ox.distance.nearest_nodes(G, [p.x for p in return_dests], [p.y for p in return_dests])

    for o, d in zip(o1, d1):
        if o != d:
            od_counts[(int(o), int(d))] += 1

    for o, d in zip(o2, d2):
        if o != d:
            od_counts[(int(o), int(d))] += 1

    return od_counts

#TODO im running the exact same od matrix for both cars and bikes and thus they are in the same quantity, idk if this is a problem tbh.
#TODO seperate edge importance for cars and bikes? (i swear i had done this but idk)
def gen_OD_trips(
    G,
    residential_sampling,
    gdf_destinations,
    rng,
    n_trips: int = 50,
    random_frac: float = 0.0,
    beta: float = ODConstants.DEFAULT_BETA,
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
    
    # split requested trips into demand trips + random trips
    n_random = int(random_frac * n_trips)
    n_demand_trip_target = max(0, n_trips - n_random)

    # each sampled tour produces ~2 trips
    n_tours = int(np.ceil(n_demand_trip_target / 2.0))

    # --- Demand ODs ---
    demand_counter = gen_home_based_tour_counter(
        G,
        residential_sampling,
        gdf_destinations,
        rng,
        n_tours=n_tours,
        beta=beta,
        max_dist=max_dist,
    )

    # --- Random ODs ---
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
    return od_counts


def gen_od_trips_timeline(
    list_total_trips_per_hour: list[int],
    G,
    residential_sampling,
    gdf_destinations,
    rng,
    random_frac: float = 0.0,
    beta: float = ODConstants.DEFAULT_BETA,
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
            residential_sampling,
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






def _iter_od_triples(od_data):
    """
    Canonical iterator over (origin, destination, total_weight).

    Supported inputs:
      - Mapping[(o, d) -> w]
      - Iterable[(o, d, w)]
      - Iterable[((o, d), w)] (e.g. Counter.items())
    """
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
                # Supports rows shaped like: ((o, d), w), e.g. Counter.items().
                (o, d), w = row_vals
            else:
                raise ValueError("row has invalid length")
        except Exception as exc:
            raise TypeError(
                "od_data must be Mapping[(o,d)->w], Iterable[(o,d,w)], or Iterable[((o,d),w)]."
            ) from exc

        yield int(o), int(d), float(w)


def to_od_counter(od_data) -> OD:
    """
    Canonical conversion entrypoint to Counter[(origin, destination)] -> weight.
    """
    out: OD = Counter()
    for o, d, w in _iter_od_triples(od_data):
        out[(o, d)] += float(w)
    return out


def normalize_od_pairs(od_pairs: OD) -> OD:
    """
    Normalize OD weights so mean positive OD weight is 1.
    """
    od_counts = to_od_counter(od_pairs)
    total_weights = [float(w) for w in od_counts.values() if float(w) > 0]
    if not total_weights:
        return Counter(od_counts)

    scale = len(total_weights) / sum(total_weights)
    out: OD = Counter()
    for key, w in od_counts.items():
        out[key] = float(w) * scale
    return out


def to_od_pairs(
    od_data,
    *,
    mode: Literal["split", "car_only", "bike_only"] = "split",
    bike_share: float = 0.1,
    is_auxiliary: bool = False,
    normalize: bool = False,
) -> OD:
    """
    Backward-compatible helper that now returns Counter[(o,d)] only.

    mode
    ----
    Retained for compatibility with older call sites.
    With counter-only OD demand, mode and is_auxiliary are metadata-only.
    """
    if mode == "split" and not (0.0 <= bike_share <= 1.0):
        raise ValueError("bike_share must be in [0, 1] when mode='split'.")
    if mode not in {"split", "car_only", "bike_only"}:
        raise ValueError(f"Unknown mode '{mode}'.")

    out = to_od_counter(od_data)

    if normalize:
        return normalize_od_pairs(out)
    return out


def scale_OD_pairs(ods_counts, bike_share: float = 0.1) -> OD:
    """
    Backward-compatible helper for:
      to_od_pairs(..., mode="split", normalize=True)
    """
    return to_od_pairs(
        ods_counts,
        mode="split",
        bike_share=bike_share,
        is_auxiliary=False,
        normalize=True,
    )


def append_auxiliary_chain_od_pairs(
    OD_demand: OD,
    rng,
    nodes: list[int],
    shuffle_nodes: bool = True,
) -> OD:
    """
    Augment demand OD with chained auxiliary OD pairs (zero weight):
      (v1,v2), (v2,v3), ..., (v{n-1},vn), (vn,v1)

    Notes
    -----
    - Duplicates (o,d) already present in OD_demand are not added again.
    - If fewer than 2 nodes are provided, input OD is returned unchanged.
    """
    od_aug: OD = Counter(to_od_counter(OD_demand))
    unique_nodes = list(dict.fromkeys(nodes))
    if len(unique_nodes) < 2:
        return od_aug

    if shuffle_nodes:
        rng.shuffle(unique_nodes)

    existing_pairs = set(od_aug.keys())

    for i in range(len(unique_nodes) - 1):
        o = int(unique_nodes[i])
        d = int(unique_nodes[i + 1])
        if (o, d) in existing_pairs:
            continue
        od_aug[(o, d)] = 0.0
        existing_pairs.add((o, d))

    # Close the chain with (vn, v1)
    o = int(unique_nodes[-1])
    d = int(unique_nodes[0])
    if (o, d) not in existing_pairs:
        od_aug[(o, d)] = 0.0

    return od_aug
