from matplotlib.ticker import FuncFormatter
from matplotlib.ticker import MultipleLocator
import matplotlib.pyplot as plt
import numpy as np
from Plotting import renderer
from Plotting.renderer import  PlotSettings


thousand_formatter = FuncFormatter(lambda x, pos: f"{int(x/1000)}k")
hour_formatter = FuncFormatter(lambda x, pos: f"{int(x/3600)}")
hour_locator = MultipleLocator(3600)


def plot_simulation_results(summary_df, tripinfo_df, edgedata_df,):


    # -----------------------------
    # 1 & 2. NETWORK SPEED PLOTS (side-by-side)
    # -----------------------------
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Mean speed
    axes[0].plot(summary_df["time"], summary_df["meanSpeed"] * 3.6)
    axes[0].set_xlabel("Time (hr)")
    axes[0].set_ylabel("Mean Speed (km/hr)")
    axes[0].set_title("Network Mean Speed Over Time")
    axes[0].xaxis.set_major_formatter(hour_formatter)
    axes[0].xaxis.set_major_locator(hour_locator)
    axes[0].grid(True)

    # Relative mean speed
    if summary_df["meanSpeedRelative"].notna().any():
        axes[1].plot(summary_df["time"], summary_df["meanSpeedRelative"])
        axes[1].set_xlabel("Time (hr)")
        axes[1].set_ylabel("Mean Speed Relative")
        axes[1].set_title("Network Mean Speed Relative Over Time")
        axes[1].xaxis.set_major_formatter(hour_formatter)
        axes[1].xaxis.set_major_locator(hour_locator)
        axes[1].grid(True)
    else:
        axes[1].set_visible(False)

    plt.tight_layout()
    plt.show()

    # -----------------------------
    # 3. VEHICLES RUNNING OVER TIME
    # -----------------------------
    plt.figure()
    plt.plot(summary_df["time"], summary_df["running"])
    plt.xlabel("Time (hr)")
    plt.ylabel("Vehicles in Network")
    plt.title("Vehicles Currently in Simulation Over Time")
    ax = plt.gca()
    ax.yaxis.set_major_formatter(thousand_formatter)
    ax.xaxis.set_major_formatter(hour_formatter)
    ax.xaxis.set_major_locator(hour_locator)
    plt.grid()
    plt.show()

    # -----------------------------
    # 4. CUMULATIVE VEHICLES INSERTED
    # -----------------------------
    plt.figure()
    plt.plot(summary_df["time"], summary_df["inserted"])
    plt.xlabel("Time (hr)")
    plt.ylabel("Cumulative Vehicles")
    plt.title("Cumulative Vehicles Inserted Over Time")
    ax = plt.gca()
    ax.yaxis.set_major_formatter(thousand_formatter)
    ax.xaxis.set_major_formatter(hour_formatter)
    ax.xaxis.set_major_locator(hour_locator)
    plt.grid()
    plt.show()

    # -----------------------------
    # 5. VEHICLES ARRIVED OVER TIME
    # -----------------------------
    plt.figure()
    plt.plot(summary_df["time"], summary_df["arrived"])
    plt.xlabel("Time (hr)")
    plt.ylabel("Arrived Vehicles")
    plt.title("Vehicles Arrived Over Time")
    ax = plt.gca()
    ax.yaxis.set_major_formatter(thousand_formatter)
    ax.xaxis.set_major_formatter(hour_formatter)
    ax.xaxis.set_major_locator(hour_locator)
    plt.grid()
    plt.show()

    # -----------------------------
    # 6. HALTING VEHICLES OVER TIME
    # -----------------------------
    plt.figure()
    plt.plot(summary_df["time"], summary_df["halting"])
    plt.xlabel("Time (hr)")
    plt.ylabel("Halting Vehicles")
    plt.title("Halting Vehicles Over Time")
    ax = plt.gca()
    ax.yaxis.set_major_formatter(thousand_formatter)
    ax.xaxis.set_major_formatter(hour_formatter)
    ax.xaxis.set_major_locator(hour_locator)
    plt.grid()
    plt.show()

    # -----------------------------
    # 7. TRAVEL TIME DISTRIBUTION
    # -----------------------------
    plt.figure()
    tripinfo_df["duration"].hist(bins=30)
    plt.xlabel("Travel Time (hr)")
    plt.ylabel("Vehicles")
    plt.title("Travel Time Distribution")
    ax = plt.gca()
    ax.xaxis.set_major_formatter(hour_formatter)
    ax.xaxis.set_major_locator(hour_locator)
    plt.show()

    # -----------------------------
    # 8. EDGE SPEED DISTRIBUTION
    # -----------------------------
    plt.figure()
    (edgedata_df["speed"] * 3.6).hist(bins=40)
    plt.xlabel("Edge Speed (km/hr)")
    plt.ylabel("Frequency")
    plt.title("Distribution of Edge Speeds")
    plt.show()


def plot_sumo_edges(net, metric_dict=None, title="SUMO Plot", cmap=plt.cm.managua_r, colorbar_label="Value", **kwargs:PlotSettings):
    # Merge defaults with overrides
    settings = renderer.DEFAULTS | kwargs

    fig, ax = plt.subplots(figsize=settings.get("fig_size", (12, 12)))

    fig.patch.set_facecolor(settings["bgcolor"])
    ax.set_facecolor(settings["bgcolor"])

    linewidth = settings["edge_linewidth"]
    alpha = settings.get("alpha", 1.0)

    # --- normalization (only if metric provided) ---
    if metric_dict is not None:
        values = np.array([v for v in metric_dict.values() if not np.isnan(v)])
        norm = plt.Normalize(vmin=values.min(), vmax=values.max())

    # --- plotting ---
    for edge in net.getEdges():
        shape = edge.getShape()
        xs = [p[0] for p in shape]
        ys = [p[1] for p in shape]

        if metric_dict is None:
            color = settings["edge_color"]
        else:
            val = metric_dict.get(edge.getID(), np.nan)
            color = settings["edge_color"] if np.isnan(val) else cmap(norm(val))

        ax.plot(xs, ys, color=color, linewidth=linewidth, alpha=alpha)

    # --- styling ---
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(title)

    # --- colorbar ---
    if metric_dict is not None:
        sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
        sm.set_array([])
        cbar = fig.colorbar(sm, ax=ax, fraction=0.03, pad=0.01)
        cbar.set_label(colorbar_label)

    plt.show()