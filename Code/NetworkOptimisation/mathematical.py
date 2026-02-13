from collections import defaultdict
from networkx import MultiDiGraph
import gurobipy as gp
from gurobipy import GRB
import copy


from Demand import paths_util
import graph_util

def solve_batch_knapsack(seg_coef: dict, car_harm_seg, batch_size: int, harm_remaining_frac:float, C0):
    """
    Solve a batch knapsack problem:
        max sum coef[e] * z_e
        s.t. sum z_e <= batch_size
             z_e ∈ {0,1}
                      
    Stops when reaching a harm limit to the car network relative to the base network.

    Parameters
    ----------
    seg_coef : dict[(u,v,k) -> float]
        Objective coefficient per edge.
    batch_size : int
        Maximum number of edges to select this iteration.

    Returns
    -------
    list[(u,v,k)]
        Selected edges.
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
        G_sub: Subgraph to be optimised, If NONE then whole G_master will be Optimised
        car_harm_delta: how much percent is the car network allowed to get. e.g. 0.05. The car netork can get 5% worse
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
            graph_util.reallocate_edge(G_master, rep_arc)
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