from geopandas import GeoDataFrame
from networkx import MultiDiGraph

import osmnx as ox
import networkx as nx
import numpy as np
import geopandas as gpd
from constants import SafetyClass, InfraType, FIETSSTRAAT_SPEED_KMH

from collections import Counter
from shapely.geometry import Point


safety_to_risk_factor_map = {
    SafetyClass.PROTECTED: 0.5, 
    SafetyClass.PAINTED: 1,
    SafetyClass.LOW_CAR_FLOW: 2,#NOTE Cyclists perceive travel on car-dominated lanes as twice as costly
    SafetyClass.HIGH_CAR_FLOW: 4,#TODO highway twice as costly ig?
    SafetyClass.UNCLASSIFIED:2,
}

#TODO
def bike_safety_classification(G: MultiDiGraph) -> MultiDiGraph:
    for _, _, data in G.edges(data=True):

        highway = data.get("highway")
        bicycle = data.get("bicycle")
        cycleway = data.get("cycleway")

        # ==========================================================
        # STEP 1 — Determine infra_type
        # ==========================================================
        if cycleway == "track" or highway == "cycleway" or bicycle == "designated":
            infra_type = "cycle_track"        # physically separated
        elif cycleway in {"lane"}:
            infra_type = "bike_lane"          # painted lane
        elif cycleway in {"shared", "shared_lane"}:
            infra_type = "mixed"              # no markings, shared with cars
        elif highway in {"residential"}:
            infra_type = "mixed"              # low-speed streets
        else:
            infra_type = "car"                # default assumption

        # Store inferred type
        data["infra_type"] = infra_type

        # ==========================================================
        # STEP 2 — Safety classification 
        # ==========================================================
        if infra_type == "cycle_track":
            classification = SafetyClass.PROTECTED

        elif infra_type == "bike_lane":
            classification = SafetyClass.PAINTED

        elif infra_type == "mixed":
            # Potentially a good fietsstraat candidate
            if highway in {"residential",}:
                classification = SafetyClass.LOW_CAR_FLOW

        elif highway in {"primary", "secondary", "trunk", "tertiary"}:
            classification = SafetyClass.HIGH_CAR_FLOW

        elif highway in {"track", "service", "non_motorised"}:
            classification = SafetyClass.LOW_CAR_FLOW

        else:
            classification = SafetyClass.UNCLASSIFIED

        # ==========================================================
        # STEP 3 — Update attributes
        # ==========================================================
        data["safety"] = classification
        data["risk_factor"] = float(safety_to_risk_factor_map[classification])

        """      
        # Dangerous roads should not be bikeable
        if classification == SafetyClass.HIGH_CAR_FLOW:
            #TODO NOTE this was set to false orginally, but was causing proble,s
            #I have now set it true, and made the bikeable subgraph reachable to all nodes
            data["bike_allowed"] = False
        else:
            data["bike_allowed"] = True
        """
    return G


#TODO move to clean_input data?
def load_and_clean_localities(G, place_name, locality_to_region) -> tuple[GeoDataFrame, GeoDataFrame]:
    """
    Fetch Malta localities (admin_level=8), clean them, then construct
    region geometries by dissolving localities according to a manual
    locality -> region mapping.

    Returns
    -------
    gdf_regions_proj
        Region polygons created from dissolving localities.
    gdf_local_proj
        Cleaned locality polygons.
    """

    gdf_local = ox.features.features_from_place(
        place_name,
        tags={"boundary": "administrative", "admin_level": "8"}
    )

    # Basic cleaning-
    gdf_local = gdf_local[["name", "admin_level","geometry"]]
    gdf_local = gdf_local[gdf_local["admin_level"].isin(["8"])]
    gdf_local = gdf_local[["name", "geometry"]].dropna()
    gdf_local = gdf_local.drop_duplicates(subset=["name"])

    # Keep largest polygon if multipolygon
    for idx, row in gdf_local.iterrows():
        if row.geometry.geom_type == "MultiPolygon":
            largest_poly = max(row.geometry.geoms, key=lambda g: g.area)
            gdf_local.at[idx, "geometry"] = largest_poly

    # Add region from manual mapping
    gdf_local["region"] = gdf_local["name"].map(locality_to_region)

    missing = gdf_local[gdf_local["region"].isna()]
    if len(missing) > 0:
        print("Warning: localities missing region mapping:")
        print(missing["name"].tolist())

    # Project to graph CRS
    gdf_local_proj = gdf_local.to_crs(G.graph["crs"])

    # Build regions by dissolving localities
    gdf_regions_proj = (gdf_local_proj.dissolve(by="region", as_index=False)[["region", "geometry"]]
                        .rename(columns={"region": "name"}))

    print("Localities:", len(gdf_local_proj))
    print("Regions:", len(gdf_regions_proj))

    return gdf_regions_proj, gdf_local_proj


"""def tag_reallocatable_edges(G:MultiDiGraph):
    # mark bridges as not reallocatable
    bridges = set(nx.bridges(G.to_undirected()))
    for u, v, k, d in G.edges(keys=True, data=True):
        if (u, v) in bridges or (v, u) in bridges:
            d["reallocatable"] = False

        #Can only reallocate from car lanes
        elif d.get("car_allowed", False) == False or d.get("car_lanes",0) <= 0:
            d["reallocatable"] = False

        #Can only reallocate from where its bikeable (i.e not tunnels or highways)
        elif d.get("bike_allowed", True) == False:
            d["reallocatable"] = False


        else:
            d["reallocatable"] = True"""

def tag_reallocatable_edges(G:MultiDiGraph, verbose: bool = False) -> Counter:
    """
    Mark edges as reallocatable and return a Counter with how many edges hit each rule.
    Set verbose=True to print a short summary.
    """
    counters = Counter()
    # mark bridges as not reallocatable
    bridges = set(nx.bridges(G.to_undirected()))
    for u, v, k, d in G.edges(keys=True, data=True):
        # default to False until proven otherwise (defensive)
        if (u, v) in bridges or (v, u) in bridges:
            d["reallocatable"] = False
            counters["bridge"] += 1

        # Never touch protected cycle tracks
        elif d.get("infra_type") == InfraType.CYCLE_TRACK:
            d["reallocatable"] = False

        # Can only reallocate from car lanes
        elif d.get("car_allowed", False) == False:
            d["reallocatable"] = False
            counters["no_car_allowed"] += 1
        
        #Cars can not enter exit roundabouts if there a dedicated cyclelane with a phyiscal barier
        elif d.get("junction") == "roundabout":
            d["reallocatable"] = False
            counters["roundabouts"] += 1

        #TODO can remove
        elif d.get("car_lanes", 0) <= 0:
            d["reallocatable"] = False
            counters["no_car_lanes"] += 1
        
        #Dont touch relativly safe roads
        #TODO service?
            """
        elif d.get("highway") in {"track", "residential"}:
            d["reallocatable"] = False
            counters["highway type"] += 1"""

        # Can only reallocate where biking is allowed (i.e. not tunnels/highways)
        #TODO NOTE this is temp reomced, as i am now allowing main roads?
            """
        elif d.get("bike_allowed", True) == False:
            d["reallocatable"] = False
            counters["no_bike_allowed"] += 1"""

        else:
            d["reallocatable"] = True
            counters["reallocatable"] += 1

        counters["total"] += 1

    if verbose:
        print("Reallocatability summary:", counters.most_common())

    return counters

def _lookup_intersections(geom, gdf, sindex, name_col="name"):
    """
    Return all polygon names whose geometry intersects the given geometry.
    """
    matches = []
    for idx in sindex.intersection(geom.bounds):
        row = gdf.iloc[idx]
        if geom.intersects(row.geometry):
            matches.append(row[name_col])
    return sorted(set(matches))


def _nearest_name(geom, gdf, name_col="name"):
    """
    Return the name of the nearest polygon to the geometry centroid.
    """
    centroid = geom.centroid
    nearest_idx = gdf.geometry.distance(centroid).idxmin()
    return gdf.loc[nearest_idx, name_col]


def _resolve_context_col(gdf, attr, fallback_cols):
    """
    Pick a GeoDataFrame column for spatial-name lookups.
    Preference: `attr` if present, otherwise first available fallback.
    """
    if attr in gdf.columns:
        return attr

    for col in fallback_cols:
        if col in gdf.columns:
            return col

    raise KeyError(f"No matching column found for '{attr}'. Tried fallbacks: {fallback_cols}")


def _assign_geometry_context(
    geom,
    gdf_regions_proj,
    gdf_local_proj,
    sindex_regions,
    sindex_local,
    *,
    allow_multiple=True,
    region_attr="regions",
    locality_attr="localities",
):
    """
    Assign region/locality names to a geometry.

    Parameters
    ----------
    geom
        Shapely geometry (Point or LineString).
    allow_multiple : bool
        If True, returns all intersecting names as lists.
        If False, returns a single name for each via first match / nearest fallback.

    Returns
    -------
    dict
        {
            region_attr: list[str] or str,
            locality_attr: list[str] or str
        }
    """
    if geom is None or geom.is_empty:
        return {
            region_attr: [] if allow_multiple else None,
            locality_attr: [] if allow_multiple else None,
        }

    region_col = _resolve_context_col(gdf_regions_proj, region_attr, ("name",))
    locality_col = _resolve_context_col(gdf_local_proj, locality_attr, ("locality", "name"))

    # ---- Regions ----
    regions = _lookup_intersections(geom, gdf_regions_proj, sindex_regions, region_col)
    if not regions:
        nearest_region = _nearest_name(geom, gdf_regions_proj, region_col)
        regions = [nearest_region]

    # ---- Localities ----
    localities = _lookup_intersections(geom, gdf_local_proj, sindex_local, locality_col)
    if not localities:
        nearest_locality = _nearest_name(geom, gdf_local_proj, locality_col)
        localities = [nearest_locality]

    if allow_multiple:
        return {
            region_attr: regions,
            locality_attr: localities,
        }
    else:
        return {
            region_attr: regions[0] if regions else None,
            locality_attr: localities[0] if localities else None,
        }


def assign_node_regions(
    G: MultiDiGraph,
    gdf_regions_proj: gpd.GeoDataFrame,
    gdf_local_proj: gpd.GeoDataFrame,
    *,
    region_attr="region",
    locality_attr="locality",
) -> MultiDiGraph:
    """
    Assign each node a single region and locality.

    Attributes added to each node:
      - node[region_attr]   : str
      - node[locality_attr] : str
    """
    sindex_regions = gdf_regions_proj.sindex
    sindex_local = gdf_local_proj.sindex

    for node, data in G.nodes(data=True):
        x = data.get("x")
        y = data.get("y")

        if x is None or y is None:
            data[region_attr] = None
            data[locality_attr] = None
            continue

        geom = Point(x, y)
        context = _assign_geometry_context(
            geom,
            gdf_regions_proj,
            gdf_local_proj,
            sindex_regions,
            sindex_local,
            allow_multiple=False,
            region_attr=region_attr,
            locality_attr=locality_attr,
        )

        data[region_attr] = context[region_attr]
        data[locality_attr] = context[locality_attr]

    return G


def assign_edge_regions(
    G: MultiDiGraph,
    gdf_regions_proj: gpd.GeoDataFrame,
    gdf_local_proj: gpd.GeoDataFrame,
    *,
    region_attr="regions",
    locality_attr="localities",
) -> MultiDiGraph:
    """
    Assign each edge all intersecting regions and localities.

    Attributes added to each edge:
      - d[region_attr]   : list[str]
      - d[locality_attr] : list[str]
    """
    sindex_regions = gdf_regions_proj.sindex
    sindex_local = gdf_local_proj.sindex

    for u, v, k, d in G.edges(keys=True, data=True):
        geom = d.get("geometry")

        context = _assign_geometry_context(
            geom,
            gdf_regions_proj,
            gdf_local_proj,
            sindex_regions,
            sindex_local,
            allow_multiple=True,
            region_attr=region_attr,
            locality_attr=locality_attr,
        )

        d[region_attr] = context[region_attr]
        d[locality_attr] = context[locality_attr]

    return G


def assign_spatial_context(G: MultiDiGraph, gdf_regions_proj: gpd.GeoDataFrame, gdf_local_proj: gpd.GeoDataFrame,) -> MultiDiGraph:
    """
    Assign spatial administrative context to both nodes and edges.

    Node attributes:
      - region
      - locality

    Edge attributes:
      - regions
      - localities
    """
    #print("GDF region",gdf_regions_proj.head())
    #print("gdf local", gdf_local_proj.head())

    G = assign_node_regions(G, gdf_regions_proj, gdf_local_proj)
    G = assign_edge_regions(G, gdf_regions_proj, gdf_local_proj)
    return G
