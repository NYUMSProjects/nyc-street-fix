from __future__ import annotations

from pathlib import Path

import structlog

from schemas.incident import IncidentReport

logger = structlog.get_logger(__name__)

SEVERITY_COLORS = {
    "critical": "#FF2D00",
    "high": "#FF8C00",
    "moderate": "#FFD700",
    "low": "#32CD32",
}

ISSUE_ICONS = {
    "pothole": "POTHOLE",
    "clogged_catch_basin": "CLOGGED DRAIN",
    "flooding": "FLOODING",
    "illegal_dumping": "ILLEGAL DUMP",
    "broken_traffic_signal": "BROKEN SIGNAL",
    "cracked_sidewalk": "CRACKED SIDEWALK",
    "accessibility_barrier": "ACCESS BARRIER",
    "fallen_tree": "FALLEN TREE",
    "street_light_outage": "LIGHT OUTAGE",
    "graffiti": "GRAFFITI",
    "unknown": "UNKNOWN ISSUE",
}


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    return r, g, b


async def generate_visual_card(incident: IncidentReport, output_path: str) -> str:
    """Generate a visual hazard card PNG for the given incident.

    Creates an 800x600 PNG with issue type, severity, location, agency, and summary.

    Args:
        incident: The populated IncidentReport.
        output_path: File path to save the PNG to.

    Returns:
        The output_path string where the card was saved.
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        from matplotlib.patches import FancyBboxPatch
    except ImportError:
        logger.error("generate_visual_card: matplotlib not installed")
        raise

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    severity_val = incident.severity.value if incident.severity else "moderate"
    sev_color = SEVERITY_COLORS.get(severity_val, "#FFD700")
    sev_rgb = _hex_to_rgb(sev_color)

    issue_label = ISSUE_ICONS.get(incident.issue_type.value, "STREET ISSUE")
    location = incident.location_text or "Location not specified"
    agency = incident.likely_agency or "311"
    summary = incident.report_summary or "No summary available."

    # Wrap summary text
    max_chars = 80
    words = summary.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 <= max_chars:
            current = f"{current} {word}".strip()
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    summary_text = "\n".join(lines[:3])  # max 3 lines

    fig, ax = plt.subplots(figsize=(8, 6), dpi=100)
    fig.patch.set_facecolor("#1A1A2E")
    ax.set_facecolor("#1A1A2E")
    ax.set_xlim(0, 8)
    ax.set_ylim(0, 6)
    ax.axis("off")

    # Header bar
    header = FancyBboxPatch((0, 4.8), 8, 1.2, boxstyle="square,pad=0", color="#16213E")
    ax.add_patch(header)

    # NYC StreetFix branding
    ax.text(0.3, 5.55, "NYC StreetFix", color="#00D4FF", fontsize=14, fontweight="bold", va="center")
    ax.text(0.3, 5.15, "311 Incident Report", color="#8892B0", fontsize=9, va="center")

    # Severity badge
    sev_badge = FancyBboxPatch((5.8, 5.05), 1.9, 0.7, boxstyle="round,pad=0.05", color=sev_rgb, alpha=0.9)
    ax.add_patch(sev_badge)
    ax.text(6.75, 5.42, severity_val.upper(), color="white", fontsize=11, fontweight="bold",
            ha="center", va="center")

    # Issue type block
    issue_bg = FancyBboxPatch((0.3, 3.7), 7.4, 0.9, boxstyle="round,pad=0.1", color="#0F3460", alpha=0.8)
    ax.add_patch(issue_bg)
    ax.text(4.0, 4.15, issue_label, color="white", fontsize=18, fontweight="bold",
            ha="center", va="center")

    # Severity indicator bar
    bar_color = FancyBboxPatch((0.3, 3.5), 7.4, 0.12, boxstyle="square,pad=0", color=sev_rgb)
    ax.add_patch(bar_color)

    # Location section
    ax.text(0.3, 3.2, "LOCATION", color="#00D4FF", fontsize=8, fontweight="bold")
    ax.text(0.3, 2.9, location[:70] + ("..." if len(location) > 70 else ""),
            color="white", fontsize=10)

    # Agency section
    ax.text(0.3, 2.55, "RESPONSIBLE AGENCY", color="#00D4FF", fontsize=8, fontweight="bold")
    ax.text(0.3, 2.25, agency, color="#FFD700", fontsize=11, fontweight="bold")

    # Summary section
    ax.text(0.3, 1.9, "SUMMARY", color="#00D4FF", fontsize=8, fontweight="bold")
    ax.text(0.3, 1.55, summary_text, color="#CBD5E1", fontsize=9, va="top", wrap=True)

    # Safety risk
    safety_val = incident.safety_risk.value.replace("_", " ").title() if incident.safety_risk else "None"
    if safety_val.lower() != "none":
        risk_bg = FancyBboxPatch((0.3, 0.55), 3.5, 0.45, boxstyle="round,pad=0.05", color="#7B0000", alpha=0.7)
        ax.add_patch(risk_bg)
        ax.text(2.05, 0.77, f"RISK: {safety_val.upper()}", color="#FF8C8C", fontsize=9,
                fontweight="bold", ha="center", va="center")

    # Footer
    footer_bg = FancyBboxPatch((0, 0.0), 8, 0.45, boxstyle="square,pad=0", color="#16213E")
    ax.add_patch(footer_bg)
    ax.text(4.0, 0.22, "Report via nyc.gov/311 or call 311", color="#8892B0", fontsize=8,
            ha="center", va="center")

    plt.tight_layout(pad=0)
    plt.savefig(output_path, dpi=100, bbox_inches="tight", facecolor="#1A1A2E")
    plt.close(fig)

    logger.info("generate_visual_card: saved card", path=output_path)
    return output_path
