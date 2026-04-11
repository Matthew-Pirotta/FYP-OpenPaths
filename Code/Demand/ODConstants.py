#TODO idk if i should hava constants or ODutil idk

from collections import defaultdict

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

#TODO store these as dataframes?
PURPOSE_COUNTS_BY_DEST_REGION = {
    "Southern Harbour": {
        "education_and_escort_education": 9827,
        "going_to_main_place_of_work": 43922,
        "shopping": 6119,
        "personal_errands": 7540,
        "escort_other": 4714,
        "medical": 2317,
        "recreation": 6596,
        "visiting": 4827,
        "other": 4138,
    },
    "Northern Harbour": {
        "education_and_escort_education": 22182,
        "going_to_main_place_of_work": 66821,
        "shopping": 13770,
        "personal_errands": 10470,
        "escort_other": 8075,
        "medical": 9213,
        "recreation": 10447,
        "visiting": 8551,
        "other": 6814,
    },
    "South Eastern": {
        "education_and_escort_education": 3329,
        "going_to_main_place_of_work": 18298,
        "shopping": 3234,
        "personal_errands": 3610,
        "escort_other": 2109,
        "medical": 1142,  # table marks this as caution
        "recreation": 4927,
        "visiting": 3501,
        "other": 2218,
    },
    "Western": {
        "education_and_escort_education": 3661,
        "going_to_main_place_of_work": 16011,
        "shopping": 4777,
        "personal_errands": 4217,
        "escort_other": 2856,
        "medical": 610,   # inferred residual; table suppresses this value
        "recreation": 5765,
        "visiting": 2986,
        "other": 3941,
    },
    "Northern": {
        "education_and_escort_education": 6603,
        "going_to_main_place_of_work": 19654,
        "shopping": 8128,
        "personal_errands": 5366,
        "escort_other": 3732,
        "medical": 1209,  # table marks this as caution
        "recreation": 6310,
        "visiting": 3750,
        "other": 2964,
    },
}

REGION_TO_REGION_COUNTS = {
    "Southern Harbour": {
        "Southern Harbour": 42182,
        "Northern Harbour": 33186,
        "South Eastern": 21460,
        "Western": 9829,
        "Northern": 10524,
    },
    "Northern Harbour": {
        "Southern Harbour": 33463,
        "Northern Harbour": 115270,
        "South Eastern": 17104,
        "Western": 22230,
        "Northern": 28066,
    },
    "South Eastern": {
        "Southern Harbour": 22855,
        "Northern Harbour": 18215,
        "South Eastern": 31355,
        "Western": 4808,
        "Northern": 3079,
    },
    "Western": {
        "Southern Harbour": 10344,
        "Northern Harbour": 24399,
        "South Eastern": 4800,
        "Western": 25630,
        "Northern": 12377,
    },
    "Northern": {
        "Southern Harbour": 11801,
        "Northern Harbour": 30491,
        "South Eastern": 3761,
        "Western": 13344,
        "Northern": 45393,
    },
}


PURPOSE_TO_TYPES = {
    "going_to_main_place_of_work": ["bank", "work", "shop"],  
    "education_and_escort_education": ["college", "language_school", "university", "child_care", "school"],
    "shopping": ["mall", "marketplace", "shop"],
    "personal_errands": ["bank", "library", "monastery", "place_of_worship", "social_facility", "veterinary"],
    "medical": ["dentist", "doctors", "hospital", "pharmacy"],
    "recreation": ["bar", "bench", "cafe", "fast_food", "food_court", "restaurant"],
    "visiting": ["residential"],
    "escort_other": ["*"], 
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

DEFAULT_BETA = 0.0002
TARGET_AVG_DISTANCE = 6100