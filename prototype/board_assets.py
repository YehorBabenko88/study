"""Local board assets and opt-in OCR. Only on loopback, not multi-user secure."""
from pathlib import Path
from runtime_paths import data_path
from uuid import uuid4, UUID
from io import BytesIO
import os
import tempfile
from PIL import Image, ImageOps, UnidentifiedImageError

ROOT=data_path(__file__,"board_assets")
MAX_BYTES=8_000_000
MAX_PIXELS=16_000_000

def _decode(data):
    if not isinstance(data,bytes) or not 1<=len(data)<=MAX_BYTES:
        raise ValueError("Image must be at most 8 MB")
    try:
        with Image.open(BytesIO(data)) as src:
            if src.format not in ("PNG","JPEG","WEBP"):
                raise ValueError("Unsupported image type")
            if src.width*src.height>MAX_PIXELS:
                raise ValueError("Image exceeds pixel limit")
            src.load()
            im=ImageOps.exif_transpose(src).convert("RGB")
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError) as exc:
        raise ValueError("Invalid image") from exc
    return im

def store(data, *, asset_id=None):
    im=_decode(data)
    asset_id=str(UUID(asset_id)) if asset_id is not None else str(uuid4())
    ROOT.mkdir(exist_ok=True)
    encoded=BytesIO()
    im.save(encoded,format="PNG",optimize=True)
    payload=encoded.getvalue()
    path=ROOT/(asset_id+".png")
    # Publish complete bytes atomically and without replacing an original asset.
    with tempfile.NamedTemporaryFile(dir=ROOT, prefix=".asset-", delete=False) as output:
        temporary=Path(output.name)
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())
    try:
        try: os.link(temporary,path)
        except FileExistsError:
            if path.read_bytes()!=payload: raise ValueError("Asset ID already contains different image")
    finally:
        temporary.unlink()
    return {"asset_id":asset_id,"image_url":"/v1/board-assets/"+asset_id}

def read(asset_id):
    name=str(UUID(asset_id))+".png"
    path=ROOT/name
    return path.read_bytes() if path.is_file() else None

def recognize(data,lang="deu"):
    im=_decode(data)
    if lang not in ("deu","rus","deu+rus"):
        raise ValueError("Unsupported OCR language")
    try:
        import pytesseract
        from pytesseract import TesseractNotFoundError, TesseractError
    except ImportError:
        return {"status":"unavailable","reason":"pytesseract_missing","text":""}
    try:
        text=pytesseract.image_to_string(im,lang=lang,config="--psm 3",timeout=35)
    except (TesseractNotFoundError,TesseractError,RuntimeError) as exc:
        return {"status":"unavailable","reason":"tesseract_or_language_data_missing","text":""}
    return {"status":"ok","text":text[:50000],"engine":"tesseract","review_status":"unverified_ocr"}
