import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from Demand import ODGeneration, paths_util
import constants

def run_beta_sweep(
    G_drive,
    residential_sampling,
    gdf_destinations,
    real_od_normalized,
    rng,
    beta_range,
    list_total_trips_per_hour,
    compute_lengths=False,
):
    results = []
    best_od_norm_matrix = None
    best_od_locality_matrix = None
    best_od_locality_pairs = None
    best_od_locality_timeline_tables = None
    min_rmse = float("inf")

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
        od = ODGeneration.aggregate_timeline_ods(od_timeline)

        eval_result = evaluate_od_against_real(
            G_drive,
            od,
            real_od_normalized,
            locality_to_region=constants.LOCALITY_TO_REGION,
            compute_lengths=compute_lengths,
        )

        rmse = eval_result["rmse"]

        if rmse < min_rmse:
            min_rmse = rmse
            best_od_norm_matrix = eval_result["od_norm"].copy()
            best_od_locality_pairs = od
            best_od_locality_timeline_tables = ODGeneration.build_region_od_tables_from_timeline(
                od_timeline,
                G_drive,
            )
            best_od_locality_matrix = ODGeneration.build_region_od_table(G_drive, od)

        results.append({
            "beta": b,
            "rmse": rmse,
            "avg_length": eval_result["avg_length"],
        })

    df_sweep = pd.DataFrame(results)
    return (
        df_sweep,
        best_od_norm_matrix,
        best_od_locality_matrix,
        best_od_locality_pairs,
        best_od_locality_timeline_tables,
        min_rmse,
    )

def calculate_random_baseline(
    G,
    real_locality_od_normalized,
    rng,
    n_trips=50_000,
    compute_lengths=False,
    min_random_dist=3000,
    locality_to_region=None,
):
    random_od_counts = ODGeneration.gen_random_OD_counter(
        G,
        rng,
        n_trips=n_trips,
        min_euclid_m=min_random_dist,
    )

    eval_result = evaluate_od_against_real(
        G,
        random_od_counts,
        real_locality_od_normalized,
        locality_to_region=locality_to_region,
        compute_lengths=compute_lengths,
    )

    print(f"Random Baseline RMSE: {eval_result['rmse']:.4f}")
    print(f"Average Random Distance in Malta: {(eval_result['avg_length'] / 1000):.2f} km")

    return (
        eval_result["rmse"],
        eval_result["avg_length"],
        eval_result["od_norm"],
        random_od_counts,
    )


def evaluate_od_against_real(
    G,
    od_counts,
    real_od_normalized,
    *,
    locality_to_region=None,
    compute_lengths=False,
):
    od_df = ODGeneration.build_region_od_table(
        G,
        od_counts,
        locality_to_region=locality_to_region,
    )

    od_norm = od_df.div(od_df.sum(axis=1), axis=0).fillna(0)

    od_norm = od_norm.reindex(
        index=real_od_normalized.index,
        columns=real_od_normalized.columns,
    ).fillna(0)

    rmse = np.sqrt(((od_norm - real_od_normalized) ** 2).values.mean())

    avg_m = 0
    if compute_lengths:
        if isinstance(od_counts, dict):
            od_for_paths = [(o, d, w) for (o, d), w in od_counts.items()]
        else:
            od_for_paths = od_counts
        avg_m = paths_util.calculate_path_metrics(G, od_for_paths, "length")

    return {
        "od_table": od_df,
        "od_norm": od_norm,
        "rmse": rmse,
        "avg_length": avg_m,
    }