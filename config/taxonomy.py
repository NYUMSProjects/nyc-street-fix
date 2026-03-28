from __future__ import annotations

from enum import Enum


class IssueType(str, Enum):
    POTHOLE = "pothole"
    CLOGGED_CATCH_BASIN = "clogged_catch_basin"
    FLOODING = "flooding"
    ILLEGAL_DUMPING = "illegal_dumping"
    BROKEN_TRAFFIC_SIGNAL = "broken_traffic_signal"
    CRACKED_SIDEWALK = "cracked_sidewalk"
    ACCESSIBILITY_BARRIER = "accessibility_barrier"
    FALLEN_TREE = "fallen_tree"
    STREET_LIGHT_OUTAGE = "street_light_outage"
    GRAFFITI = "graffiti"
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
    IssueType.POTHOLE: "DOT / 311",
    IssueType.CLOGGED_CATCH_BASIN: "DEP / 311",
    IssueType.FLOODING: "DEP / OEM",
    IssueType.ILLEGAL_DUMPING: "DSNY / 311",
    IssueType.BROKEN_TRAFFIC_SIGNAL: "DOT / 311",
    IssueType.CRACKED_SIDEWALK: "DOT / 311",
    IssueType.ACCESSIBILITY_BARRIER: "DOT / 311",
    IssueType.FALLEN_TREE: "DPR / 311",
    IssueType.STREET_LIGHT_OUTAGE: "DOT / 311",
    IssueType.GRAFFITI: "DSNY / 311",
    IssueType.UNKNOWN: "311",
}

CATEGORY_311_CODES: dict[IssueType, str] = {
    IssueType.POTHOLE: "Pothole",
    IssueType.CLOGGED_CATCH_BASIN: "Catch Basin Clogged/Flooding",
    IssueType.FLOODING: "Sewer Backup/Flooding",
    IssueType.ILLEGAL_DUMPING: "Illegal Dumping",
    IssueType.BROKEN_TRAFFIC_SIGNAL: "Traffic Signal Condition",
    IssueType.CRACKED_SIDEWALK: "Sidewalk Condition",
    IssueType.ACCESSIBILITY_BARRIER: "Blocked Driveway",
    IssueType.FALLEN_TREE: "Fallen Tree",
    IssueType.STREET_LIGHT_OUTAGE: "Street Light Condition",
    IssueType.GRAFFITI: "Graffiti",
    IssueType.UNKNOWN: "Other",
}

SUPPORTED_LANGUAGES: list[str] = ["en", "es", "zh", "ru", "bn", "ko"]
