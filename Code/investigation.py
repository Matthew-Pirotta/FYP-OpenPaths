from collections import defaultdict, Counter
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import numpy as np
import osmnx as ox

def analyze_parallel_edges(G):
    # Count number of parallel edges for each directed (u, v) pair
    pair_counts: dict[tuple, int] = {}
    for u in G.adj:
        for v in G.adj[u]:
            pair_counts[(u, v)] = len(G[u][v])  # number of keys (parallel edges)

    # Set per-edge attribute 'parallel_count' so we can color by it
    for u, v, k, d in G.edges(keys=True, data=True):
        d["parallel_count"] = pair_counts[(u, v)]

    # Summary stats
    counts = list(pair_counts.values())
    num_pairs = len(counts)
    num_parallel_pairs = sum(c > 1 for c in counts)
    max_parallel = max(counts) if counts else 0
    total_extra_edges = sum(c - 1 for c in counts if c > 1)

    print(f"Directed node pairs: {num_pairs}")
    print(f"Pairs with parallel edges (>1): {num_parallel_pairs}")
    print(f"Total extra edges beyond single-edge pairs: {total_extra_edges}")
    print(f"Max parallel edges on a single pair: {max_parallel}")

    # Top examples
    top = sorted(pair_counts.items(), key=lambda kv: kv[1], reverse=True)[:10]
    print("\nTop pairs by parallel edges:")
    for (u, v), c in top:
        print(f"  ({u} -> {v}): {c}")

    # Optional: distribution of parallel counts
    dist = Counter(counts)
    print("\nDistribution (parallel_count -> number of (u,v) pairs):")
    for c in sorted(dist):
        print(f"  {c}: {dist[c]}")

    return pair_counts


def compare_parallel_edges(G):
    """Compare parallel edges (same u→v) by 'highway' and 'cycleway' attributes."""
    comparison_counts = Counter()

    for u, v in G.edges():
        data_list = list(G[u][v].values())
        if len(data_list) > 1:
            # Extract the relevant attributes
            highways = [d.get("highway") for d in data_list]
            cycleways = [d.get("cycleway") for d in data_list]

            # Determine if attributes differ
            highway_diff = len(set(highways)) > 1
            cycleway_diff = len(set(cycleways)) > 1

            if highway_diff and cycleway_diff:
                print(data_list)
                comparison_counts["different_highway_and_cycleway"] += 1
            elif highway_diff:
                comparison_counts["different_highway_only"] += 1
            elif cycleway_diff:
                comparison_counts["different_cycleway_only"] += 1
            else:
                comparison_counts["same_highway_and_cycleway"] += 1

    print("Parallel edge attribute comparison:")
    for k, v in comparison_counts.items():
        print(f"  {k:30s}: {v}")

    return comparison_counts

def plot_parallel_edges(G):
    # Colors by parallel_count (single edges=1, higher=hotter)
    vals = [d.get("parallel_count", 1) for _, _, _, d in G.edges(keys=True, data=True)]
    vmin, vmax = 1, max(vals) if vals else 1
    norm = plt.Normalize(vmin=vmin, vmax=vmax)
    cmap = cm.get_cmap("plasma")
    edge_colors = [cmap(norm(v)) for v in vals]

    fig, ax = ox.plot.plot_graph(
        G, node_size=0, edge_color=edge_colors, edge_linewidth=0.6, show=False, close=False
    )
    sm = cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = plt.colorbar(sm, ax=ax, shrink=0.8, pad=0.02)
    cbar.set_label("Parallel edges per directed pair", rotation=270, labelpad=20)
    plt.title("Parallel Edges (Same Direction)")
    plt.show()


def print_osmid():
    networkname = ["bike", "drive", "master"]
    networks = [self.G_bike,G_drive, G_master]

    for network, networkname in zip(networks, networkname):
        i = 0
        print(f"In network {networkname}")
        for _,_,data in network.edges(data=True):
            osmid = data.get("osmid", -1)
            
            if osmid == -1:
                i += 1
                #print(f"Node {node} does not have an osmid")
        print(i)

def print_node_data():
    node = 9068823240
    print(my_graph.G_master.nodes[node])
    print(my_graph.G_master.nodes[node].get("elevation"))
    neighs = my_graph.G_master.neighbors(node)

    print("\nneighbours")
    for neigh in neighs:
        print(neigh, my_graph.G_master.nodes[neigh])


def print_missing_edges():
    # count edges missing 'geometry' (or with geometry == None)
    G = my_graph.G_master
    missing = [(u, v, k) for u, v, k, d in G.edges(keys=True, data=True) if d.get("geometry") is None]
    print("Edges without geometry:", len(missing), "/", G.number_of_edges(), f"({100*len(missing)/G.number_of_edges():.2f}%)")
    # show up to 10 examples
    print("Examples:", missing[:10])

def print_single_edge():
    edges = list(G_master.edges(keys=True, data=True))
    u, v, k, data = edges[0]
    print(u, v, k)
    print(data)