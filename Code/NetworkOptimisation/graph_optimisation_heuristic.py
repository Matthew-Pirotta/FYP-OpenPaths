from networkx import MultiDiGraph
import graph_util as graph_util
import copy
import random
import pandas as pd
import networkx as nx 
import inspect
from tqdm.notebook import tqdm
from collections.abc import Callable
from Demand import paths_util
from dataclasses import dataclass
import constants

from . import heuristic, evaluation

def _keep_arc_policy_for_heuristic(heuristic_func):
    name = heuristic_func.__name__

    if name in {
        "heuristic_segment_betweenness_centrality",
        "heuristic_od_segment_betweenness",
    }:
        return "score"

    if name == "heuristic_random":
        return "random"

    return "first"


def _keep_arc_scores_for_heuristic(
    heuristic_func,
    car_edge_importance=None,
    edge_betweenness_scores=None,
) -> dict | None:
    """
    Scores used only to decide which car direction survives when needed.
    """
    name = heuristic_func.__name__

    if name == "heuristic_od_segment_betweenness":
        # Keep the car direction with the larger OD car importance, so the
        # marginal car harm counts the less important direction as lost.
        return car_edge_importance

    if name == "heuristic_segment_betweenness_centrality":
        return edge_betweenness_scores

    return None

@dataclass
class StopState:
    baseline_bike_cost: float | None = None
    baseline_car_cost: float | None = None
    prev_bike_cost: float | None = None
    small_gain_streak: int = 0


@dataclass
class OptimisationRun:
    G_working: MultiDiGraph
    segment_inventory: dict
    arc_to_seg: dict
    seg_to_arcs: dict
    evaluations: list
    event_log: list
    sig: inspect.Signature
    stop_state: StopState
    rng: random.Random


@dataclass
class IterationGraphs:
    G_drive: MultiDiGraph
    G_bikeable: MultiDiGraph
    G_realloc: MultiDiGraph
    G_protected: MultiDiGraph


@dataclass
class HeuristicCache:
    bike_paths: object | None = None
    car_paths: object | None = None
    od_bike_edge_importance: dict | None = None
    od_car_edge_importance: dict | None = None
    bike_edge_betweenness_scores: dict | None = None
    bike_graph_dirty: bool = True


@dataclass(frozen=True)
class SegmentChoice:
    segment: object
    action: object

def _compute_progress_metrics(ev: dict, state: StopState) -> tuple[dict, StopState]:
    """
    Add baseline-relative progress metrics to a raw evaluation dict.
    Returns the enriched evaluation and updated stop state.
    """
    print(ev)
    bike_cost = ev["full_od_total_bike_cost"]
    car_cost = ev["car_od_total_car_cost"]

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
    iteration: int,
    od,
    k_sample,
    diff_log: list,
    state: StopState,
    clear_diff: bool = False,
    dry_run: bool = False,
) -> tuple[dict, StopState]:
    """
    Build one evaluation snapshot for the current graph state.
    """
    if dry_run:
        # Return dummy data that keeps metrics safe
        ev = {
            "full_od_total_bike_cost": 0.0,
            "car_od_total_car_cost": 0.0,
            "iteration": iteration,
            "diff_log": list(diff_log),
            "stop_reason": None,
            "bike_gain_vs_baseline": 0.0,
            "car_harm_vs_baseline": 0.0
        }
        if clear_diff: diff_log.clear()
        return ev, state

    G_protected = graph_util.make_protected_subgraph(G_master)
    G_drive = graph_util.make_drive_subgraph(G_master)
    G_bike = graph_util.make_bikeable_subgraph(G_master)

    ev = evaluation.network_evaluation(
        G_protected,
        G_bike,
        G_drive,
        OD_pairs=od,
        k_sample=k_sample,
    )

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
    arc_to_seg,
    seg_to_arcs,
    bike_edge_importance=None,
    car_edge_importance=None,
    edge_betweenness_scores=None,
    candidate_actions=None,
    rng=None,
):
    """
    Dispatch to heuristic function according to its signature.
    Also forwards precomputed maps / cached score objects when supported.
    """
    kwargs = {}

    if "bike_paths" in sig.parameters:
        kwargs["bike_paths"] = bike_paths
    if "car_paths" in sig.parameters:
        kwargs["car_paths"] = car_paths
    if "beta" in sig.parameters:
        kwargs["beta"] = beta
    if "k_sample" in sig.parameters:
        kwargs["k_sample"] = k_sample

    if "arc_to_seg" in sig.parameters:
        kwargs["arc_to_seg"] = arc_to_seg
    if "seg_to_arcs" in sig.parameters:
        kwargs["seg_to_arcs"] = seg_to_arcs

    if "bike_edge_importance" in sig.parameters:
        kwargs["bike_edge_importance"] = bike_edge_importance
    if "car_edge_importance" in sig.parameters:
        kwargs["car_edge_importance"] = car_edge_importance
    if "edge_betweenness_scores" in sig.parameters:
        kwargs["edge_betweenness_scores"] = edge_betweenness_scores
    if "candidate_actions" in sig.parameters:
        kwargs["candidate_actions"] = candidate_actions
    if "rng" in sig.parameters:
        kwargs["rng"] = rng

    return heuristic_func(
        G_working,
        G_drive,
        G_bikeable,
        G_realloc,
        G_protected,
        **kwargs,
    )


def _setup_optimisation_run(
    G_master: MultiDiGraph,
    heuristic_func: Callable,
) -> OptimisationRun:
    G_working = copy.deepcopy(G_master)
    segment_inventory = graph_util.build_segment_inventory(G_working)
    arc_to_seg, seg_to_arcs = graph_util.build_arc_to_segment_map(G_working)
    graph_util.refresh_segment_reallocatable_flags(G_working, segment_inventory, seg_to_arcs)

    return OptimisationRun(
        G_working=G_working,
        segment_inventory=segment_inventory,
        arc_to_seg=arc_to_seg,
        seg_to_arcs=seg_to_arcs,
        evaluations=[],
        event_log=[],
        sig=inspect.signature(heuristic_func),
        stop_state=StopState(),
        rng=random.Random(heuristic.SEED),
    )


def _build_iteration_graphs(G_working: MultiDiGraph) -> IterationGraphs:
    G_bikeable = graph_util.make_bikeable_subgraph(G_working)
    return IterationGraphs(
        G_drive=graph_util.make_drive_subgraph(G_working),
        G_bikeable=G_bikeable,
        G_realloc=graph_util.make_reallocatable_subgraph(G_bikeable),
        G_protected=graph_util.make_protected_subgraph(G_working),
    )


def _refresh_heuristic_cache(
    cache: HeuristicCache,
    heuristic_func: Callable,
    graphs: IterationGraphs,
    od,
    iteration: int,
    EVALUATION_MOD: int,
    k_sample,
) -> HeuristicCache:
    """
    Refresh expensive path and centrality data only for heuristics that use it.
    """
    heuristic_name = heuristic_func.__name__

    if heuristic_name == "heuristic_od_segment_betweenness":
        refresh_paths = (
            cache.bike_paths is None
            or cache.car_paths is None
            or iteration % EVALUATION_MOD == 0
        )

        if refresh_paths:
            cache.bike_paths = paths_util.compute_candidate_paths(
                graphs.G_bikeable,
                od,
                path_weight_metric="bike_cost_penalty",
            )
            cache.car_paths = paths_util.compute_candidate_paths(
                graphs.G_drive,
                od,
                path_weight_metric="car_cost_current",
            )

            cache.od_bike_edge_importance = paths_util.compute_edge_importance(
                graphs.G_bikeable,
                cache.bike_paths,
                "bike_cost_penalty"
            )
            cache.od_car_edge_importance = paths_util.compute_edge_importance(
                graphs.G_drive,
                cache.car_paths,
                "car_cost_current"
            )

    if heuristic_name == "heuristic_segment_betweenness_centrality":
        refresh_paths = (
            cache.bike_edge_betweenness_scores is None
            or iteration % EVALUATION_MOD == 0
        )

        if refresh_paths:
            k_eff = None if k_sample is None else min(graphs.G_bikeable.number_of_nodes(), k_sample)

            cache.bike_edge_betweenness_scores = nx.edge_betweenness_centrality(
                graphs.G_bikeable,
                weight="bike_cost_penalty",
                normalized=True,
                k=k_eff,
                seed=heuristic.SEED,
                backend="parallel",
            )
            cache.bike_graph_dirty = False

    return cache


def _choose_segment_to_reallocate(
    run: OptimisationRun,
    cache: HeuristicCache,
    graphs: IterationGraphs,
    heuristic_func: Callable,
    k_sample,
    beta: float,
) -> SegmentChoice | None:
    """
    Build candidate segment actions, then ask the selected heuristic to choose one.
    """
    candidate_segments, _, _ = heuristic.get_candidate_segments(
        graphs.G_realloc,
        arc_to_seg=run.arc_to_seg,
        seg_to_arcs=run.seg_to_arcs,
    )

    if not candidate_segments:
        return None

    keep_arc_policy = _keep_arc_policy_for_heuristic(heuristic_func)
    keep_arc_scores = _keep_arc_scores_for_heuristic(
        heuristic_func,
        car_edge_importance=cache.od_car_edge_importance,
        edge_betweenness_scores=cache.bike_edge_betweenness_scores,
    )
    candidate_actions = graph_util.build_segment_reallocation_actions(
        run.G_working,
        candidate_segments,
        run.segment_inventory,
        run.seg_to_arcs,
        keep_arc_policy=keep_arc_policy,
        keep_arc_scores=keep_arc_scores,
        rng=run.rng,
    )

    segment_to_reallocate = _select_edge(
        heuristic_func,
        run.sig,
        run.G_working,
        graphs.G_drive,
        graphs.G_bikeable,
        graphs.G_realloc,
        graphs.G_protected,
        cache.bike_paths,
        cache.car_paths,
        beta,
        k_sample,
        run.arc_to_seg,
        run.seg_to_arcs,
        bike_edge_importance=cache.od_bike_edge_importance,
        car_edge_importance=cache.od_car_edge_importance,
        edge_betweenness_scores=cache.bike_edge_betweenness_scores,
        candidate_actions=candidate_actions,
        rng=run.rng,
    )

    if segment_to_reallocate is None:
        return None

    selected_action = candidate_actions.get(segment_to_reallocate)
    if selected_action is None:
        selected_action = graph_util.build_segment_reallocation_actions(
            run.G_working,
            [segment_to_reallocate],
            run.segment_inventory,
            run.seg_to_arcs,
            keep_arc_policy=keep_arc_policy,
            keep_arc_scores=keep_arc_scores,
            rng=run.rng,
        )[segment_to_reallocate]

    return SegmentChoice(segment=segment_to_reallocate, action=selected_action)


def _apply_segment_choice(
    run: OptimisationRun,
    choice: SegmentChoice,
    iteration: int,
) -> bool:
    """
    Apply the chosen segment change, or mark the segment blocked if it breaks drive connectivity.

    Returns whether bike-graph-dependent caches should be recomputed next iteration.
    """
    keep_arc = choice.action.keep_arc

    if graph_util.check_segment_reallocatable(
        run.G_working,
        choice.segment,
        run.segment_inventory,
        run.seg_to_arcs,
        keep_arc=keep_arc,
    ):
        created_edges = graph_util.reallocate_segment_dedicated(
            run.G_working,
            choice.segment,
            run.segment_inventory,
            run.seg_to_arcs,
            keep_arc=keep_arc,
        )

        event_type = "reallocated_segment"
        bike_graph_dirty = True
    else:
        run.segment_inventory[choice.segment]["reallocatable"] = False

        for u, v, k in run.seg_to_arcs[choice.segment]:
            run.G_working[u][v][k]["reallocatable"] = False

        graph_util.refresh_segment_reallocatable_flags(
            run.G_working,
            run.segment_inventory,
            run.seg_to_arcs,
        )

        created_edges = None
        event_type = "marked_segment_not_reallocatable"
        bike_graph_dirty = False

    run.event_log.append({
        "iteration": iteration,
        "event_type": event_type,
        "segment": choice.segment,
        "remaining_after": choice.action.remaining_after,
        "keep_arc": keep_arc,
        "bike_arcs": choice.action.bike_arcs,
        "lost_car_arcs": choice.action.lost_car_arcs,
        "created_edges": created_edges,
    })

    return bike_graph_dirty


def run_optimisation(
    G_master: MultiDiGraph,
    heuristic_func: Callable,
    od,
    heuristic_name:str,
    EVALUATION_MOD=10,
    n_iterations=10,
    k_sample=None,
    dry_run: bool = False,
):
    """Run heuristic optimisation on one main graph."""

    print(f"[start] Starting {heuristic_name}")
    run = _setup_optimisation_run(G_master, heuristic_func)
    cache = HeuristicCache()
    beta = 1.0

    ev, run.stop_state = _evaluate_current_state(
        run.G_working,
        iteration=0,
        od=od,
        k_sample=k_sample,
        diff_log=run.event_log,
        state=run.stop_state,
        clear_diff=False,
        dry_run=dry_run,
    )
    run.evaluations.append(ev)

    last_iteration = 0

    for i in tqdm(range(1, n_iterations + 1), desc=f"Iterations ({heuristic_name})", unit="iter", leave=False):
        last_iteration = i
        graphs = _build_iteration_graphs(run.G_working)

        if graphs.G_realloc.number_of_edges() == 0:
            print(f"[stop] No reallocatable segments left for {heuristic_name}, stopping early at iteration {i}")
            break

        cache = _refresh_heuristic_cache(
            cache,
            heuristic_func,
            graphs,
            od,
            i,
            EVALUATION_MOD,
            k_sample,
        )

        choice = _choose_segment_to_reallocate(
            run,
            cache,
            graphs,
            heuristic_func,
            k_sample,
            beta,
        )

        if choice is None:
            print(f"[stop] No more valid segments left to reallocate for {heuristic_name}")
            break

        cache.bike_graph_dirty = _apply_segment_choice(run, choice, i)

        if i % EVALUATION_MOD == 0:
            ev, run.stop_state = _evaluate_current_state(
                run.G_working,
                iteration=i,
                od=od,
                k_sample=k_sample,
                diff_log=run.event_log,
                state=run.stop_state,
                clear_diff=True,
                dry_run=dry_run,
            )
            stop, reason = _should_stop(ev, run.stop_state)

            if stop:
                ev["stop_reason"] = reason
                run.evaluations.append(ev)
                print(f"[stop] Stopping {heuristic_name} at iteration {i}: {reason}")
                break

            run.evaluations.append(ev)

    if run.evaluations[-1]["iteration"] != last_iteration:
        ev, run.stop_state = _evaluate_current_state(
            run.G_working,
            iteration=last_iteration,
            od=od,
            k_sample=k_sample,
            diff_log=run.event_log,
            state=run.stop_state,
            clear_diff=False,
            dry_run=dry_run,
        )
        run.evaluations.append(ev)

    evaluations_df = pd.DataFrame(run.evaluations)
    return run.G_working, evaluations_df
