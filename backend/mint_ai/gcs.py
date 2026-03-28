"""Local file storage utility for product shot images.

Saves images to backend/output/{session_id}/ and returns URLs
served by FastAPI's static file mount.
"""

from pathlib import Path

# Output directory — relative to backend/
OUTPUT_DIR = Path(__file__).parent.parent / "output"


def upload_panel(session_id: str, filename: str, data: bytes) -> str:
    """Save image locally and return a URL path for static serving.

    Args:
        session_id: Session identifier (used as folder prefix).
        filename: e.g. "shot_01.png"
        data: Raw PNG bytes.

    Returns:
        URL path like /output/abc123/shot_01.png
    """
    session_dir = OUTPUT_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    file_path = session_dir / filename
    file_path.write_bytes(data)

    return f"/output/{session_id}/{filename}"
