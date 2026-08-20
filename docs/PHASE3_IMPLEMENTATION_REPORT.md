# PHASE 3 IMPLEMENTATION REPORT

Generated: 2026-08-20 · Branch `arena/01a01c11-ratio-2` · All values below were produced by executing the current repository. No result is asserted from memory.

## Architecture

RATIO 2.0 remains a deterministic evidence-gating pipeline. Phase 3 is an additive layer:

```text
USER / IMAGE
  → RATIO SCIENTIFIC ENGINE (Phase 1 comparability + visual change, frozen)
  → Phase 2 terrain verification (registration / DEM / physical support / risk / policy, frozen)
  → Phase 3 additive modules:
     3A high-resolution real-data reference path
     3B independent registration validation point
     3C synthetic hazard test range + false-positive controls
     3D enhancement/model drift monitor
     3E structured evidence API (read-only, whitelisted)
     3F natural-language explainability (Claude) + deterministic fallback
     3G Evidence Navigator (read-only, audited)
     3H 8-step evidence-chain UI
     3I Playwright browser E2E
     3J SIH demo mode (8 one-click cases, judge view)
  → FINAL DECISION (deterministic, pre-LLM)
  → CLAUDE EXPLAINS (structured evidence only)
```

Claude never decides SAFE / REVIEW / BLOCK. The decision exists before Claude is invoked. Claude receives compact structured JSON — never images, rasters, heatmaps, or raw pixels.

## New Scientific Capabilities

| Capability | Where | Notes |
|---|---|---|
| Independent registration validation | `ratio_core/registration/affine.py::fit_affine_validated` | 3 fit points define the transform; a 4th point (never in the fit) tests it. Status: HIGH / MEDIUM / LOW / INVALID. A zero fit RMSE is never treated as proof. |
| High-resolution real reference | `datasets/real/derived/psr_site001_dem_crop.tif` | REAL LOLA-derived south-polar site DEM, 5 m/pixel, polar stereographic CRS, 320×320 crop, sha256-verified. Provenance limited (documented honestly). |
| Synthetic hazard range | `ratio_core/benchmark/` | 7 hazard types, 8 benign perturbation types, pixel ground-truth masks, deterministic seeds, scene-level splits. |
| Ground-truth metrics | `ratio_core/benchmark/metrics.py` | pixel precision/recall, IoU, Dice, FPR, FNR, region-level detection (IoU ≥ 0.3), suspicious-area error, per-class summaries. |
| Enhancement drift monitor | `ratio_core/benchmark/runner.py` | Fixed benchmark through enhancer v1/v2/v3; PASS / REVIEW / QUARANTINE from configured absolute + percentage thresholds (percentage thresholds only apply above a 0.01 baseline to avoid tiny-baseline artifacts). |
| Terrain-consistent synthetic support test | `tests/test_phase3_demo_highres.py::test_physical_consistency_synthetic_support_case` | SYNTHETIC_PHYSICAL_CONSISTENCY_TEST: a feature present in BOTH visual input and reference DEM yields SUPPORTED/PARTIALLY_SUPPORTED — proving the pipeline recognizes supportive evidence, not only contradiction. |

## New Backend Services

- `backend/app/services/evidence_api.py` — read-only structured evidence views; the security/correctness boundary for the LLM.
- `backend/app/services/llm_client.py` — Claude client; fixed system prompt; JSON-schema validation; one strict retry; typed failure modes (timeout / network / rate limit / auth / invalid body / invalid JSON).
- `backend/app/services/navigator.py` — intent router, whitelisted tool execution, deterministic fallback answers, JSONL audit trail.
- `backend/app/services/benchmarks.py` — benchmark + drift jobs (separated from interactive analysis; artifacts only under `data/`).
- `backend/app/services/demo.py` — 8 SIH one-click cases built from the same services the interactive UI uses.
- `backend/app/services/phase2.py` — additive 3B wiring (independent validation points); failed registration now yields physical status `UNRESOLVED` (never `CONTRADICTED`); writes `evidence_report.json` per analysis.
- `backend/app/services/datasets.py` — loads Phase-2 and Phase-3 manifests; every dataset carries mission/instrument/product_id/source/resolution/CRS/processing level/license notes/hashes.

## New APIs

Evidence API (all GET, read-only):

- `/api/evidence/analysis/{id}/summary`
- `/api/evidence/feature/{fid}` and `/api/evidence/feature/{fid}/evidence`
- `/api/evidence/feature/{fid}/dem-support`
- `/api/evidence/registration?analysis_id=…&feature_id=…`
- `/api/evidence/passport/{analysis_id}`
- `/api/evidence/compare?feature_a=…&feature_b=…`
- `/api/evidence/region-summary/{analysis_id}?region=ALL`
- `/api/evidence/mission-decision?analysis_id=…&feature_id=…`
- `/api/evidence/benchmark` and `/api/evidence/drift`
- `/api/benchmarks/run` (POST), `/api/benchmarks/latest`, `/api/benchmarks/report.html`
- `/api/drift/run` (POST), `/api/drift/latest`
- `POST /api/analyses/{id}/explain?feature_id=…`
- `POST /api/navigator/query`, `GET /api/navigator/audit`
- `GET /api/health/phase3` (reports CLAUDE_OFFLINE / CLAUDE_EXPLANATION_ENABLED)
- `GET /api/demo/cases`, `POST /api/demo/run/{case_id}`
- `POST /api/analyses/{id}/align` accepts optional `validation_image_points` / `validation_reference_points` (additive; Phase-2 3-point payloads remain valid).

## New Frontend Features

- 8-step evidence chain per feature (`WHAT CHANGED?` → `FINAL DECISION`) with check/warn/fail icons, component grid, and “NOT A PROBABILITY” labeling.
- Evidence Quality summary (comparison / registration / reference / physical support / unsupported risk) — no single “confidence = 87%” number.
- Comparison-gate guardrail panel for incomparable inputs: status, compatibility score, reason code, what was deliberately NOT produced, and operator guidance.
- Evidence Navigator panel with suggested questions, tool chips, deterministic decision chip, offline badge.
- Manual 3+1 point alignment modal with an independent validation point (V marker) and “ACCEPT WITH VALIDATION”.
- BENCHMARKS page (per-split tables: samples / detected / missed / false alarms / avg & median IoU / precision; HTML report download).
- MODEL GOVERNANCE page (per-version metric cards, PASS/REVIEW/QUARANTINE badges, reason codes, measured deltas).
- SIH DEMO page (judge view): case cards → VERIFY → decision banner, visuals, evidence chain, WHY, ADVANCED METRICS drawer.
- REAL / SYNTHETIC_DEMO / TEST_DATA labels on the dataset strip; high-res reference banner (resolution / feature scale / adequacy).
- Header system badge switches to CLAUDE OFFLINE when no API key is configured.

## Real Data Used

1. **NASA SVS CGI Moon Kit ID 4720** (Phase 2, frozen): LROC WAC-derived color asset + LOLA-derived `ldem_4.tif`, common footprint lon/lat ±45°. Classified REAL but explicitly documented as a rendering composite — not a calibrated science image.
2. **Phase 3 high-res reference**: `Site001PSR.tif` from the GlobalPathPlan repository (LOLA/LDEM-derived lunar south-polar site DEM), 5 m/pixel, polar stereographic CRS. Downloaded from GitHub, sha256 `e6365857…e36262` verified, RATIO 320×320 geographic crop only. Classification REAL with an explicit limited-provenance note: the source repository does not document the derivation chain. Image inputs for the high-res cases are RATIO hillshade renderings of that DEM (DERIVED_RENDERING), never presented as calibrated observations.

## Synthetic Benchmark

- 7 hazard classes × 4 seeds × 2 development scenes, 2 validation scenes, 2 held-out scenes + real-base (NASA SVS) hazard/benign samples in held-out = 376 samples per run (120/120/136).
- Scene-level split: development/validation/held-out scenes are disjoint by construction.
- Recorded run (report `1175b6b87e16`, `docs/benchmark_drift_record.json`):

| Split | Samples | Hazard region recall | Pixel FPR (benign controls) | Unsupported-candidate rate | Mean suspicious area |
|---|---|---|---|---|---|
| development | 120 | 82.7% | 0.0550% | 34.2% | 0.804% |
| validation | 120 | 83.3% | 0.0470% | 36.7% | 0.574% |
| held_out | 136 | 84.5% | 0.0577% | 34.6% | 0.819% |

Interpretation: benign perturbations (sharpening, denoising, contrast, brightness, JPEG, resampling, sensor noise, illumination) are rarely flagged (FPR ≈ 0.05%); injected hazards are usually detected (recall ≈ 83%). RATIO separates VISUAL CHANGE from UNSUPPORTED-TERRAIN CANDIDATE. No ML is trained; thresholds are the frozen Phase-1 settings.

## Model Drift Results

Recorded run (report `e1c804fe6798`):

| Enhancer | policy-block rate | unsupported-risk mean | pixel FPR | pixel FNR | mean regions |
|---|---|---|---|---|---|
| v1 (baseline, mild sharpening) | 0.6875 | 0.2008 | 0.000161 | 0.1514 | 0.59 |
| v2 (stronger sharpening) | 0.8125 | 0.1677 | 0.002257 | 0.1493 | 1.85 |
| v3 (aggressive CLAHE) | 1.0000 | 0.2137 | 0.311658 | 0.0310 | 1.44 |

Decisions (configured thresholds, measured deltas): **v2 → REVIEW** (`policy_block_rate:+18.18%`, `region_count_mean:+213.75%`, `visual_change_rate:+7.55%`, …). **v3 → QUARANTINE** (`false_positive_rate:+193476.40%`, `average_changed_area_pct:+632.40%`, `policy_block_rate:+45.45%`, …). These values are computed from the fixed benchmark; nothing is invented.

## Claude Integration

- Fixed system prompt with the mandatory guardrails (never invent measurements/observations/coordinates/DEM values; never override the policy decision; never call risk a probability; never call a feature physically proven; delimited untrusted payload).
- Structured-only payloads (`ratio_core/explain/payload.py`): compact fields, no images.
- Response schema `{executive_summary, risk_assessment, evidence_explanation, recommendation, limitations}` validated server-side; one strict retry; deterministic fallback on any failure.
- Failure taxonomy: CLAUDE_TIMEOUT, CLAUDE_NETWORK_FAILURE, CLAUDE_RATE_LIMITED, CLAUDE_AUTH_FAILED, CLAUDE_MALFORMED_BODY, CLAUDE_INVALID_JSON, CLAUDE_RESPONSE_INVALID_AFTER_RETRY, CLAUDE_API_KEY_UNAVAILABLE.
- Policy decision is attached to every explanation response by the BACKEND, never by the model.
- No LLM call is made during analysis; Claude is invoked only when the user requests an explanation or opens the Evidence Navigator.
- Verified offline in this environment (no API key configured): scientific mode continues, fallback explanation returns, `CLAUDE_OFFLINE` is reported. Mock-transport tests cover the success path, retry, timeout, network failure, rate limit, and invalid JSON.

## Evidence Navigator

- Deterministic intent router (why / compare / which / show / missing-evidence / registration / benchmark / drift / decision / summarize / policy-immutability).
- Whitelisted tool execution; unknown tools rejected (`REJECTED_<tool>`).
- Deterministic fallback answers per intent (offline-grade quality).
- JSONL audit trail per request: timestamp, analysis_id, feature_id, user question, tools called, tool-result IDs, model identifier, response status, fallback flag.
- Read-only by construction: no mutating endpoint exists in the tool whitelist.

## Browser E2E

- Playwright 1.62.1, 15 tests in 4 spec files (`frontend/tests/e2e/`), **15/15 passed in ~24 s** on the workspace-provided Chromium.
- Coverage: open app → upload → create analysis → mission → reference → verify → feature inspection → 8-step chain → manual 3+1 alignment → export allowed → export blocked (HTTP 409) → passport download → evidence-report download → Evidence Navigator tool call → Claude-disabled mode → incomparable gate panel → fast path → REAL/SYNTHETIC labeling → SIH demo cases (judge flow, coarse DEM, high-res, Claude offline).
- Restricted-environment bootstrap: `scripts/bootstrap_e2e_browser.sh` extracts the Chromium shipped in `@sparticuz/chromium` and, when the host lacks NSS/NSPR, builds them from source (NSPR + NSS 3.53) — verified from scratch in this workspace (~130 s cold, ~2 s warm). A system Chrome can be used via `RATIO_CHROMIUM_PATH`.

## Security / Guardrails

Verified by execution:

- Path traversal, malformed IDs, malformed JSON, >20 MB upload, corrupted raster, unknown dataset/feature → structured errors, no stack traces, no filesystem paths, no secrets.
- Navigator tool whitelist rejects non-listed tools.
- LLM state-override fields (`policy_decision`, `risk_score`, …) are discarded by the report validator.
- Prompt-injection attempts (question text, filenames) cannot change `policy_decision`, `physical_support`, `unsupported_risk`, thresholds, or weights — asserted by tests.
- Original uploads remain immutable bytes; stored hash re-verified on every read (Phase 1 behavior preserved).
- No LLM ever receives raw images/rasters — asserted by payload tests.

## Passport / Audit Trail

- Phase-2 processing passport unchanged (hash-chained). Passport download verified in-browser.
- New artifacts per analysis: `evidence_report.json`, `llm_explanation[_<feature>].json`; per run: `benchmark_report_<id>.json`, `drift_report_<id>.json`; per navigator day: `navigator_audit_<date>.jsonl`.
- Storage remains local JSON/file persistence — no schema migration, no distributed database.

## Known Limitations

### Expected research limitations (by design)
- No perspective/camera-model registration; affine only.
- No automatic landmark matching beyond metadata/common-footprint validation.
- High-res reference provenance is limited (source repository does not document the derivation chain); classified honestly as “REAL DEM, LIMITED PROVENANCE”.
- Hillshade comparison remains unavailable without acquisition illumination metadata (bundled data has none).
- Scores are deterministic engineering measures, not calibrated probabilities.
- Synthetic scenes are procedural; real-base samples use the NASA SVS rendering composite, not calibrated science imagery.
- Claude integration is unverified against a live API in this environment (no key configured); all failure paths and the success path are covered by mock-transport tests.

### Actual software defects
- None known at report time. All recorded suites pass.

## Test Summary

Executed 2026-08-20 on this repository:

| Suite | Total | Passed | Failed | Skipped |
|---|---|---|---|---|
| pytest (Phase 1 frozen + Phase 2 frozen + Phase 3) | 137 | 137 | 0 | 0 |
| Phase-2 acceptance matrix (`scripts/phase2_acceptance.py`) | 27 | 27 | 0 | 0 |
| Phase-3 acceptance matrix (`scripts/phase3_acceptance.py`) | 14 | 14 | 0 | 0 |
| Playwright browser E2E (`npm run test:e2e`) | 18 | 18 | 0 | 0 |
| Frontend production build (`npm run build`) | 1 | 1 | 0 | 0 |

Phase-1 and Phase-2 tests were not deleted or weakened; the historical 66-test regression suite runs unchanged as part of the 137 (71 Phase-3 tests, including the filename-based prompt-injection case).

Fresh-clone re-verification (2026-08-20, `git clone` of the pushed branch into an empty directory, full documented setup): 137/137 pytest, 27/27 Phase-2 matrix, 14/14 Phase-3 matrix (after E2E), 18/18 browser E2E, production build OK, 8/8 SIH demo cases. See `docs/RATIO_2_INTEGRATED_AUDIT_REPORT.md` §Clean-environment verification.

## SIH Demo Cases

All eight cases run server-side from the real pipeline (nothing pre-scripted). Recorded outcomes:

1. **Legitimate enhancement** → NO_SIGNIFICANT_CHANGE, DEM verification NOT_REQUIRED. ✓
2. **Synthetic fake boulder** → visual change 0.751, physical support 0.441, unsupported risk 0.398, NOT_SAFE, export blocked (409). ✓
3. **Coarse DEM (160 m/px downsampled reference)** → physical status REFERENCE_INADEQUATE (never CONTRADICTED), REVIEW_REQUIRED. ✓
4. **Bad registration (wrong 3-point + validation point)** → validation residual > 20 px, quality INVALID, status UNRESOLVED (never CONTRADICTED). ✓
5. **Good registration + high-res (5 m/px) reference** → FIT_3_VALIDATE_INDEPENDENT, validation ≤ 2 px, REFERENCE_RESOLUTION_ADEQUATE, SUPPORTED. ✓
6. **Model drift** → v1 PASS (baseline), v2 REVIEW, v3 QUARANTINE (measured deltas recorded). ✓
7. **Evidence Navigator** → “Why was F01 blocked?” answered via get_feature_evidence + get_mission_decision; decision NOT_SAFE attached by backend. ✓
8. **Claude offline** → fallback explanation, scientific state intact (NOT_SAFE unchanged). ✓

## Final Verdict

# PHASE 3 ACCEPTED

(Backed by the executed suites above; see `docs/phase3_acceptance_matrix.json`, `docs/integrated_e2e_sample.json`, `docs/benchmark_drift_record.json`, and the integrated audit report `docs/RATIO_2_INTEGRATED_AUDIT_REPORT.md`.)

Phase 4 must not begin before this report is reviewed; Phase 4 scope (multi-view persistence, counterfactual terrain consistency, uncertainty propagation, research-grade benchmarking, deployment architecture) is intentionally out of scope.
