"""Phase 3C — Synthetic Hazard Test Range.

Reproducible generator of controlled synthetic hazards and benign perturbations
on real/procedural base scenes, with pixel-accurate ground-truth masks.

Everything here is labeled SYNTHETIC_BENCHMARK or SYNTHETIC_DEMO. No synthetic
sample is ever presented as a natural lunar observation.

Scene-level separation is enforced by construction: samples inherit the base
scene id, and benchmark splits (development / validation / held-out) operate on
whole scenes, never on individual samples.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any
import hashlib
import json
import cv2
import numpy as np

GENERATION_VERSION = "1.0.0"

HAZARD_TYPES = [
    "fake_boulder",
    "fake_ridge",
    "fake_crater",
    "false_depression",
    "high_frequency_texture",
    "edge_exaggeration",
    "artificial_terrain_structure",
]

BENIGN_TYPES = [
    "mild_sharpening",
    "denoising",
    "contrast_adjustment",
    "brightness_change",
    "compression",
    "resampling",
    "sensor_noise",
    "illumination_variation",
]

CONFUSION_TYPES = [
    "shadow",
    "strong_albedo_boundary",
    "high_texture",
    "low_dem_slope",
    "coarse_reference",
    "registration_uncertainty",
    "partial_dem_coverage",
    "mixed_terrain",
]


@dataclass(frozen=True)
class SyntheticSample:
    sample_id: str
    classification: str          # SYNTHETIC_BENCHMARK | SYNTHETIC_DEMO | REAL
    base_scene_id: str
    base_image_id: str
    modified_image_id: str
    hazard_type: str             # hazard, benign, or confusion type
    ground_truth_mask: np.ndarray | None  # pixel mask of the injected alteration
    injection_location: list[int]
    injection_scale: int
    injection_strength: float
    random_seed: int
    generation_version: str
    metadata: dict[str, Any]
    modified_image: np.ndarray | None = None
    ground_truth: bool = True

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ground_truth_mask"] = _mask_sha256(self.ground_truth_mask)
        d.pop("modified_image", None)
        d["has_ground_truth_mask"] = self.ground_truth_mask is not None
        return d


def _mask_sha256(mask: np.ndarray | None) -> str | None:
    if mask is None:
        return None
    return hashlib.sha256(np.asarray(mask, np.uint8).tobytes()).hexdigest()


def sample_sha256(sample: SyntheticSample) -> str:
    """Deterministic sample identity over all scalar fields."""
    d = sample.to_dict()
    d.pop("modified_image_id", None)
    return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:16]


def _center(shape: tuple[int, int], seed: int) -> tuple[int, int]:
    rng = np.random.default_rng(seed)
    h, w = shape[:2]
    return int(rng.integers(w // 4, 3 * w // 4)), int(rng.integers(h // 4, 3 * h // 4))


def _apply_hazard(image: np.ndarray, hazard_type: str, cx: int, cy: int, scale: int,
                  strength: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Return (modified image, binary ground-truth mask) for one hazard type."""
    rng = np.random.default_rng(seed)
    out = image.copy().astype(np.float32)
    h, w = out.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    grayscale = out.ndim == 2

    def draw(mask_roi: np.ndarray):
        mask[mask_roi] = 255

    if hazard_type == "fake_boulder":
        r = max(3, scale)
        y, x = np.ogrid[:h, :w]
        disc = (x - cx) ** 2 + (y - cy) ** 2 <= r * r
        draw(disc)
        bump = 220.0 * strength * np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2 * (r / 2.2) ** 2))
        if grayscale:
            out[disc] += bump[disc]
        else:
            for ch in range(3):
                out[..., ch][disc] += bump[disc]
        out = np.clip(out, 0, 255)
    elif hazard_type == "fake_ridge":
        length = max(6, 2 * scale)
        t = np.arange(length)
        pts = np.stack([cx + t - length // 2, np.full(length, cy)], axis=1)
        pts = np.clip(pts, 0, [w - 1, h - 1])
        cv2.polylines(out, [pts.astype(np.int32)], False, (255,) if grayscale else (255, 255, 255), max(2, scale // 2))
        cv2.polylines(mask, [pts.astype(np.int32)], False, 255, max(2, scale // 2))
        cv2.GaussianBlur(mask, (0, 0), max(1, scale / 6), dst=mask)
        out = cv2.GaussianBlur(out, (0, 0), 0.8)
    elif hazard_type == "fake_crater":
        r = max(3, scale)
        y, x = np.ogrid[:h, :w]
        disc = (x - cx) ** 2 + (y - cy) ** 2 <= r * r
        draw(disc)
        if grayscale:
            out[disc] *= 0.45
        else:
            out[disc] *= 0.45
        ring = (x - cx) ** 2 + (y - cy) ** 2 <= (r + max(1, r // 5)) ** 2
        ring &= ~disc
        draw(ring)
        if grayscale:
            out[ring] = np.clip(out[ring] * 1.6, 0, 255)
        else:
            out[ring] = np.clip(out[ring] * 1.6, 0, 255)
    elif hazard_type == "false_depression":
        r = max(4, scale)
        y, x = np.ogrid[:h, :w]
        ellipse = ((x - cx) / r) ** 2 + ((y - cy) / (r * 0.8)) ** 2 <= 1
        draw(ellipse)
        depth = 200.0 * strength * np.exp(-(((x - cx) / r) ** 2 + ((y - cy) / (r * 0.8)) ** 2))
        if grayscale:
            out[ellipse] -= depth[ellipse]
        else:
            for ch in range(3):
                out[..., ch][ellipse] -= depth[ellipse]
        out = np.clip(out, 0, 255)
    elif hazard_type == "high_frequency_texture":
        r = max(4, scale)
        y, x = np.ogrid[:h, :w]
        disc = (x - cx) ** 2 + (y - cy) ** 2 <= r * r
        draw(disc)
        texture = rng.normal(0, 60.0 * strength, (h, w)).astype(np.float32)
        texture = cv2.GaussianBlur(texture, (3, 3), 0)
        add = np.zeros_like(out)
        if grayscale:
            add[disc] = texture[disc]
        else:
            for ch in range(3):
                add[..., ch][disc] = texture[disc]
        out = np.clip(out + add, 0, 255)
    elif hazard_type == "edge_exaggeration":
        r = max(4, scale)
        y, x = np.ogrid[:h, :w]
        disc = (x - cx) ** 2 + (y - cy) ** 2 <= r * r
        draw(disc)
        sharp = cv2.addWeighted(image, 1.0 + 1.6 * strength,
                                cv2.GaussianBlur(image, (0, 0), 1.4), -1.6 * strength, 0)
        out[disc] = sharp[disc]
    elif hazard_type == "artificial_terrain_structure":
        r = max(5, scale)
        y, x = np.ogrid[:h, :w]
        disc = (x - cx) ** 2 + (y - cy) ** 2 <= r * r
        draw(disc)
        structure = (90.0 * strength * np.sin(0.55 * x) * np.cos(0.45 * y)).astype(np.float32)
        if grayscale:
            out[disc] += structure[disc]
        else:
            for ch in range(3):
                out[..., ch][disc] += structure[disc]
        out = np.clip(out, 0, 255)
    else:
        raise ValueError(f"Unknown hazard type: {hazard_type}")
    return np.clip(np.rint(out), 0, 255).astype(np.uint8), (mask > 0).astype(np.uint8)


def _apply_benign(image: np.ndarray, benign_type: str, strength: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    if benign_type == "mild_sharpening":
        return cv2.addWeighted(image, 1.0 + 0.5 * strength, cv2.GaussianBlur(image, (0, 0), 1.2), -0.5 * strength, 0)
    if benign_type == "denoising":
        return cv2.fastNlMeansDenoising(image, None, h=6 + 6 * strength)
    if benign_type == "contrast_adjustment":
        return cv2.convertScaleAbs(image, alpha=1.0 + 0.25 * strength, beta=0)
    if benign_type == "brightness_change":
        return cv2.convertScaleAbs(image, alpha=1.0, beta=18 * strength)
    if benign_type == "compression":
        ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, max(20, int(95 - 60 * strength))])
        assert ok
        return cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
    if benign_type == "resampling":
        s = max(0.75, 1.0 - 0.2 * strength)
        small = cv2.resize(image, (max(2, int(image.shape[1] * s)), max(2, int(image.shape[0] * s))),
                            interpolation=cv2.INTER_AREA)
        return cv2.resize(small, (image.shape[1], image.shape[0]), interpolation=cv2.INTER_CUBIC)
    if benign_type == "sensor_noise":
        noise = rng.normal(0, 1.5 + 4 * strength, image.shape)
        return np.clip(np.rint(image.astype(np.float32) + noise), 0, 255).astype(np.uint8)
    if benign_type == "illumination_variation":
        h, w = image.shape[:2]
        y, x = np.mgrid[:h, :w]
        gradient = 1.0 + 0.22 * strength * (x / max(w - 1, 1) - 0.5)
        out = image.astype(np.float32) * gradient[..., None] if image.ndim == 3 else image.astype(np.float32) * gradient
        return np.clip(np.rint(out), 0, 255).astype(np.uint8)
    raise ValueError(f"Unknown benign perturbation: {benign_type}")


def generate_hazard_sample(base: np.ndarray, base_scene_id: str, hazard_type: str,
                           seed: int, scale: int | None = None, strength: float | None = None,
                           location: tuple[int, int] | None = None,
                           classification: str = "SYNTHETIC_BENCHMARK") -> SyntheticSample:
    """Inject one controlled hazard with a pixel-exact ground-truth mask."""
    if hazard_type not in HAZARD_TYPES:
        raise ValueError(f"Not a hazard type: {hazard_type}")
    rng = np.random.default_rng(seed)
    h, w = base.shape[:2]
    scale = scale or int(rng.integers(max(6, h // 24), max(8, h // 8)))
    strength = strength if strength is not None else float(rng.uniform(0.35, 0.85))
    cx, cy = location if location is not None else _center(base.shape, seed + 1)
    modified, mask = _apply_hazard(base, hazard_type, cx, cy, scale, strength, seed)
    return SyntheticSample(
        sample_id=f"{base_scene_id}__{hazard_type}__{seed}",
        classification=classification,
        base_scene_id=base_scene_id,
        base_image_id=hashlib.sha256(np.ascontiguousarray(base).tobytes()).hexdigest()[:16],
        modified_image_id=hashlib.sha256(np.ascontiguousarray(modified).tobytes()).hexdigest()[:16],
        hazard_type=hazard_type,
        ground_truth_mask=mask,
        injection_location=[int(cx), int(cy)],
        injection_scale=int(scale),
        injection_strength=round(float(strength), 4),
        random_seed=int(seed),
        generation_version=GENERATION_VERSION,
        metadata={"note": "Synthetic hazard injected into base scene; not a natural lunar observation.",
                  "intent": "unsupported-terrain candidate"},
        modified_image=modified, ground_truth=True,
    )


def generate_benign_sample(base: np.ndarray, base_scene_id: str, benign_type: str,
                           seed: int, strength: float | None = None,
                           classification: str = "SYNTHETIC_BENCHMARK") -> SyntheticSample:
    """Apply a benign perturbation; expected outcome is visual change without an
    unsupported-terrain candidate. Ground-truth mask is empty by definition."""
    if benign_type not in BENIGN_TYPES:
        raise ValueError(f"Not a benign perturbation: {benign_type}")
    rng = np.random.default_rng(seed)
    strength = strength if strength is not None else float(rng.uniform(0.2, 0.9))
    modified = _apply_benign(base, benign_type, strength, seed)
    return SyntheticSample(
        sample_id=f"{base_scene_id}__{benign_type}__{seed}",
        classification=classification,
        base_scene_id=base_scene_id,
        base_image_id=hashlib.sha256(np.ascontiguousarray(base).tobytes()).hexdigest()[:16],
        modified_image_id=hashlib.sha256(np.ascontiguousarray(modified).tobytes()).hexdigest()[:16],
        hazard_type=benign_type,
        ground_truth_mask=None,
        injection_location=[0, 0],
        injection_scale=0,
        injection_strength=round(float(strength), 4),
        random_seed=int(seed),
        generation_version=GENERATION_VERSION,
        metadata={"note": "Benign image-processing perturbation; expected to stay below the "
                          "unsupported-terrain threshold while VISUAL CHANGE may be measurable.",
                  "intent": "false-positive control"},
        modified_image=modified, ground_truth=False,
    )


# ---------------------------------------------------------------- base scenes

def make_procedural_scene(seed: int, size: tuple[int, int] = (256, 256)) -> np.ndarray:
    """Deterministic cratered, noise-textured procedural scene (not lunar data)."""
    rng = np.random.default_rng(seed)
    h, w = size
    y, x = np.mgrid[:h, :w]
    base = (46 + 26 * np.exp(-((x - w * 0.55) ** 2 + (y - h * 0.5) ** 2) / (2 * (w * 0.4) ** 2))).astype(np.float32)
    for i in range(5):
        cx, cy = int(rng.integers(w // 8, 7 * w // 8)), int(rng.integers(h // 8, 7 * h // 8))
        r = int(rng.integers(w // 14, w // 7))
        d = np.hypot(x - cx, y - cy)
        base += 16 * np.exp(-((d - r) / max(2, r // 8)) ** 2) - 9 * np.exp(-(d / (r * 0.75)) ** 4)
    base += rng.normal(0, 2.2, base.shape)
    return np.uint8(np.clip(base, 0, 255))


SCENE_REGISTRY = {
    "scene_alpha": lambda: make_procedural_scene(101),
    "scene_beta": lambda: make_procedural_scene(202),
    "scene_gamma": lambda: make_procedural_scene(303),
    "scene_delta": lambda: make_procedural_scene(404),
    "scene_epsilon": lambda: make_procedural_scene(505),
    "scene_zeta": lambda: make_procedural_scene(606),
}
