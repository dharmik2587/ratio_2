# RATIO 2.0 — Phase 2

RATIO is a deterministic evidence-gating prototype for AI-enhanced planetary imagery. It asks whether visually changed terrain information has adequate independent DEM support for a selected mission use.

It does **not** output hallucination probability, truth probability, or flight certification.

## Current pipeline

```text
Original + enhanced image
→ Phase-1 comparability and visual-change analysis
→ no-significant-change fast path OR registered DEM verification
→ coverage and resolution adequacy
→ DEM support + intensity/elevation gradient alignment + local relief
→ physical support and reference quality
→ unsupported risk
→ mission policy
→ export firewall
→ processing passport
```

Phase 1 remains isolated in `ratio_core/evidence/`. Phase-2 modules are additive:

- `ratio_core/dem/`
- `ratio_core/registration/`
- `ratio_core/physical/`
- `ratio_core/policy/`
- `ratio_core/provenance/`
- `configs/phase2.json`

## Clean local run

Requires Python 3.11+ and Node.js 20+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/generate_demo_cases.py
python scripts/prepare_phase2_demo.py
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
PYTHONPATH=. python scripts/phase2_acceptance.py
cd frontend && npm ci && npm run build
```

Recorded results:

- 66 automated tests passed
- 27/27 acceptance-matrix cases passed
- production frontend build passed
- results: `docs/phase2_acceptance_matrix.json`

## Phase-2 API

Phase-1 routes are unchanged. Added routes:

- `GET /api/datasets`
- `POST /api/datasets`
- `GET /api/datasets/{id}/preview`
- `POST /api/analyses/{id}/reference`
- `POST /api/analyses/{id}/align`
- `POST /api/analyses/{id}/verify`
- `GET /api/analyses/{id}/physical-evidence`
- `POST /api/analyses/{id}/export`
- `GET /api/analyses/{id}/passport`

Mission-use export is blocked when policy is not satisfied. The underlying analysis report remains downloadable.

## Data

Bundled real-data-derived demonstration:

- NASA SVS CGI Moon Kit ID 4720 LROC WAC-derived color asset
- NASA SVS CGI Moon Kit ID 4720 LOLA-derived `ldem_4.tif`
- Source: https://svs.gsfc.nasa.gov/4720

Source files and hashes are in `datasets/real/source/`. The manifest is `datasets/manifests/phase2_datasets.json`.

The color asset is a rendering product, not a calibrated science image. The injected hazard is clearly labeled `SYNTHETIC_DEMO` and is not mission evidence.

## Scientific safeguards

- Visual change is never counted as physical support.
- Unavailable evidence is omitted, not set to zero.
- Flat/zero gradients return `UNRESOLVED`.
- Coarse DEMs return `REFERENCE_INADEQUATE`, not contradiction.
- Automatic metadata alignment requires manifest footprint metadata and reference-image correspondence.
- Exactly three manual points are marked as a minimal exact fit and quality-capped.
- Hillshade comparison is unavailable without acquisition illumination metadata.
- Scores are deterministic engineering measures, not calibrated probabilities.

Detailed assumptions and failure modes: `docs/PHASE2_SCIENTIFIC_METHODS.md`.

## Expected limitations

- No perspective/camera-model registration
- No automatic landmark matching beyond metadata/common-footprint validation
- No geographic lookup service
- No DEM uncertainty raster propagation
- No calibrated representative lunar benchmark
- No database server; local JSON/file persistence remains the SIH prototype architecture
- No Claude, model drift, multi-view persistence, or counterfactual renderer

**Prototype only — not flight certified.**
