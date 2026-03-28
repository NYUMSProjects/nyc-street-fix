# NYC StreetFix

**Multimodal 311 Co-Pilot for New York City**

NYC StreetFix is an AI agent that helps New Yorkers report street-level issues (potholes, flooding, illegal dumping, broken signals, accessibility barriers) by accepting photos, voice recordings, and text — then producing structured incident reports, 311 complaint drafts, visual hazard cards, and multilingual summaries.

Built with Google Gemini, Google ADK, and NYC Open Data.

---

## Architecture

See [docs/architecture.md](docs/architecture.md) for a full Mermaid diagram and component details.

```
User Input (photo/voice/text)
        ↓
  Live API Layer (TextChat / AudioChat / LiveStream)
        ↓
  Orchestrator (Google ADK Agent)
        ↓
  Tools: classify_scene → extract_incident → geocode_location
       → draft_311_report → generate_visual_card → translate_summary
       → check_mta_elevators → lookup_flood_history
        ↓
  Outputs: IncidentReport JSON, 311 Complaint, Visual Card, Translations
```

---

## Setup

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd nyc-streetfix

# Install with uv (recommended)
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Or with pip
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your API keys:

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Yes | Google AI Studio API key — [get one here](https://aistudio.google.com/) |
| `GOOGLE_MAPS_API_KEY` | Yes | Google Maps Platform API key with Geocoding API enabled |
| `MTA_API_KEY` | No | MTA developer API key for elevator/escalator status |
| `NYC_OPEN_DATA_APP_TOKEN` | No | NYC Open Data app token for higher rate limits |

---

## Running Each Phase

### Phase 0 — Text Chat (no vision, no live)

```python
import asyncio
from live.stream import TextChat

async def main():
    chat = TextChat()
    response = await chat.chat("There's a pothole on 5th Ave and 14th St.")
    print(response)

asyncio.run(main())
```

### Phase 1 — Vision Classification

```python
import asyncio
from tools.classify_scene import classify_scene

async def main():
    result = await classify_scene(
        image_path="demo/sample_images/pothole.jpg",
        description="Large hole in the road"
    )
    print(result.issue_type, result.severity, result.confidence)

asyncio.run(main())
```

### Phase 2 — Audio Transcription

```python
import asyncio
from live.stream import AudioChat

async def main():
    audio = AudioChat()
    response = await audio.transcribe_and_respond("recording.mp3")
    print(response)

asyncio.run(main())
```

### Phase 3 — Full Live API

```python
from live.stream import LiveStream
stream = LiveStream()
# See docs/architecture.md for full setup requirements
```

### Full Automated Journey

```python
import asyncio
from agents.orchestrator import NYCStreetFixOrchestrator

async def main():
    orchestrator = NYCStreetFixOrchestrator()
    incident = await orchestrator.run_full_journey(
        description="This drain keeps flooding every time it rains.",
        location_text="Corner of Newark Ave and Grove St",
        image_path="demo/sample_images/drain.jpg",
        translate_to=["es", "zh"],
        visual_card_output_path="demo/output/visual_card.png",
    )
    print(incident.model_dump_json(indent=2))

asyncio.run(main())
```

---

## Demo

### Mock mode (no API keys required)

```bash
python demo/demo_script.py --mock
```

### Live mode (requires API keys in .env)

```bash
python demo/demo_script.py

# With an image
python demo/demo_script.py --image demo/sample_images/drain.jpg
```

Demo outputs are saved to `demo/output/`:
- `incident.json` — full structured incident record
- `complaint.txt` — 311-ready complaint text
- `visual_card.png` — shareable hazard card
- `translations.json` — multilingual summaries

---

## Development

### Run tests

```bash
pytest
pytest -v                    # verbose
pytest tests/test_e2e.py     # single file
```

### Lint and format

```bash
ruff check .
ruff format .
```

### Project structure

```
nyc-streetfix/
├── agents/
│   ├── orchestrator.py     # ADK agent + NYCStreetFixOrchestrator class
│   └── prompts.py          # System prompt + few-shot examples
├── config/
│   ├── settings.py         # Pydantic BaseSettings
│   └── taxonomy.py         # IssueType, SeverityLevel, SafetyRisk enums
├── demo/
│   ├── demo_script.py      # CLI demo (typer + rich)
│   ├── sample_images/      # Add test images here
│   └── output/             # Generated outputs
├── docs/
│   └── architecture.md     # Mermaid diagram + docs
├── live/
│   └── stream.py           # TextChat, AudioChat, LiveStream
├── schemas/
│   └── incident.py         # IncidentReport, ClassificationResult
├── tests/
│   ├── test_classify_scene.py
│   ├── test_extract_incident.py
│   ├── test_geocode_location.py
│   ├── test_draft_311_report.py
│   ├── test_generate_visual_card.py
│   ├── test_translate_summary.py
│   ├── test_check_mta_elevators.py
│   ├── test_lookup_flood_history.py
│   └── test_e2e.py
└── tools/
    ├── classify_scene.py
    ├── extract_incident.py
    ├── geocode_location.py
    ├── draft_311_report.py
    ├── generate_visual_card.py
    ├── translate_summary.py
    ├── check_mta_elevators.py
    └── lookup_flood_history.py
```

---

## Extension Ideas

| Extension | Description |
|-----------|-------------|
| Subway Accessibility Companion | Route planning using live MTA elevator outage data |
| Flood & Storm Safety Agent | Real-time hazard reports + evacuation checklists |
| Neighborhood Dashboard | Aggregate reports into a public-facing heatmap |
| Follow-up Tracker | Status updates on submitted 311 reports |

---

## License

MIT
