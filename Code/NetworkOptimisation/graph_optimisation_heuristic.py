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
from dataclasses import dataclass
import constants

from . import heuristic, evaluation

@dataclass
class StopState:
    baseline_bike_cost: float | None = None
    baseline_car_cost: float | None = None
    prev_bike_cost: float | None = None
    small_gain_streak: int = 0

def _compute_progress_metrics(ev: dict, state: StopState) -> tuple[dict, StopState]:
    """
    Add baseline-relative progress metrics to a raw evaluation dict.
    Returns the enriched evaluation and updated stop state.
    """
    bike_cost = ev["bike_od_total_cost"]
    car_cost = ev["car_od_total_cost"]

    # First evaluation initializes baselines
    if state.baseline_bike_cost is None:
        state.baseline_bike_cost = bike_cost
        state.baseline_car_cost = car_cost
        state.prev_bike_cost = bike_cost

        ev["bike_gain_vs_baseline"] = 0.0
        ev["car_harm_vs_baseline"] = 0.0
        return ev, state

    baseline_bike = state.baseline_bike_cost
    baseline_car = state.baseline_car_cost
    prev_bike = state.prev_bike_cost

    bike_gain_vs_prev = (
        (prev_bike - bike_cost) / baseline_bike
        if baseline_bike and baseline_bike > 0 else 0.0
    )

    bike_gain_vs_baseline = (
        (baseline_bike - bike_cost) / baseline_bike
        if baseline_bike and baseline_bike > 0 else 0.0
    )

    car_harm_vs_baseline = (
        (car_cost - baseline_car) / baseline_car
        if baseline_car and baseline_car > 0 else 0.0
    )

    if bike_gain_vs_prev < constants.MIN_BIKE_GAIN:
        state.small_gain_streak += 1
    else:
        state.small_gain_streak = 0

    state.prev_bike_cost = bike_cost

    # Store only stable derived metrics
    ev["bike_gain_vs_baseline"] = float(bike_gain_vs_baseline)
    ev["car_harm_vs_baseline"] = float(car_harm_vs_baseline)

    return ev, state

def _should_stop(ev: dict, state: StopState) -> tuple[bool, str | None]:
    """
    Stopping logic based on enriched evaluation + controller state.
    """
    car_harm = ev.get("car_harm_vs_baseline", 0.0)

    if car_harm > constants.MAX_CAR_HARM:
        return True, "car_budget_exceeded"

    if state.small_gain_streak >= constants.PATIENCE:
        return True, "bike_benefit_flattened"

    return False, None

def _evaluate_current_state(
    G_master: MultiDiGraph,
    *,
    name: str,
    iteration: int,
    od,
    k_sample,
    diff_log: list,
    state: StopState,
    clear_diff: bool = False,
) -> tuple[dict, StopState]:
    """
    Build one evaluation snapshot for the current graph state.
    """
    G_protected = graph_util.make_protected_subgraph(G_master)
    G_drive = graph_util.make_drive_subgraph(G_master)

    ev = evaluation.network_evaluation(
        G_protected,
        G_drive,
        OD_pairs=od,
        k_sample=k_sample,
    )

    ev["locality"] = name
    ev["iteration"] = iteration
    ev["diff_log"] = list(diff_log)
    ev["stop_reason"] = None

    ev, state = _compute_progress_metrics(ev, state)

    if clear_diff:
        diff_log.clear()

    return ev, state

def _select_edge(
    heuristic_func,
    sig,
    G_working,
    G_drive,
    G_bikeable,
    G_realloc,
    G_protected,
    bike_paths,
    car_paths,
    beta,
    k_sample,
):
    """
    Dispatch to heuristic function according to its signature.
    """
    if "bike_paths" in sig.parameters and "car_paths" in sig.parameters:
        return heuristic_func(
            G_working, G_drive, G_bikeable, G_realloc, G_protected,
            bike_paths, car_paths, beta
        )
    if "k_sample" in sig.parameters:
        return heuristic_func(
            G_working, G_drive, G_bikeable, G_realloc, G_protected,
            k_sample=k_sample
        )
    return heuristic_func(
        G_working, G_drive, G_bikeable, G_realloc, G_protected
    )

def run_locality_task(args):
    name, G_sub, n_iterations, heuristic_func, k_sample, od, EVALUATION_MOD = args

    print(f"🏙️ Starting {name} in process")
    G_working = copy.deepcopy(G_sub)

    evaluations = []
    diff_log = []
    sig = inspect.signature(heuristic_func)

    state = StopState()

    bike_paths = None
    car_paths = None
    beta = 1.0

    # Initial evaluation
    ev, state = _evaluate_current_state(
        G_working,
        name=name,
        iteration=0,
        od=od,
        k_sample=k_sample,
        diff_log=diff_log,
        state=state,
        clear_diff=False,
    )
    evaluations.append(ev)

    last_iteration = 0

    for i in tqdm(range(1, n_iterations + 1), desc=f"Iterations ({name})", unit="iter", leave=False):
        last_iteration = i

        G_drive = graph_util.make_drive_subgraph(G_working)
        G_bikeable = graph_util.make_bikeable_subgraph(G_working)
        G_realloc = graph_util.make_reallocatable_subgraph(G_bikeable)
        G_protected = graph_util.make_protected_subgraph(G_working)

        if G_realloc.number_of_edges() == 0:
            print(f"🚫 No reallocatable edges left for {name}, stopping early at iteration {i}")
            break

        if "bike_paths" in sig.parameters and "car_paths" in sig.parameters:
            if (i % EVALUATION_MOD == 0) or (bike_paths is None) or (car_paths is None):
                bike_paths = paths_util.compute_candidate_paths(
                    G_bikeable,
                    od,
                    path_weight_metric="bike_cost_penalty",
                )
                car_paths = paths_util.compute_candidate_paths(
                    G_drive,
                    od,
                    path_weight_metric="length",
                )

        edge_to_reallocate = _select_edge(
            heuristic_func,
            sig,
            G_working,
            G_drive,
            G_bikeable,
            G_realloc,
            G_protected,
            bike_paths,
            car_paths,
            beta,
            k_sample,
        )

        if edge_to_reallocate is None:
            print(f"🚫 No more valid edges left to reallocate for {name}")
            break

        if graph_util.check_edge_reallocateability(G_drive, edge_to_reallocate):
            created_edges = graph_util.reallocate_edge_dedicated(G_working, edge_to_reallocate)
            diff_log.append({
                "edge": edge_to_reallocate,
                "created_edges": created_edges,
            })
        else:
            u, v, k = edge_to_reallocate
            G_working[u][v][k]["reallocateable"] = False
            print(f"edge {edge_to_reallocate} is not reallocatable")

        if i % EVALUATION_MOD == 0:
            ev, state = _evaluate_current_state(
                G_working,
                name=name,
                iteration=i,
                od=od,
                k_sample=k_sample,
                diff_log=diff_log,
                state=state,
                clear_diff=True,
            )
            stop, reason = _should_stop(ev, state)

            if stop:
                ev["stop_reason"] = reason
                evaluations.append(ev)
                print(f"🛑 Stopping {name} at iteration {i}: {reason}")
                break

            evaluations.append(ev)

    # Final evaluation only if we do not already have one for the final state
    if evaluations[-1]["iteration"] != last_iteration:
        ev, state = _evaluate_current_state(
            G_working,
            name=name,
            iteration=last_iteration,
            od=od,
            k_sample=k_sample,
            diff_log=diff_log,
            state=state,
            clear_diff=False,
        )
        evaluations.append(ev)

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
