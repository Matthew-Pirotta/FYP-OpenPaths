from networkx import MultiDiGraph
import osmnx as ox
from collections import Counter


#TODO very safe?
safety_to_risk_factor_map = {
    "safe": 1,
    "moderate": 1.5,
    "caution": 2 ,#NOTE Cyclists perceive travel on car-dominated lanes as twice as costly
    "dangerous": 4, #TODO highway twice as costly ig?
    "unsuitable": 2,
    "unclassified": 2,
}

def merge_semantically_equivalent_road_tags(G:MultiDiGraph):
    highway_equivalence = {
    # Merging link types
    "motorway_link": "motorway",
    "trunk_link": "trunk",
    "primary_link": "primary",
    "secondary_link": "secondary",
    "tertiary_link": "tertiary",
    
    # Local road equivalences
    "living_street": "residential",
    "unclassified": "residential",
    
    """# Access / minor roads
    "track": "service",""" #TODO
    
    # Non-motorised
    "footway": "non_motorised",
    "pedestrian": "non_motorised",
    "path": "non_motorised",
    "busway": "non_motorised"  # often bus-priority corridor #TODO?
    }

    cycle_equivalence = {
        "shared_lane"
    }
    
    for _,_, data in G.edges(data=True):
        highway = data.get("highway")

        if isinstance(highway, list):
            updated_highway = []
            for entry in highway:
                if entry in highway_equivalence:
                    updated_highway.append(highway_equivalence[entry])
                else:
                    updated_highway.append(entry)
            data["highway"] = updated_highway
            continue

        if highway in highway_equivalence:
            data["highway"] = highway_equivalence[highway]

def select_primary_label(highway_list:list[str]|str, priority_order:list) -> str:
    """Select the highest priority highway type from a list."""
    if not isinstance(highway_list, list):
        return highway_list
    
    # Find highest priority highway type
    best_highway = highway_list[0]  # fallback
    best_priority = -1
    
    for highway in highway_list:
        try:
            priority = priority_order.index(highway)
            if priority > best_priority:
                best_priority = priority
                best_highway = highway
        except ValueError:
            # Highway type not in priority list, use as fallback
            continue
    
    return best_highway


def collapse_road_tag_lists(G):
    highway_priority = [          
        "service", # Lowest priority - often just access roads
        "residential",
        "pedestrian"
        "tertiary",
        "secondary",
        "primary",
        "trunk",
        "track"
        "cycleway"         # Highest priority - dedicated cycling infrastructure
    ]

    bicycle_priority = [
        # Lowest priority
        'None',
        'permissive'
        'yes',
        'private'
        'designated',
        # Highest priority
    ]

    cycleway_priority = [
        'None',
        'no',
        'crossing',
        'shared',
        'shared_lane', # cycling along side cars
        'lane', # lies within the roadway 
        'track', # separated by buffer
    ]

    for _, _, data in G.edges(data=True):
        highway = data.get("highway")
        #NOTE that some entries have a list of labels, and the safest option is taken for classification

        highway = select_primary_label(highway, highway_priority)
        data["highway"] = highway

        # Defines legal access — whether bicycles may use the way.
        bicycle = data.get("bicycle")
        bicycle = select_primary_label(bicycle, bicycle_priority)
        data['bicycle'] = bicycle

        #Describes infrastructure type — if and how a bike facility exists
        cycleway = data.get("cycleway")
        cycleway = select_primary_label(cycleway, cycleway_priority)
        data["cycleway"] = cycleway


def clean_graph(G:MultiDiGraph):
    """Merges semantically equivalent road tags and collapses road tag lists into just the most prominent one"""
    merge_semantically_equivalent_road_tags(G)
    collapse_road_tag_lists(G)
    



#TODO
def bike_safety_classification(G_bike:MultiDiGraph):
    for _, _, data in G_bike.edges(data=True):
        #TODO although im filtering based on road priority for classification, i still need to see the seperate bike and car lanes
        # and in reality they should be 2 seperate graphs? but currently the bike can cycle over the car network
        # ig in reality i just need to see how these connections are being stored

        highway = data.get("highway")
        # Defines legal access — whether bicycles may use the way.
        bicycle = data.get("bicycle")
        #Describes infrastructure type — if and how a bike facility exists
        cycleway = data.get("cycleway")

        #Separated 
        if cycleway == 'track' or highway == "cycleway" or bicycle == "designated":
            classification = "very_safe"
        #Demarcated Shared
        elif cycleway in {"shared", "lane"}:
            classification = "safe"

        # MODERATE - Cyclist-friendly streets  
        elif highway in {"non_motorised", "residential"}:
            classification = "moderate"

        # CAUTION - Mixed traffic but manageable
        elif highway == "service":
            classification = "caution"
        
        # Dangerous - active traffic
        elif highway in {"trunk", "secondary","primary", "tertiary"}:
            classification = "dangerous"

         #Not suitable for urban transport
        elif highway == "track":
            classification ="unsuitable"
        else:
            classification = "unclassified"

        data["safety"] = classification
        data["risk_factor"] = safety_to_risk_factor_map.get(data.get("safety",-1))

        #print(f"highway: {highway},\t\t bicycle: {bicycle},\t\t cycleway: {cycleway}") 


def summarise_road_type_stats(G:MultiDiGraph):
    highway_counts = Counter()
    bikeway_counts = Counter()
    cycleway_counts = Counter()

    for u, v, data in G.edges(data=True):
        highway_counts[data.get("highway")] += 1
        bikeway_counts[data.get("bicycle")] += 1
        cycleway_counts[data.get("cycleway")] += 1
    
    
    print("Highway type counts:")
    for highway_type, count in highway_counts.most_common():
        print(f"{highway_type}: {count}")

    print("-------")
    print("bikeway classification type counts:")
    for bikeway_type, count in bikeway_counts.most_common():
        print(f"{bikeway_type}: {count}")

    print("------")
    print("cycleway type counts:")
    for cycleway_type, count in cycleway_counts.most_common():
        print(f"{cycleway_type}: {count}")
