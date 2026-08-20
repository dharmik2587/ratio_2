"""Phase 3A/3J — high-resolution real reference and SIH demo cases."""
import json
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_origin

from backend.app.main import app
from backend.app.services import demo

ROOT = Path(__file__).parents[1]
client = TestClient(app)

HIGH_RES_AVAILABLE = (ROOT / "datasets/real/derived/psr_site001_dem_crop.tif").exists()


def test_phase3_manifest_has_real_highres_entry_with_provenance():
    manifest = json.loads((ROOT / "datasets/manifests/phase3_datasets.json").read_text())
    real = [e for e in manifest["entries"] if e["classification"] == "REAL"]
    assert real
    entry = real[0]
    for field in ("mission", "instrument", "product_id", "source", "resolution_m_per_pixel",
                  "coordinate_reference_system", "processing_level", "license_notes", "hashes"):
        assert field in entry, f"missing provenance field {field}"
    assert entry["resolution_m_per_pixel"] == 5.0
    assert "limited provenance" in entry["note"].lower() or "not documented" in entry["processing_level"].lower()


@pytest.mark.skipif(not HIGH_RES_AVAILABLE, reason="run scripts/prepare_phase3_highres.py first")
def test_high_res_reference_loads_and_is_projected():
    from ratio_core.dem import load_dem
    dem = load_dem(str(ROOT / "datasets/real/derived/psr_site001_dem_crop.tif"))
    assert dem.x_resolution_m == 5.0 and dem.y_resolution_m == 5.0
    assert dem.valid_mask.any()
    assert dem.crs_wkt


@pytest.mark.skipif(not HIGH_RES_AVAILABLE, reason="run scripts/prepare_phase3_highres.py first")
def test_coarse_vs_highres_resolution_adequacy():
    """The same feature-scale test: adequate at 5 m/px, inadequate at 160 m/px."""
    from ratio_core.physical import resolution_adequacy
    config = json.loads((ROOT / "configs/phase2.json").read_text())
    status_high, ratio_high = resolution_adequacy(140.0, 5.0, config)
    assert status_high == "REFERENCE_RESOLUTION_ADEQUATE" and ratio_high >= 3
    status_coarse, ratio_coarse = resolution_adequacy(140.0, 160.0, config)
    assert status_coarse == "REFERENCE_TOO_COARSE" and ratio_coarse < 1.5


def test_sih_case1_legitimate_enhancement():
    r = demo.run_case("case1_legitimate_enhancement")
    assert r["dem_verification_status"] == "NOT_REQUIRED"
    assert r["policy"]["decision"] == "NO_SIGNIFICANT_CHANGE"


def test_sih_case2_synthetic_fake_boulder():
    r = demo.run_case("case2_synthetic_fake_boulder")
    assert r["feature"]["visual_change"] > 0.5
    assert r["feature"]["physical_support"] < 0.6
    assert r["feature"]["unsupported_risk"] > 0.3
    assert r["policy"]["decision"] in {"NOT_SAFE", "REVIEW_REQUIRED"}
    assert r["export_blocked"] is True


def test_sih_case3_coarse_dem_not_contradicted():
    r = demo.run_case("case3_coarse_dem")
    assert r["feature"]["status"] == "REFERENCE_INADEQUATE"
    assert r["feature"]["status"] != "CONTRADICTED"


def test_sih_case4_bad_registration_unresolved():
    r = demo.run_case("case4_bad_registration")
    assert r["registration"]["validation_max_error_px"] > 20
    assert r["registration"]["quality_label"] == "INVALID"
    assert r["feature"]["status"] == "UNRESOLVED"
    assert r["feature"]["status"] != "CONTRADICTED"


@pytest.mark.skipif(not HIGH_RES_AVAILABLE, reason="run scripts/prepare_phase3_highres.py first")
def test_sih_case5_good_registration_highres():
    r = demo.run_case("case5_good_registration_highres")
    assert r["registration"]["validation_basis"] == "FIT_3_VALIDATE_INDEPENDENT"
    assert r["registration"]["validation_max_error_px"] <= 2.0
    assert r["feature"]["reference_resolution"]["status"] == "REFERENCE_RESOLUTION_ADEQUATE"
    assert r["feature"]["reference_resolution"]["meters_per_pixel"] == 5.0
    assert r["feature"]["physical_support"] is not None


def test_sih_case6_model_drift_versions():
    r = demo.run_case("case6_model_drift")
    decisions = {c["candidate"]: c["decision"] for c in r["comparisons"]}
    assert decisions.get("v2") in {"REVIEW", "QUARANTINE"}
    assert decisions.get("v3") in {"REVIEW", "QUARANTINE"}


def test_sih_case7_navigator_answers_from_evidence():
    r = demo.run_case("case7_evidence_navigator")
    assert r["intent"] == "why_feature"
    assert "get_feature_evidence" in r["tools_called"]
    assert r["explanation"]["executive_summary"]


def test_sih_case8_claude_offline_fallback():
    r = demo.run_case("case8_claude_offline")
    assert r["fallback_used"] is True
    assert r["explanation"]["recommendation"]
    assert r["scientific_state_intact"]["policy_decision"] in {"NOT_SAFE", "REVIEW_REQUIRED", "SAFE_TO_EXPORT"}


def test_demo_cases_endpoint_lists_eight_cases():
    body = client.get("/api/demo/cases").json()
    assert len(body["cases"]) == 8


def test_unknown_demo_case_is_structured():
    r = client.post("/api/demo/run/case99")
    assert r.status_code == 404 and r.json()["error"] == "UNKNOWN_DEMO_CASE"


def test_physical_consistency_synthetic_support_case():
    """SYNTHETIC_PHYSICAL_CONSISTENCY_TEST: a synthetic feature present in BOTH the
    visual input and the reference terrain must produce stronger physical support
    than a visual-only hazard."""
    from ratio_core.dem import clear_dem_cache, load_dem
    from ratio_core.evidence import analyze_image_pair
    from ratio_core.physical import verify_region
    from ratio_core.registration import auto_dimension_registration
    config = json.loads((ROOT / "configs/phase2.json").read_text())
    y, x = np.mgrid[:80, :80]
    ridge = 60.0 * np.exp(-((x - 40) ** 2 + (y - 40) ** 2) / (2 * 7 ** 2))
    dem_arr = (10.0 + 0.5 * x + ridge).astype("float32")
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        with rasterio.open(tmp.name, "w", driver="GTiff", height=80, width=80, count=1,
                           dtype="float32", crs="EPSG:3857", transform=from_origin(0, 800, 10, 10)) as dst:
            dst.write(dem_arr, 1)
    gy, gx = np.gradient(dem_arr, 10.0, 10.0)
    shade = np.clip((np.hypot(gx, gy) / 6.0), 0, 1)
    render = np.uint8(60 + 160 * shade)
    noise = np.random.default_rng(7).normal(0, 10, render.shape)
    original = np.clip(np.rint(render.astype(float) + noise), 0, 255).astype(np.uint8)
    enhanced = original.copy()
    disc = (x - 40) ** 2 + (y - 40) ** 2 <= 10 ** 2
    enhanced[disc] = np.clip(enhanced[disc].astype(float) + 40, 0, 255).astype(np.uint8)
    result = analyze_image_pair(original, enhanced, json.loads((ROOT / "configs/stage1.json").read_text()))
    regions = [r for r in result.regions if r.visual_score >= config["visual"]["min_meaningful_change"]]
    assert regions, "ridge brightening must be detected"
    clear_dem_cache()
    dem = load_dem(tmp.name)
    registration = auto_dimension_registration((80, 80), (80, 80), True)
    feature = {"id": "F01", "bbox": [30, 30, 20, 20], "visual_score": regions[0].visual_score}
    evidence = verify_region(feature, result.normalized_original, result.normalized_enhanced,
                             dem, registration, 1.0, config, illumination=None)
    assert evidence.physical_support is not None
    assert evidence.physical_support >= 0.5, "terrain-consistent synthetic feature should show physical support"
    assert evidence.status in {"SUPPORTED", "PARTIALLY_SUPPORTED"}
