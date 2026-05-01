import copy
import random

from networkx import MultiDiGraph
import networkx as nx

from constants import SafetyClass
from NetworkOptimisation import impedance_calculator
from PreProcessing import enrich_attributes

from .segments import refresh_segment_reallocatable_flags
from .subgraphs import make_drive_subgraph
from .types import KeepArcPolicy, SegmentReallocationAction


def _segment_is_oneway(
    G: MultiDiGraph,
    seg_id,
    seg_to_arcs: dict,
) -> bool:
    arcs = seg_to_arcs[seg_id]

    for u, v, k in arcs:
        if not G.has_edge(u, v, k):
            continue
        d = G[u][v][k]
        if d.get("highway") == "cycleway":
            continue
        return d.get("oneway", True)

    return True


def get_segment_drive_arcs(
    G: MultiDiGraph,
    seg_id,
    seg_to_arcs: dict,
) -> list[tuple]:
    """
    Return one representative non-cycleway drive arc per direction.

    Segment actions operate on directions, not duplicate parallel edge keys.
    """
    drive_arcs = []
    seen_dirs = set()

    for u, v, k in seg_to_arcs[seg_id]:
        if not G.has_edge(u, v, k):
            continue
        d = G[u][v][k]
        if d.get("highway") == "cycleway":
            continue

        direction = (u, v)
        if direction in seen_dirs:
            continue

        seen_dirs.add(direction)
        drive_arcs.append((u, v, k))

    return drive_arcs


def get_segment_remaining_after_reallocation(
    segment_inventory: dict,
    seg_id,
) -> int | float:
    return max(0, segment_inventory[seg_id]["lanes_remaining"] - 1)


def segment_needs_keep_arc(
    G: MultiDiGraph,
    seg_id,
    segment_inventory: dict,
    seg_to_arcs: dict,
) -> bool:
    return (
        not _segment_is_oneway(G, seg_id, seg_to_arcs)
        and get_segment_remaining_after_reallocation(segment_inventory, seg_id) == 1
        and bool(get_segment_drive_arcs(G, seg_id, seg_to_arcs))
    )


def choose_keep_arc_for_policy(
    seg_id,
    seg_to_arcs: dict,
    G: MultiDiGraph,
    policy: KeepArcPolicy = "first",
    arc_scores: dict | None = None,
    rng=None,
) -> tuple | None:
    """Choose the car direction to keep for a two-way segment reduced to one lane."""
    if _segment_is_oneway(G, seg_id, seg_to_arcs):
        return None

    unique_arcs = sorted(
        get_segment_drive_arcs(G, seg_id, seg_to_arcs),
        key=lambda arc: (arc[0], arc[1], arc[2]),
    )

    if not unique_arcs:
        return None
    if len(unique_arcs) == 1:
        return unique_arcs[0]

    if policy == "first":
        return unique_arcs[0]

    if policy == "random":
        random_source = rng if rng is not None else random
        return random_source.choice(unique_arcs)

    if policy == "score":
        arc_scores = arc_scores or {}
        best_score = max(arc_scores.get(arc, float("-inf")) for arc in unique_arcs)
        for arc in unique_arcs:
            if arc_scores.get(arc, float("-inf")) == best_score:
                return arc

    raise ValueError(f"Unknown keep-arc policy: {policy}")


def get_segment_lost_car_arcs_for_reallocation(
    G: MultiDiGraph,
    seg_id,
    segment_inventory: dict,
    seg_to_arcs: dict,
    keep_arc: tuple | None = None,
) -> list[tuple]:
    """
    Return the car arcs/directions disabled by the next reallocation action.

    This evaluates the consequence of the supplied action; it does not choose
    random-vs-score-vs-first behavior itself.
    """
    total = segment_inventory[seg_id]["lanes_remaining"]
    if total <= 0:
        return []

    remaining_after = get_segment_remaining_after_reallocation(segment_inventory, seg_id)
    current_car_arcs = [
        arc
        for arc in get_segment_drive_arcs(G, seg_id, seg_to_arcs)
        if G[arc[0]][arc[1]][arc[2]].get("car_allowed", False)
    ]

    if not current_car_arcs:
        return []

    if _segment_is_oneway(G, seg_id, seg_to_arcs):
        return current_car_arcs if remaining_after <= 0 else []

    if remaining_after >= 2:
        return []

    if remaining_after == 1:
        if keep_arc is None:
            raise ValueError(
                f"keep_arc is required to estimate lost car arcs for two-way segment {seg_id}"
            )
        keep_dir = keep_arc[:2]
        return [arc for arc in current_car_arcs if arc[:2] != keep_dir]

    return current_car_arcs


def get_segment_bike_arcs_for_reallocation(
    G: MultiDiGraph,
    seg_id,
    seg_to_arcs: dict,
) -> list[tuple]:
    """Return the drive directions that would receive a new dedicated bike edge."""
    bike_arcs = []
    for u, v, k in get_segment_drive_arcs(G, seg_id, seg_to_arcs):
        if not _has_dedicated_bike_edge(G, u, v):
            bike_arcs.append((u, v, k))
    return bike_arcs


def get_segment_reallocation_action(
    G: MultiDiGraph,
    seg_id,
    segment_inventory: dict,
    seg_to_arcs: dict,
    keep_arc: tuple | None = None,
) -> SegmentReallocationAction:
    """Describe the marginal effect of reallocating this segment once, now."""
    return SegmentReallocationAction(
        seg_id=seg_id,
        keep_arc=keep_arc,
        remaining_after=get_segment_remaining_after_reallocation(segment_inventory, seg_id),
        bike_arcs=tuple(get_segment_bike_arcs_for_reallocation(G, seg_id, seg_to_arcs)),
        lost_car_arcs=tuple(
            get_segment_lost_car_arcs_for_reallocation(
                G,
                seg_id,
                segment_inventory,
                seg_to_arcs,
                keep_arc=keep_arc,
            )
        ),
    )


def build_segment_reallocation_actions(
    G: MultiDiGraph,
    candidate_segments,
    segment_inventory: dict,
    seg_to_arcs: dict,
    keep_arc_policy: KeepArcPolicy = "first",
    keep_arc_scores: dict | None = None,
    rng=None,
) -> dict:
    """Build marginal reallocation actions for candidates using an explicit policy."""
    actions = {}

    for seg_id in sorted(candidate_segments, key=repr):
        keep_arc = None
        if segment_needs_keep_arc(G, seg_id, segment_inventory, seg_to_arcs):
            keep_arc = choose_keep_arc_for_policy(
                seg_id,
                seg_to_arcs,
                G,
                policy=keep_arc_policy,
                arc_scores=keep_arc_scores,
                rng=rng,
            )

        actions[seg_id] = get_segment_reallocation_action(
            G,
            seg_id,
            segment_inventory,
            seg_to_arcs,
            keep_arc=keep_arc,
        )

    return actions


def check_segment_reallocatable(
    G: MultiDiGraph,
    seg_id,
    segment_inventory: dict,
    seg_to_arcs: dict,
    keep_arc: tuple | None = None,
) -> bool:
    G_test = copy.deepcopy(G)

    total = segment_inventory[seg_id]["lanes_remaining"]
    if total <= 0 or not segment_inventory[seg_id].get("reallocatable", True):
        return False

    remaining_total = get_segment_remaining_after_reallocation(segment_inventory, seg_id)
    is_oneway = _segment_is_oneway(G_test, seg_id, seg_to_arcs)

    if (not is_oneway) and remaining_total == 1 and keep_arc is None:
        keep_arc = choose_first_keep_arc_for_segment(seg_id, seg_to_arcs, G_test)

    _apply_segment_capacity_to_arcs(
        G_test,
        seg_id,
        seg_to_arcs=seg_to_arcs,
        remaining_total=remaining_total,
        keep_arc=keep_arc,
    )

    G_drive_test = make_drive_subgraph(G_test)
    return G_drive_test.number_of_edges() > 0 and nx.is_strongly_connected(G_drive_test)


def _create_bike_edge(G, u, v, base_data):
    """Create a new bike-only edge parallel to (u, v)."""
    new_data = copy.deepcopy(base_data)

    new_data["car_allowed"] = False
    new_data["bike_allowed"] = True
    new_data["highway"] = "cycleway"
    new_data["bicycle"] = "designated"
    new_data["infra_type"] = "dedicated_bike_lane"
    new_data["bike_lanes"] = new_data.get("bike_lanes", 0) + 1
    new_data["safety"] = SafetyClass.PROTECTED
    new_data["risk_factor"] = float(
        enrich_attributes.safety_to_risk_factor_map[SafetyClass.PROTECTED]
    )
    new_data["reallocatable"] = False

    new_key = G.add_edge(u, v, **new_data)
    impedance_calculator.update_bike_costs(G, [(u, v, new_key)])

    return (u, v, new_key)


def _has_dedicated_bike_edge(G, u, v):
    if not G.has_edge(u, v):
        return False

    for _, d in G[u][v].items():
        if d.get("highway") == "cycleway":
            return True
    return False


def reallocate_segment_dedicated(
    G: MultiDiGraph,
    seg_id,
    segment_inventory: dict,
    seg_to_arcs: dict,
    keep_arc: tuple | None = None,
) -> list[tuple]:
    """
    Reallocate one authoritative car lane from a segment.

    If the segment becomes one-lane two-way, keep_arc determines which direction
    survives for cars.
    """
    created_edges = []
    arcs = seg_to_arcs[seg_id]

    new_total = get_segment_remaining_after_reallocation(segment_inventory, seg_id)
    segment_inventory[seg_id]["lanes_remaining"] = new_total

    _apply_segment_capacity_to_arcs(
        G,
        seg_id,
        seg_to_arcs=seg_to_arcs,
        remaining_total=new_total,
        keep_arc=keep_arc,
    )

    for u, v, k in arcs:
        d = G[u][v][k]
        if d.get("highway") == "cycleway":
            continue

        d["bike_allowed"] = False
        if not _has_dedicated_bike_edge(G, u, v):
            created_edges.append(_create_bike_edge(G, u, v, d))

    refresh_segment_reallocatable_flags(G, segment_inventory, seg_to_arcs)
    return created_edges


def _apply_segment_capacity_to_arcs(
    G: MultiDiGraph,
    seg_id,
    seg_to_arcs: dict,
    remaining_total: int | float,
    keep_arc: tuple | None = None,
):
    unique_arcs = get_segment_drive_arcs(G, seg_id, seg_to_arcs)

    if not unique_arcs:
        return

    is_oneway = _segment_is_oneway(G, seg_id, seg_to_arcs)

    if is_oneway:
        for u, v, k in unique_arcs:
            G[u][v][k]["car_lanes"] = max(remaining_total, 0)
            G[u][v][k]["car_allowed"] = remaining_total > 0
            G[u][v][k]["reallocatable"] = remaining_total > 0
        return

    if remaining_total >= 2:
        for u, v, k in unique_arcs:
            G[u][v][k]["car_lanes"] = remaining_total
            G[u][v][k]["car_allowed"] = True
            G[u][v][k]["reallocatable"] = True
        return

    if remaining_total == 1:
        if keep_arc is None:
            raise ValueError(
                f"keep_arc is required when two-way segment {seg_id} is reduced to one remaining car lane"
            )

        keep_dir = keep_arc[:2]
        for u, v, k in unique_arcs:
            keep = (u, v) == keep_dir
            G[u][v][k]["car_lanes"] = 1 if keep else 0
            G[u][v][k]["car_allowed"] = keep
            G[u][v][k]["reallocatable"] = keep
        return

    for u, v, k in unique_arcs:
        G[u][v][k]["car_lanes"] = 0
        G[u][v][k]["car_allowed"] = False
        G[u][v][k]["reallocatable"] = False


def choose_keep_arc_for_segment(
    seg_id,
    seg_to_arcs: dict,
    arc_scores: dict,
    G: MultiDiGraph,
) -> tuple | None:
    """For a two-way segment with one car lane, choose which direction to keep."""
    return choose_keep_arc_for_policy(
        seg_id,
        seg_to_arcs,
        G,
        policy="score",
        arc_scores=arc_scores,
    )


def choose_first_keep_arc_for_segment(
    seg_id,
    seg_to_arcs: dict,
    G: MultiDiGraph,
) -> tuple | None:
    """Deterministically keep the first available drive arc."""
    return choose_keep_arc_for_policy(
        seg_id,
        seg_to_arcs,
        G,
        policy="first",
    )
