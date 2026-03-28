# ShotCraft AI — CLAUDE.md

AI product photography studio. Upload product photos, get professional shots in seconds. **Trae Hackathon 2026.**

---

## Project Structure

```
trae-hackathon/
├── CLAUDE.md
├── README.md
├── .gitignore                        # .env, output/, node_modules/ all ignored
├── docs/
│   ├── hackathon-info.md             # Schedule, rules, judging, prizes
│   ├── gemini-3.md                   # Gemini 3.1 Pro/Flash API reference
│   ├── nano-banana-image-generation.md  # Image gen API + prompting
│   ├── adk-llms.txt                  # ADK Python SDK reference
│   └── prompt-design.md              # Gemini prompting best practices
├── cloudbuild.yaml                   # Cloud Build config
├── backend/                          # FastAPI + ADK agent (Python, uv)
│   ├── .env                          # GOOGLE_API_KEY — gitignored, never commit
│   ├── Dockerfile                    # Python 3.12-slim + pip install
│   ├── .dockerignore                 # Excludes .env, output/, __pycache__/
│   ├── main.py                       # FastAPI app (POST /generate/stream, POST /edit, GET /health)
│   ├── pyproject.toml                # uv managed dependencies
│   ├── requirements.txt              # pip deps for Docker (mirrors pyproject.toml)
│   ├── run.sh                        # ./run.sh [--reload] — starts FastAPI on :8000
│   ├── output/                       # Generated PNG files — gitignored
│   └── mint_ai/                      # ADK agent package
│       ├── __init__.py
│       ├── agent.py                  # root_agent (product_photo_director) — 4 tools + system prompt
│       ├── gcs.py                    # upload_panel() → GCS public URL
│       ├── styles.py                 # 4 photography style definitions (studio, lifestyle, flat-lay, cinematic)
│       ├── tools/
│       │   ├── story_engine.py       # decompose_story() — Flash → N-shot JSON shot list
│       │   ├── image_gen.py          # generate_all_panels() / _generate_single_panel() — 2-step: Flash optimize → Flash Image + GCS
│       │   ├── panel_editor.py       # edit_panel() — 2-step: Flash edit prompt → Flash Image + GCS
│       │   └── character.py          # extract_character() — product photos → product description + reference sheet
│       └── prompts/
│           └── system.py             # MINT_DIRECTOR_INSTRUCTION — 3-phase product photo director
└── frontend/                         # Next.js 14 app (deploy to Vercel)
    ├── app/
    │   ├── layout.tsx                # Black Han Sans + Noto Sans KR, title: "ShotCraft"
    │   ├── globals.css               # CSS variables, animations, split layout classes
    │   ├── page.tsx                  # Root: Phase state machine (0=style, 1=input, 2=viewer)
    │   └── components/
    │       ├── ChatPanel.tsx         # Left panel: product input + edit chat
    │       └── PhotoViewer.tsx      # Right panel: product shots grid, loading skeletons
    └── (no api/ routes — frontend calls backend directly)
```

---

## API Keys & Environment

```bash
# backend/.env  (gitignored — never commit)
GOOGLE_API_KEY=your_key_here
```

The server loads `backend/.env` on startup via `load_dotenv(Path(__file__).parent / ".env")`.
Frontend has no secrets — it calls the backend directly (CORS open).

### Production (Cloud Run)
`GOOGLE_API_KEY` is stored in **Secret Manager** and mounted as env var via `--set-secrets`.
GCS auth uses the Cloud Run service account — no extra config needed.

---

## Models

| Step | Model | Thinking | Purpose |
|------|-------|----------|---------|
| Orchestrator | `gemini-3.1-pro-preview` | low | Directs 3-phase flow, calls tools, chats |
| `decompose_story` | `gemini-3-flash-preview` | low | N-shot JSON shot list from product brief |
| `_generate_single_panel` step 1 | `gemini-3-flash-preview` | minimal | Optimizes image prompt from shot metadata |
| `_generate_single_panel` step 2 | `gemini-3.1-flash-image-preview` | -- | Generates 1:1 product shot image |
| `edit_panel` step 1 | `gemini-3-flash-preview` | minimal | Creates updated prompt with edit applied |
| `edit_panel` step 2 | `gemini-3.1-flash-image-preview` | -- | Regenerates edited shot |
| `extract_character` | `gemini-3.1-pro-preview` | low | Product photos (1-4) → product description + reference sheet |

**Do NOT use** `gemini-3-pro-preview` — deprecated.

---

## Running Locally

```bash
# ADK dev UI — run from backend/
cd backend
uv run --project .. adk web --port 8080
# → http://localhost:8080/dev-ui/  →  select mint_ai

# FastAPI backend
cd backend
./run.sh              # port 8000
./run.sh --reload     # with hot reload

# Next.js frontend
cd frontend
npm run dev           # port 3000
```

---

## Agent Architecture (3-Phase Pipeline)

### ADK path (adk web)
```
User message
  → root_agent (gemini-3.1-pro-preview, product_photo_director)
      Phase 1: calls decompose_story() → presents shot list → asks for approval
      Phase 2: (after user confirms) calls generate_all_panels() in parallel
      Phase 3: calls edit_panel() on user edit request
```

### FastAPI path (FE → backend, SSE streaming)
```
POST /generate/stream  (primary endpoint)
  1. product photos (1-4) → extract_character() → product description + reference sheet
  2. InMemoryRunner(root_agent) decomposes brief → captures decompose_story result
     (agent creates shot list: scenes, camera angles, lighting, props)
  3. asyncio.gather() → _generate_single_panel() × N in parallel (semaphore: max 6 concurrent)
  4. each shot uploaded to GCS → SSE streams each panel as it completes
  5. SSE events: status → character → storyboard → panel (×N) → done

POST /generate  (non-streaming fallback, legacy)
  Same pipeline but returns full JSON at the end.

POST /edit
  → edit_panel() [direct call, no agent overhead]
    (FE sends back scene_description + face_description + outfit + camera_angle + mood)
  → edited shot uploaded to GCS → returns public URL
```

The key insight: agent runs for shot list decomposition (to get the system prompt's creative direction), then we break out of the event stream and do image gen in parallel ourselves.

---

## API Shapes

### POST /generate/stream (multipart/form-data, SSE)
Input: `story: str` (product brief), `style?: str` (default `"studio"`), `photos?: File[]` (1-4 product photos)

SSE events:
```
data: {"type": "status", "message": "Analyzing product photos..."}
data: {"type": "character", "face_description": "...", "face_ref_image": "..."}
data: {"type": "storyboard", "session_id": "abc123", "title": "...", "panel_count": 8, ...}
data: {"type": "panel", "panel": {"panel_number": 1, "image_url": "https://...", ...}}
...
data: {"type": "done", "session_id": "abc123"}
```

Panel object:
```json
{
  "panel_number": 1,
  "image_url": "https://storage.googleapis.com/mint-panels/{session}/shot_01.png",
  "dialogue": ["tagline text"],
  "narration": "hero",
  "image_prompt": "optimized prompt used",
  "scene_description": "...",
  "face_description": "product description",
  "character_name": "product name",
  "outfit": "styling / props",
  "character_expression": "product arrangement",
  "camera_angle": "eye level",
  "mood": "warm natural light"
}
```

### POST /edit (application/json)
Input:
```json
{
  "panel_number": 3,
  "instruction": "Add a coffee cup as a prop",
  "session_id": "abc123",
  "scene_description": "...",
  "face_description": "...",
  "outfit": "...",
  "style": "studio"
}
```
Output: `{ "panel_number": 3, "image_url": "https://...", "status": "success" }`

---

## Tool Signatures

### decompose_story(user_story, num_panels=30, style="studio") → dict
Creates a shot list from a product brief. Returns: `{"status", "storyboard": {"title", "characters": [{"name", "face_description", "role"}], "locations": [...], "panels": [{"panel_number", "act", "scene_description", "character_names", "outfits", "character_expressions", "dialogue", "dialogue_type", "camera_angle", "mood", "location_id"}]}, "panel_count"}`

### generate_all_panels(panels_json, style="studio", tool_context=None) → dict
Batch generates all shots in parallel (ThreadPoolExecutor, max 6 workers). Returns: `{"status", "session_id", "total_panels", "generated", "failed", "results": [...]}`

### _generate_single_panel(panel_number, scene_description, face_description, outfit, character_expression, camera_angle, mood, dialogue, ..., style, session_dir, session_id) → dict
Internal: generates one product shot (2-step: prompt optimize → image gen). Returns: `{"status", "panel_number", "image_path", "image_url", "artifact", "optimized_prompt"}`

### edit_panel(panel_number, edit_instruction, session_id, scene_description, face_description, outfit, ..., style, tool_context=None) → dict
Regenerates a specific shot with edits applied. Returns: `{"status", "panel_number", "image_path", "image_url", "artifact", "edit_applied"}`

### extract_character(image_path, style="studio", session_id="") → dict
Analyzes 1-4 product photos. Returns: `{"face_description": "detailed product description", "face_ref_image": "GCS URL or base64"}`

---

## 4 Photography Styles

| Style ID | Name | Description |
|----------|------|-------------|
| `studio` | Studio | Clean white/neutral background, soft diffused lighting, e-commerce look |
| `lifestyle` | Lifestyle | Natural environment, warm lighting, contextual props, aspirational setting |
| `flat-lay` | Flat Lay | Top-down, textured surface, organized arrangement, editorial precision |
| `cinematic` | Cinematic | Dramatic lighting, deep shadows, moody atmosphere, dark background |

All styles produce 1:1 square images at 1K resolution.

---

## Frontend State Machine

```
phase=0  → StyleSelector (pick studio / lifestyle / flat-lay / cinematic)
phase=1  → ProductInput (brief textarea + product photo upload, 1-4 images)
phase=2  → ShotViewer (product shots grid) + ChatEditor (edit chat)
```

Shot status: `"wait"` → `"gen"` → `"done"` (drives skeleton/spinner/image display)

Each shot carries full context: `scene_description`, `face_description`, `outfit`, `character_expression`, `camera_angle`, `mood` — used when sending edit requests.

---

## Deployment

### Backend — Cloud Run (asia-northeast3 / Seoul)
```
Region: asia-northeast3
Config: 2 CPU, 2Gi RAM, 300s timeout, max 3 instances
Secret: GOOGLE_API_KEY via Secret Manager
```

### Cloud Build
`cloudbuild.yaml` builds Docker image, pushes to Artifact Registry (`shotcraft/backend`), and deploys to Cloud Run (`shotcraft-backend`).

### Image Storage — GCS
```
Bucket: gs://mint-panels (asia-northeast3, public read)
URL pattern: https://storage.googleapis.com/mint-panels/{session_id}/shot_{NN}.png
Module: backend/mint_ai/gcs.py → upload_panel(session_id, filename, bytes)
```
Both `_generate_single_panel` and `edit_panel` upload to GCS after saving locally.
Falls back to base64 if GCS upload fails.

### Frontend — Vercel
Auto-deploys on push to `main` via Vercel Git integration.
Set `NEXT_PUBLIC_BACKEND_URL` env var in Vercel project settings to the Cloud Run URL.

---

## Key Technical Notes

### ToolContext dual-mode pattern
Both `generate_all_panels` and `edit_panel` have `tool_context=None`:
- adk web: ADK auto-injects real ToolContext → saves artifact to ADK store
- FastAPI: called directly without ToolContext → saves to disk + uploads to GCS

### SSE streaming
Primary endpoint is `POST /generate/stream`. Events flow as: `status` → `character` → `storyboard` → `panel` (one per shot, as they complete) → `done`. Frontend renders each shot the moment its SSE arrives.

### Parallel image gen with semaphore
`asyncio.gather(*tasks)` fires all shots, but `asyncio.Semaphore(6)` limits to 6 concurrent API calls to avoid rate limits. Each shot wrapped in `asyncio.to_thread()` because the Gemini SDK is sync.

### Breaking the agent event stream early
`_run_agent_stream_events()` captures the first `function_response` for `decompose_story`, then breaks out. This lets us use the agent's creative decomposition without waiting for it to sequentially generate all shots.

### Image format
`response_modalities=["TEXT", "IMAGE"]`, `aspect_ratio="1:1"`, `image_size="1K"`.
Images saved to disk as `shot_{NN}.png` + uploaded to GCS. API returns public GCS URLs (falls back to base64).

### Product analysis (extract_character)
Accepts 1-4 product photos. Step 1: Gemini Pro analyzes product → `face_description` (detailed product description) + `face_ref_prompt`. Step 2: Gemini Flash Image generates a product reference sheet. The `face_description` is injected into every shot prompt for product consistency.

---

## Hackathon Context

- **Hackathon**: Trae Hackathon 2026
- **Core concept**: Upload 1-4 product photos → AI analyzes the product → generates diverse professional product shots (studio, lifestyle, flat-lay, cinematic) → edit any shot with natural language
- **ADK dev UI** available for agent demo — run `adk web` from `backend/`

---

## Demo Prep & Pitch

### Demo Product Brief
```
Minimalist leather wallet, target: men in 20s, premium feel
```
Pre-copy this. Paste during demo. Upload product photos beforehand.

### Pitch Flow (3 minutes)

```
[0:00 - 0:20] HOOK

"Product photography costs $200-500 per shot.
A typical e-commerce listing needs 8-12 shots: hero, lifestyle, detail, flat-lay.
Small brands and solo sellers can't afford professional shoots.
What if AI could generate a complete product photo set
from a phone snapshot and a one-line brief?"


[0:20 - 0:40] PROBLEM

"The global product photography market is $6 billion.
90% of online purchase decisions are driven by product images.
But hiring a photographer, renting a studio, styling props —
that's thousands of dollars per SKU.
Marketplaces like Coupang, Amazon, Etsy have millions of sellers
who shoot products on their kitchen table."


[0:40 - 0:45] TRANSITION

"ShotCraft fixes this. Let me show you."
→ Switch to app (already open, style selector visible)


[0:45 - 0:50] STYLE SELECT

"I pick a style — Studio."
→ Click Studio


[0:50 - 1:05] INPUT

"I upload product photos..."
→ Upload 1-2 product photos
"...and type a quick brief: 'Minimalist leather wallet, premium feel.'"
→ Paste brief


[1:05 - 1:10] GENERATE

"Hit generate."
→ Click generate


[1:10 - 1:40] SHOTS LOADING (talk while waiting)

"What's happening: Gemini Pro analyzes my product photos —
materials, colors, shape, branding — creates a product reference sheet.
Then Flash creates a shot list: hero angles, lifestyle scenes,
flat-lay arrangements, all with specific lighting and props.
Flash Image generates every shot in parallel. Not one by one."
→ Shots start appearing in the grid.


[1:40 - 1:55] SHOW RESULTS

"Here are my product shots. Studio quality. Consistent product appearance.
Multiple angles, multiple moods — ready for my listing."
→ Scroll through shots. Pause on best ones.


[1:55 - 2:15] EDIT DEMO

"But what if I want changes? I click a shot and just chat:
'Add a coffee cup as a prop' or 'Make the lighting warmer.'"
→ Select shot → type edit → show regeneration.
"It regenerates just that shot. Real-time creative control."


[2:15 - 2:40] TECH + IMPACT

"Under the hood: Gemini 3.1 Pro as creative director.
Flash for shot planning. Flash Image for all shots in parallel.
Google ADK agent framework — real pipeline, not a wrapper.
Product photography market hits $10B by 2030.
We're not replacing photographers — we're giving every seller
studio-quality shots from a phone photo."


[2:40 - 3:00] CLOSE

"Your product. Your vision. Studio quality. Under a minute.
ShotCraft turns every seller into a product photographer.
Thank you."
```

### Q&A Prep

| Likely question | Answer |
|-----------------|--------|
| Product consistency across shots? | "Product photos → Gemini Pro extracts detailed product description → injected into every shot prompt" |
| How many shots? | "Default 30, configurable. All generated in parallel." |
| How long to generate? | "All shots fire in parallel with semaphore (6 concurrent) — under a minute total" |
| What models? | "Gemini 3.1 Pro orchestration, Flash shot planning, Flash Image generation. All via ADK" |
| How different from single image gen? | "Single image gen has no creative direction. We decompose into shot types, angles, lighting setups, props — coherent photo set" |
| Business model? | "Start with solo sellers and small brands. Next: API for e-commerce platforms, white-label for marketplaces" |

### Impact Numbers

- Product photography market: **$6B+ globally**
- 90% of online purchase decisions driven by product images
- Professional product shoot: **$200-500 per shot**, **$2K-5K per SKU**
- Millions of small sellers on Coupang, Amazon, Etsy shooting on kitchen tables
- We democratize studio-quality product photography
