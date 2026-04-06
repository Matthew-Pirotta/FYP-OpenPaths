import networkx as nx
from networkx import MultiDiGraph
import constants

# region bike costs
#TODO remove all references to speed
def _compute_bike_costs_from_grade(
    length_m: float,
    grade: float,  # capped in [-0.2, 0.2]
    risk_factor: float,
    base_speed_kmh: float = 18.0,     # typical urban cycling
    min_speed_kmh: float = 6.0,       # avoid absurdly slow speeds
    max_speed_kmh: float = 35.0,      # cap downhill speed
):
    """
    Returns:
      bike_cost_base: physical travel time (seconds)
      bike_cost_penalty: perceived travel time (seconds)
    """

    # Convert fractional grade to percent for interpretability
    grade_pct = 100.0 * max(-0.2, min(0.2, grade))

    # --- Physical speed from grade ---
    # Simple, monotonic speed adjustment:
    # - uphill: speed decreases faster
    # - downhill: speed increases slower (safer/more realistic)
    if grade_pct >= 0:
        # e.g., +10% grade -> noticeable slowdown
        speed_kmh = base_speed_kmh * (1.0 / (1.0 + 0.08 * grade_pct))
    else:
        # e.g., -10% grade -> modest speedup, capped later
        speed_kmh = base_speed_kmh * (1.0 + 0.03 * (-grade_pct))

    # Clamp to keep stable and realistic
    speed_kmh = max(min_speed_kmh, min(max_speed_kmh, speed_kmh))

    # Convert to m/s
    speed_ms = speed_kmh * 1000.0 / 3600.0
    # Base physical time
    bike_cost_dedicated = length_m / speed_ms

    # --- Risk-adjusted perceived cost ---
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
        grade = d.get("grade", 1)#TODO TEMP THIS SHOULD NOT BE A GET but d[]
        risk_factor = d["risk_factor"]

        base, penalty = _compute_bike_costs_from_grade(
            length_m=length_m,
            grade=grade,
            risk_factor=risk_factor,
        )

        d["bike_cost_base"] = base
        d["bike_cost_penalty"] = penalty

# region car cost
def _compute_car_costs(length_m: float, maxspeed_kph: float, fietsstraat_speed_kmh: float = constants.FIETSSTRAAT_SPEED_KMH):
    KMH_to_MS = 1000/3600

    # baseline
    v_current = maxspeed_kph * KMH_to_MS
    car_cost_base = length_m / v_current

    """
    # after fietsstraat
    v_fietsstraat = fietsstraat_speed_kmh * KMH_to_MS
    car_cost_if_fietsstraat = length_m / v_fietsstraat
    """

    return car_cost_base #, car_cost_if_fietsstraat


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

        current = _compute_car_costs(
            length_m=d["length"],
            maxspeed_kph=d.get("speed_kph_current"),
        )

        d["car_cost_current"] = current
        #d["car_cost_if_fietsstraat"] = fietsstraat
