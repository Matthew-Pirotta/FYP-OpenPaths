import osmnx as ox


highway_to_safety_map = {
    # SAFEST - Dedicated cycling infrastructure
    "cycleway": "safe",        # Dedicated bike paths - safest
    "path": "safe",           # Shared paths - generally safe
    
    # MODERATE - Cyclist-friendly streets  
    "living_street": "moderate",   # Shared space, pedestrian priority
    "residential": "moderate",        # Low speed, low traffic
    "pedestrian": "moderate",         # Walk/bike only areas

    # CAUTION - Mixed traffic but manageable
    "unclassified": "caution",  # Rural/local roads - variable safety
    "service": "caution",         # Parking lots, alleys - usually low speed
    #"track": "orange",            # Unpaved - may not be suitable

    # Dangerous
    "trunk":"dangerous",
    "secondary":"dangerous",
    "primary": "dangerous",
    "trunk_link": "dangerous",
    "secondary_link": "dangerous",
    "tertiary_link": "dangerous",
    "primary_link": "dangerous",

    #Not suitable for urban transport / Development
    "track": "unsuitable",
}

safety_to_color_map = {
    "safe": "green",
    "moderate": "yellow",
    "caution": "orange",
    "dangerous": "red",
    "unsuitable": "brown",
    "unclassified": "gray"
}

safety_to_risk_factor_map = {
    "safe": 1,
    "moderate": 1.5,
    "caution": 2 ,#NOTE Cyclists perceive travel on car-dominated lanes as twice as costly
    "dangerous": 4, #TODO highway twice as costly ig?
    "unsuitable": 2,
    "unclassified": 2,
}


def summarise_road_type_stats():
    pass