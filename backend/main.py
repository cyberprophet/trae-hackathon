import asyncio
import base64
import json
import os
import tempfile
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from google.adk.runners import InMemoryRunner
from google.genai import types as genai_types
from pydantic import BaseModel

# Load .env before importing agent (needs GOOGLE_API_KEY)
load_dotenv(Path(__file__).parent / ".env", override=False)
load_dotenv(override=False)

# Import agent AFTER env is loaded
from mint_ai.agent import root_agent
from mint_ai.styles import STYLE_NAMES
from mint_ai.tools.character import extract_character
from mint_ai.tools.image_gen import (
    _detect_language,
    _generate_single_panel,
    _get_session_dir,
)
from mint_ai.tools.panel_editor import edit_panel
from mint_ai.tools.story_engine import decompose_story

# ---------------------------------------------------------------------------
# ADK runner — single instance, shared across all requests
# ---------------------------------------------------------------------------
_runner: InMemoryRunner | None = None


def get_runner() -> InMemoryRunner:
    global _runner
    if _runner is None:
        _runner = InMemoryRunner(agent=root_agent, app_name="pagemint")
    return _runner


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="PageMint Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(
    "/output",
    StaticFiles(directory=str(Path(__file__).parent / "output")),
    name="output",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _panel_to_base64(image_path: str) -> str:
    if not image_path:
        return ""
    path = Path(image_path)
    if not path.is_file():
        return ""
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    return f"data:image/png;base64,{data}"


def _make_user_message(text: str) -> genai_types.Content:
    return genai_types.Content(role="user", parts=[genai_types.Part(text=text)])


def _sse(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _run_agent_capture_tool(
    runner: InMemoryRunner,
    session_id: str,
    user_id: str,
    message: str,
    tool_name: str,
) -> dict:
    """
    Run the agent and capture the first FunctionResponse for `tool_name`.
    Breaks out of the event stream as soon as we have the result so the
    agent doesn't try to call downstream tools (we orchestrate those ourselves).
    """
    msg = _make_user_message(message)
    captured: dict = {}

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=msg,
    ):
        if not event.content or not event.content.parts:
            continue
        for part in event.content.parts:
            fr = getattr(part, "function_response", None)
            if fr and fr.name == tool_name:
                captured = dict(fr.response) if fr.response else {}
                break
        if captured:
            break  # stop consuming — we have what we need

    return captured


async def _run_agent_stream_events(
    runner: InMemoryRunner,
    session_id: str,
    user_id: str,
    message: str,
    tool_name: str,
):
    """
    Run the agent and yield SSE events for text/thinking/tool calls.
    Captures and returns the first FunctionResponse for `tool_name`.
    """
    msg = _make_user_message(message)
    captured: dict = {}

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=msg,
    ):
        if not event.content or not event.content.parts:
            continue

        for part in event.content.parts:
            # Text from the agent (thinking or response)
            if hasattr(part, "text") and part.text:
                is_thought = hasattr(part, "thought") and part.thought
                yield _sse({
                    "type": "thought" if is_thought else "text",
                    "content": part.text,
                    "author": event.author,
                })

            # Tool call (agent requesting a tool)
            fc = getattr(part, "function_call", None)
            if fc:
                yield _sse({
                    "type": "tool_call",
                    "name": fc.name,
                    "args": dict(fc.args) if fc.args else {},
                    "author": event.author,
                })

            # Tool response (tool returning result)
            fr = getattr(part, "function_response", None)
            if fr and fr.name == tool_name:
                captured = dict(fr.response) if fr.response else {}
                # Build a trimmed preview (full storyboard is too large)
                result_data = captured
                preview = {}
                if fr.name == "decompose_story":
                    sb = result_data.get("storyboard", {})
                    preview = {
                        "title": sb.get("title", ""),
                        "panel_count": result_data.get("panel_count", 0),
                        "characters": [c.get("name") for c in sb.get("characters", [])],
                        "acts": list({p.get("act", "") for p in sb.get("panels", [])}),
                    }
                else:
                    preview = {k: v for k, v in result_data.items() if k != "artifact"}
                yield _sse({
                    "type": "tool_result",
                    "name": fr.name,
                    "status": captured.get("status", "unknown"),
                    "preview": preview,
                })
                break

        if captured:
            break

    # Return captured result as final yield
    yield captured


def _build_panel_response(gen_result: dict, meta: dict, characters: dict) -> dict:
    """Build a panel response dict from generation result and storyboard metadata."""
    image_url = gen_result.get("image_url", "") or _panel_to_base64(gen_result.get("image_path", "")) if gen_result.get("status") == "success" else ""
    dialogue = meta.get("dialogue", "")

    # Multi-character support
    char_names = meta.get("character_names", [])
    if not char_names:
        cn = meta.get("character_name", "")
        char_names = [cn] if cn else []

    # Combined face description for edit context
    face_parts = [f"[{cn}] {characters.get(cn, '')}" for cn in char_names if characters.get(cn)]
    face_desc = "\n".join(face_parts) if face_parts else characters.get(char_names[0], "") if char_names else ""

    # Combined outfit/expression from dicts or fallback
    outfits_raw = meta.get("outfits", {})
    exprs_raw = meta.get("character_expressions", {})
    outfit = "; ".join(f"{k}: {v}" for k, v in outfits_raw.items()) if isinstance(outfits_raw, dict) and outfits_raw else meta.get("outfit", "")
    char_expr = "; ".join(f"{k}: {v}" for k, v in exprs_raw.items()) if isinstance(exprs_raw, dict) and exprs_raw else meta.get("character_expression", "")

    return {
        "panel_number": meta["panel_number"],
        "image_url": image_url,
        "dialogue": [dialogue] if isinstance(dialogue, str) and dialogue else (dialogue if isinstance(dialogue, list) else []),
        "narration": meta.get("act", ""),
        "image_prompt": gen_result.get("optimized_prompt", ""),
        # Rich fields for edit context
        "scene_description": meta.get("scene_description", ""),
        "face_description": face_desc,
        "character_name": ", ".join(char_names),
        "outfit": outfit,
        "character_expression": char_expr,
        "camera_angle": meta.get("camera_angle", ""),
        "mood": meta.get("mood", ""),
    }


# ---------------------------------------------------------------------------
# POST /generate/stream  (SSE — PRIMARY endpoint)
# ---------------------------------------------------------------------------
@app.post("/generate/stream")
async def generate_stream(
    story: str = Form(...),
    style: str = Form(default="studio"),
    photos: list[UploadFile] = File(default=[]),
):
    async def event_gen():
        runner = get_runner()
        character_description = ""

        # Create session_id early so product ref image can upload to GCS
        session_id = uuid.uuid4().hex[:8]

        # 1. Extract product details from uploaded photos
        uploaded_photos = [p for p in photos if p and p.filename]
        if uploaded_photos:
            yield _sse({"type": "status", "message": "Analyzing product photos..."})
            tmp_paths = []
            try:
                for photo in uploaded_photos:
                    suffix = Path(photo.filename).suffix or ".jpg"
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                        tmp.write(await photo.read())
                        tmp_paths.append(tmp.name)
                char_result = await asyncio.to_thread(extract_character, tmp_paths, style, session_id)
                character_description = char_result.get("face_description", "")
                face_ref_image = char_result.get("face_ref_image", "")
                # Send product description event to frontend
                if character_description:
                    yield _sse({
                        "type": "character",
                        "face_description": character_description,
                        "face_ref_image": face_ref_image,
                    })
            finally:
                for tp in tmp_paths:
                    os.unlink(tp)

        # 2. Fresh session
        session = await runner.session_service.create_session(
            app_name="pagemint",
            user_id="user",
            state={"character_description": character_description, "style": style},
        )

        # 3. Decompose story via agent — stream agent events (thinking, tool calls)
        style_name = STYLE_NAMES.get(style, "Studio")
        agent_prompt = f"Create a product photo set in {style_name} style.\n\nProduct brief: {story}"
        if character_description:
            agent_prompt += f"\n\nProduct appearance: {character_description}"

        yield _sse({"type": "status", "message": "Creating shot list..."})

        story_result = {}
        async for event_data in _run_agent_stream_events(
            runner=runner,
            session_id=session.id,
            user_id="user",
            message=agent_prompt,
            tool_name="decompose_story",
        ):
            if isinstance(event_data, str):
                # SSE string — forward to client
                yield event_data
            elif isinstance(event_data, dict):
                # Final captured result
                story_result = event_data

        storyboard = story_result.get("storyboard", {})
        panels_meta = storyboard.get("panels", [])
        if not panels_meta:
            yield _sse({"type": "error", "message": "Failed to create shot list"})
            return

        # Build character lookup: name → face_description
        characters_list = storyboard.get("characters", [])
        characters = {c["name"]: c.get("face_description", "") for c in characters_list}
        locations = {loc["id"]: loc.get("description", "") for loc in storyboard.get("locations", [])}

        # Create session dir for this generation (session_id created earlier for GCS uploads)
        session_dir = _get_session_dir(session_id)

        # 4. Send storyboard event (FE uses this for panel count + metadata)
        yield _sse({
            "type": "storyboard",
            "session_id": session_id,
            "title": storyboard.get("title", ""),
            "character_description": character_description,
            "characters": characters_list,
            "panel_count": len(panels_meta),
            "panels_meta": [
                {
                    "panel_number": p["panel_number"],
                    "act": p.get("act", ""),
                    "dialogue": p.get("dialogue", ""),
                    "character_names": p.get("character_names", [p.get("character_name", "")]),
                }
                for p in panels_meta
            ],
        })

        # 5. Fire all panels in parallel, stream each as it completes
        yield _sse({"type": "status", "message": f"Generating {len(panels_meta)} product shots in parallel..."})

        # Detect language from user story for consistent text rendering
        lang = _detect_language(story)

        queue: asyncio.Queue = asyncio.Queue()
        sem = asyncio.Semaphore(6)  # max 6 concurrent to avoid API rate limits

        async def gen_one_queued(panel_meta: dict):
            # Support multi-character panels
            char_names = panel_meta.get("character_names", [])
            if not char_names:
                # Fallback for single character_name field
                cn = panel_meta.get("character_name", "")
                char_names = [cn] if cn else []

            # Build combined face description for all characters in the panel
            face_parts = []
            for cn in char_names:
                fd = characters.get(cn, "")
                if fd:
                    face_parts.append(f"[{cn}] {fd}")
            face_desc = "\n".join(face_parts)

            # Build combined outfit/expression from dicts or fallback to strings
            outfits_raw = panel_meta.get("outfits", {})
            exprs_raw = panel_meta.get("character_expressions", {})
            if isinstance(outfits_raw, dict):
                outfit = "; ".join(f"{k}: {v}" for k, v in outfits_raw.items()) if outfits_raw else panel_meta.get("outfit", "")
            else:
                outfit = str(outfits_raw)
            if isinstance(exprs_raw, dict):
                char_expr = "; ".join(f"{k}: {v}" for k, v in exprs_raw.items()) if exprs_raw else panel_meta.get("character_expression", "")
            else:
                char_expr = str(exprs_raw)

            # Prepend location description for background consistency
            scene_desc = panel_meta.get("scene_description", "")
            loc_id = panel_meta.get("location_id", "")
            if loc_id and loc_id in locations:
                scene_desc = f"[Setting: {locations[loc_id]}] {scene_desc}"

            async with sem:
                try:
                    result = await asyncio.to_thread(
                        _generate_single_panel,
                        panel_number=panel_meta["panel_number"],
                        scene_description=scene_desc,
                        face_description=face_desc,
                        outfit=outfit,
                        character_expression=char_expr,
                        camera_angle=panel_meta.get("camera_angle", "medium shot"),
                        mood=panel_meta.get("mood", ""),
                        dialogue=panel_meta.get("dialogue", ""),
                        dialogue_type=panel_meta.get("dialogue_type", "none"),
                        session_dir=session_dir,
                        session_id=session_id,
                        style=style,
                        language=lang,
                    )
                except Exception as e:
                    import logging
                    logging.error(f"Shot {panel_meta['panel_number']} generation failed: {e}")
                    result = {"status": "error", "panel_number": panel_meta["panel_number"], "message": str(e)}
            await queue.put((result, panel_meta))

        tasks = [asyncio.create_task(gen_one_queued(p)) for p in panels_meta]

        for _ in range(len(panels_meta)):
            gen_result, meta = await queue.get()
            panel_data = _build_panel_response(gen_result, meta, characters)
            panel_data["session_id"] = session_id
            yield _sse({"type": "panel", "panel": panel_data})

        await asyncio.gather(*tasks)
        yield _sse({"type": "done", "session_id": session_id})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# POST /generate  (non-streaming fallback)
# ---------------------------------------------------------------------------
@app.post("/generate")
async def generate(
    story: str = Form(...),
    style: str = Form(default="studio"),
    photos: list[UploadFile] = File(default=[]),
):
    runner = get_runner()
    character_description = ""

    # Create session_id early so product ref image can upload to GCS
    session_id = uuid.uuid4().hex[:8]

    # 1. Extract product details from uploaded photos
    face_ref_image = ""
    uploaded_photos = [p for p in photos if p and p.filename]
    if uploaded_photos:
        tmp_paths = []
        try:
            for photo in uploaded_photos:
                suffix = Path(photo.filename).suffix or ".jpg"
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(await photo.read())
                    tmp_paths.append(tmp.name)
            char_result = await asyncio.to_thread(extract_character, tmp_paths, style, session_id)
            character_description = char_result.get("face_description", "")
            face_ref_image = char_result.get("face_ref_image", "")
        finally:
            for tp in tmp_paths:
                os.unlink(tp)

    # 2. Create a fresh session
    session = await runner.session_service.create_session(
        app_name="pagemint",
        user_id="user",
        state={"character_description": character_description, "style": style},
    )

    # 3. Decompose product brief via agent
    style_name = STYLE_NAMES.get(style, "Studio")
    agent_prompt = f"Create a product photo set in {style_name} style.\n\nProduct brief: {story}"
    if character_description:
        agent_prompt += f"\n\nProduct appearance: {character_description}"

    story_result = await _run_agent_capture_tool(
        runner=runner,
        session_id=session.id,
        user_id="user",
        message=agent_prompt,
        tool_name="decompose_story",
    )

    storyboard = story_result.get("storyboard", {})
    panels_meta = storyboard.get("panels", [])
    if not panels_meta:
        raise HTTPException(status_code=500, detail="Agent failed to create shot list")

    characters_list = storyboard.get("characters", [])
    characters = {c["name"]: c.get("face_description", "") for c in characters_list}
    locations = {loc["id"]: loc.get("description", "") for loc in storyboard.get("locations", [])}

    # Create session dir (session_id created earlier for GCS uploads)
    session_dir = _get_session_dir(session_id)

    # 4. Generate all panels in parallel
    lang = _detect_language(story)

    async def gen_one(panel_meta: dict):
        # Multi-character support
        char_names = panel_meta.get("character_names", [])
        if not char_names:
            cn = panel_meta.get("character_name", "")
            char_names = [cn] if cn else []

        face_parts = [f"[{cn}] {characters.get(cn, '')}" for cn in char_names if characters.get(cn)]
        face_desc = "\n".join(face_parts)

        outfits_raw = panel_meta.get("outfits", {})
        exprs_raw = panel_meta.get("character_expressions", {})
        outfit = "; ".join(f"{k}: {v}" for k, v in outfits_raw.items()) if isinstance(outfits_raw, dict) and outfits_raw else panel_meta.get("outfit", "")
        char_expr = "; ".join(f"{k}: {v}" for k, v in exprs_raw.items()) if isinstance(exprs_raw, dict) and exprs_raw else panel_meta.get("character_expression", "")

        scene_desc = panel_meta.get("scene_description", "")
        loc_id = panel_meta.get("location_id", "")
        if loc_id and loc_id in locations:
            scene_desc = f"[Setting: {locations[loc_id]}] {scene_desc}"

        result = await asyncio.to_thread(
            _generate_single_panel,
            panel_number=panel_meta["panel_number"],
            scene_description=scene_desc,
            face_description=face_desc,
            outfit=outfit,
            character_expression=char_expr,
            camera_angle=panel_meta.get("camera_angle", "medium shot"),
            mood=panel_meta.get("mood", ""),
            dialogue=panel_meta.get("dialogue", ""),
            dialogue_type=panel_meta.get("dialogue_type", "none"),
            session_dir=session_dir,
            session_id=session_id,
            style=style,
            language=lang,
        )
        return result, panel_meta

    results = await asyncio.gather(*[gen_one(p) for p in panels_meta])

    # 5. Assemble response
    response_panels = []
    for gen_result, meta in results:
        panel_data = _build_panel_response(gen_result, meta, characters)
        panel_data["session_id"] = session_id
        response_panels.append(panel_data)

    response_panels.sort(key=lambda p: p["panel_number"])

    return {
        "session_id": session_id,
        "character_description": character_description,
        "face_ref_image": face_ref_image,
        "storyboard_title": storyboard.get("title", ""),
        "panels": response_panels,
    }


# ---------------------------------------------------------------------------
# POST /generate/more  (add more shots to existing session)
# ---------------------------------------------------------------------------
class MoreRequest(BaseModel):
    session_id: str
    story: str
    style: str = "studio"
    face_description: str = ""
    count: int = 4
    existing_count: int = 0  # how many shots already exist


@app.post("/generate/more")
async def generate_more(req: MoreRequest):
    """Generate additional product shots for an existing session."""
    session_id = req.session_id
    session_dir = _get_session_dir(session_id)
    lang = _detect_language(req.story)
    start_num = req.existing_count + 1

    # 1. Decompose additional shots
    result = await asyncio.to_thread(decompose_story, req.story, req.count, req.style)
    if result.get("status") != "success":
        raise HTTPException(status_code=500, detail=result.get("message", "Failed to create shot list"))

    storyboard = result["storyboard"]
    panels_meta = storyboard.get("panels", [])
    characters_list = storyboard.get("characters", [])
    characters = {c["name"]: c.get("face_description", "") for c in characters_list}
    locations = {loc["id"]: loc.get("description", "") for loc in storyboard.get("locations", [])}

    # Re-number panels to continue from existing
    for i, pm in enumerate(panels_meta):
        pm["panel_number"] = start_num + i

    # Override face_description if provided
    face_override = req.face_description

    # 2. Generate all in parallel
    async def gen_one(panel_meta: dict):
        char_names = panel_meta.get("character_names", [])
        if not char_names:
            cn = panel_meta.get("character_name", "")
            char_names = [cn] if cn else []

        face_parts = [f"[{cn}] {characters.get(cn, '')}" for cn in char_names if characters.get(cn)]
        face_desc = face_override or "\n".join(face_parts)

        outfits_raw = panel_meta.get("outfits", {})
        exprs_raw = panel_meta.get("character_expressions", {})
        outfit = "; ".join(f"{k}: {v}" for k, v in outfits_raw.items()) if isinstance(outfits_raw, dict) and outfits_raw else ""
        char_expr = "; ".join(f"{k}: {v}" for k, v in exprs_raw.items()) if isinstance(exprs_raw, dict) and exprs_raw else ""

        scene_desc = panel_meta.get("scene_description", "")
        loc_id = panel_meta.get("location_id", "")
        if loc_id and loc_id in locations:
            scene_desc = f"[Setting: {locations[loc_id]}] {scene_desc}"

        r = await asyncio.to_thread(
            _generate_single_panel,
            panel_number=panel_meta["panel_number"],
            scene_description=scene_desc,
            face_description=face_desc,
            outfit=outfit,
            character_expression=char_expr,
            camera_angle=panel_meta.get("camera_angle", "medium shot"),
            mood=panel_meta.get("mood", ""),
            dialogue=panel_meta.get("dialogue", ""),
            dialogue_type=panel_meta.get("dialogue_type", "none"),
            session_dir=session_dir,
            session_id=session_id,
            style=req.style,
            language=lang,
        )
        return r, panel_meta

    results = await asyncio.gather(*[gen_one(p) for p in panels_meta])

    response_panels = []
    for gen_result, meta in results:
        panel_data = _build_panel_response(gen_result, meta, characters)
        panel_data["session_id"] = session_id
        response_panels.append(panel_data)

    response_panels.sort(key=lambda p: p["panel_number"])
    return {"session_id": session_id, "panels": response_panels}


# ---------------------------------------------------------------------------
# POST /edit
# ---------------------------------------------------------------------------
class EditRequest(BaseModel):
    panel_number: int
    instruction: str
    session_id: str
    scene_description: str = ""
    face_description: str = ""
    outfit: str = ""
    character_expression: str = ""
    camera_angle: str = ""
    mood: str = ""
    dialogue: str = ""
    style: str = "studio"


@app.post("/edit")
async def edit(req: EditRequest):
    result = await asyncio.to_thread(
        edit_panel,
        panel_number=req.panel_number,
        edit_instruction=req.instruction,
        session_id=req.session_id,
        scene_description=req.scene_description,
        face_description=req.face_description,
        outfit=req.outfit,
        character_expression=req.character_expression,
        camera_angle=req.camera_angle,
        mood=req.mood,
        dialogue=req.dialogue,
        style=req.style,
    )

    image_url = result.get("image_url", "") or _panel_to_base64(result.get("image_path", ""))
    return {
        "panel_number": req.panel_number,
        "image_url": image_url,
        "status": result.get("status", "unknown"),
    }


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok", "service": "pagemint"}
