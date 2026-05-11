from networkx import MultiDiGraph
from contextlib import contextmanager
import osmnx as ox
import networkx as nx
import numpy as np

from . import clean_input_data, enrich_attributes, graph_structure
from NetworkOptimisation import impedance_calculator
import graph_util
import constants


@contextmanager
def _temporary_osmnx_all_oneway(all_oneway: bool | None):
        if all_oneway is None:
                yield
                return

        previous = ox.settings.all_oneway
        ox.settings.all_oneway = all_oneway
        try:
                yield
        finally:
                ox.settings.all_oneway = previous


def __create_master_graph(G_bike, G_drive, truncate_largest_component: bool = True,) -> MultiDiGraph:
        """Combine bike and drive networks into one multimodal master graph."""
        print("creating master graph network...")
        #NOTE attributes from G_bike take precedent
        G_master = nx.compose(G_drive, G_bike)

        if truncate_largest_component:
            G_master = ox.truncate.largest_component(G_master, strongly=True) # NOTE we kept all the disconnected networks in the subgraphs but the master network will only contain the lcc, since we cant add roads and only change they will never be reachable

        # initialize all master edges explicitly
        for u, v, k in G_master.edges(keys=True):
            G_master[u][v][k]["bike_allowed"] = False
            G_master[u][v][k]["car_allowed"] = False

        # mark drive edges
        for u, v, k in G_drive.edges(keys=True):
            if G_master.has_edge(u, v, k):
                G_master[u][v][k]["car_allowed"] = True

        # mark bike edges
        for u, v, k in G_bike.edges(keys=True):
            if G_master.has_edge(u, v, k):
                G_master[u][v][k]["bike_allowed"] = True

        return G_master

def load_network(
        location,
        simplify,
        all_oneway: bool | None = None,
        truncate_largest_component: bool = True,
) -> MultiDiGraph:
        print(f"Loading OSM networks for {location}...")
        with _temporary_osmnx_all_oneway(all_oneway):
                G_bike = ox.graph_from_place(location, network_type="bike", simplify=simplify, retain_all=False)
                G_drive = ox.graph_from_place(location, network_type="drive", simplify=simplify, retain_all=False)
        if truncate_largest_component:
                G_drive = ox.truncate.largest_component(G_drive, strongly=True)
        
        G_master = __create_master_graph(G_bike, G_drive, truncate_largest_component)
        
        return G_master


def load_optimisation_network(location, simplify: bool = True) -> MultiDiGraph:
    """Load the graph variant used by the optimiser."""
    return load_network(
        location,
        simplify=simplify,
        all_oneway=False,
        truncate_largest_component=True,
    )


def load_sumo_network(location, simplify: bool = False) -> MultiDiGraph:
    """Load the unsimplified all-oneway graph variant required for SUMO XML."""
    return load_network(
        location,
        simplify=simplify,
        all_oneway=True,
        truncate_largest_component=False,
    )


def save_sumo_osm_xml(G: MultiDiGraph, filepath, **kwargs):
    """
    Save a SUMO-facing OSM XML file with the OSMnx all_oneway setting isolated.

    OSMnx checks the current global setting while saving, so keep it scoped here
    as well as when loading the SUMO graph.
    """
    with _temporary_osmnx_all_oneway(True):
        ox.save_graph_xml(G, filepath, **kwargs)


def audit_elevation_and_grade(G, label=""):
    import numpy as np
    from collections import Counter

    missing_nodes = [
        n for n, d in G.nodes(data=True)
        if d.get("elevation") is None or (isinstance(d.get("elevation"), (int, float)) and np.isnan(d.get("elevation")))
    ]

    bad_edges = []
    for u, v, k, d in G.edges(keys=True, data=True):
        if d.get("grade") is None or (isinstance(d.get("grade"), (int, float)) and np.isnan(d.get("grade"))):
            bad_edges.append((u, v, k, G.nodes[u].get("elevation"), G.nodes[v].get("elevation"), d.get("length")))

    grade_counts = Counter()
    for _, _, _, d in G.edges(keys=True, data=True):
        g = d.get("grade")
        if not isinstance(g, (int, float)):
            grade_counts[g] += 1

    print(f"\n--- AUDIT: {label} ---")
    print("nodes:", G.number_of_nodes(), "edges:", G.number_of_edges())
    print("missing elevation nodes:", len(missing_nodes))
    print("grade None/NaN edges:", len(bad_edges))
    print("non-numeric grade counts:", grade_counts.most_common(5))
    if bad_edges:
        print("sample bad edges:", bad_edges[:10])


#TODO finalise the structure
def clean_simplified_graph(G:MultiDiGraph, place_name):
    """Merges semantically equivalent road tags and collapses road tag lists into just the most prominent one. Also projects the graph to have length in meters"""

    #NOTE that manual projection does not need to be done for length as the add_edge_lengths function is called automatically by the graph graph_from_x functions

    # --------------------
    G = clean_input_data.add_elevation_data(G)
    G = clean_input_data.impute_missing_elevation(G)

    clean_input_data.merge_semantically_equivalent_road_tags(G)
    clean_input_data.collapse_road_tag_lists(G)
    clean_input_data.standardise_edge_atr(G)

    # simplify topology (may change geometries), then recompute accurate lengths
    #graph_structure.simplify_multidigraph_in_place(G)

    clean_input_data.ensure_bidirectional_bike(G)

    
    G = ox.project_graph(G) 

    G = clean_input_data.add_grades(G)

    enrich_attributes.bike_safety_classification(G)
    impedance_calculator.update_bike_costs(G)
    impedance_calculator.update_car_costs(G)
    enrich_attributes.tag_reallocatable_edges(G, verbose=True)
    gdf_regions_proj, gdf_local_proj = enrich_attributes.load_and_clean_localities(G, place_name, constants.LOCALITY_TO_REGION)
    #NOTE imp to project before assigning regions due to using x and y co-ordinates
    G = enrich_attributes.assign_spatial_context(G, gdf_regions_proj, gdf_local_proj)

    return G, gdf_regions_proj, gdf_local_proj


def clean_unsimplified_graph(G:MultiDiGraph):
    clean_input_data.remove_self_loops(G)
    G = clean_input_data.set_roundabouts_oneway(G)
    clean_input_data.ensure_edge_geometries(G)

    return G