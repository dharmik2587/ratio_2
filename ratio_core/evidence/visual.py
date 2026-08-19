"""Interpretable Stage-1 visual-change and image-comparability analysis.

All maps use image pixel coordinates (origin top-left, x right, y down). The
compatibility gate estimates low-resolution visual correspondence only. It does
not establish semantic identity, geographic co-location, or physical truth.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from time import perf_counter
import cv2
import numpy as np
from skimage.metrics import structural_similarity


@dataclass(frozen=True)
class ComparisonMetadata:
    original_dimensions: tuple[int, int]  # width, height
    enhanced_dimensions: tuple[int, int]
    analysis_dimensions: tuple[int, int] | None
    resize_applied: bool
    resize_method: str
    aspect_ratio_difference: float
    compatibility_score: float
    compatibility_status: str
    comparison_status: str
    reason_code: str | None
    component_scores: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RegionEvidence:
    id: str
    bbox: tuple[int, int, int, int]
    area_px: int
    area_pct: float
    visual_score: float
    residual_score: float
    ssim_change: float
    edge_mismatch: float
    frequency_change: float
    classification: str = "SUSPICIOUS_CHANGE"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AnalysisResult:
    comparison: ComparisonMetadata
    width: int | None
    height: int | None
    global_metrics: dict[str, float] | None
    regions: list[RegionEvidence]
    processing_times_ms: dict[str, float] | None = None
    residual_map: np.ndarray | None = None
    ssim_change_map: np.ndarray | None = None
    edge_mismatch_map: np.ndarray | None = None
    frequency_change_map: np.ndarray | None = None
    visual_score_map: np.ndarray | None = None
    suspicious_mask: np.ndarray | None = None
    normalized_original: np.ndarray | None = None
    normalized_enhanced: np.ndarray | None = None


def validate_config(config: dict[str, Any]) -> None:
    """Reject unsafe or internally inconsistent Stage-1 configuration."""
    try:
        weights = config["visual_weights"]
        expected = {"residual", "ssim_change", "edge_mismatch", "frequency_change"}
        if set(weights) != expected:
            raise ValueError(f"Visual weights must contain exactly {sorted(expected)}")
        _validate_unit_weights(weights, "Visual weights")
        norm = config["normalization"]
        if float(norm["residual_scale"]) <= 0 or float(norm["edge_scale"]) <= 0:
            raise ValueError("Normalization scales must be positive")
        if not 0 < float(norm["frequency_percentile"]) <= 100:
            raise ValueError("Frequency percentile must be in (0,100]")
        detection = config["detection"]
        _unit(float(detection["suspicious_threshold"]), "Suspicious threshold")
        kernel = int(detection["morphology_kernel"])
        if kernel <= 0 or kernel % 2 == 0:
            raise ValueError("Morphology kernel must be a positive odd integer")
        if int(detection["minimum_region_area_px"]) <= 0 or int(detection["maximum_regions"]) <= 0:
            raise ValueError("Region limits must be positive")
        compatibility = config["compatibility"]
        low = float(compatibility["low_threshold"])
        high = float(compatibility["high_threshold"])
        _unit(low, "Low compatibility threshold")
        _unit(high, "High compatibility threshold")
        if low >= high:
            raise ValueError("Low compatibility threshold must be less than high threshold")
        max_ar = float(compatibility["maximum_aspect_ratio_difference"])
        if not 0 <= max_ar <= 1:
            raise ValueError("Maximum aspect-ratio difference must be in [0,1]")
        thumb = int(compatibility["thumbnail_size"])
        if thumb < 32 or thumb > 1024:
            raise ValueError("Compatibility thumbnail size must be between 32 and 1024")
        cweights = compatibility["weights"]
        expected_c = {"structure_correlation", "coarse_ssim", "edge_correlation", "histogram_similarity"}
        if set(cweights) != expected_c:
            raise ValueError(f"Compatibility weights must contain exactly {sorted(expected_c)}")
        _validate_unit_weights(cweights, "Compatibility weights")
        policy = config["normalization_settings"]["dimension_policy"]
        if policy != "aspect_ratio_preserving":
            raise ValueError("Unsupported dimension normalization policy")
    except KeyError as exc:
        raise ValueError(f"Missing configuration field: {exc.args[0]}") from exc
    except (TypeError, OverflowError) as exc:
        raise ValueError("Configuration contains an invalid numeric value") from exc


def _unit(value: float, name: str) -> None:
    if not np.isfinite(value) or value < 0 or value > 1:
        raise ValueError(f"{name} must be in [0,1]")


def _validate_unit_weights(weights: dict[str, float], name: str) -> None:
    values = [float(v) for v in weights.values()]
    if any(not np.isfinite(v) or v < 0 or v > 1 for v in values):
        raise ValueError(f"{name} must each be in [0,1]")
    if not np.isclose(sum(values), 1.0, atol=1e-6):
        raise ValueError(f"{name} must sum to 1")


def _gray_float(image: np.ndarray) -> np.ndarray:
    """Convert BGR/BGRA/grayscale numeric imagery to grayscale float32 [0,1]."""
    if image is None or image.size == 0:
        raise ValueError("Image is empty or unreadable")
    if not np.issubdtype(image.dtype, np.number):
        raise ValueError("Image pixels must be numeric")
    if not np.all(np.isfinite(image)):
        raise ValueError("Image contains non-finite pixel values")
    if image.ndim == 2:
        gray = image
    elif image.ndim == 3 and image.shape[2] == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    elif image.ndim == 3 and image.shape[2] == 4:
        gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    else:
        raise ValueError(f"Unsupported image shape: {image.shape}")
    gray = gray.astype(np.float32)
    if np.issubdtype(image.dtype, np.integer):
        maximum = float(np.iinfo(image.dtype).max)
        return np.clip(gray / maximum, 0, 1)
    lo, hi = float(gray.min()), float(gray.max())
    if 0 <= lo and hi <= 1:
        return gray
    if hi <= lo:
        return np.zeros_like(gray)
    return np.clip((gray - lo) / (hi - lo), 0, 1)


def _standardize_for_structure(gray: np.ndarray) -> np.ndarray:
    mean, std = float(gray.mean()), float(gray.std())
    if std < 1e-6:
        return np.zeros_like(gray)
    return np.clip((gray - mean) / (6 * std) + 0.5, 0, 1).astype(np.float32)


def _thumbnail(gray: np.ndarray, size: int) -> np.ndarray:
    return cv2.resize(gray, (size, size), interpolation=cv2.INTER_AREA)


def _positive_correlation(a: np.ndarray, b: np.ndarray) -> float:
    af, bf = a.ravel(), b.ravel()
    if float(af.std()) < 1e-6 or float(bf.std()) < 1e-6:
        return 1.0 if np.allclose(af, bf, atol=1e-6) else 0.0
    return float(np.clip(np.corrcoef(af, bf)[0, 1], 0, 1))


def _compatibility(a: np.ndarray, b: np.ndarray, config: dict[str, Any]) -> tuple[float, dict[str, float]]:
    cc = config["compatibility"]
    size = int(cc["thumbnail_size"])
    ta = _standardize_for_structure(_thumbnail(a, size))
    tb = _standardize_for_structure(_thumbnail(b, size))
    structure = _positive_correlation(ta, tb)
    coarse_ssim = float(np.clip(structural_similarity(ta, tb, data_range=1.0), 0, 1))
    ea = cv2.Canny(np.uint8(ta * 255), 60, 140).astype(np.float32) / 255
    eb = cv2.Canny(np.uint8(tb * 255), 60, 140).astype(np.float32) / 255
    edge = _positive_correlation(cv2.GaussianBlur(ea, (5, 5), 0), cv2.GaussianBlur(eb, (5, 5), 0))
    ha = cv2.calcHist([np.uint8(ta * 255)], [0], None, [32], [0, 256])
    hb = cv2.calcHist([np.uint8(tb * 255)], [0], None, [32], [0, 256])
    histogram = float(np.clip((cv2.compareHist(ha, hb, cv2.HISTCMP_CORREL) + 1) / 2, 0, 1))
    components = {"structure_correlation": structure, "coarse_ssim": coarse_ssim,
                  "edge_correlation": edge, "histogram_similarity": histogram}
    score = sum(float(cc["weights"][key]) * value for key, value in components.items())
    return round(float(np.clip(score, 0, 1)), 4), {k: round(v, 4) for k, v in components.items()}


def _resize_to_original(enhanced: np.ndarray, target_wh: tuple[int, int]) -> np.ndarray:
    width, height = target_wh
    interpolation = cv2.INTER_AREA if enhanced.shape[1] >= width and enhanced.shape[0] >= height else cv2.INTER_CUBIC
    return cv2.resize(enhanced, (width, height), interpolation=interpolation)


def _normalize_by_scale(values: np.ndarray, scale: float) -> np.ndarray:
    return np.clip(values / scale, 0, 1).astype(np.float32)


def _frequency_change(a: np.ndarray, b: np.ndarray, percentile: float) -> np.ndarray:
    ea = np.abs(cv2.Laplacian(a, cv2.CV_32F, ksize=3))
    eb = np.abs(cv2.Laplacian(b, cv2.CV_32F, ksize=3))
    diff = cv2.GaussianBlur(np.abs(eb - ea), (7, 7), 0)
    positive = diff[diff > 0]
    scale = float(np.percentile(positive, percentile)) if positive.size else 1.0
    return _normalize_by_scale(diff, max(scale, 1e-6))


def analyze_image_pair(original: np.ndarray, enhanced: np.ndarray, config: dict[str, Any]) -> AnalysisResult:
    """Gate pair comparability, normalize safe size differences, then extract change.

    Medium/low compatibility returns no residual maps, regions, or change metrics.
    Aspect-ratio differences above the configured tolerance are never auto-resized;
    they are capped at REVIEW_COMPARABILITY because Stage 1 has no crop registration.
    """
    started = perf_counter()
    validate_config(config)
    a, b = _gray_float(original), _gray_float(enhanced)
    normalized_at = perf_counter()
    original_wh, enhanced_wh = (a.shape[1], a.shape[0]), (b.shape[1], b.shape[0])
    ar_a, ar_b = original_wh[0] / original_wh[1], enhanced_wh[0] / enhanced_wh[1]
    ar_difference = abs(ar_a - ar_b) / max(ar_a, ar_b)
    score, components = _compatibility(a, b, config)
    compatibility_at = perf_counter()
    cc = config["compatibility"]
    if score < float(cc["low_threshold"]):
        status, compatibility_status, reason = "INCOMPARABLE_IMAGES", "LOW", "LOW_VISUAL_CORRESPONDENCE"
    elif score < float(cc["high_threshold"]):
        status, compatibility_status, reason = "REVIEW_COMPARABILITY", "MEDIUM", "UNCERTAIN_VISUAL_CORRESPONDENCE"
    else:
        status, compatibility_status, reason = "COMPARABLE", "HIGH", None
    if ar_difference > float(cc["maximum_aspect_ratio_difference"]) and status == "COMPARABLE":
        status, compatibility_status, reason = "REVIEW_COMPARABILITY", "MEDIUM", "ASPECT_RATIO_MISMATCH_REQUIRES_REGISTRATION"

    different = original_wh != enhanced_wh
    if status != "COMPARABLE":
        comparison = ComparisonMetadata(original_wh, enhanced_wh, None, False, "none",
            round(ar_difference, 6), score, compatibility_status, status, reason, components)
        times = {"normalization": round((normalized_at-started)*1000, 3),
                 "compatibility": round((compatibility_at-normalized_at)*1000, 3),
                 "visual_analysis": 0.0}
        return AnalysisResult(comparison, None, None, None, [], times)

    normalized_b = _resize_to_original(b, original_wh) if different else b.copy()
    resize_method = "aspect_ratio_preserving_to_original_dimensions" if different else "none"
    comparison = ComparisonMetadata(original_wh, enhanced_wh, original_wh, different, resize_method,
        round(ar_difference, 6), score, compatibility_status, status, None, components)

    weights, norm, detect = config["visual_weights"], config["normalization"], config["detection"]
    residual_raw = np.abs(normalized_b - a)
    residual = _normalize_by_scale(residual_raw, float(norm["residual_scale"]))
    _, similarity = structural_similarity(a, normalized_b, data_range=1.0, full=True, gaussian_weights=True)
    ssim_change = np.clip(1.0 - similarity, 0, 1).astype(np.float32)
    ga_x, ga_y = cv2.Sobel(a, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(a, cv2.CV_32F, 0, 1, ksize=3)
    gb_x, gb_y = cv2.Sobel(normalized_b, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(normalized_b, cv2.CV_32F, 0, 1, ksize=3)
    edge = _normalize_by_scale(np.hypot(gb_x - ga_x, gb_y - ga_y), float(norm["edge_scale"]))
    frequency = _frequency_change(a, normalized_b, float(norm["frequency_percentile"]))
    visual_score = (weights["residual"] * residual + weights["ssim_change"] * ssim_change
                    + weights["edge_mismatch"] * edge + weights["frequency_change"] * frequency).astype(np.float32)
    raw_mask = (visual_score >= float(detect["suspicious_threshold"])).astype(np.uint8) * 255
    kernel_size = int(detect["morphology_kernel"])
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    mask = cv2.morphologyEx(cv2.morphologyEx(raw_mask, cv2.MORPH_CLOSE, kernel), cv2.MORPH_OPEN, kernel)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    candidates = []
    for label in range(1, count):
        x, y, w, h, area = map(int, stats[label])
        if area >= int(detect["minimum_region_area_px"]):
            candidates.append((area, x, y, w, h, labels == label))
    candidates.sort(reverse=True, key=lambda item: item[0])
    regions = []
    for idx, (area, x, y, w, h, pixels) in enumerate(candidates[:int(detect["maximum_regions"])], 1):
        mean = lambda m: round(float(np.mean(m[pixels])), 4)
        regions.append(RegionEvidence(f"F{idx:02d}", (x, y, w, h), area,
            round(100 * area / a.size, 4), mean(visual_score), mean(residual),
            mean(ssim_change), mean(edge), mean(frequency)))
    global_metrics = {"mean_visual_score": round(float(visual_score.mean()), 4),
        "mean_absolute_residual": round(float(residual_raw.mean()), 4),
        "global_ssim": round(float(structural_similarity(a, normalized_b, data_range=1.0)), 4),
        "suspicious_area_pct": round(100 * float((mask > 0).mean()), 4), "region_count": len(regions)}
    finished = perf_counter()
    times = {"normalization": round((normalized_at-started)*1000, 3),
             "compatibility": round((compatibility_at-normalized_at)*1000, 3),
             "visual_analysis": round((finished-compatibility_at)*1000, 3)}
    return AnalysisResult(comparison, original_wh[0], original_wh[1], global_metrics, regions, times,
        residual, ssim_change, edge, frequency, visual_score, mask, a, normalized_b)
