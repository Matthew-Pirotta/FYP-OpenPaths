import networkx as nx
from networkx import MultiDiGraph
import constants

# region bike costs
def _compute_bike_costs_from_grade(
    length_m: float,
    grade: float,  # capped in [-0.2, 0.2]
    risk_factor: float,
):
    """
    Returns:
      bike_cost_base: length adjusted for grade
      bike_cost_penalty: perceived length adjusted for grade and risk
    """

    # Convert fractional grade to percent for interpretability
    grade_pct = 100.0 * max(-0.2, min(0.2, grade))

    if grade_pct >= 0:
        grade_factor = 1.0 + 0.08 * grade_pct
    else:
        grade_factor = 1.0 / (1.0 + 0.03 * (-grade_pct))

    bike_cost_dedicated = length_m * grade_factor
    bike_cost_shared = bike_cost_dedicated * risk_factor

    return bike_cost_dedicated, bike_cost_shared

def update_bike_costs(
    G: MultiDiGraph,
    edges: list[tuple] | None = None,
):
    """
    Recompute bike costs for all edges or a specified subset.

    Parameters
    ----------
    G : MultiDiGraph
    edges : list of (u, v, k), optional
        If None, recompute for all edges.
        If provided, recompute only for these edges.
    """
    if edges is None:
        edges = list(G.edges(keys=True))

    for u, v, k in edges:
        d = G[u][v][k]
        length_m = d["length"]
        grade = d.get("grade", 1)
        risk_factor = d["risk_factor"]

        base, penalty = _compute_bike_costs_from_grade(
            length_m=length_m,
            grade=grade,
            risk_factor=risk_factor,
        )

        d["bike_cost_base"] = base
        d["bike_cost_penalty"] = penalty

# region car cost
def _compute_car_costs(length_m):

    """
    # after fietsstraat
    v_fietsstraat = fietsstraat_speed_kmh * KMH_to_MS
    car_cost_if_fietsstraat = length_m / v_fietsstraat
    """

    return length_m


def update_car_costs(
    G: MultiDiGraph,
    edges: list[tuple] | None = None,
):
    """
    Recompute car costs for all edges or a specified subset.

    Parameters
    ----------
    G : MultiDiGraph
    edges : list of (u, v, k), optional
        If None, recompute for all edges.
        If provided, recompute only for these edges.
    """
    if edges is None:
        edges = list(G.edges(keys=True))

    for u, v, k in edges:
        d = G[u][v][k]

        current = _compute_car_costs(length_m=d["length"],)

        d["car_cost_current"] = current