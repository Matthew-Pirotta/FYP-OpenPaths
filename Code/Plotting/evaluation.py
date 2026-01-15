import matplotlib.pyplot as plt

def plot_metrics(df):
    fig, axs = plt.subplots(3, 2, figsize=(12, 12))

    axs[0, 0].plot(df["iteration"], df["num_components"])
    axs[0, 0].set_title("Network Fragmentation")

    axs[0, 1].plot(df["iteration"], df["lcc_length"] / 1000)
    axs[0, 1].set_title("Largest Connected Component (km)")

    axs[1, 0].plot(df["iteration"], df["mean_edge_betweenness"])
    axs[1, 0].set_title("Edge Betweenness")

    axs[1, 1].plot(df["iteration"], df["mean_node_closeness"])
    axs[1, 1].set_title("Node Closeness")

    axs[2, 0].plot(df["iteration"], df["mean_directness"])
    axs[2, 0].set_title("Directness")

    axs[2, 1].plot(df["iteration"], df["coverage_area_km2"])
    axs[2, 1].set_title("Coverage")

    for ax in axs.flat:
        ax.grid(alpha=0.3)

    fig.tight_layout()
    plt.show()
