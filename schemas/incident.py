from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from config.taxonomy import IssueType, SafetyRisk, SeverityLevel


class Coordinates(BaseModel):
    lat: float
    lng: float


class IncidentReport(BaseModel):
    issue_type: IssueType = IssueType.UNKNOWN
    severity: SeverityLevel = SeverityLevel.MODERATE
    safety_risk: SafetyRisk = SafetyRisk.NONE
    location_text: str = ""
    coordinates: Optional[Coordinates] = None
    likely_agency: str = ""
    report_summary: str = ""
    follow_up_questions: list[str] = Field(default_factory=list)
    language: str = "en"
    media_attached: bool = False
    complaint_text: Optional[str] = None
    visual_card_path: Optional[str] = None
    translations: dict[str, str] = Field(default_factory=dict)
    flood_history: Optional[dict] = None
    mta_elevator_status: Optional[dict] = None


class ClassificationResult(BaseModel):
    issue_type: IssueType
    severity: SeverityLevel
    safety_risk: SafetyRisk
    confidence: float = Field(ge=0.0, le=1.0)
    description: str
    follow_up_questions: list[str] = Field(default_factory=list)
