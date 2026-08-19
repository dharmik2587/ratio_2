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
