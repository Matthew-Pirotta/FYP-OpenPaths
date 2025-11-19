import graph_util as graph_util
import copy
import concurrent.futures
import osmnx as ox
import pandas as pd

from . import heuristic

def run_locality_task(args):
    """Worker function for a single locality."""
    name, G_sub, n_iterations, heuristic_func, EVALUATION_MOD = args
    
    print(f"🏙️ Starting {name} in process")
    G_working = copy.deepcopy(G_sub)

    evaluations = []
    edge_diffs = []
    for i in range(n_iterations):
        G_drive = graph_util.make_drive_subgraph(G_working)
        edge_to_reallocate = heuristic_func(G_drive)
        edge_diffs.append(edge_to_reallocate)
        #print(f"edge before: {G_working[u][v][k]}")
        graph_util.reallocate_edge(G_working, edge_to_reallocate)
        #print(f"edge after: {G_working[u][v][k]}" )

        if i % EVALUATION_MOD == 0:
            evaluation = heuristic.network_evaluation(G_working)
            evaluation["locality"] = name
            evaluation["iteration"] = i
            evaluation["edge_diffs"] = list(edge_diffs) # store a copy so later clears don't mutate stored evaluations
            edge_diffs.clear()
            evaluations.append(evaluation)

    #NOTE also evaluate on the last final iteration
    evaluation = heuristic.network_evaluation(G_working)
    evaluation["locality"] = name
    evaluation["iteration"] = n_iterations
    evaluation["edge_diffs"] = list(edge_diffs)
    evaluations.append(evaluation)

    return evaluations

def run_global(G_master, subgraphs, heuristic_func, EVALUATION_MOD = 10, n_iterations=10, max_workers=None, parallel=True):
    """Run heuristic on all subgraphs in parallel."""
    tasks = [(name, G_sub_master, n_iterations, heuristic_func, EVALUATION_MOD) for name, G_sub_master in subgraphs.items()]
    results = []

    if parallel:
        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor: 
            for locality_results in executor.map(run_locality_task, tasks):
                results.extend(locality_results)
    else:
        for task in tasks:
            locality_results = run_locality_task(task)
            results.extend(locality_results)

    df_results = pd.DataFrame(results)
    return df_results

if __name__ == "__main__":
    print("hello????")