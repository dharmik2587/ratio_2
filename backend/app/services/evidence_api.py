"""Phase 3E — structured evidence query API.

Read-only, deterministic views over stored analysis records. This is the
security and correctness boundary between the explanation layer and the
scientific records: no raw database access and no image data ever leaves here.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

from backend.app.core.config import ANALYSIS_DIR
from backend.app.services.store import get_analysis, valid_id

BENCHMARK_DIR = Path(__file__).resolve().parents[3] / "data" / "benchmarks"
DRIFT_DIR = Path(__file__).resolve().parents[3] / "data" / "drift"


def _phase2(analysis_id: str) -> dict:
    path = ANALYSIS_DIR / analysis_id / "phase2.json"
    if not path.exists():
        raise FileNotFoundError("PHYSICAL_EVIDENCE_UNAVAILABLE")
    return json.loads(path.read_text())


def _registration(analysis_id: str) -> dict | None:
    path = ANALYSIS_DIR / analysis_id / "registration.json"
    return json.loads(path.read_text()) if path.exists() else None


def evidence_report(analysis_id: str) -> dict:
    """Standardized per-analysis evidence-quality record (Phase-3 reporting view)."""
    record = get_analysis(analysis_id)
    report = {
        "schema_version": "3.0",
        "analysis_id": analysis_id,
        "comparison_status": record.get("comparison_status"),
        "comparison_quality": (record.get("compatibility") or {}).get("score"),
        "created_at": record.get("created_at"),
        "features": [],
    }
    try:
        phase2 = _phase2(analysis_id)
        report["dem_verification_status"] = phase2.get("dem_verification_status")
        report["no_significant_change"] = phase2.get("no_significant_change")
        report["policy"] = phase2.get("policy")
        report["dataset"] = phase2.get("dataset")
        for feature in phase2.get("features", []):
            report["features"].append({
                "feature_id": feature.get("feature_id"),
                "visual_change": feature.get("visual_change"),
                "physical_support": feature.get("physical_support"),
                "unsupported_risk": feature.get("unsupported_risk"),
                "comparison_quality": feature.get("comparison_quality"),
                "registration_quality": feature.get("registration_quality"),
                "reference_quality": feature.get("reference_quality"),
                "reference_resolution": feature.get("reference_resolution"),
                "valid_data_percentage": feature.get("valid_data_percentage"),
                "coverage_status": feature.get("coverage_status"),
                "physical_status": feature.get("status"),
                "reason_codes": feature.get("reason_codes"),
            })
    except FileNotFoundError:
        report["dem_verification_status"] = "NOT_PERFORMED"
        report["features"] = [{
            "feature_id": f.get("id"), "visual_change": f.get("visual_score"),
            "physical_support": None, "unsupported_risk": None,
            "physical_status": "VISUAL_ONLY", "reason_codes": ["PHASE2_NOT_RUN"],
        } for f in record.get("features", [])]
    path = ANALYSIS_DIR / analysis_id / "evidence_report.json"
    path.write_text(json.dumps(report, indent=2))
    return report


def get_analysis_summary(analysis_id: str) -> dict:
    """Compact deterministic summary for the explanation layer."""
    if not valid_id(analysis_id):
        raise FileNotFoundError(analysis_id)
    record = get_analysis(analysis_id)
    summary = {
        "analysis_id": analysis_id,
        "label": record.get("label"),
        "comparison_status": record.get("comparison_status"),
        "compatibility_score": (record.get("compatibility") or {}).get("score"),
        "region_count": len(record.get("features", [])),
        "metrics": record.get("metrics"),
        "created_at": record.get("created_at"),
    }
    try:
        phase2 = _phase2(analysis_id)
        summary["dem_verification_status"] = phase2.get("dem_verification_status")
        summary["no_significant_change"] = phase2.get("no_significant_change")
        summary["mission_profile"] = phase2.get("mission_profile")
        summary["policy_decision"] = (phase2.get("policy") or {}).get("decision")
        summary["policy_reason_codes"] = (phase2.get("policy") or {}).get("reason_codes")
        summary["dataset"] = phase2.get("dataset")
        summary["physical_feature_count"] = len(phase2.get("features", []))
    except FileNotFoundError:
        summary["dem_verification_status"] = "NOT_PERFORMED"
        summary["policy_decision"] = None
    return summary


def _resolve_feature(feature_id: str, analysis_id: str | None = None) -> tuple[str, dict]:
    if analysis_id:
        phase2 = _phase2(analysis_id)
        for feature in phase2.get("features", []):
            if feature.get("feature_id") == feature_id:
                return analysis_id, feature
        raise FileNotFoundError(f"FEATURE_NOT_FOUND:{feature_id}")
    candidates = []
    if ANALYSIS_DIR.exists():
        for folder in ANALYSIS_DIR.iterdir():
            if not folder.is_dir() or not valid_id(folder.name):
                continue
            path = folder / "phase2.json"
            if not path.exists():
                continue
            phase2 = json.loads(path.read_text())
            for feature in phase2.get("features", []):
                if feature.get("feature_id") == feature_id:
                    candidates.append((folder.name, feature))
    if not candidates:
        raise FileNotFoundError(f"FEATURE_NOT_FOUND:{feature_id}")
    candidates.sort(key=lambda pair: pair[1].get("visual_change", 0), reverse=True)
    return candidates[0]


def _compact_feature(feature: dict) -> dict:
    keys = ["feature_id", "visual_change", "physical_support", "unsupported_risk",
            "comparison_quality", "registration_quality", "reference_quality",
            "reference_resolution", "valid_data_percentage", "coverage_status",
            "status", "reason_codes", "support_components", "available_components",
            "component_coverage_fraction", "reference_bbox"]
    out = {k: feature.get(k) for k in keys if feature.get(k) is not None or k in
           {"physical_support", "unsupported_risk", "support_components", "reason_codes",
            "reference_resolution", "reference_bbox"}}
    out.setdefault("feature_id", feature.get("feature_id") or feature.get("id"))
    return out


def get_feature(feature_id: str, analysis_id: str | None = None) -> dict:
    analysis_id, feature = _resolve_feature(feature_id, analysis_id)
    return {"analysis_id": analysis_id, "feature": _compact_feature(feature)}


def get_feature_evidence(feature_id: str, analysis_id: str | None = None) -> dict:
    analysis_id, feature = _resolve_feature(feature_id, analysis_id)
    phase2 = _phase2(analysis_id)
    return {
        "analysis_id": analysis_id,
        "feature": _compact_feature(feature),
        "comparison_quality": phase2.get("comparison_quality"),
        "dem_verification_status": phase2.get("dem_verification_status"),
        "registration": _registration(analysis_id),
        "policy_decision": (phase2.get("policy") or {}).get("decision"),
        "mission_profile": phase2.get("mission_profile"),
        "dataset": phase2.get("dataset"),
    }


def get_dem_support(feature_id: str, analysis_id: str | None = None) -> dict:
    analysis_id, feature = _resolve_feature(feature_id, analysis_id)
    components = feature.get("support_components") or {}
    return {
        "analysis_id": analysis_id,
        "feature_id": feature.get("feature_id"),
        "dem_support": components.get("dem_support"),
        "gradient_alignment": components.get("gradient_alignment"),
        "hillshade_support": components.get("hillshade_support"),
        "local_relief_support": components.get("local_relief_support"),
        "available_components": feature.get("available_components"),
        "component_coverage_fraction": feature.get("component_coverage_fraction"),
        "physical_support": feature.get("physical_support"),
        "physical_status": feature.get("status"),
        "reference_resolution": feature.get("reference_resolution"),
        "valid_data_percentage": feature.get("valid_data_percentage"),
        "coverage_status": feature.get("coverage_status"),
    }


def get_registration(analysis_id: str | None = None, feature_id: str | None = None) -> dict:
    if analysis_id is None and feature_id is not None:
        analysis_id, _ = _resolve_feature(feature_id)
    if analysis_id is None:
        raise FileNotFoundError("ANALYSIS_ID_REQUIRED")
    registration = _registration(analysis_id)
    if registration is None:
        raise FileNotFoundError("REGISTRATION_UNAVAILABLE")
    return {"analysis_id": analysis_id, "registration": registration}


def compare_features(feature_a: str, feature_b: str, analysis_id: str | None = None) -> dict:
    aid_a, fa = _resolve_feature(feature_a, analysis_id)
    aid_b, fb = _resolve_feature(feature_b, analysis_id if analysis_id else aid_a)

    def diff(a, b):
        if a is None or b is None:
            return None
        return round(float(a) - float(b), 4)
    return {
        "feature_a": {"feature_id": feature_a, "analysis_id": aid_a, **_compact_feature(fa)},
        "feature_b": {"feature_id": feature_b, "analysis_id": aid_b, **_compact_feature(fb)},
        "comparison": {
            "visual_change_difference": diff(fa.get("visual_change"), fb.get("visual_change")),
            "physical_support_difference": diff(fa.get("physical_support"), fb.get("physical_support")),
            "risk_difference": diff(fa.get("unsupported_risk"), fb.get("unsupported_risk")),
            "registration_quality_difference": diff(fa.get("registration_quality"), fb.get("registration_quality")),
            "reference_quality_difference": diff(fa.get("reference_quality"), fb.get("reference_quality")),
            "physical_status_pair": [fa.get("status"), fb.get("status")],
        },
    }


def get_region_summary(analysis_id: str, region: str = "ALL") -> dict:
    if not valid_id(analysis_id):
        raise FileNotFoundError(analysis_id)
    phase2 = _phase2(analysis_id)
    features = phase2.get("features", [])
    policy = phase2.get("policy") or {}
    if region and region.upper() != "ALL":
        matches = [f for f in features if f.get("feature_id") == region]
        if not matches:
            raise FileNotFoundError(f"REGION_NOT_FOUND:{region}")
        feature = matches[0]
        return {"analysis_id": analysis_id, "region": region,
                "feature": _compact_feature(feature), "policy_decision": policy.get("decision")}
    supported = [f for f in features if f.get("status") == "SUPPORTED"]
    contradicted = [f for f in features if f.get("status") == "CONTRADICTED"]
    unresolved = [f for f in features if f.get("status") in {"UNRESOLVED", "REFERENCE_INADEQUATE", "REFERENCE_UNAVAILABLE"}]
    flagged = set()
    for code in (policy.get("reason_codes") or []):
        if ":" in str(code):
            flagged.add(str(code).split(":", 1)[0])
    review_required = sorted(fid for fid in flagged if any(f.get("feature_id") == fid for f in features))
    weak_dem = [f.get("feature_id") for f in features if
                (f.get("support_components") or {}).get("dem_support") is None or
                (f.get("support_components") or {}).get("dem_support", 1.0) < 0.35]
    avg = lambda key: round(sum(float(f.get(key) or 0) for f in features) / len(features), 4) if features else None
    return {
        "analysis_id": analysis_id,
        "region": "ALL",
        "feature_count": len(features),
        "supported_count": len(supported),
        "contradicted_count": len(contradicted),
        "unresolved_count": len(unresolved),
        "average_visual_change": avg("visual_change"),
        "average_physical_support": avg("physical_support"),
        "average_unsupported_risk": avg("unsupported_risk"),
        "average_registration_quality": avg("registration_quality"),
        "average_reference_quality": avg("reference_quality"),
        "review_required_feature_ids": review_required,
        "weak_dem_support_feature_ids": weak_dem,
        "policy_decision": policy.get("decision"),
    }


def get_mission_decision(analysis_id: str | None = None, feature_id: str | None = None) -> dict:
    if analysis_id is None and feature_id is not None:
        analysis_id, feature = _resolve_feature(feature_id)
    else:
        feature = None
    if analysis_id is None:
        raise FileNotFoundError("ANALYSIS_ID_REQUIRED")
    phase2 = _phase2(analysis_id)
    policy = phase2.get("policy") or {}
    return {
        "analysis_id": analysis_id,
        "mission_profile": phase2.get("mission_profile"),
        "policy_decision": policy.get("decision"),
        "export_designation": policy.get("export_designation"),
        "reason_codes": policy.get("reason_codes"),
        "feature": _compact_feature(feature) if feature else None,
        "note": "Deterministic mission-policy output; immutable via the evidence API.",
    }


def get_processing_passport(analysis_id: str) -> dict:
    path = ANALYSIS_DIR / analysis_id / "passport.json"
    if not path.exists():
        raise FileNotFoundError("PASSPORT_UNAVAILABLE")
    return json.loads(path.read_text())


def _latest_artifact(directory: Path, name: str) -> dict:
    if not directory.exists():
        raise FileNotFoundError(f"{name}_UNAVAILABLE")
    reports = sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not reports:
        raise FileNotFoundError(f"{name}_UNAVAILABLE")
    return json.loads(reports[0].read_text())


def get_benchmark_summary() -> dict:
    report = _latest_artifact(BENCHMARK_DIR, "BENCHMARK_REPORT")
    return {
        "report_id": report.get("id"),
        "generated_at": report.get("generated_at"),
        "data_classification": report.get("data_classification"),
        "splits": {split: {
            "total_samples": result.get("aggregates", {}).get("total_samples"),
            "classes": result.get("classes"),
            "aggregates": result.get("aggregates"),
        } for split, result in report.get("splits", {}).items()},
        "parameters": report.get("parameters"),
        "limitations": report.get("limitations"),
    }


def get_model_drift_report() -> dict:
    report = _latest_artifact(DRIFT_DIR, "DRIFT_REPORT")
    return {
        "report_id": report.get("id"),
        "generated_at": report.get("generated_at"),
        "baseline": report.get("baseline"),
        "versions": {k: {kk: vv for kk, vv in v.items() if kk != "function"}
                     for k, v in report.get("versions", {}).items()},
        "comparisons": report.get("comparisons"),
        "thresholds": report.get("thresholds"),
        "benchmark_samples": report.get("benchmark_samples"),
    }
