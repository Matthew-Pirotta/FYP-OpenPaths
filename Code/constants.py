#TODO cleanup class by seperating codings constants and config constants
from enum import StrEnum, auto
from typing import NamedTuple

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



class ODPair(NamedTuple):
    origin: int
    destination: int
    bike_weight: float
    car_weight: float
    is_auxiliary: bool


Arc = tuple[int, int, int]
Seg = tuple[int, int, int] 
OD = list[ODPair]

LOCALITY_TO_REGION = {
    # Southern Harbour
    "Bormla": "Southern Harbour",
    "Il-Fgura": "Southern Harbour",
    "Il-Furjana": "Southern Harbour",
    "Ħal Luqa": "Southern Harbour",
    "Ħaż-Żabbar": "Southern Harbour",
    "Il-Kalkara": "Southern Harbour",
    "Il-Marsa": "Southern Harbour",
    "Raħal Ġdid": "Southern Harbour",
    "Santa Luċija": "Southern Harbour",
    "L-Isla": "Southern Harbour",
    "Ħal Tarxien": "Southern Harbour",
    "Il-Belt Valletta": "Southern Harbour",
    "Il-Birgu": "Southern Harbour",
    "Ix-Xgħajra": "Southern Harbour",
    "Wied il-Għajn": "Southern Harbour",

    # Northern Harbour
    "Birkirkara": "Northern Harbour",
    "Il-Gżira": "Northern Harbour",
    "Ħal Qormi": "Northern Harbour",
    "Il-Ħamrun": "Northern Harbour",
    "L-Imsida": "Northern Harbour",
    "Pembroke": "Northern Harbour",
    "San Ġwann": "Northern Harbour",
    "Santa Venera": "Northern Harbour",
    "Fleur-de-Lys": "Northern Harbour",
    "San Ġiljan": "Northern Harbour",
    "Is-Swieqi": "Northern Harbour",
    "Ta' Xbiex": "Northern Harbour",
    "Tal-Pietà": "Northern Harbour",
    "Tas-Sliema": "Northern Harbour",

    # South Eastern
    "Birżebbuġa": "South Eastern",
    "Il-Gudja": "South Eastern",
    "Ħal Għaxaq": "South Eastern",
    "Ħal Kirkop": "South Eastern",
    "Ħal Safi": "South Eastern",
    "Marsaskala": "South Eastern",
    "Marsaxlokk": "South Eastern",
    "L-Imqabba": "South Eastern",
    "Il-Qrendi": "South Eastern",
    "Iż-Żejtun": "South Eastern",
    "Iż-Żurrieq": "South Eastern",

    # Western
    "Ħad-Dingli": "Western",
    "Ħal Balzan": "Western",
    "Ħal Lija": "Western",
    "Ħ'Attard": "Western",
    "Ħaż-Żebbuġ": "Western",
    "L-Iklin": "Western",
    "L-Imdina": "Western",
    "L-Imtarfa": "Western",
    "Ir-Rabat": "Western",
    "Is-Siġġiewi": "Western",

    # Northern
    "Ħal Għargħur": "Northern",
    "Il-Mellieħa": "Northern",
    "L-Imġarr": "Northern",
    "Il-Mosta": "Northern",
    "In-Naxxar": "Northern",
    "San Pawl il-Baħar": "Northern",
}

REGION_ORDER = [
    "Southern Harbour",
    "Northern Harbour",
    "South Eastern",
    "Western",
    "Northern",
]