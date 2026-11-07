"""Optional image generation provider; explicit opt-in, disabled by default.

Uses OpenAI-compatible /images/generations JSON API, not tied to any vendor.
Never sends data without STUDY_IMAGE_API_URL and STUDY_IMAGE_API_KEY.
"""
import base64
import json
import os
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
