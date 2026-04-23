#TODO cleanup class by seperating codings constants and config constants
from enum import StrEnum, auto
from collections import Counter

class SafetyClass(StrEnum):
    PROTECTED = "very_safe"
    PAINTED = "safe"
    LOW_CAR_FLOW = "moderate"
    CAUTION = "caution"
    HIGH_CAR_FLOW = "dangerous"
    UNSUITABLE = "unsuitable"
    UNCLASSIFIED = "unclassified"


class InfraType(StrEnum):
    CAR = auto() # Car only road
    BIKE_LANE = auto() # painted #TODO see how im handling painted lanes
    CYCLE_TRACK = auto() #physically separated
    FIETSSTRAAT = auto() #shared but bike priority

SAFETY_COLORS = {
        SafetyClass.PROTECTED: "magenta",
        SafetyClass.PAINTED: "green",
        SafetyClass.LOW_CAR_FLOW: "orange",
        SafetyClass.HIGH_CAR_FLOW: "darkred",
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

#stopping rules
MIN_BIKE_GAIN = 0.005   # 0.5% of baseline bike total cost
MAX_CAR_HARM = 0.03     # 3% cumulative increase in car total cost
PATIENCE = 5            # require weak bike gains for 3 evals in a row

# Evaluation penalty applied per trip when an OD pair cannot be routed.
# Units follow the evaluated weight attribute (e.g., meters for car length,
# seconds for bike impedance when using bike_cost_penalty).
UNROUTED_TRIP_PENALTY_COST = 15_000.0


Arc = tuple[int, int, int]
Seg = tuple[int, int, int] 
# OD demand represented as Counter[(origin, destination)] -> trip weight.
OD = Counter[tuple[int, int]]

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
