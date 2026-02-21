#TODO cleanup class by seperating codings constants and config constants


from enum import StrEnum, auto

class SafetyClass(StrEnum):
    VERY_SAFE = "very_safe"
    SAFE = "safe"
    MODERATE = "moderate"
    CAUTION = "caution"
    DANGEROUS = "dangerous"
    UNSUITABLE = "unsuitable"
    UNCLASSIFIED = "unclassified"


class InfraType(StrEnum):
    CAR = auto() # Car only road
    BIKE_LANE = auto() # painted #TODO see how im handling painted lanes
    CYCLE_TRACK = auto() #physically separated
    FIETSSTRAAT = auto() #shared but bike priority

SAFETY_COLORS = {
        SafetyClass.VERY_SAFE: "magenta",
        SafetyClass.SAFE: "green",
        SafetyClass.MODERATE: "orange",
        SafetyClass.CAUTION: "red",
        SafetyClass.DANGEROUS: "darkred",
        SafetyClass.UNCLASSIFIED: "gray",
    }

HWY_COLORS = {
    "trunk": "darkred",       # Highest priority
    "primary": "red",         # Major arterial
    "secondary": "orange",    # Minor arterial
    "tertiary": "gold",       # Collector
    "residential": "skyblue",  # Local street
    "service": "slategray",   # Minor access
}

FIETSSTRAAT_SPEED_KMH = 30.0
DEFUALT_MAXIUM_SPEED_KMH = 60.0 #Maltese highway code for built up areas


Arc = tuple[int, int, int]
Seg = tuple[int, int, int] 
OD = tuple[int, int, float]
