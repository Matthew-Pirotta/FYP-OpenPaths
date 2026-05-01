from collections import defaultdict


def build_segment_coef(
    G,
    eligible_segments,
    seg_to_arcs,
    arc_to_seg,
    paths_bike,
    paths_car,
    gamma: float,
):
    bike_benefit_seg = defaultdict(float)
    car_harm_seg = defaultdict(float)

    for (o, d, w), path in paths_bike.items():
        for u, v in zip(path[:-1], path[1:]):
            candidate_arcs = [(u, v, k) for k in G[u][v].keys()] if G.has_edge(u, v) else []
            for arc in candidate_arcs:
                seg = arc_to_seg.get(arc)
                if seg not in eligible_segments:
                    continue
                edge = G[arc[0]][arc[1]][arc[2]]
                delta_bike = edge["bike_cost_penalty"] - edge["bike_cost_base"]
                bike_benefit_seg[seg] += w * delta_bike

    for (o, d, w), path in paths_car.items():
        for u, v in zip(path[:-1], path[1:]):
            candidate_arcs = [(u, v, k) for k in G[u][v].keys()] if G.has_edge(u, v) else []
            for arc in candidate_arcs:
                seg = arc_to_seg.get(arc)
                if seg not in eligible_segments:
                    continue
                edge = G[arc[0]][arc[1]][arc[2]]
                delta_car = edge["car_cost_if_fietsstraat"] - edge["car_cost_current"]
                car_harm_seg[seg] += w * delta_car

    coef_seg = {}
    for seg in eligible_segments:
        coef_seg[seg] = bike_benefit_seg[seg] - gamma * car_harm_seg[seg]

    return coef_seg, bike_benefit_seg, car_harm_seg
