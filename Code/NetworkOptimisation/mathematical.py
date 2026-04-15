"""
Mathematical optimization routines for segment-level bike reallocation.

This module runs an iterative, OD-aware optimization workflow that reallocates
road segments to improve cycling utility while limiting harm to car travel cost.
"""

from collections import defaultdict
from collections.abc import Mapping
from networkx import MultiDiGraph
import gurobipy as gp
from gurobipy import GRB
import copy
import random
from typing import Optional, Callable
 
from constants import SafetyClass, OD
from Demand import paths_util
import graph_util

def solve_batch_knapsack(seg_coef: dict, car_harm_seg, batch_size: int, harm_remaining_frac:float, C0):
    """
    Solve one batch of segment selection as a binary knapsack-style MIP.

    Objective:
        maximize sum(seg_coef[seg] * z_seg)

    Constraints:
        1) Edge budget:   sum(z_seg) <= batch_size
        2) Car-harm cap:  sum((car_harm_seg[seg] / C0) * z_seg) <= harm_remaining_frac
        3) Binary vars:   z_seg in {0, 1}

    Notes
    -----
    - Only segments with positive objective coefficient are considered as candidates.
    - `car_harm_seg` is in absolute cost units; it is normalized by `C0` in the model.
    - `harm_remaining_frac` is the remaining allowable car-harm increase as a fraction
      of baseline car cost (e.g., 0.05 = 5% of baseline).

    Parameters
    ----------
    seg_coef : dict
        Mapping {segment_id -> net utility score} for current batch.
    car_harm_seg : dict
        Mapping {segment_id -> estimated car-cost increase} in absolute units.
    batch_size : int
        Maximum number of segments that may be selected in this batch.
    harm_remaining_frac : float
        Remaining harm budget as a fraction of baseline car cost.
    C0 : float
        Baseline total car cost used to normalize harm terms.

    Returns
    -------
    list
        Selected segment IDs (the keys used in `seg_coef`).
        Returns [] if no positive candidates or no optimal solution is found.
    """

    # Filter edges with positive benefit only
    candidates = {seg: c for seg, c in seg_coef.items() if c > 0}

    if not candidates:
        return []

    m = gp.Model("edge_selection")
    
    z = {
        seg: m.addVar(vtype=GRB.BINARY, name=f"z_{seg[0]}_{seg[1]}")
        for seg in candidates
    }

    m.addConstr(
        gp.quicksum(z[seg] for seg in z) <= batch_size,
        name="budget_edges",
    )

    # 1) Build normalized harm coefficient per segment
    harm_coef_norm = {}
    for seg in z:
        harm_coef_norm[seg] = car_harm_seg[seg] / C0

    # 2) Build LHS expression: total normalized harm from selected segments
    total_harm_expr = gp.quicksum(
        harm_coef_norm[seg] * z[seg]
        for seg in z
    )

    # 3) Add the harm-budget constraint
    m.addConstr(
        total_harm_expr <= harm_remaining_frac,
        name="budget_car_harm",
    )

    m.setObjective(
        gp.quicksum(candidates[seg] * z[seg] for seg in z),
        GRB.MAXIMIZE,
    )

    m.optimize()

    if m.status != GRB.OPTIMAL:
        return []

    selected_segments = [seg for seg in z if z[seg].X > 0.5]
    return selected_segments

def solve_bike_lane_selection(G_master, OD, batch_size:int, budget_total:int, car_harm_delta, gamma:float, G_sub = None):
    """
    Iteratively reallocate road segments to improve bike utility under a car-harm cap.

    Workflow per iteration
    ----------------------
    1) Compute current bike/car shortest paths for OD demand.
    2) Compute current total car cost Ccurr and remaining harm budget:
           Cmax = (1 + car_harm_delta) * C0
           harm_remaining_frac = max(0, (Cmax - Ccurr) / C0)
    3) Build segment-level coefficients and per-segment car harm.
    4) Solve batched knapsack MIP.
    5) Apply selected segments to `G_master` via representative directed arcs.

    Stopping conditions
    -------------------
    - Total segment budget exhausted.
    - Harm budget exhausted.
    - No feasible/beneficial segment selected in a batch.

    Parameters
    ----------
    G_master : networkx.MultiDiGraph
        Main graph to optimize. Mutated in place by reallocation operations.
    OD : iterable
        Weighted OD demand as (origin_node, destination_node, weight).
    batch_size : int
        Maximum number of segments selected per batch iteration.
    budget_total : int
        Total maximum number of reallocations across all batches.
    car_harm_delta : float
        Allowed relative increase in total car cost vs baseline (e.g., 0.05 = +5%).
    gamma : float
        Tradeoff weight applied to car harm in segment utility:
            coef = bike_benefit - gamma * car_harm
    G_sub : networkx.MultiDiGraph, optional
        Candidate subgraph restricting which edges/segments are eligible.
        If None, a copy of `G_master` is used.

    Returns
    -------
    tuple
        (chosen_edges, G_master)
        - chosen_edges: list of representative directed arcs actually reallocated.
        - G_master: the updated graph (same object, modified in place).
    """
    if G_sub is None:
        G_sub = copy.deepcopy(G_master)


    remaining_budget = budget_total
    chosen_edges = []

    paths_car0 = paths_util.compute_candidate_paths(G_master, OD, "car_cost_current")
    C0 = paths_util.total_cost_from_paths(G_master, paths_car0, "car_cost_current")
    Cmax = (1.0 + car_harm_delta) * C0

    while remaining_budget > 0:
        #1) recompute paths under current network
        #TODO should this be on G_master or the respective subgraphs?
        #TODO apparently it might have to be on G_sub idk man :sob:
        paths_bike = paths_util.compute_candidate_paths(G_master, OD, path_weight_metric="bike_cost_penalty") #NOTE that we dont have an issue with bikes having unreachable locations, since bikes can travel on the car network but at a higher cost.
        paths_car  = paths_util.compute_candidate_paths(G_master, OD, path_weight_metric="car_cost_current") 

        Ccurr = paths_util.total_cost_from_paths(G_master, paths_car, "car_cost_current")
        harm_remaining = max(0.0, Cmax - Ccurr)
        if harm_remaining <= 1e-9:
            break
        #Scale harm_remaing between [0,1] as range was initially in the magnitudes and could cause numerical instability
        harm_remaining_frac = max(0.0, (Cmax - Ccurr) / C0)

        
        # 2) build edge coefficients for eligible edges only
        G_sub_reallocatable = graph_util.make_reallocatable_subgraph(G_sub)
        eligible_edges = set(G_sub_reallocatable.edges(keys=True))
        seg_to_arcs = graph_util.build_segment_arc_map(G_sub_reallocatable)

        coef_seg, bike_benefit_seg, car_harm_seg = graph_util.build_segment_coef(
            G_master,
            G_sub_reallocatable,
            eligible_edges,
            paths_bike,
            paths_car,
            gamma=gamma,
        )

        print("--------")
        print("eligible segs:", len(coef_seg))
        print("nonzero bike segs:", sum(abs(v) > 1e-12 for v in bike_benefit_seg.values()))
        print("nonzero car segs:", sum(abs(v) > 1e-12 for v in car_harm_seg.values()))
        print("coef max/min:", max(coef_seg.values()), min(coef_seg.values()))
        print("Harm Remaining:", harm_remaining)


        assert len(coef_seg) > 0
        assert max(coef_seg.values()) != 0, "All coefficients are zero"

        # 3) solve knapsack for this batch
        k = min(batch_size, remaining_budget)
        selected = solve_batch_knapsack(
            seg_coef=coef_seg,
            car_harm_seg=car_harm_seg,
            harm_remaining_frac=harm_remaining_frac,
            C0 = C0,
            batch_size=k,
        )

        if not selected:
            break

        # 4) apply to master: selected items are SEGMENTS, map them back to a valid arc
        applied = 0
        for seg in selected:
            arcs = seg_to_arcs.get(seg, [])
            if not arcs:
                continue
            rep_arc = arcs[0]
            graph_util.reallocate_edge_to_fietsstraat(G_master, rep_arc)
            chosen_edges.append(rep_arc)
            applied += 1

        if applied == 0:
            break

        remaining_budget -= applied

        
        # signed: + means worse for cars, - means better
        harm_pct_signed = 100.0 * (Ccurr - C0) / C0 if C0 > 0 else 0.0

        # "harm done" (non-negative only)
        harm_abs = max(0.0, Ccurr - C0)
        harm_pct = 100.0 * harm_abs / C0 if C0 > 0 else 0.0

        # optional: how much of your allowed cap is used
        cap_abs = max(1e-12, Cmax - C0)
        cap_used_pct = 100.0 * harm_abs / cap_abs

        print(
            f"Car harm: {harm_pct:.2f}% "
            f"(signed: {harm_pct_signed:+.2f}%), "
            f"cap used: {cap_used_pct:.2f}%"
        )
        print("--------")


    return chosen_edges, G_master


Arc = tuple
Seg = tuple


def _iter_od_triples(od_data: OD):
    if isinstance(od_data, Mapping):
        rows = ((o, d, w) for (o, d), w in od_data.items())
    else:
        rows = od_data

    for row in rows:
        try:
            row_vals = tuple(row)
            if len(row_vals) == 3:
                o, d, w = row_vals
            elif len(row_vals) == 2:
                (o, d), w = row_vals
            else:
                raise ValueError("row has invalid length")
        except Exception as exc:
            raise TypeError(
                "od_data must be Mapping[(o,d)->w], Iterable[(o,d,w)], or Iterable[((o,d),w)]."
            ) from exc
        yield int(o), int(d), float(w)


def _prepare_flow_lp_data(
    G: MultiDiGraph,
    seg_to_arcs: dict[Seg, list[Arc]],
    car_cost_attr: str,
    bike_shared_cost_attr: str,
    bike_dedicated_cost_attr: str,
) -> tuple[
    list[Arc],
    list[int],
    dict[Arc, float],
    dict[Arc, float],
    dict[Arc, float],
]:
    all_arcs: list[Arc] = []
    for arcs in seg_to_arcs.values():
        all_arcs.extend(arcs)

    nodes = list(G.nodes())
    t_c: dict[Arc, float] = {}
    t_beta: dict[Arc, float] = {}
    t_b: dict[Arc, float] = {}
    for a in all_arcs:
        u, v, k = a
        d = G[u][v][k]
        t_c[a] = d[car_cost_attr]
        t_beta[a] = d[bike_shared_cost_attr]
        t_b[a] = d[bike_dedicated_cost_attr]

    return all_arcs, nodes, t_c, t_beta, t_b


def _add_capacity_block(
    m: gp.Model,
    all_arcs: list[Arc],
    eligible_bike_arcs: set[Arc],
    car_arcs:set[Arc],
    fixed_bike_1: set[Arc],
    fixed_bike_0: set[Arc],
    seg_to_arcs: dict[Seg, list[Arc]],
    Lambda_seg: dict[Seg, float],
    alpha_bike_space: float,
) -> tuple[dict[Arc, gp.Var], dict[Arc, gp.Var]]:
    lambda_c_var: dict[Arc, gp.Var] = {}
    lambda_b_var: dict[Arc, gp.Var] = {}
    for a in all_arcs:
        u, v, k = a
        if a in car_arcs:
            lambda_c_var[a] = m.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"lc_{u}_{v}_{k}")
        else:
            # no car capacity on bike-only arcs
            lambda_c_var[a] = m.addVar(lb=0.0, ub=0.0, vtype=GRB.CONTINUOUS, name=f"lc_{u}_{v}_{k}_fixed0")

        if a in eligible_bike_arcs:
            lambda_b_var[a] = m.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"lb_{u}_{v}_{k}")
        else:
            lambda_b_var[a] = m.addVar(lb=0.0, ub=0.0, vtype=GRB.CONTINUOUS, name=f"lb_{u}_{v}_{k}_fixed0")

    for a in fixed_bike_1:
        if a in lambda_b_var:
            m.addConstr(lambda_b_var[a] == 1.0, name=f"fix_b1_{a[0]}_{a[1]}_{a[2]}")
    for a in fixed_bike_0:
        if a in lambda_b_var:
            m.addConstr(lambda_b_var[a] == 0.0, name=f"fix_b0_{a[0]}_{a[1]}_{a[2]}")

    for seg, arcs in seg_to_arcs.items():
        if seg not in Lambda_seg:
            raise KeyError(f"Missing Lambda_seg for segment {seg}")
        m.addConstr(
            gp.quicksum(lambda_c_var[a] for a in arcs) +
            alpha_bike_space * gp.quicksum(lambda_b_var[a] for a in arcs)
            <= float(Lambda_seg[seg]),
            name=f"space_{seg[0]}_{seg[1]}",
        )

    m.update()
    return lambda_c_var, lambda_b_var


def _add_flow_block(
    m: gp.Model,
    od_rows: list[tuple[int, int, float]],
    all_arcs: list[Arc],
    lambda_c_var: dict[Arc, gp.Var],
    lambda_b_var: dict[Arc, gp.Var],
    car_arcs: set[Arc],
    bike_arcs: set[Arc],
    od_allowed_arcs_car: Optional[dict[paths_util.ODKey, set[Arc]]] = None,
    od_allowed_arcs_bike: Optional[dict[paths_util.ODKey, set[Arc]]] = None,
    cap_shared_bike_flow: bool = False,
    shared_bike_cap_multiplier: float = 1e6,

) -> tuple[
    dict[tuple[int, Arc], gp.Var],  # f_c
    dict[tuple[int, Arc], gp.Var],  # f_b
    dict[tuple[int, Arc], gp.Var],  # f_beta
    dict[int, set[Arc]],            # od_car_arcs_by_idx (final used arcs)
    dict[int, set[Arc]],            # od_bike_arcs_by_idx (final used arcs)
]:
    f_c_var: dict[tuple[int, Arc], gp.Var] = {}
    f_b_var: dict[tuple[int, Arc], gp.Var] = {}
    f_beta_var: dict[tuple[int, Arc], gp.Var] = {}
    od_car_arcs_by_idx: dict[int, set[Arc]] = {}
    od_bike_arcs_by_idx: dict[int, set[Arc]] = {}

    for p, (s, t, _w) in enumerate(od_rows):
        phi = 1.0  # Wiedemann-style; keep 1.0 even for auxiliary if you want connectivity

        od_key = paths_util.make_od_key((s, t))

        if od_allowed_arcs_car is None:
            arcs_car = car_arcs
        else:
            if od_key not in od_allowed_arcs_car:
                raise KeyError(f"Missing car allowed-arcs entry for OD key {od_key}")
            arcs_car = od_allowed_arcs_car[od_key]

        if od_allowed_arcs_bike is None:
            arcs_bike = bike_arcs
        else:
            if od_key not in od_allowed_arcs_bike:
                raise KeyError(f"Missing bike allowed-arcs entry for OD key {od_key}")
            arcs_bike = od_allowed_arcs_bike[od_key]
        


        # store final supports
        od_car_arcs_by_idx[p] = arcs_car
        od_bike_arcs_by_idx[p] = arcs_bike

        # --- adjacency for conservation ---
        out_c: dict[int, list[Arc]] = defaultdict(list)
        in_c: dict[int, list[Arc]] = defaultdict(list)
        nodes_c: set[int] = {s, t}

        for a in arcs_car:
            u, v, _ = a
            out_c[u].append(a)
            in_c[v].append(a)
            nodes_c.add(u); nodes_c.add(v)

        out_b: dict[int, list[Arc]] = defaultdict(list)
        in_b: dict[int, list[Arc]] = defaultdict(list)
        nodes_b: set[int] = {s, t}

        for a in arcs_bike:
            u, v, _ = a
            out_b[u].append(a)
            in_b[v].append(a)
            nodes_b.add(u); nodes_b.add(v)

        # --- variables ---
        # car + shared bike vars on car arcs
        for a in arcs_car:
            u, v, k = a
            vc = m.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"fc_{p}_{u}_{v}_{k}")
            vbeta = m.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"fbe_{p}_{u}_{v}_{k}")
            f_c_var[(p, a)] = vc
            f_beta_var[(p, a)] = vbeta
            if cap_shared_bike_flow:
                # Optional shared-bike existence cap tied to available car space.
                m.addConstr(
                    vbeta <= float(shared_bike_cap_multiplier) * lambda_c_var[a],
                    name=f"use_shared_{p}_{u}_{v}_{k}",
                )
            # Individual path-existence: OD p may use arc a only if car space exists on a.
            m.addConstr(vc <= lambda_c_var[a], name=f"use_car_{p}_{u}_{v}_{k}")

        # dedicated bike vars on bike arcs
        for a in arcs_bike:
            u, v, k = a
            vb = m.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"fb_{p}_{u}_{v}_{k}")
            f_b_var[(p, a)] = vb
            # Individual path-existence: OD p may use arc a only if bike space exists on a.
            m.addConstr(vb <= lambda_b_var[a], name=f"use_bike_{p}_{u}_{v}_{k}")

        # --- conservation ---
        # Cars: only over nodes touched by car corridor (+ s,t)
        for i in nodes_c:
            rhs = phi if i == s else (-phi if i == t else 0.0)
            out_flow = gp.quicksum(f_c_var[(p, a)] for a in out_c.get(i, []))
            in_flow  = gp.quicksum(f_c_var[(p, a)] for a in in_c.get(i, []))
            m.addConstr(out_flow - in_flow == rhs, name=f"car_cons_{p}_{i}")

        # Bikes: conservation on (dedicated + shared)
        # dedicated on bike arcs, shared on car arcs
        nodes_both = nodes_b | nodes_c
        for i in nodes_both:
            rhs = phi if i == s else (-phi if i == t else 0.0)

            out_ded = gp.quicksum(f_b_var[(p, a)] for a in out_b.get(i, []))
            in_ded  = gp.quicksum(f_b_var[(p, a)] for a in in_b.get(i, []))

            out_sh  = gp.quicksum(f_beta_var[(p, a)] for a in out_c.get(i, []))
            in_sh   = gp.quicksum(f_beta_var[(p, a)] for a in in_c.get(i, []))

            m.addConstr((out_ded + out_sh) - (in_ded + in_sh) == rhs, name=f"bike_cons_{p}_{i}")

    m.update()
    return f_c_var, f_b_var, f_beta_var, od_car_arcs_by_idx, od_bike_arcs_by_idx


def solve_flow_lp(
    G: MultiDiGraph,
    OD: OD,
    seg_to_arcs: dict[Seg, list[Arc]],
    Lambda_seg: dict[Seg, float],
    eligible_bike_arcs: set[Arc],
    fixed_bike_1: set[Arc], #arcs fixed to have a bike lane
    fixed_bike_0: set[Arc], #arcs fixed to have no bike lane (optional)
    gamma: float,
    car_arcs,
    bike_arcs,
    *,
    bike_share: float = 0.1,
    alpha_bike_space: float = 0.5,
    # edge attribute names
    car_cost_attr: str = "car_cost_current",
    bike_shared_cost_attr: str = "bike_cost_shared",         # t_beta
    bike_dedicated_cost_attr: str = "bike_cost_dedicated",   # t_b
    # behavior toggles
    cap_shared_bike_flow: bool = False,          # typically False (Wiedemann leaves f_beta unconstrained)
    shared_bike_cap_multiplier: float = 1e6,     # if cap_shared_bike_flow=True, cap is multiplier * lambda_c[a]
    # optional size control
    od_allowed_arcs_car: Optional[dict[paths_util.ODKey, set[Arc]]] = None,
    od_allowed_arcs_bike: Optional[dict[paths_util.ODKey, set[Arc]]] = None,    # solver options
    time_limit: Optional[float] = None,
    verbose: bool = False,
    print_problem_stats: bool = False,
) -> tuple[
    dict[Arc, float],  # lambda_c
    dict[Arc, float],  # lambda_b
    dict[tuple[int, Arc], float],  # f_c (indexed by (od_idx, arc))
    dict[tuple[int, Arc], float],  # f_b
    dict[tuple[int, Arc], float],  # f_beta
    float,  # objective value
]:
    """
    Build and solve the Wiedemann-style *LP relaxation* (flow-based, lane-level).

    Variables
    ---------
    Per directed arc a:
        lambda_c[a] >= 0     (car lane-equivalent capacity)
        lambda_b[a] >= 0     (bike lane-equivalent capacity; only on eligible arcs)

    Per OD index p and arc a:
        f_c[p,a]    >= 0     car flow
        f_b[p,a]    >= 0     bike flow on dedicated lane space
        f_beta[p,a] >= 0     bike flow on shared car space (penalized)

    Constraints
    -----------
    1) Segment space (shared width) coupling:
         sum_{a in A(seg)} lambda_c[a] + alpha * sum_{a in A(seg)} lambda_b[a] <= Lambda_seg[seg]

    2) Flow conservation per OD for cars and bikes:
       Cars: standard conservation on f_c
       Bikes: conservation on (f_b + f_beta)

    3) Individual path existence (non-additive across ODs):
         f_c[p,a] <= lambda_c[a]    for each OD p and arc a
         f_b[p,a] <= lambda_b[a]    for each OD p and arc a
       f_beta is unconstrained by default (cap_shared_bike_flow=False).

    Fixing
    ------
    fixed_bike_1: lambda_b[a] == 1
    fixed_bike_0: lambda_b[a] == 0

    Optional arc restriction per OD
    -------------------------------
    od_allowed_arcs: dict[ODKey, set[Arc]]
      If provided, flow variables for that OD key are created ONLY on those arcs.
      (Capacities lambda_* are still created for all arcs in seg_to_arcs.)

    Returns
    -------
    (lambda_c, lambda_b, f_c, f_b, f_beta, obj_value)

    Notes
    -----
    - This is an LP. If you later add integrality (e.g., lambda_b in {0,1}), it becomes an MILP.
    - Be careful: multi-commodity flow size is O(|OD|*|E|). Use od_allowed_arcs in real instances.
    """

    if not (0.0 <= bike_share <= 1.0):
        raise ValueError("bike_share must be in [0, 1].")

    od_rows = list(_iter_od_triples(OD))

    all_arcs, nodes, t_c, t_beta, t_b = _prepare_flow_lp_data(
        G=G,
        seg_to_arcs=seg_to_arcs,
        car_cost_attr=car_cost_attr,
        bike_shared_cost_attr=bike_shared_cost_attr,
        bike_dedicated_cost_attr=bike_dedicated_cost_attr,
    )

    m = gp.Model("flow_lane_lp")
    m.Params.OutputFlag = 1 if verbose else 0
    if time_limit is not None:
        m.Params.TimeLimit = float(time_limit)

    #TODO
    # IMPORTANT (recommended): restrict lambda_c on non-car arcs to ub=0 inside _add_capacity_block.
    # If you haven't patched that, you can still run, but cars could theoretically use bike-only arcs.
    lambda_c_var, lambda_b_var = _add_capacity_block(
        m=m,
        all_arcs=all_arcs,
        car_arcs=car_arcs,
        eligible_bike_arcs=eligible_bike_arcs,
        fixed_bike_1=fixed_bike_1,
        fixed_bike_0=fixed_bike_0,
        seg_to_arcs=seg_to_arcs,
        Lambda_seg=Lambda_seg,
        alpha_bike_space=alpha_bike_space,
    )

    f_c_var, f_b_var, f_beta_var, od_car_arcs_by_idx, od_bike_arcs_by_idx = _add_flow_block(
        m=m,
        od_rows=od_rows,
        all_arcs=all_arcs,
        lambda_c_var=lambda_c_var,
        lambda_b_var=lambda_b_var,
        car_arcs=car_arcs,
        bike_arcs=bike_arcs,
        od_allowed_arcs_car=od_allowed_arcs_car,
        od_allowed_arcs_bike=od_allowed_arcs_bike,
        cap_shared_bike_flow=cap_shared_bike_flow,
        shared_bike_cap_multiplier=shared_bike_cap_multiplier,
    )

    if print_problem_stats:
        decision_nodes = {n for u, v, _ in eligible_bike_arcs for n in (u, v)}
        m.update()
        print(
            "[lp-stats] "
            f"decision_nodes={len(decision_nodes)} "
            f"decision_edges={len(eligible_bike_arcs)} "
            f"od_size={len(od_rows)} "
            f"num_vars={m.NumVars}"
        )

    obj = gp.LinExpr()
    for p, (_o, _d, w_total) in enumerate(od_rows):
        omega_b = float(w_total) * bike_share
        omega_c = float(w_total) * (1.0 - bike_share)

        # cars on car corridor
        for a in od_car_arcs_by_idx[p]:
            obj += omega_c * gamma * t_c[a] * f_c_var[(p, a)]

        # bikes: dedicated on bike corridor
        for a in od_bike_arcs_by_idx[p]:
            obj += omega_b * t_b[a] * f_b_var[(p, a)]

        # bikes: shared on car corridor
        for a in od_car_arcs_by_idx[p]:
            obj += omega_b * t_beta[a] * f_beta_var[(p, a)]

    m.setObjective(obj, GRB.MINIMIZE)
    m.optimize()

    if m.status == GRB.INF_OR_UNBD:
        m.Params.DualReductions = 0
        m.optimize()

    if m.status == GRB.INFEASIBLE:
        m.computeIIS()
        m.write("flow_lane_lp_debug.lp")   # full model
        m.write("flow_lane_lp_iis.ilp")    # infeasible core

        print("IIS constraints:")
        for c in m.getConstrs():
            if c.IISConstr:
                print(f"  {c.ConstrName}")

        print("IIS variable bounds:")
        for v in m.getVars():
            if v.IISLB or v.IISUB:
                print(f"  {v.VarName} LB={v.LB} UB={v.UB} IISLB={v.IISLB} IISUB={v.IISUB}")

        raise RuntimeError("solve_flow_lp infeasible (status 3). IIS written to flow_lane_lp_iis.ilp")


    if m.status not in (GRB.OPTIMAL, GRB.SUBOPTIMAL):
        raise RuntimeError(f"solve_flow_lp failed with status {m.status}")

    #NOTE these werent be used by the return so i just commented them out to save memory for now
    lambda_c = {}#{a: float(var.X) for a, var in lambda_c_var.items()}
    lambda_b = {a: float(var.X) for a, var in lambda_b_var.items()}
    f_c = {} #{(p, a): float(var.X) for (p, a), var in f_c_var.items()}
    f_b = {(p, a): float(var.X) for (p, a), var in f_b_var.items()}
    f_beta = {}#{(p, a): float(var.X) for (p, a), var in f_beta_var.items()}
    obj_val = float(m.ObjVal)
    return lambda_c, lambda_b, f_c, f_b, f_beta, obj_val


def _score_segments_for_rounding(
    G: MultiDiGraph,
    OD: OD,
    seg_to_arcs: dict[Seg, list[Arc]],
    eligible_bike_arcs: set[Arc],
    fixed_bike_1: set[Arc],
    fixed_bike_0: set[Arc],
    lambda_b: dict[Arc, float],
    f_b: dict[tuple[int, Arc], float],
    min_lambda_to_consider: float,
    bike_shared_cost_attr: str,
    bike_dedicated_cost_attr: str,
) -> tuple[dict[Arc, float], list[tuple[float, Seg, list[Arc]]]]:
    arc_score: dict[Arc, float] = {}
    for a in eligible_bike_arcs:
        if a in fixed_bike_1 or a in fixed_bike_0:
            continue
        lb = float(lambda_b.get(a, 0.0))
        if lb <= min_lambda_to_consider:
            continue

        flow_fac = 0.0
        for p in range(len(OD)):
            if (p, a) in f_b:
                flow_fac += float(f_b[(p, a)])

        u, v, k = a
        d = G[u][v][k]
        t_beta = float(d.get(bike_shared_cost_attr, d.get("bike_cost_penalty", 0.0)))
        t_b = float(d.get(bike_dedicated_cost_attr, t_beta))
        arc_score[a] = flow_fac * max(0.0, t_beta - t_b)

    seg_score: list[tuple[float, Seg, list[Arc]]] = []
    for seg, arcs in seg_to_arcs.items():
        s = 0.0
        candidate_arcs: list[Arc] = []
        for a in arcs:
            if a in arc_score:
                s += arc_score[a]
                candidate_arcs.append(a)
        if candidate_arcs and s > 0:
            seg_score.append((s, seg, candidate_arcs))

    seg_score.sort(reverse=True, key=lambda x: x[0])
    return arc_score, seg_score


def _apply_segment_fixings(
    seg_score: list[tuple[float, Seg, list[Arc]]],
    arc_score: dict[Arc, float],
    fixed_bike_1: set[Arc],
    fixed_bike_0: set[Arc],
    batch: int,
    fix_both_directions: bool,
) -> int:
    fixed_this_round = 0
    for _, _, arcs in seg_score:
        if fixed_this_round >= batch:
            break

        arcs_sorted = sorted(arcs, key=lambda a: arc_score.get(a, 0.0), reverse=True)

        if fix_both_directions:
            for a in arcs_sorted[:2]:
                if a not in fixed_bike_1 and a not in fixed_bike_0:
                    fixed_bike_1.add(a)
                    fixed_this_round += 1
                    if fixed_this_round >= batch:
                        break
        else:
            a = arcs_sorted[0]
            if a not in fixed_bike_1 and a not in fixed_bike_0:
                fixed_bike_1.add(a)
                fixed_this_round += 1

    return fixed_this_round


def _build_current_network_baseline_fixings(
    G: MultiDiGraph,
    eligible_bike_arcs: set[Arc],
    fixed_bike_1_seed: set[Arc],
    fixed_bike_0_seed: set[Arc],
) -> tuple[set[Arc], set[Arc]]:
    """
    Build fixings that represent the current as-built network:
    - arcs with existing bike infra are fixed to 1
    - all other eligible decision arcs are fixed to 0
    """
    baseline_fixed_bike_1: set[Arc] = set(fixed_bike_1_seed)
    baseline_fixed_bike_0: set[Arc] = set(fixed_bike_0_seed)


    for a in eligible_bike_arcs:
        if a in baseline_fixed_bike_1 or a in baseline_fixed_bike_0:
            continue

        u, v, k = a
        d = G[u][v][k]
        safety = (d.get("safety"))
        if safety == SafetyClass.PAINTED:
            baseline_fixed_bike_1.add(a)
        else:
            baseline_fixed_bike_0.add(a)

    baseline_fixed_bike_0 -= baseline_fixed_bike_1
    return baseline_fixed_bike_1, baseline_fixed_bike_0


def baseline_objective_value(
    G,
    OD: OD,
    seg_to_arcs: dict[Seg, list[Arc]],
    Lambda_seg: dict[Seg, float],
    eligible_bike_arcs: set[Arc],
    car_arcs,
    bike_arcs,
    *,
    gamma: float,
    bike_share: float = 0.1,
    fixed_bike_1_init: Optional[set[Arc]] = None,  #arcs fixed to have a bike lane
    fixed_bike_0_init: Optional[set[Arc]] = None,  #arcs fixed to have no bike lane (optional)
    alpha_bike_space: float = 0.5,
    od_allowed_arcs_car: Optional[dict[paths_util.ODKey, set[Arc]]] = None,
    od_allowed_arcs_bike: Optional[dict[paths_util.ODKey, set[Arc]]] = None,    # solver options    
    car_cost_attr: str = "car_cost_current",
    bike_shared_cost_attr: str = "bike_cost_shared",
    bike_dedicated_cost_attr: str = "bike_cost_dedicated",
    verbose: bool = True,
    print_problem_stats: bool = False,
):
    initial_fixed_bike_1: set[Arc] = set(fixed_bike_1_init or set())
    initial_fixed_bike_0: set[Arc] = set(fixed_bike_0_init or set())

    baseline_fixed_bike_1, baseline_fixed_bike_0 = _build_current_network_baseline_fixings(
        G=G,
        eligible_bike_arcs=eligible_bike_arcs,
        fixed_bike_1_seed=initial_fixed_bike_1,
        fixed_bike_0_seed=initial_fixed_bike_0,
    )

    _, _, _, _, _, baseline_obj = solve_flow_lp(
        G=G,
        OD=OD,
        seg_to_arcs=seg_to_arcs,
        Lambda_seg=Lambda_seg,
        eligible_bike_arcs=eligible_bike_arcs,
        fixed_bike_1=baseline_fixed_bike_1,
        fixed_bike_0=baseline_fixed_bike_0,
        gamma=gamma,
        bike_share=bike_share,
        car_arcs=car_arcs,
        bike_arcs=bike_arcs,
        alpha_bike_space=alpha_bike_space,
        od_allowed_arcs_bike=od_allowed_arcs_bike,
        od_allowed_arcs_car=od_allowed_arcs_car,
        car_cost_attr=car_cost_attr,
        bike_shared_cost_attr=bike_shared_cost_attr,
        bike_dedicated_cost_attr=bike_dedicated_cost_attr,
        verbose=False,
        print_problem_stats=print_problem_stats,
    )

    if verbose:
        print(
            f"[baseline] obj={baseline_obj:.4g} "
            f"fixed_1={len(baseline_fixed_bike_1)} "
            f"fixed_0={len(baseline_fixed_bike_0)}"
        )

    return baseline_obj


def round_lp_solution_segment_aware(
    G,
    OD: OD,
    seg_to_arcs: dict[Seg, list[Arc]],
    arc_to_seg: dict[Arc, Seg],
    Lambda_seg: dict[Seg, float],
    eligible_bike_arcs: set[Arc],
    car_arcs,
    bike_arcs,
    *,
    gamma: float,
    bike_share: float = 0.1,
    k_fix: int,
    budget_bike_lanes: int,
    fix_both_directions: bool = False,  # if True, attempt to fix both arcs in a segment
    fixed_bike_1_init: Optional[set[Arc]] = None,  #arcs fixed to have a bike lane
    fixed_bike_0_init: Optional[set[Arc]] = None,  #arcs fixed to have no bike lane (optional)
    alpha_bike_space: float = 0.5,
    od_allowed_arcs_car: Optional[dict[paths_util.ODKey, set[Arc]]] = None,
    od_allowed_arcs_bike: Optional[dict[paths_util.ODKey, set[Arc]]] = None,    # solver options    
    car_cost_attr: str = "car_cost_current",
    bike_shared_cost_attr: str = "bike_cost_shared",
    bike_dedicated_cost_attr: str = "bike_cost_dedicated",
    min_lambda_to_consider: float = 1e-6,
    max_relative_deterioration: Optional[float] = 0.0,
    verbose: bool = True,
    print_problem_stats: bool = False,
):
    initial_fixed_bike_1: set[Arc] = set(fixed_bike_1_init or set())
    initial_fixed_bike_0: set[Arc] = set(fixed_bike_0_init or set())
    fixed_bike_1: set[Arc] = set(initial_fixed_bike_1)
    fixed_bike_0: set[Arc] = set(initial_fixed_bike_0)

    history = []
    rounds = 0
   
    baseline_obj = baseline_objective_value(            
            G=G,
            OD=OD,
            seg_to_arcs=seg_to_arcs,
            Lambda_seg=Lambda_seg,
            eligible_bike_arcs=eligible_bike_arcs,
            car_arcs = car_arcs,
            bike_arcs=bike_arcs,
            gamma=gamma,
            bike_share=bike_share,
            fixed_bike_1_init=fixed_bike_1,
            fixed_bike_0_init=fixed_bike_0,
            alpha_bike_space=alpha_bike_space,
            od_allowed_arcs_bike=od_allowed_arcs_bike,
            od_allowed_arcs_car=od_allowed_arcs_car,
            car_cost_attr=car_cost_attr,
            bike_shared_cost_attr=bike_shared_cost_attr,
            bike_dedicated_cost_attr=bike_dedicated_cost_attr,
            verbose=False,
            print_problem_stats=print_problem_stats,)

    while len(fixed_bike_1) < budget_bike_lanes:
        rounds += 1

        _, lambda_b, _, f_b, _, obj = solve_flow_lp(
            G=G,
            OD=OD,
            seg_to_arcs=seg_to_arcs,
            Lambda_seg=Lambda_seg,
            eligible_bike_arcs=eligible_bike_arcs,
            fixed_bike_1=fixed_bike_1,
            fixed_bike_0=fixed_bike_0,
            gamma=gamma,
            bike_share=bike_share,
            car_arcs = car_arcs,
            bike_arcs=bike_arcs,
            alpha_bike_space=alpha_bike_space,
            od_allowed_arcs_bike=od_allowed_arcs_bike,
            od_allowed_arcs_car=od_allowed_arcs_car,
            car_cost_attr=car_cost_attr,
            bike_shared_cost_attr=bike_shared_cost_attr,
            bike_dedicated_cost_attr=bike_dedicated_cost_attr,
            verbose=False,
            print_problem_stats=print_problem_stats,
        )
        

        rel_deterioration = 0.0
        denom = abs(baseline_obj)
        if denom > 1e-12:
            rel_deterioration = (obj - baseline_obj) / denom
        else:
            rel_deterioration = float("inf") if obj > baseline_obj + 1e-12 else 0.0

        if max_relative_deterioration is not None and rel_deterioration > max_relative_deterioration:
            if verbose:
                print(
                    f"[round {rounds}] Relative deterioration {rel_deterioration:.4%} "
                    f"exceeded limit {max_relative_deterioration:.4%} vs baseline obj {baseline_obj:.4g}. Stopping."
                )
            break

        arc_score, seg_score = _score_segments_for_rounding(
            G=G,
            OD=OD,
            seg_to_arcs=seg_to_arcs,
            eligible_bike_arcs=eligible_bike_arcs,
            fixed_bike_1=fixed_bike_1,
            fixed_bike_0=fixed_bike_0,
            lambda_b=lambda_b,
            f_b=f_b,
            min_lambda_to_consider=min_lambda_to_consider,
            bike_shared_cost_attr=bike_shared_cost_attr,
            bike_dedicated_cost_attr=bike_dedicated_cost_attr,
        )

        if not seg_score:
            if verbose:
                print(f"[round {rounds}] No segments to fix. Stopping.")
            break

        remaining = budget_bike_lanes - len(fixed_bike_1)
        batch = min(k_fix, remaining)

        fixed_this_round = _apply_segment_fixings(
            seg_score=seg_score,
            arc_score=arc_score,
            fixed_bike_1=fixed_bike_1,
            fixed_bike_0=fixed_bike_0,
            batch=batch,
            fix_both_directions=fix_both_directions,
        )

        if fixed_this_round == 0:
            if verbose:
                print(f"[round {rounds}] Could not fix anything (budget/filters). Stopping.")
            break

        history.append({
            "round": rounds,
            "obj": obj,
            "baseline_obj": baseline_obj,
            "relative_deterioration": rel_deterioration,
            "fixed_total": len(fixed_bike_1),
            "fixed_this_round": fixed_this_round,
            "top_seg_score": seg_score[0][0],
        })

        if verbose:
            print(
                f"[round {rounds}] obj={obj:.4g} "
                f"(rel_det={rel_deterioration:.4%} vs baseline) "
                f"fixed={len(fixed_bike_1)}/{budget_bike_lanes} "
                f"(+{fixed_this_round}) top_seg_score={seg_score[0][0]:.4g}"
            )

    newly_fixed_bike_1 = fixed_bike_1 - initial_fixed_bike_1
    newly_fixed_bike_0 = fixed_bike_0 - initial_fixed_bike_0
    return newly_fixed_bike_1, newly_fixed_bike_0, history
