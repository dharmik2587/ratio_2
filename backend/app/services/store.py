from __future__ import annotations
import hashlib, json, re
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from backend.app.core.config import UPLOAD_DIR, ANALYSIS_DIR, MAX_UPLOAD_BYTES

ID_RE = re.compile(r"^[a-f0-9]{32}$")


def ensure_dirs() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def valid_id(value: str) -> bool:
    return bool(ID_RE.fullmatch(value))


def decode_image(data: bytes) -> np.ndarray:
    """Decode while applying EXIF orientation; return OpenCV channel order."""
    try:
        with Image.open(BytesIO(data)) as source:
            source.verify()
        with Image.open(BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source)
            if image.mode in {"1", "P", "CMYK", "YCbCr", "LAB", "HSV"}:
                image = image.convert("RGB")
            array = np.asarray(image)
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise ValueError("Unable to decode this image") from exc
    if array.size == 0 or array.ndim not in (2, 3):
        raise ValueError("Unable to decode this image")
    if not np.issubdtype(array.dtype, np.number) or not np.all(np.isfinite(array)):
        raise ValueError("Image contains invalid numeric pixel values")
    if array.ndim == 3:
        if array.shape[2] == 3:
            array = cv2.cvtColor(array, cv2.COLOR_RGB2BGR)
        elif array.shape[2] == 4:
            array = cv2.cvtColor(array, cv2.COLOR_RGBA2BGRA)
        else:
            raise ValueError("Unsupported image channel layout")
    return np.ascontiguousarray(array)


def save_upload(data: bytes, filename: str, content_type: str) -> dict:
    ensure_dirs()
    if not data:
        raise ValueError("Uploaded file is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Image exceeds the configured 20 MB safety limit")
    array = decode_image(data)
    if array.shape[0] < 32 or array.shape[1] < 32:
        raise ValueError("Image must be at least 32×32 pixels")
    if array.shape[0] * array.shape[1] > 40_000_000:
        raise ValueError("Image exceeds the configured 40 megapixel safety limit")
    image_id = uuid4().hex
    ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/tiff": ".tif", "image/webp": ".webp"}.get(content_type, ".img")
    image_path = UPLOAD_DIR / f"{image_id}{ext}"
    image_path.write_bytes(data)  # immutable evidence bytes; normalization is in memory/derived outputs
    record = {"id": image_id, "filename": Path(filename).name,
              "sha256": hashlib.sha256(data).hexdigest(), "width": int(array.shape[1]),
              "height": int(array.shape[0]), "content_type": content_type,
              "path": str(image_path), "uploaded_at": utc_now()}
    (UPLOAD_DIR / f"{image_id}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def get_image(image_id: str) -> tuple[dict, np.ndarray]:
    if not valid_id(image_id):
        raise FileNotFoundError(image_id)
    meta_path = UPLOAD_DIR / f"{image_id}.json"
    if not meta_path.exists():
        raise FileNotFoundError(image_id)
    record = json.loads(meta_path.read_text(encoding="utf-8"))
    path = Path(record["path"])
    if not path.exists():
        raise FileNotFoundError("Stored image artifact missing")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != record["sha256"]:
        raise ValueError("Stored image integrity check failed")
    return record, decode_image(data)


def analysis_path(analysis_id: str) -> Path:
    if not valid_id(analysis_id):
        raise FileNotFoundError(analysis_id)
    return ANALYSIS_DIR / analysis_id


def get_analysis(analysis_id: str) -> dict:
    path = analysis_path(analysis_id) / "analysis.json"
    if not path.exists():
        raise FileNotFoundError(analysis_id)
    return json.loads(path.read_text(encoding="utf-8"))
