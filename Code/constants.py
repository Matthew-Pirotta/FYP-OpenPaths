from enum import StrEnum, auto

class SafetyClass(StrEnum):
    VERY_SAFE = "very_safe"
    SAFE = "safe"
    MODERATE = "moderate"
    CAUTION = "caution"
    DANGEROUS = "dangerous"
    UNSUITABLE = "unsuitable"
    UNCLASSIFIED = "unclassified"