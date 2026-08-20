"""Schema validation for LLM-produced explanation reports.

An LLM report must contain exactly the required narrative fields and nothing
that could be mistaken for scientific state. Extra fields are discarded; missing
fields fail validation so the caller can retry or fall back deterministically.
"""
from __future__ import annotations
from typing import Any

REQUIRED_FIELDS = ("executive_summary", "risk_assessment", "evidence_explanation", "recommendation", "limitations")
FIELD_MAX_CHARS = 3000
LIMITATIONS_MIN_ITEMS = 1
LIMITATIONS_MAX_ITEMS = 12
FORBIDDEN_STATE_FIELDS = {
    "policy_decision", "decision", "risk_score", "physical_support", "unsupported_risk",
    "visual_change", "registration_quality", "reference_quality", "comparison_quality",
    "status", "export_designation", "reason_codes", "feature_id", "analysis_id",
}


class LLMReportError(ValueError):
    pass


def validate_llm_report(report: Any) -> dict:
    """Validate and normalize an LLM explanation report.

    Returns the sanitized dict. Raises LLMReportError when the structure is not
    usable, so callers can retry once and then use the deterministic fallback.
    """
    if not isinstance(report, dict):
        raise LLMReportError("report is not a JSON object")
    for field in REQUIRED_FIELDS:
        if field == "limitations":
            continue
        if field not in report or not isinstance(report[field], str) or not report[field].strip():
            raise LLMReportError(f"missing or empty required field: {field}")
    if "limitations" not in report or not isinstance(report["limitations"], list):
        raise LLMReportError("missing or empty required field: limitations")
    if len([str(x).strip() for x in report["limitations"] if str(x).strip()]) < LIMITATIONS_MIN_ITEMS:
        raise LLMReportError("missing or empty required field: limitations")
    out: dict[str, Any] = {}
    for field in REQUIRED_FIELDS:
        value = report[field]
        if field == "limitations":
            items = [str(item).strip() for item in value if str(item).strip()][:LIMITATIONS_MAX_ITEMS]
            out[field] = items or ["Evidence limitations were not enumerated by the explanation layer."]
        else:
            text = " ".join(str(value).split())
            if len(text) > FIELD_MAX_CHARS:
                raise LLMReportError(f"{field} exceeds the maximum length")
            if not text:
                raise LLMReportError(f"empty required field: {field}")
            out[field] = text
    return out


def contains_state_override(report: dict) -> bool:
    """Detect attempts to smuggle deterministic state into the explanation."""
    return any(key in FORBIDDEN_STATE_FIELDS for key in report.keys())
