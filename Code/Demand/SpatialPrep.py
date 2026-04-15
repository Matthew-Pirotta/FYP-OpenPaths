from collections import defaultdict
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import random
import osmnx as ox
from collections import Counter
from collections.abc import Mapping
from typing import Any, Optional
import networkx as nx

import constants
from Demand import ODConstants, ODUtil, ODSampling

def prepare_residential(gdf_residential):
    """
    Keep valid residential polygons and only required columns.
    """
    gdf = gdf_residential.copy()

    gdf = gdf[gdf.geometry.notnull() & ~gdf.geometry.is_empty].copy()
    gdf = gdf[["geometry"]].copy()

    # explode multipolygons into separate polygons if needed
    gdf = gdf.explode(index_parts=False).reset_index(drop=True)

    # keep only polygonal geometries
    gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()

    return gdf

def prepare_destinations(
    gdf_destinations: gpd.GeoDataFrame,
    gdf_localities: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """
    Prepare non-residential destination opportunities (POIs), attaching locality and region.
    """
    gdf = gdf_destinations.copy()

    if not all(gdf.geometry.geom_type == "Point"):
        gdf["geometry"] = gdf.geometry.centroid

    gdf["dest_type"] = gdf.apply(ODSampling.infer_destination_type, axis=1)

    loc = gdf_localities[["name", "geometry"]].copy().rename(columns={"name": "locality"})
    if gdf.crs != loc.crs:
        loc = loc.to_crs(gdf.crs)
    

    joined = gpd.sjoin(gdf, loc, how="inner", predicate="intersects").copy()
    joined["region"] = joined["locality"].map(constants.LOCALITY_TO_REGION)

    joined = joined[joined["region"].notna()].copy()

    return joined[["geometry", "dest_type", "locality", "region"]].reset_index(drop=True)

def attach_locality_and_population_to_residential( gdf_residential, gdf_localities, locality_to_population,):
    res = gdf_residential.copy().reset_index(drop=True)
    res["res_id"] = res.index

    loc = gdf_localities[["name", "geometry"]].copy()

    if res.crs != loc.crs:
        loc = loc.to_crs(res.crs)

    joined = gpd.sjoin( res, loc, how="inner", predicate="intersects",).copy()

    joined = joined.rename(columns={"name": "locality"})

    # if a residential polygon intersects multiple localities because of boundary issues,
    # keep the first match
    joined = joined.drop_duplicates(subset=["res_id"]).reset_index(drop=True)

    joined["population"] = joined["locality"].map(locality_to_population)

    missing = joined[joined["population"].isna()]
    if len(missing) > 0:
        print("Warning: residential polygons with missing population localities:")
        print(sorted(missing["locality"].dropna().unique().tolist()))

    joined = joined[joined["population"].notna()].copy()

    joined["res_area"] = joined.geometry.area
    joined["locality_res_area_total"] = joined.groupby("locality")["res_area"].transform("sum")

    joined["raw_weight"] = (
        joined["population"] *
        joined["res_area"] / joined["locality_res_area_total"]
    )

    total = joined["raw_weight"].sum()
    if total <= 0:
        raise ValueError("Total residential sampling weight is zero.")

    joined["prob"] = joined["raw_weight"] / total

    return joined

def build_residential_destinations_from_joined_residential(
    gdf_residential_joined: gpd.GeoDataFrame,
    *,
    use_centroids: bool = True,
) -> gpd.GeoDataFrame:
    """
    Build residential destination opportunities for purposes like 'visiting'.

    Expects a residential GeoDataFrame that already has:
      - geometry
      - locality
    """
    gdf = gdf_residential_joined.copy()

    if use_centroids:
        gdf["geometry"] = gdf.geometry.centroid

    gdf["dest_type"] = "residential"
    gdf["region"] = gdf["locality"].map(constants.LOCALITY_TO_REGION)
    gdf = gdf[gdf["region"].notna()].copy()

    return gdf[["geometry", "dest_type", "locality", "region"]].reset_index(drop=True)


def append_residential_destinations(
    gdf_destinations: gpd.GeoDataFrame,
    gdf_residential_destinations: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """
    Combine POI destinations with residential destinations.
    """
    cols = ["geometry", "dest_type", "locality", "region"]
    combined = pd.concat(
        [
            gdf_destinations[cols].copy(),
            gdf_residential_destinations[cols].copy(),
        ],
        ignore_index=True,
    )
    return gpd.GeoDataFrame(combined, geometry="geometry", crs=gdf_destinations.crs)
