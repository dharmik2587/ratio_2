"""Phase 3 — performance sweep across raster sizes (audit §48).

Times the frozen Phase-1 pipeline and the Phase-2 physical verification at
multiple image sizes with real code paths, and records everything to
docs/performance_sweep.json. No production-scale claims are made.
"""
from __future__ import annotations
import io
import json
import time
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

ROOT = Path(__file__).parents[1]
import sys
sys.path.insert(0, str(ROOT))

from backend.app.main import app
from ratio_core.dem import clear_dem_cache, load_dem, terrain_derivatives
from ratio_core.evidence import analyze_image_pair

CONFIG1 = json.loads((ROOT / "configs/stage1.json").read_text())
C = TestClient(app)


def timed(fn, *args, repeat=3, **kwargs):
    best = float("inf")
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn(*args, **kwargs)
        best = min(best, time.perf_counter() - t0)
    return round(best, 4)


def main():
    rng = np.random.default_rng(2026)
    rows = []
    base = cv2.imread(str(ROOT / "datasets/real/derived/lroc_nearside_original.png"))

    for size in (256, 512, 1024, 2048):
        a = cv2.resize(base, (size, size), interpolation=cv2.INTER_AREA)
        b = a.copy()
        r = max(6, size // 26)
        cv2.circle(b, (size // 2, size // 2), r, (235, 235, 235), -1)
        cv2.circle(b, (size // 2 - r // 3, size // 2 - r // 3), max(2, 2 * r // 3), (30, 30, 30), -1)
        phase1_ms = timed(analyze_image_pair, a, b, CONFIG1) * 1000
        result = analyze_image_pair(a, b, CONFIG1)
        regions = len(result.regions)
        rows.append({"size_px": size, "phase1_analysis_ms": round(phase1_ms, 1),
                     "regions_detected": regions,
                     "comparability": result.comparison.comparison_status})

    # DEM derivative timing: Phase-2 coarse reference vs Phase-3 high-res reference
    for name, path in [("phase2_ldem_360x360", "datasets/real/derived/lola_ldem4_nearside_dem.tif"),
                       ("phase3_psr_320x320_5m", "datasets/real/derived/psr_site001_dem_crop.tif")]:
        clear_dem_cache()  # cold load, single measurement (the cache would hide real I/O)
        t0 = time.perf_counter()
        dem = load_dem(str(ROOT / path))
        load_ms = (time.perf_counter() - t0) * 1000
        deriv_ms = timed(terrain_derivatives, dem, repeat=3) * 1000
        clear_dem_cache()
        rows.append({"size_px": dem.elevation_m.shape[0], "dataset": name,
                     "dem_load_ms_cold": round(load_ms, 1), "terrain_derivatives_ms": round(deriv_ms, 1)})

    # full HTTP pipeline timing (upload → analysis → reference → verify → explain)
    a = cv2.resize(base, (512, 512), interpolation=cv2.INTER_AREA)
    b = a.copy()
    cv2.circle(b, (256, 256), 20, (235, 235, 235), -1)
    cv2.circle(b, (250, 250), 14, (30, 30, 30), -1)

    def http_pipeline():
        u1 = C.post("/api/images/upload", files={"file": ("o.png", io.BytesIO(cv2.imencode(".png", a)[1].tobytes()), "image/png")}).json()["id"]
        u2 = C.post("/api/images/upload", files={"file": ("e.png", io.BytesIO(cv2.imencode(".png", b)[1].tobytes()), "image/png")}).json()["id"]
        aid = C.post("/api/analyses", json={"original_image_id": u1, "enhanced_image_id": u2}).json()["id"]
        C.post(f"/api/analyses/{aid}/reference", json={"dataset_id": "NASA_SVS_LRO_NEARSIDE_45"})
        C.post(f"/api/analyses/{aid}/verify", json={"mission_profile": "MAPPING"})
        C.post(f"/api/analyses/{aid}/explain")
        return aid

    total_ms = timed(http_pipeline, repeat=2) * 1000
    rows.append({"size_px": 512, "full_http_pipeline_ms": round(total_ms, 1)})

    out = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "notes": ["Prototype local storage; timings are best-of-N on this workspace.",
                     "No production-scale performance claims are implied."],
           "results": rows}
    (ROOT / "docs/performance_sweep.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
