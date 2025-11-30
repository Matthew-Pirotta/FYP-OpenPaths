import numpy as np
HIGHWAY_PRIORITY = [
    "service",
    "residential",
    "pedestrian",
    "tertiary",
    "secondary",
    "primary",
    "trunk",
    "track",
    "cycleway"
]

BICYCLE_PRIORITY = [
    "None",
    "permissive",
    "yes",
    "private",
    "designated",
]

CYCLEWAY_PRIORITY = [
    "None",
    "no",
    "crossing",
    "shared",
    "shared_lane",
    "lane",
    "track",
]


def select_primary_label(value, priority_order):
    """
    Select the highest-priority tag from a scalar or list-like tag.
    """
    if value is None:
        return None
    if isinstance(value, list):
        candidates = value
    else:
        candidates = [value]

    # filter out weird empties
    candidates = [str(x) for x in candidates if x not in (None, "", np.nan)]

    if not candidates:
        return None

    # choose tag with highest priority (last in list = highest priority)
    priority_map = {k: i for i, k in enumerate(priority_order)}
    return max(candidates, key=lambda x: priority_map.get(x, -1))
