import xml.etree.ElementTree as ET
import pandas as pd


from matplotlib.ticker import ScalarFormatter

import matplotlib.pyplot as plt

#Region Loding Sim Ouput

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
            })


    df_edge = pd.DataFrame(rows).set_index("edge")

    return df_edge

#end region

#TODO these two are depricated
def build_sumo_to_osm_map(df_edge):
    mapping = {}

    for edge_id in df_edge.index:
        base_id = edge_id.split("#")[0]
        mapping.setdefault(base_id, []).append(edge_id)

    return mapping

def attach_util_results_to_graph(G_unsimplified, df_edge):
    mapping = build_sumo_to_osm_map(df_edge)

    for u, v, k, data in G_unsimplified.edges(keys=True, data=True):

        osmid = str(data.get("osmid"))

        if osmid in mapping:

            edge_ids = mapping[osmid]

            # average if multiple SUMO segments
            vals = df_edge.loc[edge_ids]

            data["overlapDensity"] = vals["overlapDensity"].mean()
            data["overlapTraveltime"] = vals["overlapTraveltime"].mean()
            data["flow"] = vals["flow"].mean()
