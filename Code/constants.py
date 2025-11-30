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