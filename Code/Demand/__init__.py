"""Public exports for the Demand package."""

from . import ODSampling as ODUtil

from .ODAggregation import (
    aggregate_timeline_ods,
    build_region_od_table,
    build_region_od_tables_from_timeline,
    build_total_region_od_table,
)
from .ODConstants import DEFAULT_BETA
from .ODGeneration import (
    append_auxiliary_chain_od_pairs,
    gen_home_based_tour_counter,
    gen_OD_trips,
    gen_od_trips_timeline,
    gen_random_OD_counter,
    scale_OD_pairs,
)
from .ODSampling import (
    infer_destination_type,
    sample_destination_for_region_and_purpose,
    sample_point_in_polygon,
)
from .paths_util import (
    build_od_allowed_arcs,
    calculate_path_metrics,
    compute_candidate_paths,
    compute_edge_importance,
    total_cost_from_paths,
)
from .sumoRun import run_simulation

# Backward-compatible name used by earlier scripts/notebooks.
sample_destination_for_purpose = sample_destination_for_region_and_purpose

__all__ = [
    # Compatibility alias
    "ODUtil",
    # Constants
    "DEFAULT_BETA",
    # Sampling helpers
    "sample_point_in_polygon",
    "infer_destination_type",
    "sample_destination_for_region_and_purpose",
    "sample_destination_for_purpose",
    # Aggregation helpers
    "build_region_od_table",
    "build_region_od_tables_from_timeline",
    "build_total_region_od_table",
    "aggregate_timeline_ods",
    # OD generation helpers
    "gen_random_OD_counter",
    "gen_home_based_tour_counter",
    "gen_OD_trips",
    "gen_od_trips_timeline",
    "scale_OD_pairs",
    "append_auxiliary_chain_od_pairs",
    # Path helpers
    "total_cost_from_paths",
    "compute_candidate_paths",
    "compute_edge_importance",
    "calculate_path_metrics",
    "build_od_allowed_arcs",
    # SUMO runner
    "run_simulation",
]
