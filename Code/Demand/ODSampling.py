from collections import defaultdict
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import random
import osmnx as ox
from collections import Counter
from collections.abc import Mapping
from constants import OD, ODPair
from typing import Any, Optional
import networkx as nx

import constants
from Demand import ODConstants


def normalize_dict(values: dict[str, float]) -> dict[str, float]:
    total = float(sum(values.values()))
    if total <= 0:
        raise ValueError("Cannot normalize dictionary with non-positive total.")
    return {k: float(v) / total for k, v in values.items()}

def prepare_population_sampling_from_joined_residential(gdf_residential_joined):
    return {
        "geoms": list(gdf_residential_joined.geometry),
        "probs": gdf_residential_joined["prob"].to_numpy(dtype=float),
        "localities": gdf_residential_joined["locality"].tolist(),
        "regions": gdf_residential_joined["locality"].map(constants.LOCALITY_TO_REGION).tolist(),
    }

def row_normalize(df: pd.DataFrame) -> pd.DataFrame:
    out = df.astype(float).copy()
    row_sums = out.sum(axis=1)
    out = out.div(row_sums.replace(0, np.nan), axis=0).fillna(0.0)
    return out


def build_purpose_shares(raw_counts: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    """
    Standardizes raw counts into probability shares for every region.
    Assumes "total" and "going_home" are already removed from the input.
    """
    shares_by_region = {}

    for region, purposes in raw_counts.items():
        total = float(sum(purposes.values()))
        
        if total <= 0:
            raise ValueError(f"No usable counts for region={region}")

        shares_by_region[region] = {
            purpose: count / total
            for purpose, count in purposes.items()
        }

    return shares_by_region


DEST_REGION_GIVEN_ORIGIN = {
    origin: normalize_dict(dest_counts)
    for origin, dest_counts in ODConstants.REGION_TO_REGION_COUNTS.items()
}

OUTWARD_PURPOSE_SHARES_BY_DEST_REGION = build_purpose_shares(
    ODConstants.PURPOSE_COUNTS_BY_DEST_REGION
)


def sample_dest_region_given_origin(
    origin_region: str,
    od_region_shares: dict[str, dict[str, float]],
    rng,
) -> str:
    shares = od_region_shares[origin_region]
    regions = np.array(list(shares.keys()))
    probs = np.array(list(shares.values()), dtype=float)
    probs /= probs.sum()
    idx = rng.choice(len(regions), p=probs)
    return str(regions[idx])


def sample_purpose_given_dest_region(
    dest_region: str,
    purpose_shares_by_dest_region: dict[str, dict[str, float]],
    rng,
) -> str:
    shares = purpose_shares_by_dest_region[dest_region]
    purposes = np.array(list(shares.keys()))
    probs = np.array(list(shares.values()), dtype=float)
    probs /= probs.sum()
    idx = rng.choice(len(purposes), p=probs)
    return str(purposes[idx])


def infer_destination_type(row) -> str:
    office = row.get("office")
    shop = row.get("shop")
    amenity = row.get("amenity")

    if pd.notna(office):
        return "work"

    if pd.notna(shop):
        return "shop"

    if pd.notna(amenity):
        if amenity in ODConstants.AMENITY_KEEP:
            return str(amenity)
        return "other"

    return "other"

def filter_destinations_for_region_and_purpose(
    destinations: gpd.GeoDataFrame,
    dest_region: str,
    purpose: str,
    purpose_to_types: dict[str, list[str]],
) -> gpd.GeoDataFrame:
    allowed = purpose_to_types[purpose]
    out = destinations[destinations["region"] == dest_region]

    if "*" in allowed:
        return out

    return out[out["dest_type"].isin(allowed)].copy()

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

def sample_destination_for_region_and_purpose(
    origin: Point,
    destinations: gpd.GeoDataFrame,
    dest_region: str,
    purpose: str,
    purpose_to_subtypes: dict[str, list[str]],
    rng,
    beta: float = ODConstants.DEFAULT_BETA,
    max_dist: float | None = None,
) -> Point:
    """
    Sample a destination point from a given destination region and purpose
    using an exponential gravity model.
    """
    candidates = filter_destinations_for_region_and_purpose(
        destinations=destinations,
        dest_region=dest_region,
        purpose=purpose,
        purpose_to_types=purpose_to_subtypes,
    )

    if len(candidates) == 0:
        raise ValueError(
            f"No destinations for purpose={purpose} in dest_region={dest_region}"
        )

    distances = candidates.geometry.distance(origin)

    if max_dist is not None:
        mask = distances <= max_dist
        candidates = candidates.loc[mask].copy()
        distances = distances.loc[mask]

        if len(candidates) == 0:
            raise ValueError(
                f"No destinations within max_dist for purpose={purpose} in dest_region={dest_region}"
            )

    weights = np.exp(-beta * distances.to_numpy(dtype=float))
    weight_sum = float(weights.sum())
    if weight_sum <= 0:
        raise ValueError("Destination weights summed to zero.")

    probs = weights / weight_sum
    idx = int(rng.choice(len(candidates), p=probs))

    return candidates.iloc[idx].geometry
