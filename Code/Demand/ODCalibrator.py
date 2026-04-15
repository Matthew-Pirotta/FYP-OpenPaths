import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from Demand import ODGeneration, paths_util, ODAggregation, ODConstants, SpatialPrep
import constants

def run_beta_sweep(
    G_drive,
    residential_sampling,
    gdf_destinations,
    rng,
    beta_range,
    list_total_trips_per_hour,
):
    results = []
    best_od_norm_matrix = None
    best_od_locality_matrix = None
    best_od_locality_pairs = None
    best_od_locality_timeline_tables = None
    best_avg_m = None
    min_abs_avg_m_error = float("inf")

    for b in beta_range:
        print(f"working on beta {b}")

        od_timeline = ODGeneration.gen_od_trips_timeline(
            list_total_trips_per_hour,
            G_drive,
            residential_sampling,
            gdf_destinations,
            rng,
            beta=b,
        )
        od = ODAggregation.aggregate_timeline_ods(od_timeline)

        print(od)

        eval_result = evaluate_od_against_real(
            G_drive,
            od,
            locality_to_region=constants.LOCALITY_TO_REGION,
        )


        if eval_result["abs_avg_m_error"] < min_abs_avg_m_error:
            min_abs_avg_m_error = eval_result["abs_avg_m_error"]
            best_avg_m = eval_result["avg_length"]
            best_od_norm_matrix = eval_result["od_norm"].copy()
            best_od_locality_pairs = od
            best_od_locality_timeline_tables = ODAggregation.build_region_od_tables_from_timeline(
                od_timeline,
                G_drive,
            )
            best_od_locality_matrix = ODAggregation.build_region_od_table(G_drive, od)

        results.append({
            "beta": b,
            "avg_length": eval_result["avg_length"],
            "abs_avg_m_error": eval_result["abs_avg_m_error"],
        })

    df_sweep = pd.DataFrame(results)
    return (
        df_sweep,
        best_od_norm_matrix,
        best_od_locality_matrix,
        best_od_locality_pairs,
        best_od_locality_timeline_tables,
        min_abs_avg_m_error,
        best_avg_m,
    )

def calculate_random_baseline(
    G,
    rng,
    n_trips=50_000,
    min_random_dist=3000,
    locality_to_region=None,
):
    random_od_counts = ODGeneration.gen_random_OD_counter(
        G,
        rng,
        n_trips=n_trips,
        min_euclid_m=min_random_dist,
    )

    print(random_od_counts)
    print(type(random_od_counts))

    eval_result = evaluate_od_against_real(
        G,
        random_od_counts,
        locality_to_region=locality_to_region,
    )

    print(f"Average Random Distance in Malta: {(eval_result['avg_length'] / 1000):.2f} km")

    return (
        eval_result["avg_length"],
        eval_result["abs_avg_m_error"],
        eval_result["od_norm"],
        random_od_counts,
    )


def evaluate_od_against_real(
    G,
    od_counts,
    *,
    locality_to_region=None,
):
    od_df = ODAggregation.build_region_od_table(
        G,
        od_counts,
        locality_to_region=locality_to_region,
    )

    od_norm = od_df.div(od_df.sum(axis=1), axis=0).fillna(0)

    avg_m = paths_util.calculate_path_metrics(G, od_counts, "length")

    abs_avg_m_error = abs(ODConstants.TARGET_AVG_DISTANCE - avg_m)

    return {
        "od_table": od_df,
        "od_norm": od_norm,
        "avg_length": avg_m,
        "abs_avg_m_error": abs_avg_m_error,
    }
