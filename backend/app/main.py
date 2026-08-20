from __future__ import annotations
from contextlib import asynccontextmanager
import json
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response, JSONResponse, FileResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from backend.app.core.config import ALLOWED_CONTENT_TYPES, MAX_UPLOAD_BYTES, ROOT
from backend.app.schemas.models import (AnalysisCreate, AnalysisCreateResponse, ImageUploadResponse,
                                        ReferenceAttach, AlignmentCreate, VerifyRequest, NavigatorQuery)
from backend.app.services.datasets import list_datasets, register_dataset, dataset_preview
from backend.app.services.phase2 import attach_reference, save_manual_registration, verify_analysis, get_physical, get_passport, export_analysis
from backend.app.services.analysis import run_analysis
from backend.app.services.store import analysis_path, ensure_dirs, get_analysis, save_upload
from backend.app.services import evidence_api, navigator, benchmarks, demo
from backend.app.services.llm_client import LLMClient, LLMUnavailableError
from ratio_core.explain import build_evidence_payload, build_fallback_explanation


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_dirs()
    yield


app = FastAPI(title="RATIO API", version="3.0.0", description="Evidence-gated verification prototype — Phase 3", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173", "http://127.0.0.1:4173"],
                   allow_methods=["*"], allow_headers=["*"])


def error(status: int, code: str, message: str, **extra) -> HTTPException:
    return HTTPException(status, detail={"error": code, "message": message, **extra})


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"error": "HTTP_ERROR", "message": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content=detail)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": "INVALID_REQUEST",
        "message": "Request data is missing or malformed.", "fields": [".".join(map(str, e["loc"])) for e in exc.errors()]})


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "ratio-api", "stage": 1}


@app.get("/api/health/phase2")
def phase2_health():
    return {"status":"ok","service":"ratio-api","phase":2,"phase1_frozen":True}


@app.get("/api/health/phase3")
def phase3_health():
    llm = LLMClient(json.loads((ROOT / "configs/phase3.json").read_text())["llm"])
    return {"status": "ok", "service": "ratio-api", "phase": 3,
            "phase1_frozen": True, "phase2_frozen": True,
            "claude_mode": "CLAUDE_EXPLANATION_ENABLED" if llm.available else "CLAUDE_OFFLINE",
            "deterministic_fallback": "ENABLED"}


@app.post("/api/images/upload", response_model=ImageUploadResponse, status_code=201)
async def upload_image(file: UploadFile = File(...)):
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise error(415, "UNSUPPORTED_IMAGE_TYPE", "Unsupported file format. Use PNG, JPEG, TIFF, or WebP.")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise error(413, "IMAGE_TOO_LARGE", "Image exceeds the configured 20 MB safety limit.")
    if not data:
        raise error(422, "EMPTY_FILE", "Uploaded file is empty.")
    try:
        return save_upload(data, file.filename or "image", content_type)
    except ValueError as exc:
        message = str(exc)
        if "40 megapixel" in message:
            raise error(413, "MEGAPIXEL_LIMIT_EXCEEDED", message) from exc
        if "decode" in message:
            raise error(422, "IMAGE_DECODE_FAILED", message) from exc
        raise error(422, "INVALID_IMAGE", message) from exc


@app.post("/api/analyses", response_model=AnalysisCreateResponse, status_code=201)
def create_analysis(request: AnalysisCreate):
    try:
        record = run_analysis(request.original_image_id, request.enhanced_image_id, request.label)
    except FileNotFoundError as exc:
        raise error(404, "IMAGE_NOT_FOUND", f"Input image was not found: {exc}") from exc
    except (ValueError, KeyError) as exc:
        raise error(422, "INVALID_CONFIGURATION", f"Scientific configuration is invalid: {exc}") from exc
    return {"id": record["id"], "status": record["status"]}


@app.get("/api/analyses/{analysis_id}")
def read_analysis(analysis_id: str):
    try:
        return get_analysis(analysis_id)
    except FileNotFoundError:
        raise error(404, "ANALYSIS_NOT_FOUND", "Analysis not found.")


@app.get("/api/analyses/{analysis_id}/features")
def read_features(analysis_id: str):
    try:
        record = get_analysis(analysis_id)
        return {"analysis_id": analysis_id, "comparison_status": record["comparison_status"],
                "features": record["features"]}
    except FileNotFoundError:
        raise error(404, "ANALYSIS_NOT_FOUND", "Analysis not found.")


@app.get("/api/analyses/{analysis_id}/download")
def download_analysis(analysis_id: str):
    try:
        path = analysis_path(analysis_id) / "analysis.json"
    except FileNotFoundError:
        raise error(404, "ANALYSIS_NOT_FOUND", "Analysis not found.")
    if not path.exists():
        raise error(404, "ANALYSIS_NOT_FOUND", "Analysis not found.")
    return FileResponse(path, media_type="application/json", filename=f"ratio-{analysis_id}.json")


@app.get("/api/analyses/{analysis_id}/evidence-report")
def evidence_report_download(analysis_id: str):
    path = analysis_path(analysis_id) / "evidence_report.json"
    if not path.exists():
        try:
            evidence_api.evidence_report(analysis_id)
        except FileNotFoundError:
            raise error(404, "EVIDENCE_REPORT_UNAVAILABLE", "Evidence report is unavailable for this analysis.")
    return FileResponse(path, media_type="application/json", filename=f"ratio-evidence-{analysis_id}.json")


@app.get("/api/analyses/{analysis_id}/artifacts/{filename}")
def artifact(analysis_id: str, filename: str):
    if filename not in {"difference_map.png", "suspicious_mask.png", "annotated.png"}:
        raise error(404, "ARTIFACT_NOT_FOUND", "Artifact not found.")
    try:
        path = analysis_path(analysis_id) / filename
    except FileNotFoundError:
        raise error(404, "ARTIFACT_NOT_FOUND", "Artifact not found.")
    if not path.exists():
        raise error(404, "ARTIFACT_NOT_AVAILABLE", "Evidence artifact is unavailable for this comparison state.")
    return FileResponse(path, media_type="image/png")


@app.get('/api/datasets')
def datasets_list():
    return {'datasets': list_datasets()}


@app.post('/api/datasets', status_code=201)
async def datasets_create(manifest: str = Form(...), file: UploadFile = File(...)):
    try:
        metadata = json.loads(manifest)
    except json.JSONDecodeError as exc:
        raise error(422, 'INVALID_DATASET_MANIFEST', 'Dataset manifest is not valid JSON.') from exc
    try:
        return register_dataset(metadata, await file.read(MAX_UPLOAD_BYTES + 1), file.filename or 'reference.tif')
    except ValueError as exc:
        raise error(422, 'INVALID_DEM', str(exc)) from exc


@app.get('/api/datasets/{dataset_id}/preview')
def datasets_preview(dataset_id: str, kind: str = 'hillshade'):
    if kind not in {'dem', 'hillshade'}:
        raise error(422, 'INVALID_PREVIEW_KIND', 'Preview kind must be dem or hillshade.')
    try:
        return Response(dataset_preview(dataset_id, kind), media_type='image/png')
    except FileNotFoundError as exc:
        raise error(404, 'DEM_NOT_FOUND', 'Dataset or DEM was not found.') from exc
    except ValueError as exc:
        raise error(422, 'INVALID_DEM', str(exc)) from exc


@app.post('/api/analyses/{analysis_id}/reference')
def analyses_reference(analysis_id: str, request: ReferenceAttach):
    try:
        return attach_reference(analysis_id, request.dataset_id)
    except FileNotFoundError as exc:
        raise error(404, 'REFERENCE_UNAVAILABLE', f'Reference could not be attached: {exc}') from exc


@app.post('/api/analyses/{analysis_id}/align')
def analyses_align(analysis_id: str, request: AlignmentCreate):
    try:
        return save_manual_registration(analysis_id, request.image_points, request.reference_points,
                                        request.validation_image_points, request.validation_reference_points)
    except FileNotFoundError as exc:
        raise error(404, 'REFERENCE_UNAVAILABLE', 'Attach a reference before alignment.') from exc
    except ValueError as exc:
        code = str(exc) if str(exc) in {'INSUFFICIENT_CONTROL_POINTS', 'DEGENERATE_CONTROL_POINTS',
                                        'INVALID_CONTROL_POINTS', 'INVALID_VALIDATION_POINTS'} else 'REGISTRATION_FAILED'
        raise error(422, code, 'Manual affine registration could not be accepted.') from exc


@app.post('/api/analyses/{analysis_id}/verify')
def analyses_verify(analysis_id: str, request: VerifyRequest):
    try:
        return verify_analysis(analysis_id, request.mission_profile)
    except FileNotFoundError as exc:
        raise error(404, 'ANALYSIS_OR_REFERENCE_NOT_FOUND', str(exc)) from exc
    except ValueError as exc:
        code = str(exc) if str(exc) in {'INVALID_MISSION_PROFILE', 'NO_OVERLAP'} else 'PHYSICAL_EVIDENCE_UNAVAILABLE'
        raise error(422, code, str(exc)) from exc


@app.get('/api/analyses/{analysis_id}/physical-evidence')
def analyses_physical(analysis_id: str):
    try:
        return get_physical(analysis_id)
    except FileNotFoundError as exc:
        raise error(404, 'PHYSICAL_EVIDENCE_UNAVAILABLE', 'Run Phase-2 verification first.') from exc


@app.post('/api/analyses/{analysis_id}/export')
def analyses_export(analysis_id: str):
    try:
        _, payload = export_analysis(analysis_id)
        return payload
    except PermissionError as exc:
        raise error(409, 'POLICY_BLOCKED_EXPORT', 'Mission-use export is blocked by the deterministic policy. The analysis report remains downloadable.') from exc
    except FileNotFoundError as exc:
        raise error(404, 'PHYSICAL_EVIDENCE_UNAVAILABLE', 'Run Phase-2 verification first.') from exc


@app.get('/api/analyses/{analysis_id}/passport')
def analyses_passport(analysis_id: str):
    try:
        return get_passport(analysis_id)
    except FileNotFoundError as exc:
        raise error(404, 'PASSPORT_UNAVAILABLE', 'Run Phase-2 verification first.') from exc


# ----------------------------------------------------------------- Phase 3E evidence API

@app.get('/api/evidence/analysis/{analysis_id}/summary')
def ev_analysis_summary(analysis_id: str):
    try:
        return evidence_api.get_analysis_summary(analysis_id)
    except FileNotFoundError as exc:
        raise error(404, 'EVIDENCE_UNAVAILABLE', str(exc)) from exc


@app.get('/api/evidence/feature/{feature_id}')
def ev_feature(feature_id: str, analysis_id: str | None = None):
    try:
        return evidence_api.get_feature(feature_id, analysis_id)
    except FileNotFoundError as exc:
        raise error(404, 'FEATURE_NOT_FOUND', str(exc)) from exc


@app.get('/api/evidence/feature/{feature_id}/evidence')
def ev_feature_evidence(feature_id: str, analysis_id: str | None = None):
    try:
        return evidence_api.get_feature_evidence(feature_id, analysis_id)
    except FileNotFoundError as exc:
        raise error(404, 'FEATURE_NOT_FOUND', str(exc)) from exc


@app.get('/api/evidence/feature/{feature_id}/dem-support')
def ev_dem_support(feature_id: str, analysis_id: str | None = None):
    try:
        return evidence_api.get_dem_support(feature_id, analysis_id)
    except FileNotFoundError as exc:
        raise error(404, 'FEATURE_NOT_FOUND', str(exc)) from exc


@app.get('/api/evidence/registration')
def ev_registration(analysis_id: str | None = None, feature_id: str | None = None):
    try:
        return evidence_api.get_registration(analysis_id, feature_id)
    except FileNotFoundError as exc:
        raise error(404, 'REGISTRATION_UNAVAILABLE', str(exc)) from exc


@app.get('/api/evidence/passport/{analysis_id}')
def ev_passport(analysis_id: str):
    try:
        return evidence_api.get_processing_passport(analysis_id)
    except FileNotFoundError as exc:
        raise error(404, 'PASSPORT_UNAVAILABLE', str(exc)) from exc


@app.get('/api/evidence/compare')
def ev_compare(feature_a: str, feature_b: str, analysis_id: str | None = None):
    try:
        return evidence_api.compare_features(feature_a, feature_b, analysis_id)
    except FileNotFoundError as exc:
        raise error(404, 'FEATURE_NOT_FOUND', str(exc)) from exc


@app.get('/api/evidence/region-summary/{analysis_id}')
def ev_region_summary(analysis_id: str, region: str = "ALL"):
    try:
        return evidence_api.get_region_summary(analysis_id, region)
    except FileNotFoundError as exc:
        raise error(404, 'EVIDENCE_UNAVAILABLE', str(exc)) from exc


@app.get('/api/evidence/mission-decision')
def ev_mission_decision(analysis_id: str | None = None, feature_id: str | None = None):
    try:
        return evidence_api.get_mission_decision(analysis_id, feature_id)
    except FileNotFoundError as exc:
        raise error(404, 'EVIDENCE_UNAVAILABLE', str(exc)) from exc


@app.get('/api/evidence/benchmark')
def ev_benchmark():
    try:
        return evidence_api.get_benchmark_summary()
    except FileNotFoundError as exc:
        raise error(404, 'BENCHMARK_UNAVAILABLE', str(exc)) from exc


@app.get('/api/evidence/drift')
def ev_drift():
    try:
        return evidence_api.get_model_drift_report()
    except FileNotFoundError as exc:
        raise error(404, 'DRIFT_REPORT_UNAVAILABLE', str(exc)) from exc


# ----------------------------------------------------------------- Phase 3C/3D benchmark + drift

@app.post('/api/benchmarks/run')
def benchmarks_run():
    try:
        return benchmarks.run_benchmark_job()
    except Exception as exc:
        raise error(500, 'BENCHMARK_FAILED', str(exc)) from exc


@app.get('/api/benchmarks/latest')
def benchmarks_latest():
    try:
        return evidence_api.get_benchmark_summary()
    except FileNotFoundError as exc:
        raise error(404, 'BENCHMARK_UNAVAILABLE', str(exc)) from exc


@app.get('/api/benchmarks/report.html')
def benchmarks_html():
    try:
        summary = evidence_api.get_benchmark_summary()
        rows = []
        for split, s in summary["splits"].items():
            for cls, c in s["classes"].items():
                rows.append(f"<tr><td>{split}</td><td>{cls}</td><td>{c['data_classification']}</td>"
                            f"<td>{c['number_of_samples']}</td><td>{c['detected']}</td><td>{c['missed']}</td>"
                            f"<td>{c['false_alarms']}</td><td>{c['average_iou']}</td><td>{c['median_iou']}</td></tr>")
        html = (f"<!doctype html><html><head><title>RATIO benchmark report</title></head><body>"
                f"<h1>RATIO synthetic benchmark report</h1><p>data_classification={summary['data_classification']} "
                f"| generated={summary['generated_at']}</p><table border='1'><tr><th>split</th><th>class</th>"
                f"<th>data</th><th>samples</th><th>detected</th><th>missed</th><th>false alarms</th>"
                f"<th>avg IoU</th><th>median IoU</th></tr>{''.join(rows)}</table></body></html>")
        return Response(html, media_type="text/html")
    except FileNotFoundError as exc:
        raise error(404, 'BENCHMARK_UNAVAILABLE', str(exc)) from exc


@app.post('/api/drift/run')
def drift_run():
    try:
        return benchmarks.run_drift_job()
    except Exception as exc:
        raise error(500, 'DRIFT_FAILED', str(exc)) from exc


@app.get('/api/drift/latest')
def drift_latest():
    try:
        return evidence_api.get_model_drift_report()
    except FileNotFoundError as exc:
        raise error(404, 'DRIFT_REPORT_UNAVAILABLE', str(exc)) from exc


# ----------------------------------------------------------------- Phase 3F explanation

@app.post('/api/analyses/{analysis_id}/explain')
async def analyses_explain(analysis_id: str, feature_id: str | None = None):
    """Generate the five-field explanation report for an analysis/feature.

    Claude receives only compact structured evidence. On any LLM failure the
    deterministic fallback explanation is returned; the scientific records are
    never modified by this endpoint.
    """
    llm_config = json.loads((ROOT / "configs" / "phase3.json").read_text())["llm"]
    llm = LLMClient(llm_config)
    try:
        phase2 = evidence_api._phase2(analysis_id)
    except FileNotFoundError:
        raise error(404, "PHYSICAL_EVIDENCE_UNAVAILABLE", "Run Phase-2 verification first.")
    feature = None
    for candidate in phase2.get("features", []):
        if candidate.get("feature_id") == feature_id:
            feature = candidate
            break
    registration = evidence_api._registration(analysis_id)
    policy = phase2.get("policy")
    payload = build_evidence_payload(analysis_id, feature_id, get_analysis(analysis_id),
                                     feature, registration, policy)
    used_llm, fallback = False, False
    model_identifier = llm.identifier() if llm.available else "deterministic-offline"
    if llm.available and phase2.get("dem_verification_status") not in {"NOT_REQUIRED"}:
        used_llm = True
        try:
            report = dict(await llm.explain_evidence(payload))
        except LLMUnavailableError:
            fallback = True
            report = build_fallback_explanation(phase2, feature, registration, policy, phase2.get("dataset"))
    else:
        fallback = True
        report = build_fallback_explanation(phase2, feature, registration, policy, phase2.get("dataset"))
    result = {
        "analysis_id": analysis_id,
        "feature_id": feature_id,
        "model_identifier": model_identifier,
        "llm_used": used_llm,
        "fallback_used": fallback,
        "report": report,
        "policy_decision": (policy or {}).get("decision"),
        "note": "The deterministic policy decision is attached by the backend, never by the LLM.",
    }
    if feature_id is not None:
        (analysis_path(analysis_id) / f"llm_explanation_{feature_id}.json").write_text(json.dumps(result, indent=2))
    else:
        (analysis_path(analysis_id) / "llm_explanation.json").write_text(json.dumps(result, indent=2))
    return result


# ----------------------------------------------------------------- Phase 3G navigator

@app.post('/api/navigator/query')
async def navigator_query(request: NavigatorQuery):
    try:
        return await navigator.answer_query(request.question, request.analysis_id, request.feature_id)
    except Exception as exc:
        raise error(500, 'NAVIGATOR_ERROR', str(exc)) from exc


@app.get('/api/navigator/audit')
def navigator_audit(limit: int = 50):
    return navigator.list_audit(min(limit, 500))


# ----------------------------------------------------------------- Phase 3J demo mode

@app.get('/api/demo/cases')
def demo_cases():
    return {"cases": demo.list_cases()}


@app.post('/api/demo/run/{case_id}')
def demo_run(case_id: str):
    try:
        return demo.run_case(case_id)
    except ValueError as exc:
        raise error(404, 'UNKNOWN_DEMO_CASE', str(exc)) from exc
    except FileNotFoundError as exc:
        raise error(404, 'DEMO_DATA_UNAVAILABLE', str(exc)) from exc
    except Exception as exc:
        raise error(500, 'DEMO_FAILED', str(exc)) from exc
