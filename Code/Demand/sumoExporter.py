from matplotlib.colors import to_rgb
import unicodedata
import re
import sumolib
import geopandas as gpd
import copy

def write_taz_polygons(gdf_localities, outfile):
    with open(outfile, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<additional>\n')

        for _, row in gdf_localities.iterrows():
            name = row["name"]
            geom = row.geometry
            color = color = _hex_to_sumo_rgb(row["color"])
            
            coords = " ".join(
                f"{x},{y}" for x, y in geom.exterior.coords
            )

            f.write(
                f'<poly id="{name}" type="taz" '
                f'color="{color}" fill="true" '
                f'shape="{coords}"/>\n'
            )

        f.write('</additional>\n')


def _hex_to_sumo_rgb(hex_color):
    rgb = to_rgb(hex_color)
    rgb = tuple(int(c*255) for c in rgb)
    r,g,b = rgb
    return f"{r},{g},{b}"

def sumo_safe_id(name: str) -> str:
    # convert accented characters → ascii
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()

    # replace spaces with underscore
    name = name.replace(" ", "_")

    # remove apostrophes
    name = name.replace("'", "")

    # remove any remaining invalid characters
    name = re.sub(r"[^A-Za-z0-9_]", "", name)

    return name


def sumo_safe_shift_polygons(net, gdf):

    # get SUMO offset
    offset_x, offset_y = net.getLocationOffset()

    # shift polygons
    gdf_shifted = copy.deepcopy(gdf) 
    gdf_shifted["name"] = (gdf_shifted["name"].apply(sumo_safe_id))
    gdf_shifted["geometry"] = gdf_shifted.translate(
        xoff=offset_x,
        yoff=offset_y
    )

    return gdf_shifted


def write_od_matrix(od_timeline_tables, outfile):
    """
    Write SUMO OD matrix from region OD tables.

    Parameters
    ----------
    od_timeline_tables : list[dict]
        Output from build_region_od_tables_from_timeline()
    outfile : str
        Path to od_matrix.xml
    """

    with open(outfile, "w") as f:

        f.write("<data>\n")

        for interval in od_timeline_tables:

            begin = interval["begin"]
            end = interval["end"]
            od_table = interval["od_table"]

            f.write(f'  <interval begin="{begin}" end="{end}">\n')

            for origin in od_table.index:
                for dest in od_table.columns:

                    trips = int(od_table.loc[origin, dest])

                    if trips <= 0:
                        continue

                    f.write(
                        f'    <tazRelation from="{origin}" '
                        f'to="{dest}" count="{trips}"/>\n'
                    )

            f.write("  </interval>\n")

        f.write("</data>\n")