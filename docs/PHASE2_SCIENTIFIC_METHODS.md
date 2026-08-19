# RATIO Phase 2 Scientific Methods and Assumptions

## Scope

Phase 2 adds independent terrain-reference evidence and deterministic mission gates to the frozen Phase-1 visual-change pipeline. It is a local research prototype, not flight-certified software.

## Evidence separation

- **Visual change** is the existing Phase-1 region score. It measures modification strength and is not positive physical support.
- **Physical support** is a weighted mean over available DEM support, gradient alignment, hillshade support, and local-relief support. Missing components are omitted rather than set to zero.
- **Reference quality** summarizes registration, valid coverage, and resolution adequacy. It is not terrain support.
- **Unsupported risk** is a confidence-weighted deterministic score, not a probability.

## DEM handling

RATIO requires a single-band DEM with a projected CRS whose horizontal units are metres. Elevations are interpreted in metres. Nodata remains masked. Missing CRS, angular-only CRS, non-metre units, invalid resolution, and multiband rasters are rejected.

Terrain derivatives use explicit x/y pixel spacing:

- `dz/dx`, `dz/dy`: NumPy central differences in metres per metre.
- slope: `atan(sqrt((dz/dx)^2 + (dz/dy)^2))`.
- aspect: direction derived from elevation gradient.
- hillshade: deterministic visualization light, azimuth 315°, altitude 45°.
- local relief: local maximum minus local minimum.

Generated hillshade is not compared with observed shading unless acquisition illumination metadata exists. The bundled NASA data has no observation-specific illumination metadata, so hillshade support is `null`.

## Registration

`AUTO_METADATA` is allowed only when the dataset manifest declares a common footprint **and** the uploaded original image has HIGH Phase-1 visual correspondence with the manifest reference image. This is not feature matching.

Manual registration fits a 2D affine transform by least squares. Three non-collinear pairs are the minimum. With exactly three pairs, residual is necessarily near zero and cannot detect a wrong landmark correspondence; quality is therefore capped at 0.85 and the passport records `MINIMAL_EXACT_FIT`. Four or more points provide residual validation.

## Resolution adequacy

Feature scale is estimated in the registered DEM pixel system. The ratio is:

`feature_scale_m / effective_reference_resolution_m`

Frozen engineering defaults:

- ratio ≥ 3: adequate
- 1.5 ≤ ratio < 3: uncertain
- ratio < 1.5: too coarse

A too-coarse reference produces `REFERENCE_INADEQUATE`, never `CONTRADICTED`.

## Physical components

### DEM support

Mean DEM gradient magnitude within the region, normalized by a configured full-support scale. It measures whether the DEM contains terrain variation. It does not establish feature identity.

### Gradient alignment

Orientation-insensitive mean absolute cosine between visual intensity-gradient vectors and DEM elevation-gradient vectors:

`A = mean(|v·d| / (||v|| ||d||))`

Zero magnitude or no overlap returns `GRADIENT_ALIGNMENT_UNRESOLVED`, not numeric zero. Alignment measures directional consistency only.

### Local relief

Elevation range in the registered patch normalized by a configured relief scale. Rough terrain is not equivalent to feature confirmation.

### Hillshade support

Unavailable unless illumination metadata exists. The display hillshade is not silently used as observed evidence.

## Physical status safeguard

`CONTRADICTED` requires adequate image comparability, successful/high registration, high DEM coverage, adequate resolution, and resolved strong disagreement. Poor, coarse, missing, or unregistered data yields `UNRESOLVED`, `REFERENCE_INADEQUATE`, or `REFERENCE_UNAVAILABLE`.

## Unsupported risk

The configured formula is a multiplicative power product:

`visual_change^a × (1-physical_support)^b × comparison_quality^c × registration_quality^d × reference_adequacy^e`

Exponents are configuration values and default to one. Poor quality reduces confidence-weighted risk, but mandatory mission quality gates prevent poor data from creating a safe result.

## Mission policy

Each mission profile has mandatory minimum physical support, reference quality, and registration quality, plus a maximum unsupported risk. Route planning is strictest. An LLM does not participate.

## Data provenance

Bundled real-data-derived demonstration sources:

- NASA SVS CGI Moon Kit, ID 4720: `lroc_color_2k.jpg`, a LROC WAC-derived rendering asset.
- NASA SVS CGI Moon Kit, ID 4720: `ldem_4.tif`, LOLA-derived elevation in kilometres, converted to metres in the RATIO derivative.
- Source: https://svs.gsfc.nasa.gov/4720

The color asset is optimized for rendering and is not represented as a calibrated science image. The controlled hazard is explicitly `SYNTHETIC_DEMO`.

## Known failure modes

- Incorrect but plausible three-point correspondences cannot be detected from exactly three residuals.
- Albedo and illumination gradients need not track elevation gradients.
- Coarse global DEMs cannot resolve small hazards.
- Dataset manifest metadata can be wrong; hashes protect integrity, not scientific correctness.
- Affine registration cannot model camera perspective, terrain parallax, or complex distortion.
