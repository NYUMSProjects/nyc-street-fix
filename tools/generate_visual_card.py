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

SAFETY_RISK_COLORS = {
    "none":               "#32CD32",
    "no risk":            "#32CD32",
    "pedestrian_hazard":  "#FF8C00",
    "traffic_hazard":     "#FF8C00",
    "property_damage":    "#FFD700",
    "injury_risk":        "#FF2D00",
    "public_health":      "#FF2D00",
}


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    return r, g, b


def _wrap(text: str, max_chars: int, max_lines: int) -> str:
    words = text.split()
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
    return "\n".join(lines[:max_lines])


def _load_image(image_path: str):
    """Return numpy image array or None on failure."""
    try:
        import matplotlib.pyplot as plt
        return plt.imread(image_path)
    except Exception:
        pass
    try:
        from PIL import Image
        import numpy as np
        return np.array(Image.open(image_path).convert("RGB"))
    except Exception as e:
        logger.warning("generate_visual_card: could not load image", error=str(e))
        return None


async def generate_visual_card(
    incident: IncidentReport,
    output_path: str,
    image_path: str | None = None,
) -> str:
    """Generate a visual hazard card PNG for the given incident.

    Creates a PNG with issue type, severity, location, agency, safety risk,
    complaint summary, and an optional image thumbnail.

    Args:
        incident: The populated IncidentReport.
        output_path: File path to save the PNG to.
        image_path: Optional path to the reported photo to embed as a thumbnail.

    Returns:
        The output_path string where the card was saved.
    """
    try:
        import matplotlib.pyplot as plt
        from matplotlib.patches import FancyBboxPatch
    except ImportError:
        logger.error("generate_visual_card: matplotlib not installed")
        raise

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # ── Extract incident fields ────────────────────────────────────────────
    severity_val  = incident.severity.value if incident.severity else "moderate"
    sev_color     = SEVERITY_COLORS.get(severity_val, "#FFD700")
    sev_rgb       = _hex_to_rgb(sev_color)

    issue_label   = ISSUE_ICONS.get(incident.issue_type.value, "STREET ISSUE")
    issue_text    = incident.issue_type.value.replace("_", " ").title()
    location      = incident.location_text or "Location not specified"
    agency        = incident.likely_agency or "311"
    summary       = incident.report_summary or "No summary available."
    complaint_txt = incident.complaint_text or ""

    safety_raw    = incident.safety_risk.value if incident.safety_risk else "none"
    safety_label  = safety_raw.replace("_", " ").title()
    risk_color    = SAFETY_RISK_COLORS.get(safety_raw.lower(), "#FFD700")
    risk_rgb      = _hex_to_rgb(risk_color)

    # ── Try to load image ─────────────────────────────────────────────────
    img_data = _load_image(image_path) if image_path else None
    has_image = img_data is not None

    # ── Figure: wider when image is present ───────────────────────────────
    FW = 11.0 if has_image else 8.0   # figure width  (inches)
    FH = 7.5                           # figure height (inches)

    fig = plt.figure(figsize=(FW, FH), dpi=100)
    fig.patch.set_facecolor("#1A1A2E")

    # Single axes covering the full canvas — used for all patches / text
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, FW)
    ax.set_ylim(0, FH)
    ax.axis("off")
    ax.set_facecolor("#1A1A2E")

    # ── Header ────────────────────────────────────────────────────────────
    ax.add_patch(FancyBboxPatch((0, 6.6), FW, 0.9, boxstyle="square,pad=0", color="#16213E"))
    ax.text(0.3, 7.18, "NYC StreetFix",      color="#00D4FF", fontsize=14, fontweight="bold", va="center")
    ax.text(0.3, 6.78, "311 Incident Report", color="#8892B0", fontsize=9,  va="center")

    # Severity badge (top-right)
    ax.add_patch(FancyBboxPatch((FW - 2.2, 6.72), 2.0, 0.65,
                                boxstyle="round,pad=0.05", color=sev_rgb, alpha=0.9))
    ax.text(FW - 1.2, 7.05, severity_val.upper(),
            color="white", fontsize=11, fontweight="bold", ha="center", va="center")

    # ── Image thumbnail (left panel, only when image is available) ─────────
    if has_image:
        # Place image axes in figure-coordinate space [left, bottom, w, h]
        img_l = 0.30 / FW
        img_b = 1.10 / FH
        img_w = 4.50 / FW
        img_h = 5.30 / FH
        img_ax = fig.add_axes([img_l, img_b, img_w, img_h])
        img_ax.imshow(img_data, aspect="auto")
        img_ax.axis("off")
        for spine in img_ax.spines.values():
            spine.set_visible(True)
            spine.set_edgecolor(sev_color)
            spine.set_linewidth(3)

        ax.text(0.30 + 4.50 / 2, 6.52, "ATTACHED MEDIA",
                color="#8892B0", fontsize=7, fontweight="bold", ha="center", va="bottom")

        DX = 5.1     # detail column x-start (right of image)
    else:
        DX = 0.3

    DR = FW - 0.3   # detail column x-end

    # ── Issue type block ───────────────────────────────────────────────────
    ax.add_patch(FancyBboxPatch((DX, 5.55), DR - DX, 0.85,
                                boxstyle="round,pad=0.1", color="#0F3460", alpha=0.8))
    ax.text((DX + DR) / 2, 5.98, issue_label,
            color="white", fontsize=15 if has_image else 18, fontweight="bold",
            ha="center", va="center")

    # Severity indicator bar
    ax.add_patch(FancyBboxPatch((DX, 5.38), DR - DX, 0.12,
                                boxstyle="square,pad=0", color=sev_rgb))

    # ── Detail rows ───────────────────────────────────────────────────────
    # Each row: label at y, value at y-0.28
    def detail_row(label: str, value: str, y: float, value_color: str = "white",
                   value_size: int = 9, bold: bool = False):
        ax.text(DX, y, label, color="#00D4FF", fontsize=8, fontweight="bold")
        ax.text(DX, y - 0.27, value, color=value_color,
                fontsize=value_size, fontweight="bold" if bold else "normal")

    detail_row("ISSUE TYPE",         issue_text,         y=5.15)
    detail_row("LOCATION",           location[:55] + ("…" if len(location) > 55 else ""), y=4.62)
    detail_row("RESPONSIBLE AGENCY", agency,             y=4.09, value_color="#FFD700",
               value_size=10, bold=True)

    # Safety risk row with coloured label
    ax.text(DX, 3.56, "SAFETY RISK", color="#00D4FF", fontsize=8, fontweight="bold")
    ax.add_patch(FancyBboxPatch((DX, 3.05), DR - DX - 0.1, 0.38,
                                boxstyle="round,pad=0.05", color=risk_rgb, alpha=0.25))
    ax.text(DX + 0.15, 3.24, safety_label.upper(),
            color=risk_color, fontsize=9, fontweight="bold", va="center")

    # Severity level row
    detail_row("SEVERITY LEVEL", severity_val.upper(), y=2.82,
               value_color=sev_color, value_size=10, bold=True)

    # ── Summary (full width below image / details) ─────────────────────────
    if has_image:
        # One-line strip spanning full width at the bottom of the image column
        sum_bg_y = 0.55
        ax.add_patch(FancyBboxPatch((0.3, sum_bg_y), FW - 0.6, 0.42,
                                    boxstyle="round,pad=0.05", color="#0F3460", alpha=0.6))
        ax.text(FW / 2, sum_bg_y + 0.21,
                _wrap(summary, max_chars=120, max_lines=1),
                color="#CBD5E1", fontsize=8, ha="center", va="center")
    else:
        # Multi-line summary + complaint snippet
        ax.text(DX, 2.30, "SUMMARY", color="#00D4FF", fontsize=8, fontweight="bold")
        ax.text(DX, 2.00, _wrap(summary, max_chars=85, max_lines=3),
                color="#CBD5E1", fontsize=9, va="top")

        if complaint_txt:
            ax.text(DX, 1.00, "COMPLAINT DRAFT",
                    color="#00D4FF", fontsize=8, fontweight="bold")
            ax.text(DX, 0.72,
                    _wrap(complaint_txt, max_chars=95, max_lines=2),
                    color="#94A3B8", fontsize=8, va="top")

    # ── Footer ─────────────────────────────────────────────────────────────
    ax.add_patch(FancyBboxPatch((0, 0.0), FW, 0.48,
                                boxstyle="square,pad=0", color="#16213E"))
    ax.text(FW / 2, 0.24, "Report via nyc.gov/311 or call 311",
            color="#8892B0", fontsize=8, ha="center", va="center")

    plt.savefig(output_path, dpi=100, bbox_inches="tight", facecolor="#1A1A2E")
    plt.close(fig)

    logger.info("generate_visual_card: saved card", path=output_path)
    return output_path
