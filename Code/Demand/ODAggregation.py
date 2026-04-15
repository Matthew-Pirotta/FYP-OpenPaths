import numpy as np
import geopandas as gpd
from shapely.geometry import Point
import random
import pandas as pd
import osmnx as ox
from collections import Counter
from collections.abc import Mapping
from typing import Any, Optional
import networkx as nx
import constants

from Demand import ODConstants

#region TAZ mapping and region-level OD counters
def build_region_od_table(
    G: nx.MultiDiGraph,
    od_counts:Counter,
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

    for (o, d), w in od_counts.items():

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
            index=ODConstants.REGION_ORDER,
            columns=ODConstants.REGION_ORDER,
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
    all_ods = Counter() # Change from list [] to Counter()

    for interval in timeline:
        # Use Counter addition instead of list.extend()
        all_ods += interval["ods"]

    return build_region_od_table(G, all_ods, micro_attr=micro_attr, locality_to_region=locality_to_region)
#endregion

def aggregate_timeline_ods(timeline):
    """
    Sum all OD flows across intervals.

    Returns
    -------
    Counter[(origin,destination)] -> total trips
    """

    total_counter = Counter()
    for interval in timeline:
        # Change this loop to iterate over .items()
        for (origin, dest), trips in interval["ods"].items():
            total_counter[(origin, dest)] += trips
    return total_counter
