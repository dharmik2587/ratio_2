# RATIO 2.0 — Phase 3

RATIO is a deterministic evidence-gating prototype for AI-enhanced planetary imagery. It asks whether visually changed terrain information has adequate independent DEM support for a selected mission use.

It does **not** output hallucination probability, truth probability, or flight certification.

## Full pipeline

```text
Original + enhanced image
→ Phase-1 comparability and visual-change analysis (frozen)
→ no-significant-change fast path OR registered DEM verification (frozen Phase 2)
→ coverage and resolution adequacy
→ DEM support + intensity/elevation gradient alignment + local relief
→ physical support and reference quality
→ unsupported risk
→ mission policy (deterministic)
→ export firewall
→ processing passport
→ Phase 3: high-res reference path · independent registration validation point ·
  synthetic hazard benchmark · enhancement drift monitor · structured evidence API ·
  Claude explanation (structured evidence only) · deterministic fallback ·
  Evidence Navigator (read-only, audited) · 8-step evidence-chain UI · browser E2E ·
  SIH demo mode
```

Phase 1 remains isolated in `ratio_core/evidence/`. Phase-2 modules are additive. Phase 3 modules are additive on top of both:

- `ratio_core/benchmark/` — synthetic hazard test range + drift monitor
- `ratio_core/explain/` — fallback explanation + LLM payload/validation
- `backend/app/services/` — evidence API, LLM client, navigator, benchmarks, demo
- `configs/phase3.json` — Phase-3 settings (drift thresholds, LLM config)
- `frontend/src/pages/` — BENCHMARKS, MODEL GOVERNANCE, SIH DEMO
- `frontend/tests/e2e/` — Playwright suite

## Clean local run

Requires Python 3.11+ and Node.js 20+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/generate_demo_cases.py
python scripts/prepare_phase2_demo.py
python scripts/prepare_phase3_highres.py     # downloads the 5 m/px REAL reference (GitHub)
PYTHONPATH=. python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

In another terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`. API documentation is at `http://localhost:8000/docs`.

## Test and acceptance

```bash
PYTHONPATH=. pytest -q
PYTHONPATH=. python scripts/phase3_performance_sweep.py   # optional timing sweep
PYTHONPATH=. python scripts/phase2_acceptance.py
PYTHONPATH=. python scripts/phase3_acceptance.py
cd frontend && npm ci && npm run build
./scripts/bootstrap_e2e_browser.sh          # provides Chromium in restricted sandboxes
cd frontend && npm run test:e2e             # 15 browser tests
./scripts/sih_demo.sh                       # one-command SIH demo (suites + 8 cases)
```

Recorded results (see `docs/` for the full reports):

- 137/137 automated tests passed (66 frozen Phase-1/2 + 71 Phase-3)
- 27/27 Phase-2 acceptance-matrix cases
- 14/14 Phase-3 acceptance-matrix cases
- 18/18 Playwright browser E2E tests
- production frontend build passed

## Phase-3 API additions

- `GET /api/health/phase3` — Claude mode + fallback status
- Evidence API: `/api/evidence/*` (summary, feature, evidence, dem-support, registration, passport, compare, region-summary, mission-decision, benchmark, drift)
- `POST /api/benchmarks/run`, `POST /api/drift/run`, `GET /api/benchmarks/report.html`
- `POST /api/analyses/{id}/explain`, `POST /api/navigator/query`, `GET /api/navigator/audit`
- `GET /api/demo/cases`, `POST /api/demo/run/{case_id}`
- `POST /api/analyses/{id}/align` accepts optional independent validation points

Claude (when `RATIO_CLAUDE_API_KEY` is set) receives compact structured JSON only and is the explanation layer — never the decision authority. Without a key, RATIO runs in CLAUDE_OFFLINE mode with deterministic template explanations; nothing else degrades.

## Data

Bundled real-data-derived demonstration:

- NASA SVS CGI Moon Kit ID 4720 LROC WAC-derived color asset (Phase 2)
- NASA SVS CGI Moon Kit ID 4720 LOLA-derived `ldem_4.tif` (Phase 2)
- GlobalPathPlan `Site001PSR.tif` — REAL LOLA-derived south-polar site DEM, 5 m/pixel, polar stereographic (Phase 3 high-res reference; limited provenance, documented)
- Source: https://svs.gsfc.nasa.gov/4720 and https://github.com/fletcher-smith-ae/GlobalPathPlan

All synthetic hazards are labeled `SYNTHETIC_DEMO` / `SYNTHETIC_BENCHMARK`. The Phase-3 image inputs for the high-res path are RATIO hillshade renderings of the real DEM (DERIVED_RENDERING), never presented as calibrated observations.

## Scientific safeguards

- Visual change is never counted as physical support.
- Unavailable evidence is omitted, never zeroed.
- Flat/zero gradients return `UNRESOLVED`.
- Coarse DEMs return `REFERENCE_INADEQUATE`, not contradiction.
- Bad registration returns `UNRESOLVED`, not contradiction.
- Exactly three manual points are a minimal exact fit and quality-capped; a zero fit RMSE is never proof. The independent fourth point is what tests the transform.
- Hillshade comparison is unavailable without acquisition illumination metadata.
- Scores are deterministic engineering measures, not calibrated probabilities.
- The LLM never receives images/rasters and can never change decisions, weights, thresholds, or evidence.

Detailed assumptions and failure modes: `docs/PHASE2_SCIENTIFIC_METHODS.md`, `docs/PHASE3_IMPLEMENTATION_REPORT.md`, `docs/RATIO_2_INTEGRATED_AUDIT_REPORT.md`.

**Prototype only — not flight certified.**
