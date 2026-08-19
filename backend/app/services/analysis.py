from __future__ import annotations
import hashlib, json
from time import perf_counter
from uuid import uuid4
import cv2
import numpy as np
from ratio_core.evidence import analyze_image_pair
from backend.app.core.config import ANALYSIS_DIR, load_scientific_config
from backend.app.services.store import get_image, utc_now


def _colored(map_: np.ndarray) -> np.ndarray:
    return cv2.applyColorMap(np.uint8(np.clip(map_, 0, 1) * 255), cv2.COLORMAP_TURBO)


def _write_png(path, array) -> None:
    ok, encoded = cv2.imencode(".png", array)
    if not ok:
        raise RuntimeError(f"Could not encode {path.name}")
    path.write_bytes(encoded.tobytes())


def run_analysis(original_id: str, enhanced_id: str, label: str | None = None) -> dict:
    total_started = perf_counter()
    original_meta, original = get_image(original_id)
    enhanced_meta, enhanced = get_image(enhanced_id)
    config = load_scientific_config()
    result = analyze_image_pair(original, enhanced, config)
    analysis_id = uuid4().hex
    output_dir = ANALYSIS_DIR / analysis_id
    output_dir.mkdir(parents=True, exist_ok=False)
    artifacts: dict[str, str] = {}
    artifact_started = perf_counter()

    if result.comparison.comparison_status == "COMPARABLE":
        assert result.visual_score_map is not None and result.suspicious_mask is not None
        assert result.normalized_enhanced is not None
        _write_png(output_dir / "difference_map.png", _colored(result.visual_score_map))
        _write_png(output_dir / "suspicious_mask.png", result.suspicious_mask)
        annotated = np.uint8(np.clip(result.normalized_enhanced, 0, 1) * 255)
        annotated = cv2.cvtColor(annotated, cv2.COLOR_GRAY2BGR)
        for region in result.regions:
            x, y, w, h = region.bbox
            cv2.rectangle(annotated, (x, y), (x + w, y + h), (32, 220, 255), 2)
            cv2.putText(annotated, region.id, (x, max(16, y - 5)), cv2.FONT_HERSHEY_SIMPLEX,
                        .48, (32, 220, 255), 1, cv2.LINE_AA)
        _write_png(output_dir / "annotated.png", annotated)
        artifacts = {name: f"/api/analyses/{analysis_id}/artifacts/{name}.png"
                     for name in ("difference_map", "suspicious_mask", "annotated")}

    artifact_ms = round((perf_counter() - artifact_started) * 1000, 3)
    processing = dict(result.processing_times_ms or {})
    processing["artifact_generation"] = artifact_ms
    processing["total"] = round((perf_counter() - total_started) * 1000, 3)
    comparison = result.comparison.to_dict()
    dimensions = {
        "original_dimensions": comparison["original_dimensions"],
        "enhanced_dimensions": comparison["enhanced_dimensions"],
        "analysis_dimensions": comparison["analysis_dimensions"],
        "resize_applied": comparison["resize_applied"],
        "resize_method": comparison["resize_method"],
        "aspect_ratio_difference": comparison["aspect_ratio_difference"],
    }
    status = result.comparison.comparison_status
    notice = ("Detected changes are not classified as hallucinations and have not been checked "
              "against physical terrain evidence." if status == "COMPARABLE" else
              "Ordinary visual-change evidence was not generated because image correspondence was not established.")
    record = {
        "schema_version": "1.1", "id": analysis_id, "label": label,
        "status": status, "comparison_status": status, "created_at": utc_now(),
        "scope": "STAGE_1_VISUAL_EVIDENCE_ONLY", "scientific_notice": notice,
        "inputs": {"original": {k: v for k, v in original_meta.items() if k != "path"},
                   "enhanced": {k: v for k, v in enhanced_meta.items() if k != "path"}},
        "configuration": config, "dimensions": dimensions,
        "compatibility": {
            "score": comparison["compatibility_score"],
            "status": comparison["compatibility_status"],
            "reason_code": comparison["reason_code"],
            "component_scores": comparison["component_scores"],
            "disclaimer": "Visual correspondence estimate only; not semantic or geographic verification."
        },
        "metrics": result.global_metrics, "features": [r.to_dict() for r in result.regions],
        "artifacts": artifacts, "processing_times_ms": processing,
    }
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    record["record_sha256"] = hashlib.sha256(canonical).hexdigest()
    (output_dir / "analysis.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record
