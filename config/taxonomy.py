from __future__ import annotations

from enum import Enum


class IssueType(str, Enum):
    # Roads & Pavement
    POTHOLE = "pothole"
    STREET_CONDITION = "street_condition"
    CURB_CONDITION = "curb_condition"
    HIGHWAY_CONDITION = "highway_condition"
    # Sidewalks & Pedestrian
    CRACKED_SIDEWALK = "cracked_sidewalk"
    SIDEWALK_CONDITION = "sidewalk_condition"
    ACCESSIBILITY_BARRIER = "accessibility_barrier"
    # Traffic & Signals
    BROKEN_TRAFFIC_SIGNAL = "broken_traffic_signal"
    STREET_LIGHT_OUTAGE = "street_light_outage"
    STREET_SIGN_DAMAGED = "street_sign_damaged"
    # Water & Drainage
    CLOGGED_CATCH_BASIN = "clogged_catch_basin"
    FLOODING = "flooding"
    SEWER = "sewer"
    WATER_LEAK = "water_leak"
    # Sanitation
    ILLEGAL_DUMPING = "illegal_dumping"
    DIRTY_CONDITION = "dirty_condition"
    MISSED_COLLECTION = "missed_collection"
    GRAFFITI = "graffiti"
    # Trees & Parks
    FALLEN_TREE = "fallen_tree"
    DAMAGED_TREE = "damaged_tree"
    OVERGROWN_TREE = "overgrown_tree"
    # Vehicles & Parking
    ILLEGAL_PARKING = "illegal_parking"
    ABANDONED_VEHICLE = "abandoned_vehicle"
    BLOCKED_DRIVEWAY = "blocked_driveway"
    # Noise
    NOISE_STREET = "noise_street"
    NOISE_VEHICLE = "noise_vehicle"
    UNKNOWN = "unknown"


class SeverityLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class SafetyRisk(str, Enum):
    NONE = "none"
    VEHICLE_DAMAGE = "vehicle_damage"
    PEDESTRIAN_SLIP_HAZARD = "pedestrian_slip_hazard"
    ACCESSIBILITY_BLOCKED = "accessibility_blocked"
    TRAFFIC_DISRUPTION = "traffic_disruption"
    FLOODING_HAZARD = "flooding_hazard"
    FALLING_HAZARD = "falling_hazard"


AGENCY_MAPPING: dict[IssueType, str] = {
    # Roads & Pavement
    IssueType.POTHOLE: "DOT / 311",
    IssueType.STREET_CONDITION: "DOT / 311",
    IssueType.CURB_CONDITION: "DOT / 311",
    IssueType.HIGHWAY_CONDITION: "DOT / 311",
    # Sidewalks & Pedestrian
    IssueType.CRACKED_SIDEWALK: "DOT / 311",
    IssueType.SIDEWALK_CONDITION: "DOT / 311",
    IssueType.ACCESSIBILITY_BARRIER: "DOT / 311",
    # Traffic & Signals
    IssueType.BROKEN_TRAFFIC_SIGNAL: "DOT / 311",
    IssueType.STREET_LIGHT_OUTAGE: "DOT / 311",
    IssueType.STREET_SIGN_DAMAGED: "DOT / 311",
    # Water & Drainage
    IssueType.CLOGGED_CATCH_BASIN: "DEP / 311",
    IssueType.FLOODING: "DEP / OEM",
    IssueType.SEWER: "DEP / 311",
    IssueType.WATER_LEAK: "DEP / 311",
    # Sanitation
    IssueType.ILLEGAL_DUMPING: "DSNY / 311",
    IssueType.DIRTY_CONDITION: "DSNY / 311",
    IssueType.MISSED_COLLECTION: "DSNY / 311",
    IssueType.GRAFFITI: "DSNY / 311",
    # Trees & Parks
    IssueType.FALLEN_TREE: "DPR / 311",
    IssueType.DAMAGED_TREE: "DPR / 311",
    IssueType.OVERGROWN_TREE: "DPR / 311",
    # Vehicles & Parking
    IssueType.ILLEGAL_PARKING: "NYPD / 311",
    IssueType.ABANDONED_VEHICLE: "NYPD / DSNY",
    IssueType.BLOCKED_DRIVEWAY: "NYPD / 311",
    # Noise
    IssueType.NOISE_STREET: "NYPD / 311",
    IssueType.NOISE_VEHICLE: "NYPD / 311",
    IssueType.UNKNOWN: "311",
}

CATEGORY_311_CODES: dict[IssueType, str] = {
    # Roads & Pavement
    IssueType.POTHOLE: "Street Condition",
    IssueType.STREET_CONDITION: "Street Condition",
    IssueType.CURB_CONDITION: "Curb Condition",
    IssueType.HIGHWAY_CONDITION: "Highway Condition",
    # Sidewalks & Pedestrian
    IssueType.CRACKED_SIDEWALK: "Sidewalk Condition",
    IssueType.SIDEWALK_CONDITION: "Sidewalk Condition",
    IssueType.ACCESSIBILITY_BARRIER: "Sidewalk Condition",
    # Traffic & Signals
    IssueType.BROKEN_TRAFFIC_SIGNAL: "Traffic Signal Condition",
    IssueType.STREET_LIGHT_OUTAGE: "Street Light Condition",
    IssueType.STREET_SIGN_DAMAGED: "Street Sign - Damaged",
    # Water & Drainage
    IssueType.CLOGGED_CATCH_BASIN: "Catch Basin Clogged/Flooding",
    IssueType.FLOODING: "Sewer Backup/Flooding",
    IssueType.SEWER: "Sewer",
    IssueType.WATER_LEAK: "Water Leak",
    # Sanitation
    IssueType.ILLEGAL_DUMPING: "Illegal Dumping",
    IssueType.DIRTY_CONDITION: "Dirty Condition",
    IssueType.MISSED_COLLECTION: "Missed Collection",
    IssueType.GRAFFITI: "Graffiti",
    # Trees & Parks
    IssueType.FALLEN_TREE: "Damaged Tree",
    IssueType.DAMAGED_TREE: "Damaged Tree",
    IssueType.OVERGROWN_TREE: "Overgrown Tree/Branches",
    # Vehicles & Parking
    IssueType.ILLEGAL_PARKING: "Illegal Parking",
    IssueType.ABANDONED_VEHICLE: "Abandoned Vehicle",
    IssueType.BLOCKED_DRIVEWAY: "Blocked Driveway",
    # Noise
    IssueType.NOISE_STREET: "Noise - Street/Sidewalk",
    IssueType.NOISE_VEHICLE: "Noise - Vehicle",
    IssueType.UNKNOWN: "Other",
}

SUPPORTED_LANGUAGES: list[str] = [
    "en", "es", "zh", "ru", "bn", "ko",
    "hi", "ht", "ar", "fr", "ur", "pl",
    "pt", "ja", "it", "de", "yi",
]
