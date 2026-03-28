"""Single source of truth for all 4 photography styles."""

STYLE_PROMPTS: dict[str, str] = {
    "studio": (
        "Professional studio product photography. Clean white or neutral background. "
        "Soft diffused lighting with minimal shadows. Sharp focus on the product with "
        "shallow depth of field. High-key lighting setup. Crisp e-commerce look. "
        "Square 1:1 composition filling the frame with the product as the sole subject."
    ),
    "lifestyle": (
        "Lifestyle product photography in a natural environment. Warm natural lighting "
        "streaming through windows or golden hour glow. Contextual props and aspirational "
        "setting that tells a story. Product integrated naturally into a styled scene. "
        "Square 1:1 composition with the product as the clear focal point amid a curated setting."
    ),
    "flat-lay": (
        "Top-down flat lay product photography. Organized arrangement on a textured surface "
        "(marble, linen, wood). Complementary props and accessories placed with editorial precision. "
        "Even overhead lighting with soft shadows. Clean negative space for balance. "
        "Square 1:1 composition shot from directly above."
    ),
    "cinematic": (
        "Cinematic product photography. Dramatic directional lighting with deep shadows "
        "and rich color grading. Moody atmosphere with volumetric light or haze. "
        "Dark background with selective accent lighting highlighting the product's form. "
        "Square 1:1 composition with bold, high-contrast visual impact."
    ),
}

STYLE_CONFIGS: dict[str, dict] = {
    "studio": {"aspect_ratio": "1:1"},
    "lifestyle": {"aspect_ratio": "1:1"},
    "flat-lay": {"aspect_ratio": "1:1"},
    "cinematic": {"aspect_ratio": "1:1"},
}

STYLE_NAMES: dict[str, str] = {
    "studio": "스튜디오",
    "lifestyle": "라이프스타일",
    "flat-lay": "플랫레이",
    "cinematic": "시네마틱",
}

# Style-specific photographer personas for decompose_story
STYLE_WRITERS: dict[str, str] = {
    "studio": "professional e-commerce product photographer specializing in clean studio shots",
    "lifestyle": "lifestyle product photographer who creates aspirational brand imagery",
    "flat-lay": "editorial flat-lay photographer known for curated overhead compositions",
    "cinematic": "cinematic product photographer specializing in dramatic, moody brand visuals",
}

# Style-specific product analysis instructions for extract_character
STYLE_PRODUCT_ANALYSIS: dict[str, str] = {
    "studio": (
        "Studio product analysis. Focus on the product's exact shape, proportions, material "
        "finish (matte, glossy, metallic), color accuracy, and surface texture. Note any logos, "
        "labels, or embossed details. Clean isolated description suitable for white-background shots."
    ),
    "lifestyle": (
        "Lifestyle product analysis. Describe the product's visual identity and the mood it evokes. "
        "Note colors, materials, and textures that suggest complementary environments and props. "
        "Identify the target audience aesthetic (modern, rustic, luxurious, minimalist)."
    ),
    "flat-lay": (
        "Flat-lay product analysis. Describe the product's top-down silhouette, footprint shape, "
        "and surface appearance from above. Note packaging, accessories, or components that could "
        "surround it in a flat-lay arrangement. Identify colors for palette coordination."
    ),
    "cinematic": (
        "Cinematic product analysis. Focus on the product's form, contours, and surfaces that "
        "catch dramatic light. Note reflective vs matte areas, edges that create rim-light appeal, "
        "and color tones that suit dark moody backgrounds."
    ),
}


def get_style_prompt(style_id: str) -> str:
    """Get the style prompt for a given style ID, defaulting to studio."""
    return STYLE_PROMPTS.get(style_id, STYLE_PROMPTS["studio"])


def get_style_config(style_id: str) -> dict:
    """Get the style config (aspect_ratio etc.) for a given style ID."""
    return STYLE_CONFIGS.get(style_id, STYLE_CONFIGS["studio"])


def get_style_writer(style_id: str) -> str:
    """Get the photographer persona for a given style ID."""
    return STYLE_WRITERS.get(style_id, STYLE_WRITERS["studio"])


def get_product_analysis(style_id: str) -> str:
    """Get product analysis instruction for a given style ID."""
    return STYLE_PRODUCT_ANALYSIS.get(style_id, STYLE_PRODUCT_ANALYSIS["studio"])
