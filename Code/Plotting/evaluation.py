import matplotlib.pyplot as plt


def plot_metrics(df):
    fig, axs = plt.subplots(3, 2, figsize=(12, 12))
    x = df["iteration"] if "iteration" in df.columns else range(len(df))

    def plot_pair(ax, bike_col, car_col, title, transform=None):
        if transform is None:
            transform = lambda s: s

        if bike_col in df.columns:
            ax.plot(x, transform(df[bike_col]), label="Bike", color="tab:green", linewidth=2)
        if car_col in df.columns:
            ax.plot(
                x,
                transform(df[car_col]),
                label="Car",
                color="tab:orange",
                linewidth=2,
                linestyle="--",
            )

        if bike_col in df.columns and car_col in df.columns:
            ax.legend()
        ax.set_title(title)
        ax.grid(alpha=0.3)

    plot_pair(
        axs[0, 0],
        bike_col="num_components",
        car_col="car_num_components",
        title="Network Fragmentation",
    )

    plot_pair(
        axs[0, 1],
        bike_col="lcc_length",
        car_col="car_lcc_length",
        title="Largest Connected Component (km)",
        transform=lambda s: s / 1000,
    )

    plot_pair(
        axs[1, 0],
        bike_col="mean_edge_betweenness",
        car_col="car_mean_edge_betweenness",
        title="Edge Betweenness",
    )

    plot_pair(
        axs[1, 1],
        bike_col="mean_node_closeness",
        car_col="car_mean_node_closeness",
        title="Node Closeness",
    )

    plot_pair(
        axs[2, 0],
        bike_col="mean_directness",
        car_col="car_mean_directness",
        title="Directness",
    )

    plot_pair(
        axs[2, 1],
        bike_col="coverage_area_km2",
        car_col="car_coverage_area_km2",
        title="Coverage (km^2)",
    )

    fig.tight_layout()
    plt.show()
