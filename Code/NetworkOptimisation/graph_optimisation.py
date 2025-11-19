import graph_util as graph_util
import copy
import concurrent.futures
import osmnx as ox
import pandas as pd

from . import heuristic

def run_locality_task(args):
    """Worker function for a single locality."""
    name, G_sub, n_iterations, heuristic_func = args

    print(f"🏙️ Starting {name} in process")
    G_working = copy.deepcopy(G_sub)

    for i in range(n_iterations):
        G_drive = graph_util.make_drive_subgraph(G_working)
        edge_to_reallocate = heuristic_func(G_drive)

        #print(f"edge before: {G_working[u][v][k]}")
        graph_util.reallocate_edge(G_working, edge_to_reallocate)
        #print(f"edge after: {G_working[u][v][k]}" )

    evaluation = heuristic.network_evaluation(G_working)
    evaluation["locality"] = name
    return evaluation

def run_global_parallel(G_master, subgraphs, heuristic_func, n_iterations=10, max_workers=None, parallel=True):
    """Run heuristic on all subgraphs in parallel."""
    tasks = [(name, G_sub_master, n_iterations, heuristic_func) for name, G_sub_master in subgraphs.items()]
    results = []

    if parallel:
        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor: 
            for result in executor.map(run_locality_task, tasks):
                results.append(result)
    else:
        for task in tasks:
            result = run_locality_task(task)
            results.append(result)

    df_results = pd.DataFrame(results)
    df_results.set_index("locality", inplace=True)
    return df_results

if __name__ == "__main__":
    print("hello????")