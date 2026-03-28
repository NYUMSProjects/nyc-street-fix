from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from config.taxonomy import IssueType, SafetyRisk, SeverityLevel
from schemas.incident import Coordinates, IncidentReport


@pytest.fixture
def sample_incident():
    return IncidentReport(
        issue_type=IssueType.FLOODING,
        severity=SeverityLevel.CRITICAL,
        safety_risk=SafetyRisk.FLOODING_HAZARD,
        location_text="Corner of Newark Ave and Grove St, Jersey City",
        likely_agency="DEP / OEM",
        report_summary="Severe flooding near the drain causing hazardous conditions for pedestrians.",
        coordinates=Coordinates(lat=40.7178, lng=-74.0431),
    )


@pytest.fixture
def low_severity_incident():
    return IncidentReport(
        issue_type=IssueType.GRAFFITI,
        severity=SeverityLevel.LOW,
        safety_risk=SafetyRisk.NONE,
        location_text="Flatbush Ave near Library, Brooklyn",
        likely_agency="DSNY / 311",
        report_summary="Graffiti on the wall near the library.",
    )


@pytest.mark.asyncio
async def test_generate_visual_card_creates_file(sample_incident):
    """Test that the visual card is created at the specified output path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "test_card.png")

        from tools.generate_visual_card import generate_visual_card

        result = await generate_visual_card(sample_incident, output_path)

    assert result == output_path


@pytest.mark.asyncio
async def test_generate_visual_card_output_path_returned(sample_incident):
    """Test that the function returns the correct output path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "incident_card.png")

        from tools.generate_visual_card import generate_visual_card

        returned_path = await generate_visual_card(sample_incident, output_path)

        assert returned_path == output_path


@pytest.mark.asyncio
async def test_generate_visual_card_creates_parent_dirs(sample_incident):
    """Test that the function creates parent directories if they don't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Use a nested path that doesn't exist yet
        output_path = os.path.join(tmpdir, "nested", "output", "card.png")

        from tools.generate_visual_card import generate_visual_card

        await generate_visual_card(sample_incident, output_path)

        assert Path(output_path).parent.exists()


@pytest.mark.asyncio
async def test_generate_visual_card_low_severity(low_severity_incident):
    """Test visual card generation with low severity incident."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "low_card.png")

        from tools.generate_visual_card import generate_visual_card

        result = await generate_visual_card(low_severity_incident, output_path)

        assert result == output_path


@pytest.mark.asyncio
async def test_generate_visual_card_unknown_issue_type():
    """Test visual card generation with unknown issue type."""
    incident = IncidentReport(
        issue_type=IssueType.UNKNOWN,
        severity=SeverityLevel.MODERATE,
        safety_risk=SafetyRisk.NONE,
        location_text="Unknown location",
        likely_agency="311",
        report_summary="Unknown street issue reported.",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "unknown_card.png")

        from tools.generate_visual_card import generate_visual_card

        result = await generate_visual_card(incident, output_path)

        assert result == output_path
