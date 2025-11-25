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
    #TODO evaluate before first reallocation
    for i in tqdm(range(n_iterations), desc=f"Iterations ({name})", unit="iter", leave = False):
        G_drive = graph_util.make_drive_subgraph(G_working)
        G_bikeable = graph_util.make_bikeable_subgraph(G_working)
        G_realloc = graph_util.make_reallocatable_subgraph(G_bikeable)
        #print(f"G_realloc.number_of_edges(): {G_realloc.number_of_edges()}")
        if G_realloc.number_of_edges() == 0:
            print(f"🚫 No reallocatable edges left for {name}, stopping early at iteration {i}")
            break 

        if "k_sample" in sig.parameters:
            edge_to_reallocate = heuristic_func(G_working, G_drive, G_bikeable, G_realloc, k_sample=k_sample)
        else:
            edge_to_reallocate = heuristic_func(G_working, G_drive, G_bikeable, G_realloc,)
        can_reallocate = graph_util.check_edge_reallocateability(G_drive, edge_to_reallocate)

        if can_reallocate:
            diff_log.append({"type":"realloc", "edge":edge_to_reallocate})
            #print(f"edge before: {G_working[u][v][k]}")
            graph_util.reallocate_edge(G_working, edge_to_reallocate)
            #print(f"edge after: {G_working[u][v][k]}" )
        else:
            u,v,k = edge_to_reallocate
            G_working[u][v][k]["reallocatable"] = False
            diff_log.append({"type":"fixed", "edge": edge_to_reallocate})

        if i % EVALUATION_MOD == 0:
            #TODO this should be the pure protected network
            evaluation = heuristic.network_evaluation(G_bikeable, k_sample=k_sample)
            evaluation["locality"] = name
            evaluation["iteration"] = i
            evaluation["diff_log"] = list(diff_log) # store a copy so later clears don't mutate stored evaluations
            diff_log.clear()
            evaluations.append(evaluation)

    #NOTE also evaluate on the last final iteration
    evaluation = heuristic.network_evaluation(G_working, k_sample=k_sample)
    evaluation["locality"] = name
    evaluation["iteration"] = n_iterations
    evaluation["diff_log"] = list(diff_log)
    evaluations.append(evaluation)

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