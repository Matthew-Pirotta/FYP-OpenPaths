from typing import Literal

from networkx import MultiDiGraph

from constants import SafetyClass


def make_drive_subgraph(G: MultiDiGraph) -> MultiDiGraph:
    return _filter_edges(G, lambda d: d.get("car_allowed", False))


def make_bikeable_subgraph(G: MultiDiGraph) -> MultiDiGraph:
    return _filter_edges(G, lambda d: d.get("bike_allowed", False))


def make_reallocatable_subgraph(G: MultiDiGraph) -> MultiDiGraph:
    return _filter_edges(G, lambda d: d.get("reallocatable") is True)


def make_protected_subgraph(G: MultiDiGraph) -> MultiDiGraph:
    return _filter_edges(
        G,
        lambda d: d.get("safety") in [SafetyClass.PAINTED, SafetyClass.PROTECTED],
    )


def make_region_subgraph(G: MultiDiGraph, region: str) -> MultiDiGraph:
    """Subgraph containing all edges that intersect the given region."""
    return _filter_edges(G, lambda d: region in d.get("regions"))


def make_locality_subgraph(G: MultiDiGraph, locality) -> MultiDiGraph:
    return _filter_edges(G, lambda d: locality in d.get("localities"))


def make_highway_subgraph(
    G: MultiDiGraph,
    road_type: Literal[
        "primary",
        "residential",
        "service",
        "track",
        "tertiary",
        "secondary",
    ],
) -> MultiDiGraph:
    return _filter_edges(G, lambda d: d.get("highway") == road_type)


def _filter_edges(G: MultiDiGraph, condition) -> MultiDiGraph:
    edges = [
        (u, v, k)
        for u, v, k, d in G.edges(keys=True, data=True)
        if condition(d)
    ]
    return G.edge_subgraph(edges).copy()
