#!/usr/bin/env python3
"""NYC StreetFix Demo Script — End-to-end demonstration of the 311 co-pilot.

Scenario: Blocked drain causing sidewalk flooding
1. Simulate user reporting via text (+ optional image)
2. Agent classifies the issue, extracts incident data, geocodes location
3. Generates a 311 complaint text
4. Generates a visual hazard card
5. Translates the summary to Spanish and Chinese
6. Saves all outputs to demo/output/
7. Prints a formatted summary to the console
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

# Ensure the project root is on the path when running from demo/
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

app = typer.Typer(help="NYC StreetFix Demo")
console = Console()

OUTPUT_DIR = PROJECT_ROOT / "demo" / "output"

DEMO_DESCRIPTION = (
    "This drain keeps flooding every time it rains. The water is covering the entire sidewalk "
    "and pooling into the street. There is visible debris blocking the catch basin grate."
)
DEMO_LOCATION = "Corner of Newark Ave and Grove St, Jersey City, NJ"


def _make_mock_incident() -> dict:
    """Return mock incident data for --mock mode."""
    return {
        "issue_type": "clogged_catch_basin",
        "severity": "high",
        "safety_risk": "pedestrian_slip_hazard",
        "location_text": DEMO_LOCATION,
        "coordinates": {"lat": 40.7178, "lng": -74.0431},
        "likely_agency": "DEP / 311",
        "report_summary": (
            "A catch basin at the corner of Newark Ave and Grove St is blocked by debris, "
            "causing standing water 3-4 inches deep on the sidewalk and roadway. "
            "This presents a significant pedestrian slip hazard."
        ),
        "follow_up_questions": [],
        "language": "en",
        "media_attached": False,
        "complaint_text": (
            "Catch basin at the corner of Newark Avenue and Grove Street is completely blocked "
            "with debris, causing standing water approximately 3-4 inches deep on the sidewalk "
            "and roadway. This presents an immediate pedestrian slip hazard and requires urgent "
            "inspection and cleaning. Category: Catch Basin Clogged/Flooding. Agency: DEP / 311."
        ),
        "visual_card_path": str(OUTPUT_DIR / "visual_card.png"),
        "translations": {
            "es": (
                "Una alcantarilla en la esquina de Newark Ave y Grove St está completamente "
                "bloqueada por escombros, causando agua estancada de aproximadamente 8-10 cm de "
                "profundidad en la acera y la calzada. Esto presenta un peligro inmediato de "
                "resbalamiento para los peatones."
            ),
            "zh": (
                "纽瓦克大道与格罗夫街交叉口的雨水篦子被杂物完全堵塞，导致人行道和路面积水约8-10厘米深。"
                "这对行人造成立即的滑倒危险，需要紧急检查和清理。类别：雨水篦子堵塞/洪水。机构：DEP / 311。"
            ),
        },
        "flood_history": {
            "status": "ok",
            "count": 4,
            "recent_incidents": [
                {
                    "date": "2026-03-01",
                    "type": "Catch Basin Clogged/Flooding",
                    "status": "Closed",
                    "address": "100 NEWARK AVE",
                    "borough": "HUDSON COUNTY",
                },
                {
                    "date": "2026-01-15",
                    "type": "Sewer Backup/Flooding",
                    "status": "Closed",
                    "address": "150 GROVE ST",
                    "borough": "HUDSON COUNTY",
                },
            ],
            "last_reported": "2026-03-01",
        },
        "mta_elevator_status": None,
    }


def _save_outputs(incident_data: dict) -> None:
    """Save all demo outputs to demo/output/."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Save incident JSON
    incident_json_path = OUTPUT_DIR / "incident.json"
    with open(incident_json_path, "w") as f:
        json.dump(incident_data, f, indent=2, default=str)
    console.print(f"  [green]Saved:[/green] {incident_json_path}")

    # Save complaint text
    complaint_path = OUTPUT_DIR / "complaint.txt"
    complaint_text = incident_data.get("complaint_text", "")
    with open(complaint_path, "w") as f:
        f.write(complaint_text)
    console.print(f"  [green]Saved:[/green] {complaint_path}")

    # Save translations
    translations_path = OUTPUT_DIR / "translations.json"
    with open(translations_path, "w") as f:
        json.dump(incident_data.get("translations", {}), f, indent=2, ensure_ascii=False)
    console.print(f"  [green]Saved:[/green] {translations_path}")


def _print_summary(incident_data: dict) -> None:
    """Print a formatted summary to the console."""
    console.print()
    console.print(Panel.fit(
        "[bold cyan]NYC StreetFix — Incident Report[/bold cyan]",
        border_style="cyan",
    ))

    # Main incident table
    table = Table(box=box.ROUNDED, show_header=False, border_style="blue")
    table.add_column("Field", style="cyan", width=22)
    table.add_column("Value", style="white")

    severity_colors = {
        "critical": "bold red",
        "high": "bold orange1",
        "moderate": "bold yellow",
        "low": "bold green",
    }
    sev = incident_data.get("severity", "moderate")
    sev_style = severity_colors.get(sev, "white")

    table.add_row("Issue Type", incident_data.get("issue_type", "").replace("_", " ").title())
    table.add_row("Severity", f"[{sev_style}]{sev.upper()}[/{sev_style}]")
    table.add_row("Safety Risk", incident_data.get("safety_risk", "none").replace("_", " ").title())
    table.add_row("Location", incident_data.get("location_text", "N/A"))

    coords = incident_data.get("coordinates")
    if coords:
        table.add_row("Coordinates", f"{coords['lat']:.4f}, {coords['lng']:.4f}")

    table.add_row("Agency", f"[bold yellow]{incident_data.get('likely_agency', '311')}[/bold yellow]")
    table.add_row("Media Attached", "Yes" if incident_data.get("media_attached") else "No")

    console.print(table)

    # Summary
    summary = incident_data.get("report_summary", "")
    if summary:
        console.print()
        console.print(Panel(
            summary,
            title="[bold]Report Summary[/bold]",
            border_style="green",
        ))

    # Complaint text
    complaint = incident_data.get("complaint_text", "")
    if complaint:
        console.print()
        console.print(Panel(
            complaint,
            title="[bold]311 Complaint Text[/bold]",
            border_style="yellow",
        ))

    # Translations
    translations = incident_data.get("translations", {})
    if translations:
        console.print()
        lang_names = {"es": "Spanish", "zh": "Chinese", "ru": "Russian", "bn": "Bengali", "ko": "Korean"}
        for lang, text in translations.items():
            lang_name = lang_names.get(lang, lang.upper())
            console.print(Panel(
                text,
                title=f"[bold]Translation — {lang_name}[/bold]",
                border_style="magenta",
            ))

    # Flood history
    flood = incident_data.get("flood_history")
    if flood and flood.get("status") == "ok":
        console.print()
        console.print(f"[bold cyan]Flood History (last 90 days):[/bold cyan] "
                      f"{flood['count']} previous reports near this location")
        if flood.get("last_reported"):
            console.print(f"  Last reported: {flood['last_reported']}")

    # Visual card
    visual_card = incident_data.get("visual_card_path")
    if visual_card and Path(visual_card).exists():
        console.print()
        console.print(f"[bold green]Visual card saved:[/bold green] {visual_card}")


async def _run_live_demo(image_path: str | None) -> None:
    """Run the demo using real API calls."""
    from agents.orchestrator import NYCStreetFixOrchestrator

    console.print("[bold cyan]Starting NYC StreetFix Live Demo...[/bold cyan]")
    console.print(f"[dim]Description:[/dim] {DEMO_DESCRIPTION}")
    console.print(f"[dim]Location:[/dim] {DEMO_LOCATION}")
    if image_path:
        console.print(f"[dim]Image:[/dim] {image_path}")
    console.print()

    visual_card_path = str(OUTPUT_DIR / "visual_card.png")

    with console.status("[bold green]Running full incident workflow..."):
        orchestrator = NYCStreetFixOrchestrator()
        incident = await orchestrator.run_full_journey(
            description=DEMO_DESCRIPTION,
            location_text=DEMO_LOCATION,
            image_path=image_path,
            translate_to=["es", "zh"],
            visual_card_output_path=visual_card_path,
        )

    incident_data = incident.model_dump()
    incident_data["visual_card_path"] = incident.visual_card_path or visual_card_path

    console.print("[bold green]Workflow complete![/bold green] Saving outputs...")
    _save_outputs(incident_data)
    _print_summary(incident_data)


@app.command()
def main(
    mock: bool = typer.Option(False, "--mock", help="Run in mock mode without real API calls"),
    image: str | None = typer.Option(None, "--image", help="Path to an image file for the demo"),
) -> None:
    """Run the NYC StreetFix end-to-end demo.

    Demonstrates: blocked drain → classification → extraction → geocoding →
    311 complaint draft → visual card → translations → output files.

    Use --mock to run without API keys.
    """
    console.print()
    console.print(Panel.fit(
        "[bold cyan]NYC StreetFix[/bold cyan]\n"
        "[dim]Multimodal 311 Co-Pilot for New York City[/dim]",
        border_style="cyan",
    ))
    console.print()

    if mock:
        console.print("[bold yellow]Running in MOCK mode (no API calls)[/bold yellow]")
        console.print()
        incident_data = _make_mock_incident()
        console.print("[bold green]Mock workflow complete! Saving outputs...[/bold green]")
        _save_outputs(incident_data)
        _print_summary(incident_data)
    else:
        console.print("[bold green]Running in LIVE mode (real API calls)[/bold green]")
        console.print("[dim]Ensure .env is configured with valid API keys.[/dim]")
        console.print()
        try:
            asyncio.run(_run_live_demo(image_path=image))
        except KeyboardInterrupt:
            console.print("[yellow]Demo interrupted by user.[/yellow]")
            raise typer.Exit(0)
        except Exception as exc:
            console.print(f"[bold red]Error during live demo:[/bold red] {exc}")
            console.print("[dim]Try running with --mock to test without API keys.[/dim]")
            raise typer.Exit(1)

    console.print()
    console.print(Panel.fit(
        "[bold green]Demo complete![/bold green]\n"
        f"Output files saved to: [cyan]{OUTPUT_DIR}[/cyan]",
        border_style="green",
    ))


if __name__ == "__main__":
    app()
