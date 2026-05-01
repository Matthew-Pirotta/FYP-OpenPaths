from dataclasses import dataclass
from typing import Literal


KeepArcPolicy = Literal["first", "random", "score"]


@dataclass(frozen=True)
class SegmentReallocationAction:
    seg_id: tuple
    keep_arc: tuple | None
    remaining_after: int | float
    bike_arcs: tuple[tuple, ...]
    lost_car_arcs: tuple[tuple, ...]
