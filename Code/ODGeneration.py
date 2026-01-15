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

# region plotting
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
import osmnx as ox


def plot_network_with_context(
    G,
    gdf_residential=None,
    gdf_amenities=None,
    *,
    amenity_size_col=None,
    origin_point=None,
    destination_point=None,
    figsize=(14, 14),
    title=None,
):
    """
    Plot a road network with optional residential areas, amenities, and OD points.

    Parameters
    ----------
    G : networkx graph
        Base road network (already projected).
    gdf_residential : GeoDataFrame, optional
        Residential polygons.
    gdf_amenities : GeoDataFrame, optional
        Amenity points.
    amenity_size_col : str, optional
        Column name in gdf_amenities used to scale marker size (e.g. 'weight').
    origin_point : shapely Point, optional
        Sampled origin point.
    destination_point : shapely Point, optional
        Sampled destination point.
    figsize : tuple
        Figure size.
    title : str, optional
        Plot title.
    """

    fig, ax = plt.subplots(figsize=figsize)

    # --- Base network ---
    ox.plot_graph( G, ax=ax, node_size=0, edge_color="gray", edge_linewidth=0.5, bgcolor="white", show=False, close=False,)

    legend_handles = []

    # --- Residential areas ---
    if gdf_residential is not None:
        gdf_residential.plot( ax=ax, facecolor="lightblue", edgecolor="none", alpha=0.6,)
        legend_handles.append(mpatches.Patch(facecolor="lightblue", alpha=0.6, label="Residential Areas",))

    # --- Amenities ---
    if gdf_amenities is not None:
        if amenity_size_col is not None and amenity_size_col in gdf_amenities.columns:
            sizes = gdf_amenities[amenity_size_col] * 4
        else:
            sizes = 6

        gdf_amenities.plot(ax=ax,color="orange",markersize=sizes,alpha=0.7,)

        legend_handles.append(mlines.Line2D( [], [], color="orange", marker="o", linestyle="None", markersize=8, label="Amenities",))

    # --- Origin / Destination points ---
    if origin_point is not None:
        ax.plot( origin_point.x, origin_point.y, marker="*", color="red", markersize=20,)
        legend_handles.append(mlines.Line2D( [], [], color="red", marker="*", linestyle="None", markersize=15, label="Origin",))

    if destination_point is not None:
        ax.plot( destination_point.x, destination_point.y, marker="*", color="blue", markersize=20,)
        legend_handles.append(mlines.Line2D( [], [], color="blue", marker="*", linestyle="None", markersize=15, label="Destination",))

    # --- Legend & title ---
    if legend_handles:
        ax.legend(handles=legend_handles, loc="upper right")

    if title:
        ax.set_title(title)

    ax.set_axis_off()
    plt.tight_layout()
    plt.show()

