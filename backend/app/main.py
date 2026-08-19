from __future__ import annotations
from contextlib import asynccontextmanager
import json
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from backend.app.core.config import ALLOWED_CONTENT_TYPES, MAX_UPLOAD_BYTES
from backend.app.schemas.models import AnalysisCreate, AnalysisCreateResponse, ImageUploadResponse, ReferenceAttach, AlignmentCreate, VerifyRequest
from backend.app.services.datasets import list_datasets, get_dataset, register_dataset, dataset_preview
from backend.app.services.phase2 import attach_reference, save_manual_registration, verify_analysis, get_physical, get_passport, export_analysis
from backend.app.services.analysis import run_analysis
from backend.app.services.store import analysis_path, ensure_dirs, get_analysis, save_upload


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_dirs()
    yield


app = FastAPI(title="RATIO API", version="0.1.1", description="Evidence-gated verification prototype — Stage 1", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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
    return {'datasets':list_datasets()}

@app.post('/api/datasets',status_code=201)
async def datasets_create(manifest: str=Form(...), file: UploadFile=File(...)):
    try:metadata=json.loads(manifest)
    except json.JSONDecodeError as exc:raise error(422,'INVALID_DATASET_MANIFEST','Dataset manifest is not valid JSON.') from exc
    try:return register_dataset(metadata,await file.read(MAX_UPLOAD_BYTES+1),file.filename or 'reference.tif')
    except ValueError as exc:raise error(422,'INVALID_DEM',str(exc)) from exc

@app.get('/api/datasets/{dataset_id}/preview')
def datasets_preview(dataset_id:str,kind:str='hillshade'):
    if kind not in {'dem','hillshade'}:raise error(422,'INVALID_PREVIEW_KIND','Preview kind must be dem or hillshade.')
    try:return Response(dataset_preview(dataset_id,kind),media_type='image/png')
    except FileNotFoundError as exc:raise error(404,'DEM_NOT_FOUND','Dataset or DEM was not found.') from exc
    except ValueError as exc:raise error(422,'INVALID_DEM',str(exc)) from exc

@app.post('/api/analyses/{analysis_id}/reference')
def analyses_reference(analysis_id:str,request:ReferenceAttach):
    try:return attach_reference(analysis_id,request.dataset_id)
    except FileNotFoundError as exc:raise error(404,'REFERENCE_UNAVAILABLE',f'Reference could not be attached: {exc}') from exc

@app.post('/api/analyses/{analysis_id}/align')
def analyses_align(analysis_id:str,request:AlignmentCreate):
    try:return save_manual_registration(analysis_id,request.image_points,request.reference_points)
    except FileNotFoundError as exc:raise error(404,'REFERENCE_UNAVAILABLE','Attach a reference before alignment.') from exc
    except ValueError as exc:
        code=str(exc) if str(exc) in {'INSUFFICIENT_CONTROL_POINTS','DEGENERATE_CONTROL_POINTS','INVALID_CONTROL_POINTS'} else 'REGISTRATION_FAILED'
        raise error(422,code,'Manual affine registration could not be accepted.') from exc

@app.post('/api/analyses/{analysis_id}/verify')
def analyses_verify(analysis_id:str,request:VerifyRequest):
    try:return verify_analysis(analysis_id,request.mission_profile)
    except FileNotFoundError as exc:raise error(404,'ANALYSIS_OR_REFERENCE_NOT_FOUND',str(exc)) from exc
    except ValueError as exc:
        code=str(exc) if str(exc) in {'INVALID_MISSION_PROFILE','NO_OVERLAP'} else 'PHYSICAL_EVIDENCE_UNAVAILABLE'
        raise error(422,code,str(exc)) from exc

@app.get('/api/analyses/{analysis_id}/physical-evidence')
def analyses_physical(analysis_id:str):
    try:return get_physical(analysis_id)
    except FileNotFoundError as exc:raise error(404,'PHYSICAL_EVIDENCE_UNAVAILABLE','Run Phase-2 verification first.') from exc

@app.post('/api/analyses/{analysis_id}/export')
def analyses_export(analysis_id:str):
    try:
        _,payload=export_analysis(analysis_id);return payload
    except PermissionError as exc:raise error(409,'POLICY_BLOCKED_EXPORT','Mission-use export is blocked by the deterministic policy. The analysis report remains downloadable.') from exc
    except FileNotFoundError as exc:raise error(404,'PHYSICAL_EVIDENCE_UNAVAILABLE','Run Phase-2 verification first.') from exc

@app.get('/api/analyses/{analysis_id}/passport')
def analyses_passport(analysis_id:str):
    try:return get_passport(analysis_id)
    except FileNotFoundError as exc:raise error(404,'PASSPORT_UNAVAILABLE','Run Phase-2 verification first.') from exc
