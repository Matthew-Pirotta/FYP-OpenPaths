from collections import Counter

from networkx import MultiDiGraph


def summarise_road_type_stats(G):
    categories = {
        "highway": "Highway type counts",
        "bicycle": "Bikeway classification type counts",
        "cycleway": "Cycleway type counts",
        "tunnel": "Tunnel counts",
        "junction": "Juntion type counts",
        "turns": "turn type counts",
        "oneway": "Oneway or twoway",
    }

    stats = {key: Counter() for key in categories}

    for _, _, data in G.edges(data=True):
        for key in categories:
            stats[key][data.get(key)] += 1

    for key, label in categories.items():
        print(f"{label}:")
        for val, count in stats[key].most_common():
            print(f"{val}: {count}")
        print("-" * 10)


def set_edge_attribute(
    G: MultiDiGraph,
    edge: tuple,
    attribute_name: str,
    value,
) -> MultiDiGraph:
    u, v, k = edge
    data = G[u][v][k]
    data[attribute_name] = value
    return G
