import graph_util as graph_util
import copy
import concurrent.futures
import osmnx as ox
import pandas as pd

from . import heuristic

def run_locality_task(args):
    """Worker function for a single locality."""
    name, G_sub, n_iterations = args

    print(f"🏙️ Starting {name} in process")
    G_working = copy.deepcopy(G_sub)

    for i in range(n_iterations):
        G_drive = graph_util.make_drive_subgraph(G_working)
        heuristic.heuristic_func(G_working, G_drive)

    evaluation = heuristic.network_evaluation(G_working)
    evaluation["locality"] = name
    return evaluation

def run_global_parallel(G_master, subgraphs, n_iterations=10, max_workers=None):
    """Run heuristic on all subgraphs in parallel."""
    tasks = [(name, G_sub_master, n_iterations) for name, G_sub_master in subgraphs.items()]
    results = []

    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor: 
        for result in executor.map(run_locality_task, tasks):
            results.append(result)
    
    """    
    for task in tasks:
        result = run_locality_task(task)
        results.append(result)
    """

    df_results = pd.DataFrame(results)
    df_results.set_index("locality", inplace=True)
    return df_results

def run_global_serial(G_master, subgraphs, n_iterations=10, max_workers=None):
    """Run heuristic on all subgraphs sequentially."""
    tasks = [(name, G_sub_master, n_iterations) for name, G_sub_master in subgraphs.items()]
    results = []
    
    for task in tasks:
        result = run_locality_task(task)
        results.append(result)

    df_results = pd.DataFrame(results)
    df_results.set_index("locality", inplace=True)
    return df_results

if __name__ == "__main__":
    print("hello????")