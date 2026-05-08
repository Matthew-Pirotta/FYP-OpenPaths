#TODO actually implement and make use
from enum import StrEnum, auto

class EdgeAttr(StrEnum):
    CAR_LANES = auto()             # Results in "car_lanes"
    BIKE_LANES = auto()            # Results in "bike_lanes"
    CAR_ALLOWED = auto()
    BIKE_ALLOWED = auto()
    REALLOCATABLE = auto()
    GRADE = auto()
    RISK_FACTOR = auto()
    BIKE_COST_PENALTY = auto()
    SPEED_KPH_CURRENT = auto()
    CAR_COST_CURRENT = auto()
    INFRA_TYPE = auto()
    
    # You can also manually map them if the string 
    # doesn't match the variable name exactly: