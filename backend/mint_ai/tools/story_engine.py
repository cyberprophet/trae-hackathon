import json

from google import genai
from google.genai import types

from ..styles import get_style_writer


STORYBOARD_PROMPT = """You are a {writer_persona}.
Given a product description and creative brief, create a professional product photography shot list in {style_name} style.

Rules:
- Create exactly {num_panels} shots.
- Organize shots into these categories (adjust count based on total):
  - Hero Shot (1-2): The signature product image. Clean, prominent, defines the product identity.
  - Detail Shot (1-2): Close-up of textures, materials, craftsmanship, labels, or unique features.
  - Lifestyle Shot (1-2): Product in use or in an aspirational environment with contextual props.
  - Scale Shot (0-1): Product next to a common object to communicate size and proportions.
  - In-Use Shot (1-2): Product being used or interacted with (hands, model, or implied usage).
  - Flat Lay (0-1): Top-down arranged composition with the product and complementary items.
  - Group/Collection (0-1): Multiple variants, colorways, or the product with its accessories.
  - Packaging (0-1): Product with its packaging or unboxing moment.
- Vary angles, lighting setups, and compositions across shots for a diverse visual library.
- CRITICAL: ALL text fields (title, descriptions) MUST be in the SAME language as the user's input. If user writes in English, everything is English. If user writes in Korean, everything is Korean.
- Each scene_description must be a SELF-CONTAINED visual paragraph that an image generator can
  use WITHOUT any other context. It must include BOTH:
  (a) BACKGROUND/ENVIRONMENT: specific surface, backdrop, lighting setup, props, color palette,
      and styling details.
  (b) PRODUCT PLACEMENT: exact position, angle, and presentation of the product in the frame.
  BAD: "Product on a table with nice lighting" (too vague)
  GOOD: "A matte black wireless speaker sits centered on a light oak tabletop. Soft diffused
  window light from the left creates a gentle gradient across the speaker's curved surface.
  A small potted succulent and a linen napkin are placed to the right, slightly out of focus.
  Warm neutral tones throughout. The speaker's LED indicator glows a soft blue."
- Consider the product's material properties for lighting: reflective surfaces need controlled
  highlights, matte products benefit from softer wrapping light, transparent items need
  backlighting or edge lighting.

CRITICAL — Lighting & Consistency:
- Define the PRIMARY LIGHTING SETUP for each shot (key light position, fill, rim/accent).
- Maintain consistent color temperature within related shots.
- Hero shots should use the most flattering, clean lighting for the product.
- Detail shots may use raking light to reveal texture.
- Lifestyle shots should use natural or environmental lighting appropriate to the setting.
- Cinematic shots should use dramatic directional lighting with intentional shadows.

CRITICAL — Product presentation rules:
- face_description is the PERMANENT product description: shape, materials, colors, brand elements,
  key features. It NEVER changes between shots.
- The product must be recognizably the same item in every shot — consistent color, shape, branding.
- Props and styling should complement, never overshadow, the product.
- Each shot should serve a distinct purpose in telling the product's visual story.

Return ONLY valid JSON. No markdown, no code fences. Exactly this structure:

{{
  "title": "shot list title / product name",
  "characters": [
    {{
      "name": "product name",
      "face_description": "PERMANENT product description: type, materials, colors, finish, shape, dimensions, brand elements, key visual features. Example: Matte black cylindrical wireless speaker, 15cm tall, soft-touch rubberized finish, brushed aluminum base ring, subtle embossed logo on front, LED status ring on top glowing blue, fabric mesh grille wrapping the body",
      "role": "hero product"
    }}
  ],
  "locations": [
    {{
      "id": "location_1",
      "name": "White studio setup",
      "description": "Clean white seamless backdrop with soft diffused overhead lighting. White acrylic shooting surface with subtle reflection. Two softbox key lights at 45 degrees."
    }}
  ],
  "panels": [
    {{
      "panel_number": 1,
      "act": "hero / detail / lifestyle / scale / in-use / flat-lay / group / packaging",
      "location_id": "location_1",
      "scene_description": "SELF-CONTAINED visual paragraph: describe the FULL ENVIRONMENT (surface, backdrop, lighting, props, colors) + PRODUCT PLACEMENT (position, angle, presentation). Must work as a standalone image prompt.",
      "character_names": ["product name"],
      "outfits": {{"product name": "product state or configuration for this shot (e.g. lid open, power on, unboxed)"}},
      "character_expressions": {{"product name": "product highlight for this shot (e.g. LED ring glowing blue, steam rising, label facing camera)"}},
      "dialogue": "",
      "dialogue_type": "none",
      "camera_angle": "eye-level / low angle / top-down / 45-degree / macro / three-quarter / straight-on / worm's eye",
      "mood": "lighting and color mood description"
    }}
  ]
}}

Product description and brief:
{user_story}"""


def decompose_story(user_story: str, num_panels: int = 4, style: str = "studio") -> dict:
    """Analyze a product description and produce a structured photography shot list as JSON.

    Calls Gemini 3 Flash (low thinking) to act as a professional product photographer.
    Takes the user's product description and creative brief, then returns a full shot list
    with product definitions, location setups, per-shot scene descriptions, camera angles,
    and lighting/mood.

    The orchestrator should present this shot list to the user for review and editing
    before proceeding to image generation.

    Args:
        user_story: The user's product description and creative brief in free text. Any language.
        num_panels: Target number of shots. Default 4, minimum 4.
        style: Photography style ID (studio, lifestyle, flat-lay, cinematic).

    Returns:
        dict with 'storyboard' containing the full structured JSON shot list,
        or 'error' if generation failed.
    """
    if num_panels < 4:
        num_panels = 4

    client = genai.Client()

    response = None
    try:
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[STORYBOARD_PROMPT.format(
                user_story=user_story,
                num_panels=num_panels,
                writer_persona=get_style_writer(style),
                style_name=style,
            )],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(thinking_level="low"),
            ),
        )

        storyboard = json.loads(response.text)
        return {
            "status": "success",
            "storyboard": storyboard,
            "panel_count": len(storyboard.get("panels", [])),
        }

    except json.JSONDecodeError as e:
        raw = response.text[:500] if response else "(no response)"
        return {"status": "error", "message": f"Invalid JSON from model: {e}", "raw": raw}
    except Exception as e:
        return {"status": "error", "message": str(e)}
