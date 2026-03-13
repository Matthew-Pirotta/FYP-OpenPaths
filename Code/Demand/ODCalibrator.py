import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from Demand import ODGeneration, paths_util
import constants

def run_beta_sweep(G_drive, gdf_residential, gdf_destinations,
                    real_od_normalized, rng, beta_range, n_trips=50_000, compute_lengths=False):

    results = []
    best_od_norm_matrix = None 
    best_od_locality_matrix = None
    best_od_locality_pairs= None
    min_rmse = float('inf')

    for b in beta_range:
        print(f"workong on beta {b}")
        # 1. Generate OD with the specific beta
        # Assuming your gen_OD_trips function accepts a beta parameter
        od = ODGeneration.gen_OD_trips(G_drive, gdf_residential, gdf_destinations, rng, 
                                    n_trips=n_trips, beta=b)
        
        # 2. Build and Normalize Matrix
        od_df = ODGeneration.build_region_od_table(G_drive, od, locality_to_region=constants.LOCALITY_TO_REGION)
        od_matrix_norm = od_df.div(od_df.sum(axis=1), axis=0).fillna(0)
        
        # 3. Calculate RMSE
        # Ensure indices match real_od_normalized
        od_matrix_norm = od_matrix_norm.reindex(index=real_od_normalized.index, 
                                columns=real_od_normalized.columns).fillna(0)
        rmse = np.sqrt(((od_matrix_norm - real_od_normalized) ** 2).values.mean())

        # Save the matrix that produced this RMSE
        if rmse < min_rmse:
            min_rmse = rmse
            best_od_norm_matrix = od_matrix_norm.copy()
            best_od_locality_pairs = od
            best_od_locality_matrix = ODGeneration.build_region_od_table(G_drive, od)
        
        # 4. Path Lengths (Optional toggle)
        avg_m = 0
        if compute_lengths:
            avg_m = paths_util.calculate_path_metrics(G_drive, od, "length")
        
        # Store results
        results.append({
            "beta": b,
            "rmse": rmse,
            "avg_length": avg_m
        })

    # Convert to DataFrame for easy analysis
    df_sweep = pd.DataFrame(results)
    return df_sweep, best_od_norm_matrix, best_od_locality_matrix, best_od_locality_pairs, min_rmse


def calculate_random_baseline(G, gdf_residential, gdf_destinations, real_locality_od_normalized, rng, n_trips=50_000, compute_lengths=False):

    # Create an equiprobable matrix of the same shape
    n_regions = len(real_locality_od_normalized)
    random_matrix = np.full((n_regions, n_regions), 1.0 / n_regions)

    # Convert to DataFrame to match your real_od structure
    random_df = pd.DataFrame(
        random_matrix, 
        index=real_locality_od_normalized.index, 
        columns=real_locality_od_normalized.columns
    )

    # Calculate Random RMSE
    random_rmse = np.sqrt(((random_df - real_locality_od_normalized) ** 2).values.mean())
    print(f"Random Baseline RMSE: {random_rmse:.4f}")

    # Path Lengths (Optional toggle)
    avg_m = 0
    if compute_lengths:
        # Generate Random Trips (beta=0)
        random_region_od = ODGeneration.gen_OD_trips(
            G, gdf_residential, gdf_destinations, rng, 
            n_trips=n_trips, beta=0)

        avg_m = paths_util.calculate_path_metrics(G, random_region_od, "length")

    print(f"Average Random Distance in Malta: {(avg_m/1000):.2f} km")

    return random_rmse, avg_m