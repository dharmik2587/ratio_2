"""Deterministic fallback explanation generator.

Produces the standard five-field report from structured evidence and the frozen
policy decision — no LLM involved. This guarantees RATIO remains explainable
when Claude is unavailable, offline, or returns invalid output.
"""
from __future__ import annotations
from typing import Any


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _status_phrase(status: str | None) -> str:
    if not status:
        return "not established"
    return {"SUPPORTED": "supported by independent terrain evidence",
            "PARTIALLY_SUPPORTED": "partially supported by independent terrain evidence",
            "CONTRADICTED": "contradicted by independent terrain evidence",
            "UNRESOLVED": "unresolved",
            "REFERENCE_INADEQUATE": "limited by reference adequacy (inadequate, not contradicted)",
            "REFERENCE_UNAVAILABLE": "limited by reference availability (unavailable, not contradicted)",
            }.get(status, status.replace("_", " ").lower())


def build_fallback_explanation(analysis: dict[str, Any] | None,
                               feature: dict[str, Any] | None,
                               registration: dict[str, Any] | None,
                               policy: dict[str, Any] | None,
                               dataset: dict[str, Any] | None = None) -> dict[str, Any]:
    """Template-based, evidence-grounded explanation.

    The recommendation NEVER invents a decision: it restates the deterministic
    policy decision recorded by the frozen mission policy.
    """
    decision = (policy or {}).get("decision", "UNKNOWN")
    mission = ((policy or {}).get("mission_profile") or (analysis or {}).get("mission_profile") or "MISSION").replace("_", " ")

    if feature is None:
        summary = ("RATIO did not retain a meaningful visual-change region in this analysis; "
                   "no feature-level explanation applies.")
        risk = "No feature-level unsupported risk was computed."
        evidence = "Visual-change evidence is absent or below the configured detection threshold."
        recommendation = f"The deterministic mission policy for {mission} returned {decision}."
        limitations = ["No feature evidence was available to explain.",
                       "This explanation restates backend records only; no measurements were inferred."]
        return {"executive_summary": summary, "risk_assessment": risk,
                "evidence_explanation": evidence, "recommendation": recommendation,
                "limitations": limitations}

    fid = feature.get("feature_id") or feature.get("id") or "UNKNOWN"
    visual = feature.get("visual_change")
    support = feature.get("physical_support")
    risk = feature.get("unsupported_risk")
    reg_q = feature.get("registration_quality")
    ref_q = feature.get("reference_quality")
    status = feature.get("status")
    resolution = feature.get("reference_resolution") or {}
    res_status = resolution.get("status")
    res_mpp = resolution.get("meters_per_pixel")
    reasons = feature.get("reason_codes") or []
    components = feature.get("support_components") or {}
    hillshade = components.get("hillshade_support")
    gradient = components.get("gradient_alignment")
    dem_support = components.get("dem_support")
    relief = components.get("local_relief_support")
    reg = registration or {}
    basis = reg.get("validation_basis")
    fit_rmse = reg.get("rmse_px")
    v_rmse = reg.get("validation_rmse_px")

    summary = (f"Feature {fid} shows a visual change score of {_fmt(visual)}. "
               f"Independent terrain evidence is {_status_phrase(status)} "
               f"with a physical support score of {_fmt(support)}.")
    risk_text = (f"The unsupported-risk score is {_fmt(risk)}. This is a deterministic engineering "
                 f"measure, not a probability." if risk is not None else
                 f"The unsupported-risk score is unavailable because physical support was not computed.")
    evidence_parts = [f"visual change = {_fmt(visual)}"]
    if reg_q is not None:
        evidence_parts.append(f"registration quality = {_fmt(reg_q)}")
    if basis:
        evidence_parts.append(f"registration basis = {basis.replace('_', ' ').lower()}")
    if fit_rmse is not None:
        evidence_parts.append(f"fit RMSE = {_fmt(fit_rmse)} px")
    if v_rmse is not None:
        evidence_parts.append(f"independent validation RMSE = {_fmt(v_rmse)} px")
    if ref_q is not None:
        evidence_parts.append(f"reference quality = {_fmt(ref_q)}")
    if res_status:
        adequacy = "adequate for the feature scale" if res_status == "REFERENCE_RESOLUTION_ADEQUATE" else \
            "inadequate for the feature scale" if res_status == "REFERENCE_TOO_COARSE" else "uncertain for the feature scale"
        evidence_parts.append(f"reference resolution {_fmt(res_mpp)} m/pixel is {adequacy}")
    if dem_support is not None:
        evidence_parts.append(f"DEM support = {_fmt(dem_support)}")
    if gradient is not None:
        evidence_parts.append(f"gradient alignment = {_fmt(gradient)}")
    if hillshade is not None:
        evidence_parts.append(f"hillshade support = {_fmt(hillshade)}")
    else:
        evidence_parts.append("hillshade comparison = unavailable")
    if relief is not None:
        evidence_parts.append(f"local relief support = {_fmt(relief)}")
    evidence = "Independent terrain evidence for feature " + fid + ": " + "; ".join(evidence_parts) + "."
    reason_text = "; ".join(sorted(set(reasons))) if reasons else "no reason codes recorded"
    evidence += f" Recorded reason codes: {reason_text}."
    recommendation = (f"The configured mission policy for {mission} returned {decision} "
                      f"for this feature. This decision is deterministic and was not produced by the explanation layer.")
    limitations = [
        "Visual change is never counted as physical support.",
        "Hillshade comparison is unavailable without acquisition illumination metadata."
        if hillshade is None else "Hillshade comparison is a deterministic visualization derivative.",
        "A zero fit RMSE with three control points is not proof of registration correctness."
        if basis == "MINIMAL_EXACT_FIT" else None,
        "Scores are deterministic engineering measures, not calibrated probabilities.",
    ]
    return {"executive_summary": summary, "risk_assessment": risk_text,
            "evidence_explanation": evidence, "recommendation": recommendation,
            "limitations": [item for item in limitations if item]}
