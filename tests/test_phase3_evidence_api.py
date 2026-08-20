"""Phase 3E — structured evidence API endpoints."""
import io
from pathlib import Path

import cv2
from fastapi.testclient import TestClient

from backend.app.main import app

ROOT = Path(__file__).parents[1]
client = TestClient(app)


def _png(a):
    ok, d = cv2.imencode(".png", a)
    assert ok
    return d.tobytes()


def _upload(data):
    r = client.post("/api/images/upload", files={"file": ("x.png", io.BytesIO(data), "image/png")})
    assert r.status_code == 201
    return r.json()["id"]


def _verified_hazard_analysis():
    base = cv2.imread(str(ROOT / "datasets/real/derived/lroc_nearside_original.png"))
    hazard = cv2.imread(str(ROOT / "datasets/real/derived/lroc_nearside_synthetic_hazard.png"))
    aid = client.post("/api/analyses", json={
        "original_image_id": _upload(_png(base)),
        "enhanced_image_id": _upload(_png(hazard)),
        "label": "evidence api test"}).json()["id"]
    attached = client.post(f"/api/analyses/{aid}/reference",
                           json={"dataset_id": "NASA_SVS_LRO_SYNTHETIC_HAZARD"})
    assert attached.status_code == 200
    verified = client.post(f"/api/analyses/{aid}/verify", json={"mission_profile": "ROUTE_PLANNING"})
    assert verified.status_code == 200
    return aid, verified.json()


def test_evidence_api_full_surface():
    aid, verified = _verified_hazard_analysis()
    feature_id = verified["features"][0]["feature_id"]

    summary = client.get(f"/api/evidence/analysis/{aid}/summary")
    assert summary.status_code == 200
    assert summary.json()["analysis_id"] == aid
    assert summary.json()["policy_decision"] == verified["policy"]["decision"]

    feature = client.get(f"/api/evidence/feature/{feature_id}", params={"analysis_id": aid})
    assert feature.status_code == 200
    body = feature.json()["feature"]
    assert body["feature_id"] == feature_id
    assert body["visual_change"] > 0

    evidence = client.get(f"/api/evidence/feature/{feature_id}/evidence", params={"analysis_id": aid})
    assert evidence.status_code == 200
    assert evidence.json()["feature"]["feature_id"] == feature_id
    assert evidence.json()["policy_decision"] == verified["policy"]["decision"]

    dem = client.get(f"/api/evidence/feature/{feature_id}/dem-support", params={"analysis_id": aid})
    assert dem.status_code == 200
    body = dem.json()
    assert body["dem_support"] is not None
    assert body["hillshade_support"] is None  # no illumination metadata in this dataset

    registration = client.get("/api/evidence/registration", params={"analysis_id": aid})
    assert registration.status_code == 200
    assert registration.json()["registration"]["method"] == "AUTO_METADATA"

    passport = client.get(f"/api/evidence/passport/{aid}")
    assert passport.status_code == 200
    assert len(passport.json()["passport_sha256"]) == 64

    decision = client.get("/api/evidence/mission-decision", params={"analysis_id": aid})
    assert decision.status_code == 200
    assert decision.json()["policy_decision"] == verified["policy"]["decision"]

    region = client.get(f"/api/evidence/region-summary/{aid}")
    assert region.status_code == 200
    assert region.json()["feature_count"] >= 1


def test_compare_features_backend_computation():
    base = cv2.imread(str(ROOT / "datasets/real/derived/lroc_nearside_original.png"))
    hazard = base.copy()
    cv2.circle(hazard, (380, 140), 18, (230, 230, 230), -1)
    cv2.circle(hazard, (260, 340), 16, (230, 230, 230), -1)
    aid = client.post("/api/analyses", json={
        "original_image_id": _upload(_png(base)),
        "enhanced_image_id": _upload(_png(hazard))}).json()["id"]
    client.post(f"/api/analyses/{aid}/reference", json={"dataset_id": "NASA_SVS_LRO_NEARSIDE_45"})
    verified = client.post(f"/api/analyses/{aid}/verify", json={"mission_profile": "MAPPING"}).json()
    ids = [f["feature_id"] for f in verified["features"]]
    assert len(ids) >= 2
    r = client.get("/api/evidence/compare", params={"feature_a": ids[0], "feature_b": ids[1], "analysis_id": aid})
    assert r.status_code == 200
    body = r.json()
    assert body["feature_a"]["feature_id"] == ids[0] and body["feature_b"]["feature_id"] == ids[1]
    assert body["comparison"]["visual_change_difference"] is not None
    assert "physical_support_difference" in body["comparison"]


def test_feature_resolution_without_analysis_id():
    aid, verified = _verified_hazard_analysis()
    feature_id = verified["features"][0]["feature_id"]
    r = client.get(f"/api/evidence/feature/{feature_id}")
    assert r.status_code == 200
    assert r.json()["analysis_id"]


def test_missing_feature_is_structured():
    r = client.get("/api/evidence/feature/F99")
    assert r.status_code == 404 and r.json()["error"] == "FEATURE_NOT_FOUND"


def test_benchmark_and_drift_endpoints_after_run():
    client.post("/api/benchmarks/run")
    b = client.get("/api/evidence/benchmark")
    assert b.status_code == 200
    assert b.json()["data_classification"] in {"SYNTHETIC", "MIXED", "REAL"}
    client.post("/api/drift/run")
    d = client.get("/api/evidence/drift")
    assert d.status_code == 200
    assert d.json()["baseline"]["version"]
    html = client.get("/api/benchmarks/report.html")
    assert html.status_code == 200 and "benchmark" in html.text


def test_health_phase3_reports_offline_mode_without_api_key():
    r = client.get("/api/health/phase3")
    assert r.status_code == 200
    body = r.json()
    assert body["phase"] == 3 and body["phase1_frozen"] and body["phase2_frozen"]
    assert body["claude_mode"] in {"CLAUDE_OFFLINE", "CLAUDE_EXPLANATION_ENABLED"}
    assert body["deterministic_fallback"] == "ENABLED"


def test_evidence_report_artifact_written():
    aid, verified = _verified_hazard_analysis()
    r = client.get(f"/api/analyses/{aid}/evidence-report")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    body = r.json()
    assert body["analysis_id"] == aid
    assert body["features"]
