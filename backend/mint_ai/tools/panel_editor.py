import base64
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types

from ..gcs import upload_panel
from ..styles import get_style_config, get_style_prompt
from .image_gen import OUTPUT_BASE

EDIT_PROMPT_TEMPLATE = """You are an expert product photography prompt specialist.
Given an original product shot's metadata and an edit instruction, create a NEW optimized
image generation prompt that applies ONLY the requested edit while preserving everything else.

RULES:
1. Write as a narrative paragraph, NOT keywords.
2. Start with the style directive below.
3. Keep the PRODUCT DESCRIPTION exactly as provided — this is the hero subject and must remain
   consistent and faithfully rendered.
4. Apply the edit instruction — change ONLY what was requested.
5. Preserve: camera angle, mood/lighting, styling/props, product arrangement UNLESS the edit
   explicitly changes them.
6. If overlay text is present, describe it as elegant typography overlaid on the image — specify
   font style, placement, and color that complements the scene.
7. Ensure the scene fills the entire canvas — full-bleed composition, background extends to every
   edge corner to corner.
8. The product must remain the clear hero/focal point. All other elements support it.
9. Maintain professional studio-quality lighting: describe key light direction, fill, rim/accent
   lights, reflections, and shadows that enhance the product's form and texture.

STYLE DIRECTIVE:
{style}

PRODUCT DESCRIPTION (permanent):
{face_description}

ORIGINAL SHOT:
- Scene / Setting: {scene_description}
- Styling / Props: {outfit}
- Product State / Arrangement: {character_expression}
- Camera Angle: {camera_angle}
- Mood / Lighting: {mood}
- Overlay Text: {dialogue}

EDIT INSTRUCTION: {edit_instruction}

Return ONLY the new image prompt. Nothing else."""


def edit_panel(
    panel_number: int,
    edit_instruction: str,
    session_id: str,
    scene_description: str,
    face_description: str,
    outfit: str,
    character_expression: str = "",
    camera_angle: str = "",
    mood: str = "",
    dialogue: str = "",
    style: str = "studio",
    language: str = "English",
    tool_context: Optional[object] = None,
) -> dict:
    """Regenerate a specific product shot with edits. Two-step process:
    1) Gemini 3 Flash (minimal thinking) creates an updated image prompt applying the edit.
    2) Gemini 3.1 Flash Image generates the new product shot image.

    The orchestrator passes the original shot metadata plus the user's edit request.
    Only the specified edit is applied — everything else is preserved.

    Args:
        panel_number: Which shot to edit (1-based index).
        edit_instruction: What the user wants changed (e.g., "change lighting to golden hour").
        session_id: The session ID from generate_all_panels — used to save edited shot in the same folder.
        scene_description: Original scene/setting description from the shot plan.
        face_description: PERMANENT product description (appearance, form, materials).
        outfit: Styling/props used in this shot.
        character_expression: Product state/arrangement in this shot.
        camera_angle: Original camera angle.
        mood: Original mood/lighting.
        dialogue: Original overlay text/tagline.
        tool_context: Optional ADK ToolContext — saves artifacts when running via adk web.

    Returns:
        dict with updated artifact filename, panel_number, image_path, and the edit applied.
    """
    client = genai.Client()

    # Use the same session directory as the original generation
    session_dir = OUTPUT_BASE / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Generate edited prompt
    edit_response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=[EDIT_PROMPT_TEMPLATE.format(
            style=get_style_prompt(style),
            face_description=face_description,
            scene_description=scene_description,
            outfit=outfit,
            character_expression=character_expression,
            camera_angle=camera_angle,
            mood=mood,
            dialogue=dialogue,
            edit_instruction=edit_instruction,
        )],
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level="minimal"),
        ),
    )
    edited_prompt = edit_response.text.strip()

    # Step 2: Generate image
    style_cfg = get_style_config(style)
    try:
        image_response = client.models.generate_content(
            model="gemini-3.1-flash-image-preview",
            contents=[edited_prompt],
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
                image_config=types.ImageConfig(aspect_ratio=style_cfg["aspect_ratio"], image_size="1K"),
            ),
        )

        for part in image_response.candidates[0].content.parts:
            if part.inline_data is not None:
                filename = f"shot_{panel_number:02d}.png"
                image_path = session_dir / filename

                raw_bytes = part.inline_data.data
                if isinstance(raw_bytes, str):
                    raw_bytes = base64.b64decode(raw_bytes)
                with open(image_path, "wb") as f:
                    f.write(raw_bytes)

                if tool_context is not None:
                    artifact_part = types.Part(
                        inline_data=types.Blob(
                            mime_type=part.inline_data.mime_type,
                            data=part.inline_data.data,
                        )
                    )
                    tool_context.save_artifact(filename, artifact_part)

                # Upload to GCS
                gcs_url = ""
                try:
                    gcs_url = upload_panel(session_id, filename, raw_bytes)
                except Exception:
                    pass

                return {
                    "status": "success",
                    "panel_number": panel_number,
                    "image_path": str(image_path),
                    "image_url": gcs_url,
                    "artifact": filename,
                    "edit_applied": edit_instruction,
                }

        return {"status": "error", "panel_number": panel_number, "message": "No image in response"}

    except Exception as e:
        return {"status": "error", "panel_number": panel_number, "message": str(e)}
