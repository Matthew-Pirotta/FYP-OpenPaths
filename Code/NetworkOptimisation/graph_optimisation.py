from networkx import MultiDiGraph
import graph_util as graph_util
import copy
import concurrent.futures
import osmnx as ox
import pandas as pd
import inspect
from tqdm.notebook import tqdm


from . import heuristic

def run_locality_task(args):
    """Worker function for a single locality."""
    name, G_sub, n_iterations, heuristic_func, k_sample, EVALUATION_MOD = args
    
    print(f"🏙️ Starting {name} in process")
    G_working = copy.deepcopy(G_sub)

    evaluations = []
    diff_log = []
    sig = inspect.signature(heuristic_func)
    
    # helper to build & append evaluation (copies diff_log when provided)
    def append_evaluation(G_master:MultiDiGraph, iteration, clear_diff=False):
        G_protected = graph_util.make_protected_subgraph(G_master)
        G_drive = graph_util.make_drive_subgraph(G_master)

        ev = heuristic.network_evaluation(G_protected, G_drive, k_sample=k_sample)
        ev["locality"] = name
        ev["iteration"] = iteration
        ev["diff_log"] = list(diff_log)  # store snapshot
        evaluations.append(ev)
        if clear_diff:
            diff_log.clear()


    # initial evaluation on the original state (before any reallocations)
    append_evaluation(G_working, iteration=0)

    for i in tqdm(range(1, n_iterations+1), desc=f"Iterations ({name})", unit="iter", leave = False):
        G_drive = graph_util.make_drive_subgraph(G_working)
        G_bikeable = graph_util.make_bikeable_subgraph(G_working)
        G_realloc = graph_util.make_reallocatable_subgraph(G_bikeable)
        G_protected = graph_util.make_protected_subgraph(G_working)
        #print(f"G_realloc.number_of_edges(): {G_realloc.number_of_edges()}")
        if G_realloc.number_of_edges() == 0:
            print(f"🚫 No reallocatable edges left for {name}, stopping early at iteration {i}")
            break 

        if "k_sample" in sig.parameters:
            edge_to_reallocate = heuristic_func(G_working, G_drive, G_bikeable, G_realloc,G_protected, k_sample=k_sample)
        else:
            edge_to_reallocate = heuristic_func(G_working, G_drive, G_bikeable, G_realloc,G_protected)

        if edge_to_reallocate == None:
            print("No more valid edges left to reallocate")
            break

        reallocated_edges = graph_util.reallocate_edge(G_working, edge_to_reallocate)
        for reallocated_edge in reallocated_edges:
            diff_log.append({"edge":reallocated_edge})

        if i % EVALUATION_MOD == 0:
            append_evaluation(G_working, iteration=i, clear_diff=True)

    # final evaluation on the final working graph
    append_evaluation(G_working, iteration=n_iterations, clear_diff=False)

    return evaluations

def run_global(G_master, heuristic_func, subgraphs = None, EVALUATION_MOD = 10, n_iterations=10, k_sample = None, max_workers=None, parallel=True):
    """Run heuristic on all subgraphs in parallel."""
    
    if not subgraphs:
        subgraphs = {"MASTER": G_master}

    tasks = [(name, G_sub_master, n_iterations, heuristic_func, k_sample, EVALUATION_MOD)
             for name, G_sub_master in subgraphs.items()]
    results = []

    if not parallel:
        for task in tqdm(tasks, desc="Processing localities", unit="loc"):
            locality_results = run_locality_task(task)
            results.extend(locality_results)
        return pd.DataFrame(results)


    if parallel:
        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(run_locality_task, task): task[0] for task in tasks}

            with tqdm(total=len(futures), desc="Localities", unit="loc") as pbar:
                for future in concurrent.futures.as_completed(futures):
                    locality_name = futures[future]
                    try:
                        locality_results = future.result()
                        results.extend(locality_results)
                    except Exception as e:
                        print(f"❌ Locality {locality_name} failed: {e}")
                    pbar.update(1)

    df_results = pd.DataFrame(results)
    return df_results

if __name__ == "__main__":
    print("hello????")