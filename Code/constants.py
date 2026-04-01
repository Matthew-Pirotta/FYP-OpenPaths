#TODO cleanup class by seperating codings constants and config constants
from enum import StrEnum, auto
from typing import NamedTuple

class SafetyClass(StrEnum):
    PROTECTED = "very_safe"
    PAINTED = "safe"
    LOW_TRAFFIC = "moderate"
    CAUTION = "caution"
    HIGH_TRAFFIC = "dangerous"
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
        SafetyClass.LOW_TRAFFIC: "orange",
        SafetyClass.HIGH_TRAFFIC: "darkred",
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

LOCALITY_TO_POPULATION = {
    # Southern Harbour
    "Bormla": 4654,
    "Il-Fgura": 13066,
    "Il-Furjana": 1985,          # Floriana
    "Ħal Luqa": 7249,
    "Ħaż-Żabbar": 17148,
    "Il-Kalkara": 3105,
    "Il-Marsa": 5468,
    "Raħal Ġdid": 9339,
    "Santa Luċija": 2617,
    "L-Isla": 2304,
    "Ħal Tarxien": 9464,
    "Il-Belt Valletta": 5157,    # Valletta
    "Il-Birgu": 2261,
    "Ix-Xgħajra": 2192,

    # Northern Harbour
    "Birkirkara": 25807,
    "Il-Gżira": 10331,
    "Ħal Qormi": 18099,
    "Il-Ħamrun": 10514,
    "L-Imsida": 13587,
    "Pembroke": 3545,
    "San Ġwann": 14244,
    "Santa Venera": 8834,
    "San Ġiljan": 11653,
    "Is-Swieqi": 13044,
    "Ta' Xbiex": 2092,
    "Tal-Pietà": 5892,
    "Tas-Sliema": 19655,

    # South Eastern
    "Birżebbuġa": 11844,
    "Il-Gudja": 3229,
    "Ħal Għaxaq": 5538,
    "Ħal Kirkop": 2527,
    "Ħal Safi": 2641,
    "L-Imqabba": 3525,
    "Il-Qrendi": 3148,
    "Iż-Żejtun": 12409,
    "Iż-Żurrieq": 12295,
    "Marsaxlokk": 3988,
    "Wied il-Għajn": 16804,      # Marsaskala

    # Western
    "Ħad-Dingli": 3865,
    "Ħal Balzan": 4774,
    "Ħal Lija": 3162,
    "Ħ'Attard": 12268,
    "Ħaż-Żebbuġ": 13785,
    "L-Iklin": 3399,
    "L-Imdina": 193,
    "L-Imtarfa": 2566,
    "Ir-Rabat": 11936,
    "Is-Siġġiewi": 9318,

    # Northern
    "Ħal Għargħur": 3741,
    "Il-Mellieħa": 12738,
    "L-Imġarr": 4840,
    "Il-Mosta": 23482,
    "In-Naxxar": 16912,
    "San Pawl il-Baħar": 32042,
}

REGION_ORDER = [
    "Southern Harbour",
    "Northern Harbour",
    "South Eastern",
    "Western",
    "Northern",
]

PURPOSE_SHARES = {
    "commuting": 0.422,
    "education": 0.116,
    "escort_education": 0.049,
    "shopping": 0.093,
    "personal_errands": 0.078,
    "medical": 0.038,
    "recreation": 0.089,
    "visiting": 0.060,
    "other": 0.055,
}

PURPOSE_TO_TYPES = {
    "commuting": ["bank", "work", "shop"],  
    "education": ["college", "language_school", "university"],
    "escort_education": ["child_care", "school"], # Trips to drop off/pick up students
    "shopping": ["mall", "marketplace", "shop"],
    "personal_errands": ["bank", "library", "monastery", "place_of_worship", "social_facility", "veterinary"],
    "medical": ["dentist", "doctors", "hospital", "pharmacy"],
    "recreation": ["bar", "bench", "cafe", "fast_food", "food_court", "restaurant"],
    "visiting": ["*"],  #TODO residential
    "other": ["other"]
}

AMENITY_KEEP = {
    "bank",
    "bar",
    "bench",
    "cafe",
    "child_care",
    "college",
    "dentist",
    "doctors",
    "fast_food",
    "food_court",
    "hospital",
    "language_school",
    "library",
    "mall",
    "marketplace",
    "monastery",
    "pharmacy",
    "place_of_worship",
    "restaurant",
    "school",
    "social_facility",
    "university",
    "veterinary"
}