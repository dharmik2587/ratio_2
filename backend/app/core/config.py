from __future__ import annotations
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = Path(os.getenv("RATIO_DATA_DIR", ROOT / "data"))
CONFIG_PATH = Path(os.getenv("RATIO_CONFIG", ROOT / "configs" / "stage1.json"))
PHASE2_CONFIG_PATH = Path(os.getenv("RATIO_PHASE2_CONFIG", ROOT / "configs" / "phase2.json"))
UPLOAD_DIR = DATA_DIR / "uploads"
ANALYSIS_DIR = DATA_DIR / "analyses"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/tiff", "image/webp"}


def load_scientific_config() -> dict:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)

def load_phase2_config() -> dict:
    from ratio_core.phase2_config import validate_phase2_config
    with PHASE2_CONFIG_PATH.open(encoding="utf-8") as f:
        config=json.load(f)
    validate_phase2_config(config)
    return config
