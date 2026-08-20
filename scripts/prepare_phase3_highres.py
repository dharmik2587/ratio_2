"""Phase 3A — prepare the high-resolution REAL local lunar terrain reference.

The source is a real LOLA/LDEM-derived south-polar site DEM (5 m/pixel, polar
stereographic) distributed in the GlobalPathPlan GitHub repository:

  https://github.com/fletcher-smith-ae/GlobalPathPlan (file Site001PSR.tif)

RATIO does not fabricate provenance. The source repository does not document the
derivation chain beyond its project description ("using LDEM slope and elevation
data"), so the manifest records exactly what is known and flags what is not.

Outputs (all derived, not sensor products):

  datasets/real/source/psr_site001_dem_5m.tif      (downloaded source; sha256-verified)
  datasets/real/derived/psr_site001_dem_crop.tif   (RATIO crop, native 5 m/px)
  datasets/real/derived/psr_site001_shaded.png     (RATIO hillshade rendering — DERIVED_RENDERING)
  datasets/real/derived/psr_site001_synth_hazard.png (rendering + SYNTHETIC hazard)
  datasets/manifests/phase3_datasets.json          (provenance manifest)

The image inputs are RATIO renderings of the real DEM; they are NOT calibrated
sensor observations and are labeled as such.
"""
from __future__ import annotations
import hashlib
import json
import urllib.request
from pathlib import Path

import cv2
import numpy as np
import rasterio

ROOT = Path(__file__).parents[1]
SOURCE_URL = "https://api.github.com/repos/fletcher-smith-ae/GlobalPathPlan/contents/Site001PSR.tif"
SOURCE_SHA256 = "e6365857e96e9ba597898a498ae033840554b2b6e4b4c09889ef2438bce36262"  # verified at preparation time
CROP_ORIGIN = (350, 300)   # x0, y0 of the RATIO crop inside the source raster
CROP_SIZE = 320            # 320 x 320 px = 1.6 km x 1.6 km at 5 m/px


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> dict:
    src_dir = ROOT / "datasets/real/source"
    out_dir = ROOT / "datasets/real/derived"
    src_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    source_path = src_dir / "psr_site001_dem_5m.tif"
    if not source_path.exists():
        print(f"downloading {SOURCE_URL}")
        req = urllib.request.Request(SOURCE_URL, headers={"Accept": "application/vnd.github.raw"})
        source_path.write_bytes(urllib.request.urlopen(req, timeout=120).read())
    actual = sha256(source_path)
    if actual != SOURCE_SHA256:
        raise RuntimeError(f"source sha256 mismatch: expected {SOURCE_SHA256}, got {actual}")
    with rasterio.open(source_path) as ds:
        src_crs = ds.crs.to_wkt()
        src_res = abs(float(ds.transform.a))
        full = ds.read(1, masked=True)
    # RATIO crop: keep native 5 m/pixel spacing, metre CRS, nodata preserved.
    crop = full[CROP_ORIGIN[1]:CROP_ORIGIN[1] + CROP_SIZE, CROP_ORIGIN[0]:CROP_ORIGIN[0] + CROP_SIZE]
    transform = rasterio.transform.from_origin(
        float(ds.transform.c) + CROP_ORIGIN[0] * float(ds.transform.a),
        float(ds.transform.f) + CROP_ORIGIN[1] * float(ds.transform.e),
        float(ds.transform.a), abs(float(ds.transform.e)))
    crop_path = out_dir / "psr_site001_dem_crop.tif"
    with rasterio.open(crop_path, "w", driver="GTiff", height=crop.shape[0], width=crop.shape[1],
                       count=1, dtype="float32", crs=src_crs, transform=transform,
                       nodata=float(ds.nodata) if ds.nodata is not None else None,
                       compress="deflate") as dst:
        dst.write(np.asarray(crop.data, dtype="float32"), 1)
    values = np.asarray(crop.data, dtype=np.float64)
    valid = ~np.ma.getmaskarray(crop) & np.isfinite(values)
    if not valid.any():
        raise RuntimeError("crop contains no valid elevation values")

    # Deterministic visualization hillshade of the REAL DEM (labeled DERIVED_RENDERING).
    gy, gx = np.gradient(np.where(valid, values, np.nanmedian(values[valid])), 5.0, 5.0)
    magnitude = np.hypot(gx, gy)
    slope = np.arctan(magnitude)
    aspect = (np.degrees(np.arctan2(-gx, gy)) + 360) % 360
    az, alt = np.radians(315), np.radians(45)
    shaded = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - np.radians(aspect))
    shaded = np.clip((shaded + 1) / 2, 0, 1)
    lo, hi = np.percentile(shaded[valid], [2, 98])
    render = np.zeros(shaded.shape, np.uint8)
    render[valid] = np.uint8(np.clip((shaded[valid] - lo) / max(hi - lo, 1e-9) * 255, 0, 255))
    shaded_path = out_dir / "psr_site001_shaded.png"
    cv2.imwrite(str(shaded_path), render)

    # Controlled synthetic hazard ON the rendering (SYNTHETIC_DEMO; not in the DEM).
    hazard = cv2.cvtColor(render, cv2.COLOR_GRAY2BGR)
    cv2.circle(hazard, (168, 152), 14, (255, 255, 255), -1)
    cv2.circle(hazard, (163, 147), 10, (18, 18, 18), -1)
    hazard_path = out_dir / "psr_site001_synth_hazard.png"
    cv2.imwrite(str(hazard_path), hazard)

    dem_entry = {
        "id": "LRO_LOLA_PSR_SITE001_5M",
        "classification": "REAL",
        "mission": "Lunar Reconnaissance Orbiter (per source repository attribution)",
        "instrument": "LOLA (LDEM-derived site DEM; per source repository description)",
        "product_id": "Site001PSR.tif (GlobalPathPlan repository)",
        "data_type": "DEM",
        "source": "https://github.com/fletcher-smith-ae/GlobalPathPlan",
        "local_path": str((out_dir / "psr_site001_dem_crop.tif").relative_to(ROOT)),
        "resolution_m_per_pixel": 5.0,
        "coordinate_reference_system": src_crs,
        "acquisition_date": None,
        "processing_level": "Site-scale south-polar lunar DEM distributed in the source repository; "
                           "derivation chain NOT documented in the source repository. RATIO applied a "
                           "320x320 pixel geographic crop only.",
        "coverage": {"note": "Lunar south-polar site region; footprint defined by source raster extent",
                     "common_footprint": False},
        "license_notes": "No license statement is provided in the source repository. Attribution "
                        "preserved; verify redistribution terms with the source repository before reuse.",
        "description": "REAL lunar-derived high-resolution reference (5 m/pixel). Used to demonstrate "
                       "feature-scale terrain verification that the Phase-2 7.58 km/pixel LDEM crop "
                       "cannot resolve. Provenance is limited: the source repository does not document "
                       "the production chain.",
        "reference_dimensions": [CROP_SIZE, CROP_SIZE],
        "metadata_alignment_reliable": False,
        "illumination": None,
        "hashes": {"source_sha256": actual,
                   "derived_dem_sha256": sha256(crop_path),
                   "rendered_input_sha256": sha256(shaded_path)},
        "note": "REAL DEM, LIMITED PROVENANCE",
    }
    hazard_entry = {
        "id": "LRO_LOLA_PSR_SITE001_5M_SYNTH_HAZARD",
        "classification": "SYNTHETIC_DEMO",
        "mission": "Lunar Reconnaissance Orbiter (base data)",
        "instrument": "LOLA (LDEM-derived site DEM; per source repository description)",
        "product_id": "RATIO_SYNTH_HAZARD_ON_PSR_SITE001_RENDER",
        "data_type": "DEM",
        "source": "https://github.com/fletcher-smith-ae/GlobalPathPlan",
        "local_path": str((out_dir / "psr_site001_dem_crop.tif").relative_to(ROOT)),
        "resolution_m_per_pixel": 5.0,
        "coordinate_reference_system": src_crs,
        "acquisition_date": None,
        "processing_level": "Synthetic visual alteration on a RATIO rendering of the REAL DEM",
        "coverage": {"note": "Lunar south-polar site region", "common_footprint": False},
        "license_notes": "NASA-derived base data with RATIO synthetic modification; not mission evidence.",
        "description": "SYNTHETIC_DEMO: artificial bright/dark disc painted on the shaded rendering; "
                       "NOT present in the independent DEM.",
        "reference_dimensions": [CROP_SIZE, CROP_SIZE],
        "metadata_alignment_reliable": False,
        "illumination": None,
        "hashes": {"source_sha256": actual,
                   "derived_dem_sha256": sha256(crop_path),
                   "modified_input_sha256": sha256(hazard_path)},
        "note": "SYNTHETIC hazard on REAL high-res reference",
    }
    manifest_path = ROOT / "datasets/manifests/phase3_datasets.json"
    manifest = {"schema_version": "3.0", "entries": [dem_entry, hazard_entry],
                "notice": "Phase-3 high-resolution real-data validation assets. Image inputs are RATIO "
                          "renderings of a REAL DEM (DERIVED_RENDERING), never calibrated sensor observations."}
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"source_sha256": actual, "derived": [str(crop_path.relative_to(ROOT)),
            str(shaded_path.relative_to(ROOT)), str(hazard_path.relative_to(ROOT)),
            str(manifest_path.relative_to(ROOT))]}


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
