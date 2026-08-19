# RATIO STAGE 1 ACCEPTANCE REPORT

## Overall Verdict

STAGE 1 ACCEPTED / FROZEN

## Test Summary

Total: 45 automated regression tests, plus the reproducible measurement harness
Passed: 45
Failed: 0
Skipped: 0

A clean Python virtual environment was recreated from `requirements.txt`; demo generation and all tests passed. The frontend was installed with `npm ci` and its production build completed successfully.

## Image Compatibility

Identical images:
- Status: COMPARABLE / HIGH
- Compatibility score: 1.0000
- Expected result: high compatibility, zero change, zero regions
- Actual result: SSIM 1.0000, residual 0, suspicious area 0%, regions 0

Same scene / different resolution:
- Status: COMPARABLE / HIGH
- Compatibility score: 0.9995
- Expected result: normalize 1170×1345 to the 1043×1200 comparison system and proceed
- Actual result: normalized to 1043×1200, resize reported, suspicious area 0%, regions 0

Same scene + alteration / different resolution:
- Status: COMPARABLE / HIGH
- Compatibility score: 0.9561
- Expected result: proceed after normalization and retain the known local alteration
- Actual result: normalized to 1043×1200, suspicious area 0.8558%, one localized region

Same scene / crop:
- Status: REVIEW_COMPARABILITY / MEDIUM
- Compatibility score: 0.6067
- Expected result: do not use ordinary resizing as crop registration
- Actual result: no change metrics, regions, or ordinary evidence artifacts were generated

Completely unrelated images:
- Status: INCOMPARABLE_IMAGES / LOW
- Compatibility score: 0.0580
- Expected result: withhold normal visual-evidence analysis
- Actual result: `LOW_VISUAL_CORRESPONDENCE`; no suspicious-area metric or evidence artifacts

Unrelated lunar images:
- Status: REVIEW_COMPARABILITY / MEDIUM
- Compatibility score: 0.4841
- Expected result: do not infer correspondence merely because both scenes look lunar
- Actual result: correspondence withheld; no suspicious-area metric, regions, or evidence artifacts

The compatibility score is explicitly documented as a coarse visual-correspondence estimate, not semantic identity, geographic co-location, or physical verification.

## Scientific Validation

Known alteration localization:
- Different-resolution alteration produced one localized region and 0.8558% suspicious area.

IoU:
- 0.8848 for the required different-resolution known-alteration case.

Dice:
- 0.9389 for the required different-resolution known-alteration case.

Alteration movement:
- Top-left, top-right, bottom-left, bottom-right, and center were all detected as one region.
- IoU range: 0.8610–0.8675.
- Dice range: 0.9253–0.9290.
- Suspicious-area range: 0.5527–0.5569%.

Alteration strength:
- Mean score inside ground truth increased monotonically: weak 0.6615, medium 0.6860, strong 0.6974.
- All three strengths remained COMPARABLE and generated one localized region.

Legitimate enhancement:
- Mild sharpening: compatibility 0.9993, suspicious area 0%, regions 0.
- Mild denoising: compatibility 0.9987, suspicious area 0%, regions 0.
- Moderate contrast: compatibility 0.9989, suspicious area 0%, regions 0.
- Brightness +8: compatibility 1.0000, suspicious area 0%, regions 0.
- JPEG quality 90: compatibility 0.9973, suspicious area 0%, regions 0.

Noise robustness:
- Gaussian sigma 0.5, 1, and 2 intensity levels: 0% suspicious area.
- Sigma 4: 0.0065% raw suspicious area and no retained region.
- Sigma 8: 90.9126% suspicious area and two regions. This is a measured robustness boundary and is documented as a limitation.

Determinism:
- Repeated scientific metadata, metrics, regions, score-map hashes, mask hashes, and encoded artifact hashes matched.
- Intentional differences are analysis IDs, timestamps, record hashes containing those fields, and processing timings.

## Exception Handling

Invalid file:
- PASS — empty uploads return HTTP 422, `EMPTY_FILE`, and a human-readable message.

Corrupted file:
- PASS — HTTP 422, `IMAGE_DECODE_FAILED`; no traceback is exposed.

Unsupported type:
- PASS — HTTP 415, `UNSUPPORTED_IMAGE_TYPE`.

Missing image:
- PASS — missing required JSON fields return HTTP 422 `INVALID_REQUEST`; unknown image IDs return HTTP 404 `IMAGE_NOT_FOUND`.

Oversized image:
- PASS — payload above 20 MB returns HTTP 413 `IMAGE_TOO_LARGE` before decoding.

Megapixel limit:
- PASS — a valid 40,006,400-pixel PNG returns HTTP 413 `MEGAPIXEL_LIMIT_EXCEEDED`.

Dimension mismatch:
- PASS — close-aspect same-scene inputs are explicitly normalized; substantial aspect-ratio mismatch is withheld for review.

Incomparable images:
- PASS — analysis returns a structured comparison report with status, score, components, and reason; ordinary evidence outputs are absent.

Invalid configuration:
- PASS — negative/out-of-range weights, invalid sums, negative thresholds, reversed compatibility thresholds, invalid kernels, and unsupported normalization policy are rejected. API configuration failure returns HTTP 422 `INVALID_CONFIGURATION`.

## Backend

Health:
- PASS — `/api/health` returns service and Stage-1 status.

Upload:
- PASS — supported decoding, EXIF orientation, numeric validation, limits, SHA-256, and immutable original bytes verified.

Analysis:
- PASS — comparable, review, and incomparable states verified; normalization metadata and timing fields are canonical JSON outputs.

Features:
- PASS — feature endpoint matches the canonical analysis status and region list.

Artifacts:
- PASS — comparable analyses provide valid heatmap, mask, and annotated PNGs. Withheld comparisons return `ARTIFACT_NOT_AVAILABLE` rather than misleading artifacts.

Download:
- PASS — canonical analysis JSON downloads with the correct media type.

## Frontend

Build:
- PASS — Vite production build completed; 1,567 modules transformed. Production preview loaded and reached the backend through the documented `/api` proxy.

Upload:
- PASS — production-preview upload-to-analysis network flow completed successfully.

Normalization message:
- PASS — the UI binds directly to backend dimension metadata and displays original, enhanced, and analysis dimensions plus the resize method.

Incompatible-image message:
- PASS — dedicated INCOMPARABLE/REVIEW screen explains that evidence analysis was not performed and does not render suspicious-area metrics.

Region interaction:
- PASS — comparable canonical feature JSON drives region selection, table values, score bars, bounding box, and status.

Error handling:
- PASS — backend `message` fields are surfaced; unsupported, corrupt, oversized, and malformed inputs no longer collapse into a generic failure string.

## Artifact Validation

Heatmap:
- PASS — readable PNG at analysis dimensions; deterministically encoded for identical inputs and configuration.

Mask:
- PASS — readable single-channel PNG at analysis dimensions; matches region extraction state.

Annotated image:
- PASS — generated from the normalized enhanced comparison representation, not the mismatched source dimensions.

JSON:
- PASS — contains hashes, inputs, configuration, compatibility, dimension normalization, timings, metrics, regions, artifacts, scope, scientific disclaimer, and record hash.

## Performance

Times are single local QA-harness observations in milliseconds, not deployment guarantees.

512×512:
- Pair upload/storage: 20.652
- Normalization: 0.909
- Compatibility: 4.868
- Visual analysis: 43.876
- Artifact generation: 35.041
- Backend total after upload: 90.155

1024×1024:
- Pair upload/storage: 54.074
- Normalization: 2.997
- Compatibility: 6.748
- Visual analysis: 257.458
- Artifact generation: 55.546
- Backend total after upload: 340.405

2048×2048:
- Pair upload/storage: 176.736
- Normalization: 31.788
- Compatibility: 16.476
- Visual analysis: 1311.015
- Artifact generation: 201.906
- Backend total after upload: 1634.018

Additional required paths:
- Same scene 1043×1200 versus 1170×1345: 429.945 ms backend total, including 292.868 ms visual analysis and 97.406 ms artifacts.
- Incompatible 1024×1024 pair: 25.419 ms backend total; visual analysis 0 ms and artifact generation 0.001 ms because the gate withheld ordinary evidence processing.

## Bugs Found

1. Severity: Critical
   - File: `ratio_core/evidence/visual.py`
   - Cause: unequal dimensions were rejected without distinguishing resolution mismatch from content incompatibility.
   - Fix: added aspect-ratio-aware normalization and explicit comparison-coordinate metadata.
   - Regression test: same scene at 1043×1200 and 1170×1345.

2. Severity: Critical
   - File: `ratio_core/evidence/visual.py`, `backend/app/services/analysis.py`
   - Cause: unrelated scenes could be resized and interpreted as ordinary visual change.
   - Fix: added a configurable four-signal compatibility gate and withheld normal metrics/artifacts for LOW and MEDIUM correspondence.
   - Regression tests: unrelated image, unrelated lunar-looking scene, and crop.

3. Severity: High
   - File: `ratio_core/evidence/visual.py`
   - Cause: crops could be stretched into a shared shape, producing scientifically misleading residuals.
   - Fix: high-threshold correspondence and aspect-ratio tolerance now gate automatic normalization; uncertain crop returns REVIEW_COMPARABILITY.
   - Regression test: same-scene crop.

4. Severity: High
   - File: `backend/app/main.py`
   - Cause: FastAPI default errors and free-form details did not provide stable error codes.
   - Fix: structured handlers now return `error` and `message`, with specific HTTP statuses.
   - Regression tests: corrupt, empty, unsupported, oversized, megapixel, malformed, missing-input, missing-analysis, missing-artifact, and invalid-config cases.

5. Severity: High
   - File: `ratio_core/evidence/visual.py`
   - Cause: configuration validation covered only the visual-weight sum.
   - Fix: added validation for all weights, thresholds, normalization scales, percentile, morphology, limits, thumbnail size, aspect-ratio tolerance, and policy name.
   - Regression tests: invalid and behavior-changing configuration cases.

6. Severity: Medium
   - File: `backend/app/services/store.py`
   - Cause: OpenCV `IMREAD_UNCHANGED` ignored orientation metadata and stored-file integrity was not rechecked before analysis.
   - Fix: Pillow verification and EXIF transpose are used for derived decoding; original bytes remain immutable and are hash-checked before use.
   - Regression test: immutable input hash and upload validation paths.

7. Severity: Medium
   - File: `backend/app/services/analysis.py`
   - Cause: annotation could use the original enhanced dimensions after normalization.
   - Fix: annotations are generated from the normalized enhanced comparison representation.
   - Regression test: all artifact dimensions must equal analysis dimensions.

8. Severity: Medium
   - File: `frontend/src/App.jsx`, `frontend/src/api.js`
   - Cause: the UI assumed metrics/artifacts always existed and did not expose normalization or compatibility states.
   - Fix: dedicated REVIEW/INCOMPARABLE view, normalization banner, precise backend messages, and absent-artifact handling.
   - Regression evidence: production build plus comparable/incomparable API-state tests and production reverse-proxy smoke test.

9. Severity: Low
   - File: `frontend/src/App.jsx`
   - Cause: preview object URLs were repeatedly created and not revoked.
   - Fix: memoized preview URLs and lifecycle cleanup.
   - Regression evidence: successful production build.

10. Severity: Medium
    - File: `frontend/vite.config.js`
    - Cause: the production preview did not have a documented API proxy and initially rejected the hosted preview origin.
    - Fix: explicit dev/preview proxy and host configuration.
    - Regression evidence: production preview loaded and `/api/health` succeeded through port 4173.

## Remaining Limitations

Expected Stage-1 limitations:
- No DEM, geospatial registration, gradient alignment, physical consistency, mission policy, export firewall, or LLM functionality.
- Compatibility is visual and coarse; it cannot establish that images depict the same physical location.
- Crop, translation, rotation, viewpoint, and illumination registration remain outside Stage 1. Uncertain pairs are withheld rather than force-compared.
- Grayscale analysis does not detect chromatic-only modifications.
- Current weights and thresholds are configurable engineering baselines, not calibrated probabilities.
- Validation measurements use controlled synthetic scenes and do not constitute representative real-lunar benchmark performance.
- File-backed storage is appropriate for a local prototype, not concurrent production operation.
- Strong pixel noise around sigma 8/255 can trigger broad visual suspicion.

Actual defects:
- No known release-blocking Stage-1 defect remained after the audit and regression run.
- Browser interaction is not covered by an automated end-to-end browser suite; frontend acceptance used production compilation, network smoke testing, canonical JSON inspection, and component-path review.

## Freeze Decision

STAGE 1 IS ACCEPTED AND FROZEN.
