import xml.etree.ElementTree as ET
from collections.abc import Mapping
from pathlib import Path

import pandas as pd


from matplotlib.ticker import ScalarFormatter

import matplotlib.pyplot as plt


def load_perceived_bike_trip_lengths(route_file, vehicle_type="bike"):
    """Load the perceived cost written by duarouter for every bicycle route.

    This expects ``duarouter --write-costs true`` and assumes the custom edge
    weight is the full perceived-equivalent edge length in metres (rather than
    a dimensionless multiplier). The resulting mean is therefore normalized
    per routed bicycle trip.
    """
    tree = ET.parse(route_file)
    root = tree.getroot()

    # Support both inline routes and vehicles that reference a top-level route.
    route_definitions = {
        route.attrib["id"]: route
        for route in root.findall("route")
        if "id" in route.attrib
    }

    rows = []
    missing_cost_ids = []

    for vehicle in root.findall("vehicle"):
        if vehicle_type is not None and vehicle.attrib.get("type") != vehicle_type:
            continue

        route = vehicle.find("route")

        if route is None:
            route_distribution = vehicle.find("routeDistribution")
            if route_distribution is not None:
                route = route_distribution.find("route")

        if route is None and "route" in vehicle.attrib:
            route = route_definitions.get(vehicle.attrib["route"])

        cost = None if route is None else route.attrib.get("cost")
        if cost is None:
            missing_cost_ids.append(vehicle.attrib.get("id", "<unknown>"))
            continue

        try:
            perceived_length_m = float(cost)
        except ValueError as exc:
            vehicle_id = vehicle.attrib.get("id", "<unknown>")
            raise ValueError(
                f"Invalid route cost {cost!r} for vehicle {vehicle_id!r}"
            ) from exc

        rows.append({
            "id": vehicle.attrib.get("id"),
            "type": vehicle.attrib.get("type"),
            "depart": pd.to_numeric(vehicle.attrib.get("depart"), errors="coerce"),
            "perceived_length_m": perceived_length_m,
            "perceived_length_km": perceived_length_m / 1000,
        })

    if missing_cost_ids:
        example_ids = ", ".join(missing_cost_ids[:5])
        raise ValueError(
            f"{len(missing_cost_ids)} bicycle routes have no cost attribute "
            f"(for example: {example_ids}). Run duarouter with "
            "--write-costs true before calculating perceived trip length."
        )

    if not rows:
        raise ValueError(
            f"No vehicles of type {vehicle_type!r} with route costs were found "
            f"in {route_file}"
        )

    return pd.DataFrame(rows)

def mean_perceived_bike_trip_length(route_file, vehicle_type="bike"):
    """Return mean perceived-equivalent bicycle trip length in metres."""
    trips = load_perceived_bike_trip_lengths(route_file, vehicle_type)
    return trips["perceived_length_m"].mean()

def load_aggregated_meandata(file, mode=None):
    tree = ET.parse(file)
    root = tree.getroot()

    rows = []

    for interval in root.findall("interval"):
        edge = interval.find("edge")
        if edge is None:
            continue

        row = {
            "begin": float(interval.attrib["begin"]),
            "end": float(interval.attrib["end"]),
            "time": float(interval.attrib["begin"]),
        }

        row.update(edge.attrib)

        if mode is not None:
            row["mode"] = mode

        rows.append(row)

    df = pd.DataFrame(rows)

    for col in df.columns:
        if col not in {"id", "mode"}:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["time_hr"] = df["time"] / 3600
    df["speed_kmh"] = df["speed"] * 3.6

    return df

# -----------------------------
# 1. LOAD SUMMARY.XML
# -----------------------------
def load_summary(file):
    tree = ET.parse(file)
    root = tree.getroot()

    rows = []
    for step in root.findall("step"):
        rows.append({
            "time": float(step.attrib["time"]),
            "running": int(step.attrib["running"]),
            "arrived": int(step.attrib.get("arrived", 0)),
            "meanSpeed": float(step.attrib["meanSpeed"]),
            "meanSpeedRelative": float(step.attrib.get("meanSpeedRelative", "nan")),
            "halting": int(step.attrib.get("halting", 0)),
            "waiting": int(step.attrib.get("waiting", 0)),
            "meanWaitingTime":  int(float(step.attrib.get("meanWaitingTime", 0))),
            "meanTravelTime":  int(float(step.attrib.get("meanTravelTime", 0))),
            "inserted": int(step.attrib.get("inserted", 0)),
        })

    return pd.DataFrame(rows)


# -----------------------------
# 2. LOAD TRIPINFO.XML
# -----------------------------
def load_tripinfo(file):
    tree = ET.parse(file)
    root = tree.getroot()

    rows = []
    for trip in root.findall("tripinfo"):
        rows.append({
            "duration": float(trip.attrib["duration"]),
            "routeLength": float(trip.attrib["routeLength"]),
            "waitingTime": float(trip.attrib["waitingTime"]),
            "timeLoss": float(trip.attrib["timeLoss"]),
        })

    return pd.DataFrame(rows)


# -----------------------------
# 3. LOAD EDGEDATA.XML
# -----------------------------
def load_edgedata(file):
    tree = ET.parse(file)
    root = tree.getroot()

    rows = []

    for interval in root.findall("interval"):
        t = float(interval.attrib["begin"])

        for edge in interval.findall("edge"):
            rows.append({
                "time": t,
                "edge": edge.attrib["id"],
                "speed": float(edge.attrib.get("speed", 0)),
                "occupancy": float(edge.attrib.get("occupancy", 0)),
                "entered": float(edge.attrib.get("entered", 0)),

                "overlapDensity": float(edge.attrib.get("overlapDensity", 0)),
                "overlapTraveltime": float(edge.attrib.get("overlapTraveltime", 0)),
                "flow": float(edge.attrib.get("flow", 0)),
                "waitingTime":  float(edge.attrib.get("waitingTime", 0)),
            })


    df_edge = pd.DataFrame(rows).set_index("edge")

    return df_edge