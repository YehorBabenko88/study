"""Optional image generation provider; explicit opt-in, disabled by default.

Uses OpenAI-compatible /images/generations JSON API, not tied to any vendor.
Never sends data without STUDY_IMAGE_API_URL and STUDY_IMAGE_API_KEY.
"""
import base64
import json
import os
import struct
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse
from uuid import UUID
from visual_memory import get_scene

MEDIA = Path(__file__).with_name("generated_media")
MAX_IMAGE_BYTES = 8_000_000

def configured():
    return bool(os.environ.get("STUDY_IMAGE_API_URL") and os.environ.get("STUDY_IMAGE_API_KEY"))

def prompt_for(scene, instruction=""):
    if len(instruction) > 400:
        raise ValueError("Instruction too long")
    target = scene["target"]
    anchors = scene["anchors"]
    links = "; ".join(
        f"sound {a['sound_fragment']}: {a['object_name']}, action {a['meaning_link']}"
        for a in anchors
    )
    return (
        "Create one imaginative, vivid educational mnemonic illustration. "
        "Include every specified object and its action; use a coherent whimsical story. "
        "Do not put text, labels or letters in the picture. "
        "The learner must associate the target meaning with the sound cues. "
        f"Meaning: {target['translation']}. Sound-object-action links: {links}. "
        f"User-requested visual changes: {instruction}"
    )

def generate(scene_id, instruction=""):
    if not configured():
        raise RuntimeError("Image provider not configured; set STUDY_IMAGE_API_URL and STUDY_IMAGE_API_KEY")
    scene_id = str(UUID(scene_id))
    scene = get_scene(scene_id)
    if scene is None:
        raise KeyError("scene_not_found")
    endpoint = os.environ["STUDY_IMAGE_API_URL"]
    url = urlparse(endpoint)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.fragment:
        raise ValueError("Provider URL must be HTTPS with no embedded credentials")
    model = os.environ.get("STUDY_IMAGE_MODEL", "gpt-image-1")
    body = json.dumps({
        "model": model,
        "prompt": prompt_for(scene, instruction),
        "size": "1024x1024",
        "response_format": "b64_json",
        "n": 1,
    }).encode("utf-8")
    req = Request(endpoint, data=body, headers={
        "Authorization": "Bearer " + os.environ["STUDY_IMAGE_API_KEY"],
        "Content-Type": "application/json",
    }, method="POST")
    with urlopen(req, timeout=90) as response:
        if response.status != 200:
            raise RuntimeError("Image provider returned an error")
        raw = response.read(12_000_001)
    if len(raw) > 12_000_000:
        raise RuntimeError("Provider response too large")
    payload = json.loads(raw)
    encoded = payload["data"][0]["b64_json"]
    binary = base64.b64decode(encoded, validate=True)
    if not binary.startswith(b"\x89PNG\r\n\x1a\n") or len(binary) > MAX_IMAGE_BYTES:
        raise RuntimeError("Expected PNG image under size limit")
    MEDIA.mkdir(exist_ok=True)
    target = MEDIA / (scene_id + ".png")
    tmp = MEDIA / (scene_id + ".tmp")
    try:
        tmp.write_bytes(binary)
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)
    return {"image_url": "/v1/mnemonics/" + scene_id + "/generated-image", "bytes": len(binary), "model": model}

def image_bytes(scene_id):
    scene_id = str(UUID(scene_id))
    if get_scene(scene_id) is None:
        return None
    target = MEDIA / (scene_id + ".png")
    return target.read_bytes() if target.is_file() else None

def import_png(scene_id, binary):
    """Store a user-selected PNG for a saved scene; no cloud call."""
    scene_id = str(UUID(scene_id))
    if get_scene(scene_id) is None:
        raise KeyError("scene_not_found")
    if not 24 <= len(binary) <= MAX_IMAGE_BYTES or not binary.startswith(b"\\x89PNG\\r\\n\\x1a\\n"):
        raise ValueError("Only PNG images up to 8 MB are supported")
    if binary[12:16] != b"IHDR":
        raise ValueError("Invalid PNG header")
    width, height = struct.unpack(">II", binary[16:24])
    if not (1 <= width <= 4096 and 1 <= height <= 4096):
        raise ValueError("Invalid image dimensions")
    # Pillow verifies PNG decoding and CRCs when available; otherwise reject to
    # avoid trusting a header-only check.
    try:
        from PIL import Image
        from io import BytesIO
    except ImportError as exc:
        raise RuntimeError("Install Pillow to validate imported PNG files") from exc
    try:
        with Image.open(BytesIO(binary)) as im:
            im.verify()
        with Image.open(BytesIO(binary)) as im:
            if im.format != "PNG" or im.size != (width, height):
                raise ValueError("Invalid PNG content")
            im.load()
    except Exception as exc:
        raise ValueError("Corrupt or unsupported PNG") from exc
    MEDIA.mkdir(exist_ok=True)
    target = MEDIA / (scene_id + ".png")
    tmp = MEDIA / (scene_id + ".upload.tmp")
    try:
        tmp.write_bytes(binary)
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)
    return {"image_url": "/v1/mnemonics/" + scene_id + "/generated-image",
            "bytes": len(binary), "source": "user_import"}
