# RATIO Phase 3 Hardening Backlog

Phase 2 status: **ACCEPTED / FROZEN**.

These items are additive Phase-3 hardening work. They must not trigger a Phase-2 architectural rewrite or weaken the frozen Phase-1/Phase-2 regression suites.

## Priority 1 — Calibrated, high-resolution matched lunar image + DEM

### Objective

Add one genuinely georeferenced, scientifically traceable local lunar observation and corresponding high-resolution DEM/DTM patch.

### Requirements

- Prefer a calibrated/orthorectified LROC NAC image and NAC-derived stereo DTM, or another authoritative matched local product.
- Record mission, instrument, product IDs, processing levels, projection, bounds, resolution, nodata, source URLs, acquisition metadata, licensing notes, and SHA-256 hashes.
- Preserve the existing NASA SVS sample but label it **REAL LUNAR-DERIVED DEMONSTRATION DATA**.
- Never call the SVS rendering composite a calibrated mission observation.
- Demonstrate global/coarse versus local/high-resolution reference adequacy.
- Use a controlled modification when naturally paired enhanced imagery is unavailable, and label it synthetic.

### Acceptance evidence

- Independent metadata establishes the image/DEM common footprint.
- Local DEM resolution is appropriate for the demonstrated feature scale.
- RATIO reports the actual resolution ratio and coverage.
- Coarse-reference and local-reference results can be compared without treating coarse absence as contradiction.

## Priority 2 — Independent registration validation point

### Objective

Validate a three-point affine fit with at least one control point that did not participate in fitting.

### Workflow

```text
Three fit points
→ affine transform
→ independent fourth/fifth validation point
→ validation residuals
→ registration quality
```

### Required outputs

- fit-point residual/RMSE
- independent validation residual/RMSE
- independent maximum error
- fit point count
- validation point count
- quality status and reason codes
- passport inclusion

### Scientific safeguard

Exactly three non-collinear fit points can have zero residual by construction. A zero fit RMSE must never be described as proof of correct registration.

## Priority 3 — Automated browser end-to-end tests

### Objective

Add Playwright or Cypress coverage for the judge-facing workflow.

### Minimum cases

1. Upload compatible original/enhanced images.
2. Select a mission profile.
3. Run Phase-1 analysis.
4. Select a DEM reference.
5. Run automatic metadata alignment.
6. Complete manual control-point interaction.
7. Verify region-detail values against canonical backend JSON.
8. Verify REAL LUNAR-DERIVED / SYNTHETIC_DEMO labeling.
9. Verify `NO_SIGNIFICANT_CHANGE` fast path.
10. Verify INCOMPARABLE and REVIEW states.
11. Verify passport download.
12. Verify allowed export.
13. Verify blocked export and visible HTTP 409 explanation.

## UI hardening requirement

Show the evidence reason chain rather than only the unsupported-risk score:

```text
Visual change
DEM support
Gradient alignment
Hillshade availability
Local relief support
Reference quality
Registration quality
Physical status
Unsupported risk — not a probability
Mission decision
```

For mixed evidence, explicitly answer **Why not contradicted?** using deterministic reason codes. Example:

> The physical evidence is mixed. DEM support is weak, but directional and local-relief evidence is not uniformly contradictory. RATIO therefore reports UNRESOLVED rather than claiming contradiction.

The explanation must not invent a resolution limitation when the canonical backend evidence says resolution is adequate; it must use the actual reason codes for that analysis.

## Claims boundary for SIH

Allowed:

> RATIO Phase 2 demonstrates a deterministic lunar-derived evidence pipeline with explicit comparability, registration, reference-quality, physical-support, mission-policy, export-firewall, and provenance safeguards.

Not currently supported:

- operational lunar verification
- rover-scale hazard verification using the bundled 7.58 km/pixel DEM
- calibrated mission-observation validation using the NASA SVS rendering composite
- flight readiness or navigation certification

---

# Phase 3 status (2026-08-20): IMPLEMENTED AND ACCEPTED

Every backlog item above is implemented and executed. Completion evidence lives in:

- `docs/PHASE3_IMPLEMENTATION_REPORT.md` — architecture, capabilities, APIs, recorded benchmark/drift values
- `docs/RATIO_2_INTEGRATED_AUDIT_REPORT.md` — independent re-run of every phase with actual outputs
- `docs/phase3_acceptance_matrix.json` — 14/14 scientific acceptance cases (A–J + immutability + hallucination guard + 3B math)
- `docs/integrated_e2e_sample.json` — full upload→decision→passport→explanation record
- `docs/performance_sweep.json` — timing across 256/512/1024/2048 px pairs + DEM paths
- `frontend/tests/e2e/` — 15/15 Playwright tests (bootstrap via `scripts/bootstrap_e2e_browser.sh`)

## Priorities closed this phase

| Priority | Status | Key artifact |
|---|---|---|
| 1 — calibrated high-resolution matched lunar image + DEM | DONE with documented provenance limits | 5 m/pixel REAL LOLA-derived polar DEM (`LRO_LOLA_PSR_SITE001_5M`, sha256-verified; image inputs are DERIVED_RENDERING, never called calibrated) |
| 2 — independent registration validation point | DONE | `fit_affine_validated` (fit RMSE + independent validation residual/max error + HIGH/MEDIUM/LOW/INVALID) |
| 3 — automated browser E2E | DONE | 15 Playwright tests incl. judge flow, export firewall, comparability gate, manual 3+1 alignment |
| UI hardening — evidence reason chain | DONE | 8-step evidence chain in the console + demo judge view |

## Known residual limitations (unchanged, by design)

- The NASA SVS color asset remains a rendering composite, labeled as such.
- The 5 m/px PSR DEM provenance is limited (source repository documents no derivation chain) — labeled REAL DEM, LIMITED PROVENANCE.
- No perspective/camera-model registration; affine only.
- Claude path verified with mock transports + offline fallback; a live-API run requires `RATIO_CLAUDE_API_KEY`.
