from networkx import MultiDiGraph
import graph_util as graph_util
import copy
import concurrent.futures
from concurrent.futures import ProcessPoolExecutor, as_completed
import osmnx as ox
import pandas as pd
import inspect
from tqdm.notebook import tqdm
from collections.abc import Callable
from Demand import paths_util

from . import heuristic, evaluation

def run_locality_task(args):
    """Worker function for a single locality."""
    name, G_sub, n_iterations, heuristic_func, k_sample, od,  EVALUATION_MOD = args
    
    print(f"🏙️ Starting {name} in process")
    G_working = copy.deepcopy(G_sub)

    evaluations = []
    diff_log = []
    sig = inspect.signature(heuristic_func)
    
    # helper to build & append evaluation (copies diff_log when provided)
    def append_evaluation(G_master:MultiDiGraph, iteration, clear_diff=False):
        G_protected = graph_util.make_protected_subgraph(G_master)
        G_drive = graph_util.make_drive_subgraph(G_master)

        
        #ev = evaluation.network_evaluation(G_protected, G_drive,OD_pairs=od, k_sample=k_sample,) TODO TEMP
        ev = dict()
        ev["locality"] = name
        ev["iteration"] = iteration
        ev["diff_log"] = list(diff_log)  # store snapshot
        evaluations.append(ev)
        if clear_diff:
            diff_log.clear()


    # initial evaluation on the original state (before any reallocations)
    append_evaluation(G_working, iteration=0)

    bike_paths = None
    car_paths = None

    beta = 1 #TODO TEMP
    for i in tqdm(range(1, n_iterations+1), desc=f"Iterations ({name})", unit="iter", leave = False):
        G_drive = graph_util.make_drive_subgraph(G_working)
        G_bikeable = graph_util.make_bikeable_subgraph(G_working)
        G_realloc = graph_util.make_reallocatable_subgraph(G_bikeable)
        G_protected = graph_util.make_protected_subgraph(G_working)
        #print(f"G_realloc.number_of_edges(): {G_realloc.number_of_edges()}")
        if G_realloc.number_of_edges() == 0:
            print(f"🚫 No reallocatable edges left for {name}, stopping early at iteration {i}")
            break 

        if "bike_paths" in sig.parameters and "car_paths" in sig.parameters:
            if (i % EVALUATION_MOD == 0) or (bike_paths is None) or (car_paths is None):
                bike_paths = paths_util.compute_candidate_paths( G_bikeable, od, path_weight_metric="bike_cost_penalty",)
                car_paths = paths_util.compute_candidate_paths( G_drive, od, path_weight_metric="length",)

            edge_to_reallocate = heuristic_func(G_working, G_drive, G_bikeable, G_realloc,G_protected, bike_paths, car_paths,  beta)
        elif "k_sample" in sig.parameters:
            edge_to_reallocate = heuristic_func(G_working, G_drive, G_bikeable, G_realloc,G_protected, k_sample=k_sample)
        else:
            edge_to_reallocate = heuristic_func(G_working, G_drive, G_bikeable, G_realloc,G_protected)

        if edge_to_reallocate == None:
            print("No more valid edges left to reallocate")
            break

        created_edges = graph_util.reallocate_edge_dedicated(G_working, edge_to_reallocate)
        diff_log.append({"edge": edge_to_reallocate, "created_edges": created_edges})

        if i % EVALUATION_MOD == 0:
            append_evaluation(G_working, iteration=i, clear_diff=True)

    # final evaluation on the final working graph
    append_evaluation(G_working, iteration=n_iterations, clear_diff=False)

    return G_working, evaluations

def run_global(G_master, heuristic_func:Callable, od, subgraphs = None, EVALUATION_MOD = 10, n_iterations=10, k_sample = None, max_workers=None, parallel=True):
    """Run heuristic on all subgraphs in parallel."""
    
    if not subgraphs:
        subgraphs = {"MASTER": G_master}

    tasks = [(name, G_sub_master, n_iterations, heuristic_func, k_sample, od, EVALUATION_MOD)
             for name, G_sub_master in subgraphs.items()]
    evaluations = []
    graphs = dict()

    if not parallel:
        for task in tqdm(tasks, desc="Processing localities", unit="loc"):
            new_graph, locality_results = run_locality_task(task)
            evaluations.extend(locality_results)
            graphs[heuristic_func.__name__] = new_graph

    if parallel:
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(run_locality_task, task): task[0] for task in tasks}

            with tqdm(total=len(futures), desc="Localities", unit="loc") as pbar:
                for future in as_completed(futures):
                    locality_name = futures[future]
                    try:
                        new_graph, locality_results = future.result()
                        evaluations.extend(locality_results)
                        graphs[heuristic_func.__name__] = new_graph
                    except Exception as e:
                        print(f"❌ Locality {locality_name} failed: {e}")
                    pbar.update(1)

    evaluations_df = pd.DataFrame(evaluations)
    return graphs, evaluations_df
