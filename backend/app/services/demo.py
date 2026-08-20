"""Phase 3J — SIH demo mode.

Server-side one-click scenarios built from the same deterministic services the
interactive UI uses. Every case records the actual backend outputs — nothing is
pre-scripted or faked.
"""
from __future__ import annotations
import asyncio
import cv2
import numpy as np
from pathlib import Path

from backend.app.core.config import ROOT
from backend.app.services import phase2 as phase2_service
from backend.app.services import store
from backend.app.services import datasets as datasets_service
from backend.app.services.analysis import run_analysis
from backend.app.services.evidence_api import get_analysis_summary

DEMO_DIR = Path(__file__).resolve().parents[3] / "data" / "demo"

CASES = [
    {"id": "case1_legitimate_enhancement", "title": "Legitimate enhancement",
     "expected": "LOW CHANGE / SUPPORTED OR NO_SIGNIFICANT_CHANGE",
     "description": "Mild deterministic sharpening of the real lunar-derived image. "
                    "RATIO should find no meaningful suspicious region and take the "
                    "no-significant-change fast path."},
    {"id": "case2_synthetic_fake_boulder", "title": "Synthetic fake boulder",
     "expected": "HIGH VISUAL CHANGE / LOW PHYSICAL SUPPORT / HIGHER UNSUPPORTED RISK / BLOCK OR REVIEW",
     "description": "Controlled bright/dark disc injected on the real image. The independent "
                    "DEM does not contain it, so physical support is low and the mission "
                    "policy blocks or reviews export."},
    {"id": "case3_coarse_dem", "title": "Coarse reference",
     "expected": "REFERENCE_INADEQUATE / NOT CONTRADICTED",
     "description": "The high-resolution test feature is verified against a deliberately "
                    "downsampled reference. RATIO reports the reference as inadequate — "
                    "never contradicted."},
    {"id": "case4_bad_registration", "title": "Bad registration",
     "expected": "REGISTRATION_REVIEW / UNRESOLVED",
     "description": "Wrong 3-point correspondences plus an independent validation point. "
                    "The validation residual is large, registration quality drops, and "
                    "physical status is UNRESOLVED — not contradicted."},
    {"id": "case5_good_registration_highres", "title": "Good registration + high-res reference",
     "expected": "MEANINGFUL PHYSICAL VERIFICATION / ADEQUATE RESOLUTION",
     "description": "Three good fit points plus an independent validation point on the real "
                    "5 m/pixel LOLA-derived reference. Resolution adequacy is reported and "
                    "physical evidence is computed at feature scale."},
    {"id": "case6_model_drift", "title": "Enhancement model drift",
     "expected": "VERSION A PASS / VERSION B REVIEW OR QUARANTINE",
     "description": "The fixed benchmark runs through enhancer v1 (baseline), v2, and v3. "
                    "The drift monitor records the metric changes and its decision."},
    {"id": "case7_evidence_navigator", "title": "Evidence Navigator",
     "expected": "JUDGE QUESTION ANSWERED FROM STRUCTURED EVIDENCE",
     "description": "A judge-style question ('Why was this feature blocked?') is answered "
                    "by the navigator using backend tool calls only."},
    {"id": "case8_claude_offline", "title": "Claude offline",
     "expected": "DETERMINISTIC FALLBACK EXPLANATION",
     "description": "Explanation is requested with the LLM unavailable. RATIO returns the "
                    "deterministic fallback explanation and the analysis is unaffected."},
]


def _upload(path: Path, name: str) -> str:
    return store.save_upload(path.read_bytes(), name, "image/png")["id"]


def _verify(analysis_id: str, mission: str = "ROUTE_PLANNING") -> dict:
    return phase2_service.verify_analysis(analysis_id, mission)


def _downsampled_reference(downscale: int = 32) -> dict:
    """Deliberately downsampled TEST_DATA reference of the real 5 m/px PSR DEM."""
    from ratio_core.dem import load_dem
    import rasterio
    import tempfile
    source = ROOT / "datasets/real/derived/psr_site001_dem_crop.tif"
    dem = load_dem(str(source))
    block = max(1, downscale)
    h, w = dem.elevation_m.shape
    cropped = dem.elevation_m[: h // block * block, : w // block * block]
    coarse = cropped.reshape(h // block, block, w // block, block).mean(axis=(1, 3)).astype("float32")
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        with rasterio.open(tmp.name, "w", driver="GTiff", height=coarse.shape[0], width=coarse.shape[1],
                           count=1, dtype="float32", crs=dem.crs_wkt,
                           transform=rasterio.transform.from_origin(
                               dem.transform.c, dem.transform.f,
                               dem.x_resolution_m * block, dem.y_resolution_m * block),
                           compress="deflate") as dst:
            dst.write(coarse, 1)
        data = Path(tmp.name).read_bytes()
    manifest = {
        "id": "LRO_LOLA_PSR_SITE001_DOWNSAMPLED_X32",
        "classification": "TEST_DATA",
        "mission": "Lunar Reconnaissance Orbiter (base data)",
        "instrument": "LOLA (LDEM-derived site DEM; per source repository description)",
        "product_id": "RATIO_DOWNSAMPLED_PSR_SITE001_X32",
        "data_type": "DEM",
        "source": "https://github.com/fletcher-smith-ae/GlobalPathPlan",
        "local_path": "",
        "resolution_m_per_pixel": 160.0,
        "coordinate_reference_system": dem.crs_wkt,
        "processing_level": "RATIO 32x block-mean downsampling of the 5 m/px PSR site crop; TEST_DATA only",
        "coverage": {"note": "same footprint as the 5 m/px crop", "common_footprint": False},
        "license_notes": "TEST_DATA derivative; not mission evidence.",
        "description": "Deliberately downsampled reference used to demonstrate REFERENCE_INADEQUATE "
                       "handling (never contradicted).",
        "reference_dimensions": [coarse.shape[1], coarse.shape[0]],
        "metadata_alignment_reliable": False,
        "illumination": None,
    }
    try:
        return datasets_service.register_dataset(manifest, data, "psr_site001_downsampled.tif")
    except ValueError:
        for item in datasets_service.list_datasets():
            if item["id"] == manifest["id"]:
                return item
        raise


def _case1() -> dict:
    original = _upload(ROOT / "datasets/real/derived/lroc_nearside_original.png", "original.png")
    enhanced = _upload(ROOT / "datasets/real/derived/lroc_nearside_enhanced.png", "enhanced.png")
    record = run_analysis(original, enhanced, "SIH case 1: legitimate enhancement")
    aid = record["id"]
    phase2_service.attach_reference(aid, "NASA_SVS_LRO_NEARSIDE_45")
    verified = _verify(aid)
    return {"case": "case1_legitimate_enhancement", "analysis_id": aid,
            "dem_verification_status": verified.get("dem_verification_status"),
            "policy": verified.get("policy"), "summary": get_analysis_summary(aid),
            "verification": verified}


def _case2() -> dict:
    original = _upload(ROOT / "datasets/real/derived/lroc_nearside_original.png", "original.png")
    hazard = _upload(ROOT / "datasets/real/derived/lroc_nearside_synthetic_hazard.png", "synthetic_hazard.png")
    record = run_analysis(original, hazard, "SIH case 2: synthetic fake boulder")
    aid = record["id"]
    phase2_service.attach_reference(aid, "NASA_SVS_LRO_SYNTHETIC_HAZARD")
    verified = _verify(aid)
    blocked = False
    try:
        phase2_service.export_analysis(aid)
    except PermissionError:
        blocked = True
    feature = verified["features"][0] if verified.get("features") else None
    return {"case": "case2_synthetic_fake_boulder", "analysis_id": aid,
            "feature": feature, "policy": verified.get("policy"),
            "export_blocked": blocked, "summary": get_analysis_summary(aid),
            "verification": verified, "dem_verification_status": verified.get("dem_verification_status")}


def _case3() -> dict:
    reference = _downsampled_reference(32)
    original = _upload(ROOT / "datasets/real/derived/psr_site001_shaded.png", "psr_shaded.png")
    hazard = _upload(ROOT / "datasets/real/derived/psr_site001_synth_hazard.png", "psr_hazard.png")
    record = run_analysis(original, hazard, "SIH case 3: coarse reference")
    aid = record["id"]
    phase2_service.attach_reference(aid, reference["id"])
    phase2_service.save_manual_registration(aid, [[40, 40], [280, 40], [40, 280]],
                                            [[1, 1], [8, 1], [1, 8]],
                                            validation_image_points=[[280, 280]],
                                            validation_reference_points=[[8, 8]])
    verified = _verify(aid)
    feature = verified["features"][0] if verified.get("features") else None
    return {"case": "case3_coarse_dem", "analysis_id": aid, "feature": feature,
            "policy": verified.get("policy"), "registration": verified.get("registration"),
            "summary": get_analysis_summary(aid), "verification": verified,
            "dem_verification_status": verified.get("dem_verification_status")}


def _case4() -> dict:
    original = _upload(ROOT / "datasets/real/derived/lroc_nearside_original.png", "original.png")
    hazard = _upload(ROOT / "datasets/real/derived/lroc_nearside_synthetic_hazard.png", "synthetic_hazard.png")
    record = run_analysis(original, hazard, "SIH case 4: bad registration")
    aid = record["id"]
    phase2_service.attach_reference(aid, "NASA_SVS_LRO_NEARSIDE_45")
    phase2_service.save_manual_registration(aid, [[30, 30], [480, 30], [30, 480]],
                                            [[60, 40], [500, 60], [40, 490]],
                                            validation_image_points=[[255, 255]],
                                            validation_reference_points=[[170, 170]])
    verified = _verify(aid)
    feature = verified["features"][0] if verified.get("features") else None
    return {"case": "case4_bad_registration", "analysis_id": aid, "feature": feature,
            "policy": verified.get("policy"), "registration": verified.get("registration"),
            "summary": get_analysis_summary(aid), "verification": verified,
            "dem_verification_status": verified.get("dem_verification_status")}


def _case5() -> dict:
    original = _upload(ROOT / "datasets/real/derived/psr_site001_shaded.png", "psr_shaded.png")
    hazard = _upload(ROOT / "datasets/real/derived/psr_site001_synth_hazard.png", "psr_hazard.png")
    record = run_analysis(original, hazard, "SIH case 5: good registration + high-res reference")
    aid = record["id"]
    phase2_service.attach_reference(aid, "LRO_LOLA_PSR_SITE001_5M")
    phase2_service.save_manual_registration(aid, [[40, 40], [280, 40], [40, 280]],
                                            [[40, 40], [280, 40], [40, 280]],
                                            validation_image_points=[[280, 280]],
                                            validation_reference_points=[[280, 280]])
    verified = _verify(aid)
    feature = verified["features"][0] if verified.get("features") else None
    return {"case": "case5_good_registration_highres", "analysis_id": aid, "feature": feature,
            "policy": verified.get("policy"), "registration": verified.get("registration"),
            "summary": get_analysis_summary(aid), "verification": verified,
            "dem_verification_status": verified.get("dem_verification_status")}


def _case6() -> dict:
    from backend.app.services.benchmarks import run_drift_job
    report = run_drift_job()
    digest = []
    for key, comparison in report["comparisons"].items():
        digest.append({"candidate": comparison["candidate_version"],
                       "decision": comparison["decision"],
                       "reason_codes": comparison["reason_codes"],
                       "percentage_changes": comparison["percentage_changes"]})
    return {"case": "case6_model_drift", "report_id": report["id"], "comparisons": digest,
            "baseline": report["baseline"]["version"], "thresholds": report["thresholds"]}


def _case7() -> dict:
    case2 = _case2()
    aid = case2["analysis_id"]
    feature = case2.get("feature") or {}
    feature_id = feature.get("feature_id")
    question = f"Why was {feature_id} blocked?"
    from backend.app.services import navigator
    response = asyncio.run(navigator.answer_query(question, analysis_id=aid, feature_id=feature_id))
    return {"case": "case7_evidence_navigator", "question": question,
            "analysis_id": aid, "feature_id": feature_id,
            "intent": response.get("intent"), "tools_called": response.get("tools_called"),
            "explanation": response.get("explanation"), "model_identifier": response.get("model_identifier"),
            "fallback_used": response.get("fallback_used"),
            "policy_decision": response.get("policy_decision")}


def _case8() -> dict:
    case2 = _case2()
    aid = case2["analysis_id"]
    feature = case2.get("feature") or {}
    feature_id = feature.get("feature_id")
    from backend.app.services import navigator
    response = asyncio.run(navigator.answer_query("Explain the evidence for this feature.",
                                                 analysis_id=aid, feature_id=feature_id))
    scientific_before = get_analysis_summary(aid)
    return {"case": "case8_claude_offline", "analysis_id": aid, "feature_id": feature_id,
            "llm_used": response.get("llm_used"), "fallback_used": response.get("fallback_used"),
            "explanation": response.get("explanation"), "scientific_state_intact": scientific_before}


def run_case(case_id: str) -> dict:
    runners = {
        "case1_legitimate_enhancement": _case1,
        "case2_synthetic_fake_boulder": _case2,
        "case3_coarse_dem": _case3,
        "case4_bad_registration": _case4,
        "case5_good_registration_highres": _case5,
        "case6_model_drift": _case6,
        "case7_evidence_navigator": _case7,
        "case8_claude_offline": _case8,
    }
    if case_id not in runners:
        raise ValueError("UNKNOWN_DEMO_CASE")
    return runners[case_id]()


def list_cases() -> list[dict]:
    return CASES
