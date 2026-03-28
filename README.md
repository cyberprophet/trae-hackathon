# ShotCraft AI — Product Photography Studio

Upload 1-4 product photos, type a brief, and get a complete set of professional product shots in under a minute. Edit any shot with natural language.

**Built for the Trae Hackathon 2026.**

---

## How It Works

```
[Product Photos + Brief]
        |
        v
[extract_character]  ->  product analysis (materials, colors, shape, branding)
        |
        v
[decompose_story]  ->  shot list (scenes, angles, lighting, props)
        |
        v
[generate shots x N]  ->  all shots in parallel:
        |                    1. Flash optimizes image prompt
        |                    2. Flash Image generates 1:1 product shot
        v
[Shot Gallery]  ->  product shots in grid + edit chat
        |
        v
[Edit]  ->  "Add a coffee cup as a prop" -> regenerates just that shot
```

---

## 4 Photography Styles

| Style | Best For |
|-------|----------|
| **Studio** (default) | Clean e-commerce shots, white background, product hero |
| **Lifestyle** | Aspirational brand imagery, natural environments, storytelling |
| **Flat Lay** | Editorial overhead compositions, curated arrangements |
| **Cinematic** | Dramatic moody shots, dark backgrounds, premium brands |

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **Agent Framework** | Google ADK |
| **Orchestrator** | Gemini 3.1 Pro (low thinking) |
| **Shot Planning** | Gemini 3 Flash (low thinking) |
| **Image Generation** | Gemini 3.1 Flash Image |
| **Backend** | FastAPI on Cloud Run (Seoul) |
| **Frontend** | Next.js 14 on Vercel |
| **Image Storage** | Google Cloud Storage |

---

## Architecture

```
mint_ai/
├── agent.py                 # root_agent (product_photo_director, 4 tools)
├── styles.py                # 4 photography style definitions
├── gcs.py                   # GCS upload utility
├── tools/
│   ├── story_engine.py      # decompose_story() — brief -> N-shot shot list
│   ├── image_gen.py         # generate_all_panels() — parallel batch generation
│   ├── panel_editor.py      # edit_panel() — 2-step: edit prompt -> regen image
│   └── character.py         # extract_character() — product photos -> description + reference
└── prompts/
    └── system.py            # 3-phase director: Plan -> Generate -> Edit
```

### Key Design Decisions

- **2-step prompt pipeline**: Each shot goes through a Flash prompt optimizer before image generation — narrative paragraphs, not keyword lists
- **Product description injection**: Product photos are analyzed once, and the description is injected into every shot prompt for consistency
- **Parallel generation**: All shots fire simultaneously via `asyncio.gather()` with semaphore (max 6 concurrent) — under 1 minute
- **SSE streaming**: Primary endpoint streams each shot as it completes, so the UI renders progressively
- **Agent + direct call hybrid**: Agent handles creative shot planning, then we break out of the event stream and do image gen in parallel ourselves

---

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Node.js 18+
- A [Google AI Studio](https://aistudio.google.com/) API key

### Setup

```bash
# Clone
git clone <repo-url>
cd trae-hackathon

# Backend — set API key
echo "GOOGLE_API_KEY=your_key_here" > backend/.env

# Install Python deps
cd backend && uv sync && cd ..

# Install frontend deps
cd frontend && npm install && cd ..
```

### Run Locally

```bash
# Option 1: ADK Dev UI (interactive agent chat)
cd backend && uv run --project .. adk web --port 8080
# -> http://localhost:8080/dev-ui/  ->  select mint_ai

# Option 2: FastAPI backend + Next.js frontend
cd backend && ./run.sh          # port 8000
cd frontend && npm run dev      # port 3000
# -> http://localhost:3000
```

---

## API

### POST /generate/stream (multipart/form-data, SSE)

| Field | Type | Description |
|-------|------|-------------|
| `story` | string | Product brief (e.g., "Minimalist leather wallet, premium feel") |
| `style` | string | `studio`, `lifestyle`, `flat-lay`, or `cinematic` (default: `studio`) |
| `photos` | file[] | 1-4 product photos for AI analysis |

Streams SSE events: `status` -> `character` -> `storyboard` -> `panel` (x N) -> `done`.

### POST /edit (JSON)

| Field | Type | Description |
|-------|------|-------------|
| `panel_number` | int | Which shot to edit |
| `instruction` | string | Natural language edit (e.g., "Add a coffee cup as a prop") |
| `session_id` | string | Session from generation |
| `scene_description` | string | Current scene context |
| `face_description` | string | Product description |
| `outfit` | string | Current styling/props |
| `style` | string | Photography style |

Returns the regenerated shot with a new `image_url`.

---

## Deployment

- **Backend**: Cloud Run (Seoul / asia-northeast3)
- **Frontend**: Vercel (auto-deploys on push to main)
- **Images**: GCS bucket (public read, Seoul region)

To deploy your own instance:
1. A GCP project with Cloud Run, GCS, and Secret Manager
2. Cloud Build or manual `gcloud run deploy --source backend/`
3. Vercel project linked to the repo with `NEXT_PUBLIC_BACKEND_URL` env var

---

## License

Built at the Trae Hackathon 2026.
Powered by Google ADK + Gemini 3.1 Pro + Gemini 3.1 Flash Image.
