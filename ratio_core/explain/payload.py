"""Compact structured-evidence payloads for the explanation layer.

Claude never receives images or rasters. Only these compact JSON structures are
sent, derived from the deterministic backend records.
"""
from __future__ import annotations
from typing import Any

FEATURE_FIELDS = [
    "feature_id", "visual_change", "physical_support", "unsupported_risk",
    "comparison_quality", "registration_quality", "reference_quality",
    "valid_data_percentage", "coverage_status", "status",
    "support_components", "available_components", "component_coverage_fraction",
    "reason_codes", "reference_resolution",
]

ANALYSIS_FIELDS = [
    "analysis_id", "comparison_status", "comparison_quality",
    "dem_verification_status", "no_significant_change",
    "visual_change_summary", "dataset", "mission_profile",
]


def compact_feature(feature: dict[str, Any]) -> dict[str, Any]:
    """Reduce one feature record to the fixed compact evidence shape."""
    if not feature:
        return {}
    out = {k: feature.get(k) for k in FEATURE_FIELDS}
    out.setdefault("feature_id", feature.get("id", feature.get("feature_id")))
    return {k: v for k, v in out.items() if v is not None or k in
            {"physical_support", "unsupported_risk", "support_components", "reason_codes", "reference_resolution"}}


def compact_analysis(record: dict[str, Any]) -> dict[str, Any]:
    return {k: record.get(k) for k in ANALYSIS_FIELDS}


def compact_registration(registration: dict[str, Any] | None) -> dict[str, Any] | None:
    if not registration:
        return None
    keys = ["method", "status", "rmse_px", "max_error_px", "quality_score", "quality_label",
            "validation_basis", "fit_rmse_px", "fit_point_count", "validation_rmse_px",
            "validation_max_error_px", "validation_point_count"]
    return {k: registration.get(k) for k in keys if registration.get(k) is not None}


def build_evidence_payload(analysis_id: str, feature_id: str | None,
                           analysis: dict[str, Any], feature: dict[str, Any] | None,
                           registration: dict[str, Any] | None,
                           policy: dict[str, Any] | None) -> dict[str, Any]:
    """Structured-only payload. No images, no rasters, no raw pixels."""
    payload: dict[str, Any] = {
        "analysis": compact_analysis(analysis),
        "registration": compact_registration(registration),
        "policy": policy,
    }
    if feature is not None:
        payload["feature"] = compact_feature(feature)
    return payload
