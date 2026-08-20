"""Phase 3C/3D — benchmark runner and enhancement drift monitor.

The runner evaluates RATIO's frozen Phase-1 visual-change pipeline against the
synthetic test range. It computes pixel/region metrics against ground truth and
separates VISUAL CHANGE from UNSUPPORTED-TERRAIN-CANDIDATE behavior.

The drift monitor runs the SAME fixed benchmark through registered enhancer
versions and compares aggregate rates, with configurable thresholds. It does not
claim statistical drift beyond the recorded measurements.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Callable
import cv2
import numpy as np

from ratio_core.evidence import analyze_image_pair
from ratio_core.benchmark.metrics import ClassSummary, pixel_metrics, region_detection, summarize_class, suspicious_area_error

BENCHMARK_SCHEMA = "3.0"
RELATIVE_BASELINE_FLOOR = 0.01  # relative-% thresholds only apply above this baseline value


def evaluate_sample(base: np.ndarray, modified: np.ndarray, sample: dict, config: dict,
                    min_meaningful_change: float = 0.34) -> dict:
    """Run the visual pipeline and score against the sample's ground truth."""
    result = analyze_image_pair(base, modified, config)
    status = result.comparison.comparison_status
    kind = sample.get("sample_kind", "hazard")
    if status != "COMPARABLE" or result.suspicious_mask is None:
        return {
            "sample_id": sample["sample_id"], "hazard_type": sample["hazard_type"],
            "sample_kind": kind,
            "comparison_status": status, "pipeline_state": "NOT_ANALYZED",
            "visual_change_regions": 0, "suspicious_area_pct": 0.0,
            "unsupported_terrain_candidate": False,
            "max_region_visual_score": 0.0, "pixels": pixel_metrics(None, sample.get("ground_truth_mask")),
            "region": region_detection([], sample.get("ground_truth_mask"), base.shape[:2]),
            "area_error": suspicious_area_error(None, sample.get("ground_truth_mask")),
        }
    bboxes = [(r.bbox[0], r.bbox[1], r.bbox[2], r.bbox[3]) for r in result.regions]
    meaningful = [r for r in result.regions if r.visual_score >= min_meaningful_change]
    pred = (result.suspicious_mask > 0)
    pixels = pixel_metrics(pred, sample.get("ground_truth_mask"))
    region = region_detection([(r.bbox[0], r.bbox[1], r.bbox[2], r.bbox[3]) for r in meaningful],
                              sample.get("ground_truth_mask"), base.shape[:2])
    suspicious_area_pct = round(100 * float(pred.mean()), 6)
    unsupported_candidate = len(meaningful) > 0
    return {
        "sample_id": sample["sample_id"], "hazard_type": sample["hazard_type"],
        "sample_kind": kind,
        "comparison_status": status, "pipeline_state": "ANALYZED",
        "visual_change_regions": len(result.regions),
        "unsupported_terrain_candidate": unsupported_candidate,
        "suspicious_area_pct": suspicious_area_pct,
        "max_region_visual_score": round(max([r.visual_score for r in result.regions], default=0.0), 6),
        "pixels": pixels,
        "region": region,
        "area_error": suspicious_area_error(pred, sample.get("ground_truth_mask")),
    }


def run_benchmark(samples: list[dict], config: dict, split: str, min_meaningful_change: float = 0.34) -> dict:
    """Run all samples, then aggregate per-class summaries."""
    records = []
    for sample in samples:
        record = evaluate_sample(sample["base"], sample["modified"], sample, config, min_meaningful_change)
        record["classification"] = sample["classification"]
        record["split"] = split
        records.append(record)
    classes = {}
    for key in {r["hazard_type"] for r in records}:
        classes[key] = summarize_class([r for r in records if r["hazard_type"] == key]).to_dict()
    aggregates = {
        "total_samples": len(records),
        "hazard_samples": sum(1 for r in records if r.get("sample_kind") == "hazard"),
        "benign_samples": sum(1 for r in records if r.get("sample_kind") == "benign"),
        "visual_change_region_rate": round(np.mean([r["visual_change_regions"] for r in records]), 6) if records else None,
        "unsupported_candidate_rate": round(np.mean([int(r.get("unsupported_terrain_candidate", r["visual_change_regions"] > 0)) for r in records]), 6) if records else None,
        "average_suspicious_area_pct": round(np.mean([r["suspicious_area_pct"] for r in records]), 6) if records else None,
        "false_positive_rate": _overall_fpr(records),
        "false_negative_rate": _overall_fnr(records),
        "policy_block_rate": None,
    }
    return {
        "schema_version": BENCHMARK_SCHEMA,
        "split": split,
        "generation_version": samples[0]["generation_version"] if samples else None,
        "data_classification": _scene_classification(samples),
        "classes": classes,
        "aggregates": aggregates,
        "samples": records,
    }


def _overall_fpr(records) -> float | None:
    values = [r["pixels"]["false_positive_rate"] for r in records
              if r["pixels"]["false_positive_rate"] is not None]
    return round(float(np.mean(values)), 6) if values else None


def _overall_fnr(records) -> float | None:
    values = [r["pixels"]["false_negative_rate"] for r in records
              if r["pixels"]["false_negative_rate"] is not None]
    return round(float(np.mean(values)), 6) if values else None


def _scene_classification(samples) -> str:
    kinds = {s["classification"] for s in samples}
    if kinds <= {"SYNTHETIC_BENCHMARK"}:
        return "SYNTHETIC"
    if kinds <= {"REAL"}:
        return "REAL"
    return "MIXED"


# ------------------------------------------------------------- drift monitor

def register_enhancer(name: str, version: str, fn: Callable[[np.ndarray], np.ndarray], description: str) -> dict:
    return {"name": name, "version": version, "function": fn, "description": description}


def default_enhancers() -> dict[str, dict]:
    """Deterministic enhancement-pipeline variants used as drift-monitor subjects."""
    def v1(img):
        return cv2.addWeighted(img, 1.18, cv2.GaussianBlur(img, (0, 0), 1.2), -0.18, 0)

    def v2(img):
        # stronger sharpening; behaves differently on textured scenes
        return cv2.addWeighted(img, 1.35, cv2.GaussianBlur(img, (0, 0), 1.8), -0.35, 0)

    def v3(img):
        # aggressive local-contrast enhancement; expected to over-produce edges
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB) if img.ndim == 3 else None
        if lab is not None:
            l, a, b = cv2.split(lab)
            cl = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8)).apply(l)
            out = cv2.merge([cl, a, b])
            return cv2.cvtColor(out, cv2.COLOR_LAB2BGR)
        return cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8)).apply(img)

    return {
        "enhancer_v1": register_enhancer("enhancer", "v1", v1, "Phase-2 bundled mild sharpening"),
        "enhancer_v2": register_enhancer("enhancer", "v2", v2, "Stronger unsharp masking"),
        "enhancer_v3": register_enhancer("enhancer", "v3", v3, "Aggressive CLAHE local contrast"),
    }


def _benchmark_rates(samples: list[dict], config: dict, min_meaningful_change: float) -> dict:
    """Aggregate the drift-monitor rates for one enhancer version over fixed samples.

    The enhancer processes the ALREADY-ALTERED benchmark images (hazards injected,
    benign perturbations applied); RATIO then compares base vs enhanced output.
    """
    records = [evaluate_sample(s["base"], s["enhanced"], s, config, min_meaningful_change) for s in samples]
    hazard = [r for r in records if r["sample_kind"] == "hazard"]
    benign = [r for r in records if r["sample_kind"] == "benign"]

    def fraction(rs, key):
        return round(float(np.mean([bool(r[key]) for r in rs])), 6) if rs else None

    def mean(rs, key):
        vals = [float(r[key]) for r in rs]
        return round(float(np.mean(vals)), 6) if vals else None

    def pixel_mean(rs, key):
        vals = [r["pixels"].get(key) for r in rs if r["pixels"].get(key) is not None]
        return round(float(np.mean(vals)), 6) if vals else None

    for record in records:
        record.setdefault("unsupported_terrain_candidate", record["visual_change_regions"] > 0)
    return {
        "visual_change_rate": fraction(records, "visual_change_regions"),
        "suspicious_region_rate": fraction(records, "unsupported_terrain_candidate"),
        "unsupported_risk_mean": None,  # risk requires DEM verification; recorded by the service layer when available
        "false_positive_rate": pixel_mean(benign, "false_positive_rate"),
        "false_negative_rate": pixel_mean(hazard, "false_negative_rate"),
        "region_count_mean": mean(records, "visual_change_regions"),
        "average_changed_area_pct": mean(records, "suspicious_area_pct"),
        "policy_block_rate": None,
    }


def _pct_change(baseline: float | None, candidate: float | None) -> float | None:
    if baseline is None or candidate is None or baseline == 0:
        return None
    return round(100 * (candidate - baseline) / baseline, 4)


def drift_decision(baseline: dict, candidate: dict, thresholds: dict) -> dict:
    """PASS / REVIEW / QUARANTINE over recorded metric changes.

    Thresholds are configurable. Absolute changes always apply; relative
    percentage changes apply only when the baseline metric is meaningfully
    non-zero (>= RELATIVE_BASELINE_FLOOR) so tiny-baseline artifacts cannot
    trigger decisions. Reasons always name the metrics that moved.
    """
    reasons = []
    worst = "PASS"
    for metric, limit in thresholds.items():
        base = baseline.get(metric)
        cand = candidate.get(metric)
        if base is None or cand is None:
            continue
        absolute = round(float(cand) - float(base), 6)
        delta = _pct_change(base, cand)
        pct_eligible = float(base) >= RELATIVE_BASELINE_FLOOR and delta is not None
        quarantine_hit = (abs(absolute) >= float(limit.get("quarantine_abs", 1e18))
                          or (pct_eligible and abs(delta) >= float(limit.get("quarantine", 1e18))))
        review_hit = (abs(absolute) >= float(limit.get("review_abs", 1e18))
                      or (pct_eligible and abs(delta) >= float(limit.get("review", 1e18))))
        if quarantine_hit:
            reasons.append(f"{metric}:{delta:+.2f}%")
            worst = "QUARANTINE"
        elif review_hit and worst != "QUARANTINE":
            reasons.append(f"{metric}:{delta:+.2f}%")
            worst = "REVIEW"
    return {"decision": worst, "reason_codes": sorted(set(reasons)),
            "basis": "configured absolute and percentage thresholds on recorded benchmark metrics; "
                     "percentage thresholds apply only when the baseline metric is >= 0.01"}


def compare_versions(baseline: dict, candidate: dict, thresholds: dict) -> dict:
    changes = {k: _pct_change(baseline.get(k), candidate.get(k)) for k in baseline if k.endswith(("_rate", "_mean", "_pct"))}
    absolute = {}
    for k in changes:
        if baseline.get(k) is None or candidate.get(k) is None:
            absolute[k] = None
        else:
            absolute[k] = round(float(candidate[k]) - float(baseline[k]), 6)
    return {
        "baseline_version": baseline.get("version"),
        "candidate_version": candidate.get("version"),
        "baseline_metrics": {k: v for k, v in baseline.items() if k != "version"},
        "candidate_metrics": {k: v for k, v in candidate.items() if k != "version"},
        "percentage_changes": changes,
        "absolute_changes": absolute,
        **drift_decision(baseline, candidate, thresholds),
    }


def run_drift_monitor(enhancers: dict[str, dict], samples: list[dict], config: dict,
                      thresholds: dict, baseline_key: str = "enhancer_v1",
                      min_meaningful_change: float = 0.34) -> dict:
    """Run the fixed benchmark through each enhancer and compare to the baseline."""
    versions = {}
    for key, enhancer in enhancers.items():
        enhanced_samples = []
        for s in samples:
            enhanced = enhancer["function"](s["modified"])
            enhanced_samples.append({**s, "enhanced": enhanced})
        rates = _benchmark_rates(enhanced_samples, config, min_meaningful_change)
        rates["version"] = enhancer["version"]
        rates["enhancer_name"] = enhancer["name"]
        rates["description"] = enhancer["description"]
        versions[key] = rates
    baseline = versions[baseline_key]
    comparisons = {}
    for key, rates in versions.items():
        if key == baseline_key:
            continue
        comparisons[key] = compare_versions(baseline, rates, thresholds)
    return {
        "schema_version": BENCHMARK_SCHEMA,
        "baseline": baseline,
        "versions": versions,
        "comparisons": comparisons,
        "thresholds": thresholds,
        "benchmark_samples": len(samples),
    }
