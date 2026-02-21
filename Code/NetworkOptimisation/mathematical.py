"""
Mathematical optimization routines for segment-level bike reallocation.

This module runs an iterative, OD-aware optimization workflow that reallocates
road segments to improve cycling utility while limiting harm to car travel cost.
"""

from collections import defaultdict
from networkx import MultiDiGraph
import gurobipy as gp
from gurobipy import GRB
import copy
from typing import Optional

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
ODPair = tuple[int, int, float]


def solve_flow_lp(
    G: MultiDiGraph,
    OD: list[ODPair],
    seg_to_arcs: dict[Seg, list[Arc]],
    Lambda_seg: dict[Seg, float],
    eligible_bike_arcs: set[Arc],
    fixed_bike_1: set[Arc],
    fixed_bike_0: set[Arc],
    gamma: float,
    *,
    alpha_bike_space: float = 0.5,
    # edge attribute names
    car_cost_attr: str = "car_cost_current",
    bike_shared_cost_attr: str = "bike_cost_shared",         # t_beta
    bike_dedicated_cost_attr: str = "bike_cost_dedicated",   # t_b
    # behavior toggles
    cap_shared_bike_flow: bool = False,          # typically False (Wiedemann leaves f_beta unconstrained)
    shared_bike_cap_multiplier: float = 1e6,     # if cap_shared_bike_flow=True, cap is multiplier * Lambda (big)
    # optional size control
    od_allowed_arcs: Optional[dict[int, set[Arc]]] = None,
    # solver options
    time_limit: Optional[float] = None,
    verbose: bool = False,
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

    3) Capacity:
         sum_p f_c[p,a] <= lambda_c[a]
         sum_p f_b[p,a] <= lambda_b[a]
       f_beta is unconstrained by default (cap_shared_bike_flow=False).

    Fixing
    ------
    fixed_bike_1: lambda_b[a] == 1
    fixed_bike_0: lambda_b[a] == 0

    Optional arc restriction per OD
    -------------------------------
    od_allowed_arcs: dict od_idx -> set(arcs)
      If provided, flow variables for OD od_idx are created ONLY on those arcs.
      (Capacities lambda_* are still created for all arcs in seg_to_arcs.)

    Returns
    -------
    (lambda_c, lambda_b, f_c, f_b, f_beta, obj_value)

    Notes
    -----
    - This is an LP. If you later add integrality (e.g., lambda_b in {0,1}), it becomes an MILP.
    - Be careful: multi-commodity flow size is O(|OD|*|E|). Use od_allowed_arcs in real instances.
    """

    # ----------------------------
    # Collect arcs and nodes
    # ----------------------------
    all_arcs: list[Arc] = []
    for arcs in seg_to_arcs.values():
        all_arcs.extend(arcs)

    nodes = list(G.nodes())

    # Precompute per-node outgoing/incoming arcs for conservation
    out_arcs_all: dict[int, list[Arc]] = defaultdict(list)
    in_arcs_all: dict[int, list[Arc]] = defaultdict(list)
    for (u, v, k) in all_arcs:
        out_arcs_all[u].append((u, v, k))
        in_arcs_all[v].append((u, v, k))

    # Pull cost parameters for objective (t_c, t_beta, t_b)
    t_c: dict[Arc, float] = {}
    t_beta: dict[Arc, float] = {}
    t_b: dict[Arc, float] = {}

    for a in all_arcs:
        u, v, k = a
        d = G[u][v][k]

        t_c[a] = d[car_cost_attr]
        t_beta[a] =d[bike_shared_cost_attr]
        t_b[a] = d[bike_dedicated_cost_attr]

    # ----------------------------
    # Build model
    # ----------------------------
    m = gp.Model("flow_lane_lp")
    m.Params.OutputFlag = 1 if verbose else 0

    # ----------------------------
    # Capacity decision variables
    # ----------------------------
    lambda_c_var: dict[Arc, gp.Var] = {}
    lambda_b_var: dict[Arc, gp.Var] = {}

    for a in all_arcs:
        u, v, k = a
        lambda_c_var[a] = m.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"lc_{u}_{v}_{k}")

        # bike capacity only if eligible; otherwise force to 0
        if a in eligible_bike_arcs:
            lambda_b_var[a] = m.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"lb_{u}_{v}_{k}")
        else:
            # create var but fix to 0 for uniformity (simplifies expressions)
            lambda_b_var[a] = m.addVar(lb=0.0, ub=0.0, vtype=GRB.CONTINUOUS, name=f"lb_{u}_{v}_{k}_fixed0")

    m.update()

    # ----------------------------
    # Fixing constraints
    # ----------------------------
    for a in fixed_bike_1:
        if a not in lambda_b_var:
            continue
        m.addConstr(lambda_b_var[a] == 1.0, name=f"fix_b1_{a[0]}_{a[1]}_{a[2]}")

    for a in fixed_bike_0:
        if a not in lambda_b_var:
            continue
        m.addConstr(lambda_b_var[a] == 0.0, name=f"fix_b0_{a[0]}_{a[1]}_{a[2]}")

    # ----------------------------
    # Segment space constraints (shared street width)
    # ----------------------------
    for seg, arcs in seg_to_arcs.items():
        if seg not in Lambda_seg:
            raise KeyError(f"Missing Lambda_seg for segment {seg}")

        m.addConstr(
            gp.quicksum(lambda_c_var[a] for a in arcs) +
            alpha_bike_space * gp.quicksum(lambda_b_var[a] for a in arcs)
            <= float(Lambda_seg[seg]),
            name=f"space_{seg[0]}_{seg[1]}",
        )

    # ----------------------------
    # Flow variables (multi-commodity)
    # ----------------------------
    # Index OD pairs by integer to avoid big tuple keys in gurobi names
    n_od = len(OD)

    f_c_var: dict[tuple[int, Arc], gp.Var] = {}
    f_b_var: dict[tuple[int, Arc], gp.Var] = {}
    f_beta_var: dict[tuple[int, Arc], gp.Var] = {}

    # For capacity constraints we need fast per-arc sums over OD.
    # We'll store per-arc lists of vars.
    f_c_on_arc: dict[Arc, list[gp.Var]] = defaultdict(list)
    f_b_on_arc: dict[Arc, list[gp.Var]] = defaultdict(list)
    f_beta_on_arc: dict[Arc, list[gp.Var]] = defaultdict(list)

    for p, (s, t, w) in enumerate(OD):
        # choose allowed arcs for this OD (if provided)
        if od_allowed_arcs is not None:
            arcs_p = od_allowed_arcs.get(p, set())
        else:
            arcs_p = set(all_arcs)

        # Build per-node arc lists for this OD to speed conservation
        out_p: dict[int, list[Arc]] = defaultdict(list)
        in_p: dict[int, list[Arc]] = defaultdict(list)
        for a in arcs_p:
            u, v, k = a
            out_p[u].append(a)
            in_p[v].append(a)

        # Flow vars on allowed arcs
        for a in arcs_p:
            u, v, k = a
            # Car flow
            vc = m.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"fc_{p}_{u}_{v}_{k}")
            f_c_var[(p, a)] = vc
            f_c_on_arc[a].append(vc)

            # Bike on dedicated facility
            vb = m.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"fb_{p}_{u}_{v}_{k}")
            f_b_var[(p, a)] = vb
            f_b_on_arc[a].append(vb)

            # Bike on shared car space
            vbeta = m.addVar(lb=0.0, vtype=GRB.CONTINUOUS, name=f"fbe_{p}_{u}_{v}_{k}")
            f_beta_var[(p, a)] = vbeta
            f_beta_on_arc[a].append(vbeta)

        # Conservation constraints (cars)
        # out - in = +w at source, -w at sink, 0 else
        for i in nodes:
            rhs = 0.0
            if i == s:
                rhs = float(w)
            elif i == t:
                rhs = -float(w)

            out_expr = gp.quicksum(f_c_var[(p, a)] for a in out_p.get(i, []))
            in_expr = gp.quicksum(f_c_var[(p, a)] for a in in_p.get(i, []))
            m.addConstr(out_expr - in_expr == rhs, name=f"car_cons_{p}_{i}")

        # Conservation constraints (bikes): on (f_b + f_beta)
        for i in nodes:
            rhs = 0.0
            if i == s:
                rhs = float(w)
            elif i == t:
                rhs = -float(w)

            out_expr = gp.quicksum(f_b_var[(p, a)] + f_beta_var[(p, a)] for a in out_p.get(i, []))
            in_expr = gp.quicksum(f_b_var[(p, a)] + f_beta_var[(p, a)] for a in in_p.get(i, []))
            m.addConstr(out_expr - in_expr == rhs, name=f"bike_cons_{p}_{i}")

    m.update()

    # ----------------------------
    # Capacity constraints (per arc). How much capacity the arc has for the flow 
    # ----------------------------
    for a in all_arcs:
        # Car capacity
        u,v,k = a
        if a in f_c_on_arc:
            m.addConstr(gp.quicksum(f_c_on_arc[a]) <= lambda_c_var[a], name=f"cap_car_{u}_{v}_{k}")
        else:
            # No OD uses this arc => no constraint needed
            pass

        # Bike facility capacity
        if a in f_b_on_arc:
            m.addConstr(gp.quicksum(f_b_on_arc[a]) <= lambda_b_var[a], name=f"cap_bike_{u}_{v}_{k}")
        else:
            pass

        """# Optional: cap shared biking as well (usually not in Wiedemann)
        if cap_shared_bike_flow and (a in f_beta_on_arc):
            # Big-M style cap: <= big * lambda_c_var[a] or big * Lambda(seg)
            # Here: big cap proportional to segment width if we can find it.
            seg = (min(a[0], a[1]), max(a[0], a[1]))
            big = float(Lambda_seg.get(seg, 1.0)) * float(shared_bike_cap_multiplier)
            m.addConstr(gp.quicksum(f_beta_on_arc[a]) <= big, name=f"cap_shared_{a[0]}_{a[1]}_{a[2]}")"""
        
    # ----------------------------
    # Objective
    # ----------------------------
    obj = gp.LinExpr()
    for (p, (s, t, w)) in enumerate(OD):

        # Use OD restriction if provided; else all arcs
        arcs_p = od_allowed_arcs.get(p, set()) if od_allowed_arcs is not None else set(all_arcs)

        for a in arcs_p:
            # car
            obj += w * gamma * t_c[a] * f_c_var[(p, a)]
            # bike dedicated
            obj += w * t_b[a] * f_b_var[(p, a)]
            # bike shared
            obj += w * t_beta[a] * f_beta_var[(p, a)]

    m.setObjective(obj, GRB.MINIMIZE)

    # ----------------------------
    # Solve
    # ----------------------------
    m.optimize()

    if m.status not in (GRB.OPTIMAL, GRB.SUBOPTIMAL):
        raise RuntimeError(f"solve_flow_lp failed with status {m.status}")

    # ----------------------------
    # Extract solution
    # ----------------------------
    lambda_c = {a: float(var.X) for a, var in lambda_c_var.items()}
    lambda_b = {a: float(var.X) for a, var in lambda_b_var.items()}

    f_c = {(p, a): float(var.X) for (p, a), var in f_c_var.items()}
    f_b = {(p, a): float(var.X) for (p, a), var in f_b_var.items()}
    f_beta = {(p, a): float(var.X) for (p, a), var in f_beta_var.items()}

    obj_val = float(m.ObjVal)

    return lambda_c, lambda_b, f_c, f_b, f_beta, obj_val
