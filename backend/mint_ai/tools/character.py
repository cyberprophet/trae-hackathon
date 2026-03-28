import base64
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image

from ..gcs import upload_panel
from ..styles import get_product_analysis, STYLE_NAMES


def extract_character(image_path: str, style: str = "studio", session_id: str = "") -> dict:
    """Analyze product photos and generate a product reference sheet.

    Two-step process:
    1) Gemini Pro analyzes the product image(s) → face_description (product description)
       + face_ref_prompt (product reference prompt)
    2) Gemini Flash Image generates a product reference sheet image from the prompt

    Args:
        image_path: Path to the uploaded product image file, or a comma-separated
            string of paths for multiple product images (up to 4).
        style: Photography style ID for style-specific product analysis.
        session_id: Session ID for GCS upload. If provided, uploads reference to GCS.

    Returns:
        dict with:
        - face_description: Detailed product description for image generation prompts.
        - face_ref_image: GCS URL (if session_id provided) or base64 data URL.
    """
    client = genai.Client()
    style_name = STYLE_NAMES.get(style, "스튜디오")
    product_analysis = get_product_analysis(style)

    # Load product image(s) — supports list of paths or comma-separated string
    if isinstance(image_path, list):
        image_paths = [str(p).strip() for p in image_path if str(p).strip()]
    else:
        image_paths = [p.strip() for p in image_path.split(",") if p.strip()]
    product_images = []
    for p in image_paths[:4]:  # Max 4 images
        img = Image.open(p)
        img.load()
        product_images.append(img)

    # Step 1: Analyze product images → face_description + face_ref_prompt
    try:
        contents = list(product_images) + [
            f"""You are a professional {style_name} product photographer and creative director.

Analyze the provided product photo(s) and create TWO outputs:

1. FACE_DESCRIPTION: A detailed product description optimized for {style_name} product photography.
   Include ALL of the following:
   - Product type and category
   - Materials and finish (matte, glossy, metallic, textured, transparent, etc.)
   - Colors (primary, secondary, accent) with specific color names
   - Shape, proportions, and dimensions (relative if exact not known)
   - Surface details (logos, labels, embossing, patterns, seams, hardware)
   - Brand elements if visible (logo placement, typography, brand colors)
   - Key visual features that must be captured in every shot
   Style direction: {product_analysis}
   Write as a single detailed paragraph.

2. FACE_REF_PROMPT: A complete image generation prompt to create a 1:1 square product reference
   sheet showing this product on a clean white background. Show the product from front view and
   three-quarter angle side by side. {style_name} style photography. Clean, well-lit, neutral.
   Include the full product description in the prompt for the image generator.

Return as JSON:
{{"face_description": "...", "face_ref_prompt": "..."}}"""
        ]

        response = client.models.generate_content(
            model="gemini-3.1-pro-preview",
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(thinking_level="low"),
            ),
        )

        import json
        result = json.loads(response.text)
        face_description = result.get("face_description", "")
        face_ref_prompt = result.get("face_ref_prompt", "")

    except Exception as e:
        return {"status": "error", "message": f"Step 1 failed: {e}"}

    # Step 2: Generate product reference sheet image (using product photo as visual reference)
    face_ref_image = ""
    if face_ref_prompt:
        try:
            img_response = client.models.generate_content(
                model="gemini-3.1-flash-image-preview",
                contents=[
                    product_images[0],
                    f"Using the photo above as visual reference for the product, generate: {face_ref_prompt}",
                ],
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                    image_config=types.ImageConfig(aspect_ratio="1:1", image_size="1K"),
                ),
            )

            for part in img_response.candidates[0].content.parts:
                if part.inline_data is not None:
                    raw_bytes = part.inline_data.data
                    if isinstance(raw_bytes, str):
                        raw_bytes = base64.b64decode(raw_bytes)

                    # Save to disk
                    out_dir = Path(image_paths[0]).parent
                    ref_path = out_dir / "product_ref.png"
                    with open(ref_path, "wb") as f:
                        f.write(raw_bytes)

                    # Upload to GCS if session_id provided, otherwise fall back to base64
                    if session_id:
                        try:
                            face_ref_image = upload_panel(session_id, "product_ref.png", raw_bytes)
                        except Exception:
                            b64 = base64.b64encode(raw_bytes).decode()
                            face_ref_image = f"data:image/png;base64,{b64}"
                    else:
                        b64 = base64.b64encode(raw_bytes).decode()
                        face_ref_image = f"data:image/png;base64,{b64}"
                    break

        except Exception:
            # Non-fatal — we still have the text description
            pass

    return {
        "status": "success",
        "face_description": face_description,
        "face_ref_image": face_ref_image,
    }
