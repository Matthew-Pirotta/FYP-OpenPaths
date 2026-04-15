import subprocess
import os
import sumolib
import xml.etree.ElementTree as ET


def build_network(sim_dir, simulation_name, verbose):
    # 1. NETCONVERT — Convert OSM → SUMO network
    print("Running netconvert")
    subprocess.run([
        "netconvert",
        "--osm-files", f"{simulation_name}.osm",
        "--output-file", f"{simulation_name}.net.xml",
        "--lefthand",
        "--osm.all-attributes", "true",
        "--osm.extra-attributes", "bike_cost_penalty",
        "--plain-output-prefix", f"{simulation_name}_plain",
        "--ramps.guess",
        "--junctions.join",
        "--tls.guess-signals", #TODO get traffic signals from OSM
        "--tls.discard-simple",
        "--tls.join",
    ], cwd=sim_dir, capture_output=True, check=True, text=True)


def build_taz(sim_dir, simulation_name, verbose):
    print("Running edgesInDistricts.py for cars")
    subprocess.run([
        "python",
        r"C:\Program Files (x86)\Eclipse\Sumo\tools\edgesInDistricts.py",
        "-n", f"{simulation_name}.net.xml",
        "-t", "../localities.poly.xml",
        "-o", f"car_{simulation_name}.taz.xml",
        "--vclass", "passenger",
        "-v"
    ], cwd=sim_dir, capture_output=True, check=True, text=True)

    print("Running edgesInDistricts for bikes")
    subprocess.run([
        "python",
        r"C:\Program Files (x86)\Eclipse\Sumo\tools\edgesInDistricts.py",
        "-n", f"{simulation_name}.net.xml",
        "-t", "../localities.poly.xml",
        "-o", f"bike_{simulation_name}.taz.xml",
        "--vclass", "bicycle",
        "-v"
    ],cwd=sim_dir, capture_output=True, check=True, text=True)

    bike_taz = filter_bike_taz(sim_dir, simulation_name)

#TODO i dont like this
#this is so that bikes dont spawn at the edge of bikeable networks and get stuck
def filter_bike_taz(sim_dir, simulation_name):
    net = sumolib.net.readNet(os.path.join(sim_dir, f"{simulation_name}.net.xml"))

    # identify valid edges
    valid_edges = set()

    for edge in net.getEdges():
        if not edge.allows("bicycle"):
            continue

        # --- lane-level safety ---
        lanes = edge.getLanes()
        if not all(lane.allows("bicycle") for lane in lanes):
            continue

        # --- adjacency ---
        outgoing = edge.getOutgoing()
        incoming = edge.getIncoming()

        # ❗ fix empty adjacency bug
        if not outgoing or not incoming:
            continue

        # --- ALL neighbors must allow bikes ---
        if not all(out_edge.allows("bicycle") for out_edge in outgoing):
            continue

        if not all(in_edge.allows("bicycle") for in_edge in incoming):
            continue

        valid_edges.add(edge.getID())

    # load TAZ file
    taz_file = os.path.join(sim_dir, f"bike_{simulation_name}.taz.xml")
    tree = ET.parse(taz_file)
    root = tree.getroot()

    # filter edges in each TAZ
    for taz in root.findall("taz"):
        edges = taz.get("edges").split()
        filtered = [e for e in edges if e in valid_edges]

        if filtered:
            taz.set("edges", " ".join(filtered))
        else:
            # remove empty TAZs
            root.remove(taz)

    # save new filtered file
    out_file = os.path.join(sim_dir, f"bike_{simulation_name}_filtered.taz.xml")
    tree.write(out_file)

    return out_file


def generate_trips(sim_dir, simulation_name, car_scale, bike_scale, verbose):
    #TODO NOTE edges arent identical between networks?, so seperate OD start end points need to be generated
    #Mainly due to the fact that some edges might not be accesible to bike/cars after reallocation differences
    #Although I think I could get away with sharing the same for everyone and just skip invalid routes?
    print("Running od2trips for cars")
    subprocess.run([
        "od2trips",
        "-n", f"car_{simulation_name}.taz.xml",
        "--tazrelation-files", "../od_matrix.xml",
        "--spread.uniform" ,"true", #TODO i might want this to be false? and update writeup ovs
        "--vtype", "car_junction_safe",
        "--prefix", "car_",
        "--scale", f"{car_scale}",
        "-o", "trips_cars.xml",
    ], cwd=sim_dir, capture_output=True, check=True, text=True)


    print("Running od2trips for bicycles")
    subprocess.run([
        "od2trips",
        "-n", f"bike_{simulation_name}_filtered.taz.xml",
        "--tazrelation-files", "../od_matrix.xml",
        "--vtype", "bike",
        "--prefix", "bike_",
        "--scale", f"{bike_scale}",
        "-o", "trips_bikes.xml",
    ], cwd=sim_dir, capture_output=True, check=True, text=True)


def run_router(sim_dir, simulation_name, mode, verbose):
    print(f"Running Router {mode}")

    subprocess.run([
        "duarouter",
        "-n", f"{simulation_name}.net.xml",
        "-r", f"trips_{mode}.xml",
        "--vtype-output", "vtypes_tmp.xml",
        "--additional-files", "../types.add.xml",
        "--repair", "true",
        "--repair.from", "true",
        "--repair.to", "true",
        "-o", f"routes_{mode}.rou.xml",
        "--ignore-errors"
    ], cwd=sim_dir, capture_output=True, check=True, text=True)

def run_sumo(sim_dir, verbose):
    print("Running simulation")
    subprocess.run([
        "sumo",
        "-c", "Malta.sumocfg",
    ],cwd=sim_dir, capture_output=True, check=True, text=True)


def run_simulation(simulation_name:str, car_scale:float, bike_scale:float,
                   should_build_network:bool,  force_taz_update:bool, should_gen_trips:bool, should_run_router:bool, should_execute_sim:bool, verbose:bool=False):
    # Path to the simulation folder relative to Code/
    sim_dir = os.path.join("..", "Simulations", simulation_name)
    sim_out_dir = os.path.join(sim_dir, "Output")
    print(sim_dir)

    # Create the folder if it doesn't exist
    os.makedirs(sim_dir, exist_ok=True)
    os.makedirs(sim_out_dir, exist_ok=True)
    
    if should_build_network:
        build_network(sim_dir,simulation_name, verbose)

    if force_taz_update:
        build_taz(sim_dir,simulation_name, verbose)

    if should_gen_trips:
        generate_trips(sim_dir,simulation_name,car_scale, bike_scale, verbose)
    
    if should_run_router:
        run_router(sim_dir, simulation_name, "cars", verbose)
        run_router(sim_dir, simulation_name, "bikes", verbose)

    if should_execute_sim:
        run_sumo(sim_dir, verbose)


