import xml.etree.ElementTree as ET
import pandas as pd


from matplotlib.ticker import ScalarFormatter

import matplotlib.pyplot as plt

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