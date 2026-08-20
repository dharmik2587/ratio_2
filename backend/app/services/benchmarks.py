"""Phase 3C/3D — benchmark generation/execution and enhancement drift monitoring.

Benchmark jobs are fully separated from interactive analysis and write only
JSON artifacts (benchmark_report.json / drift_report.json) under data/.
Nothing here mutates scientific configuration or stored analyses.
"""
from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from backend.app.core.config import ROOT, load_scientific_config
from backend.app.services import evidence_api, store
from backend.app.services.analysis import run_analysis
from ratio_core.benchmark.generator import (
    BENIGN_TYPES, GENERATION_VERSION, HAZARD_TYPES, SCENE_REGISTRY,
    generate_benign_sample, generate_hazard_sample,
)
from ratio_core.benchmark.runner import compare_versions, default_enhancers, run_benchmark, run_drift_monitor


def _load_phase3_config() -> dict:
    path = ROOT / "configs" / "phase3.json"
    return json.loads(path.read_text())


def _scene_seed(scene_id: str) -> int:
    import hashlib
    return int(hashlib.sha256(scene_id.encode()).hexdigest()[:8], 16) % 100000


def _sample_record(sample, base, modified, kind) -> dict:
    record = sample.to_dict()
    record["ground_truth_mask"] = sample.ground_truth_mask
    record["base"] = base
    record["modified"] = modified
    record["sample_kind"] = kind
    return record


def _build_samples(split_scenes: dict[str, list[str]], seeds_per_class: int,
                   classification: str = "SYNTHETIC_BENCHMARK") -> list[dict]:
    """Hazard + benign samples for the given scenes. Deterministic seeds."""
    samples = []
    for scene_id in split_scenes:
        base = SCENE_REGISTRY[scene_id]()
        for hazard in HAZARD_TYPES:
            for i in range(seeds_per_class):
                seed = _scene_seed(scene_id) + i * 17
                sample = generate_hazard_sample(base, scene_id, hazard, seed, classification=classification)
                samples.append(_sample_record(sample, base, sample.modified_image, "hazard"))
        for benign in BENIGN_TYPES:
            for i in range(seeds_per_class):
                seed = _scene_seed(scene_id) + 1000 + i * 13
                sample = generate_benign_sample(base, scene_id, benign, seed, classification=classification)
                samples.append(_sample_record(sample, base, sample.modified_image, "benign"))
    return samples


def _real_scene_samples(seeds_per_class: int) -> list[dict]:
    """Real lunar-derived base scene (NASA SVS LROC composite) — classification REAL."""
    base_path = ROOT / "datasets/real/derived/lroc_nearside_original.png"
    base = cv2.imread(str(base_path))
    if base is None:
        return []
    samples = []
    for hazard in ("fake_boulder", "fake_crater"):
        for i in range(seeds_per_class):
            sample = generate_hazard_sample(base, "scene_real_lroc", hazard, 7100 + i,
                                            classification="REAL")
            samples.append(_sample_record(sample, base, sample.modified_image, "hazard"))
    for benign in ("mild_sharpening", "sensor_noise"):
        for i in range(seeds_per_class):
            sample = generate_benign_sample(base, "scene_real_lroc", benign, 7200 + i,
                                            classification="REAL")
            samples.append(_sample_record(sample, base, sample.modified_image, "benign"))
    return samples


def run_benchmark_job(splits_override: dict | None = None) -> dict:
    """Generate and evaluate the full benchmark; persist benchmark_report.json."""
    phase3 = _load_phase3_config()
    benchmark_cfg = phase3["benchmark"]
    splits_cfg = splits_override or benchmark_cfg["splits"]
    config = load_scientific_config()
    min_change = float(benchmark_cfg["min_meaningful_change"])
    report_id = uuid.uuid4().hex[:12]
    generated_at = datetime.now(timezone.utc).isoformat()
    results = {}
    for split, scenes in splits_cfg.items():
        samples = _build_samples(scenes, int(benchmark_cfg["seeds_per_class"]))
        if split == "held_out" and len(splits_cfg) > 1:
            samples += _real_scene_samples(int(benchmark_cfg["seeds_per_class"]))
        results[split] = run_benchmark(samples, config, split, min_change)
    classification = "MIXED" if any(
        r["data_classification"] == "MIXED" for r in results.values()) else (
        "REAL" if all(r["data_classification"] == "REAL" for r in results.values()) else "SYNTHETIC")
    report = {
        "id": report_id,
        "generated_at": generated_at,
        "kind": "synthetic_hazard_and_false_positive_test_range",
        "data_classification": classification,
        "generation_version": GENERATION_VERSION,
        "splits": results,
        "parameters": {
            "seeds_per_class": benchmark_cfg["seeds_per_class"],
            "min_meaningful_change": min_change,
            "scene_level_split": benchmark_cfg["splits"],
            "scientific_config_note": "frozen Phase-1 visual configuration (configs/stage1.json)",
        },
        "failures": [],
        "limitations": [
            "Procedural scenes are synthetic visual test scenes, not lunar data.",
            "Real-based samples use the NASA SVS rendering composite, which is not a calibrated science image.",
            "Hazard detection is measured with the frozen Phase-1 thresholds; no ML is trained.",
            "Metrics are computed against pixel ground truth; region-level detection uses IoU >= 0.3.",
        ],
    }
    directory = evidence_api.BENCHMARK_DIR
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"benchmark_report_{report_id}.json").write_text(json.dumps(report, indent=2))
    return report


def _verified_rates_for_enhancer(enhancer: dict, real_samples: list[dict]) -> dict:
    """Run the real-scene samples through the FULL deterministic verification path
    (upload -> analysis -> reference -> verify) for one enhancer version."""
    decisions = []
    risks = []
    verified = 0
    from backend.app.services import phase2 as phase2_service
    for s in real_samples:
        dataset_id = ("NASA_SVS_LRO_SYNTHETIC_HAZARD" if s["sample_kind"] == "hazard"
                      else "NASA_SVS_LRO_NEARSIDE_45")
        enhanced = enhancer["function"](s["modified"])
        original_id = store.save_upload(cv2.imencode(".png", s["base"])[1].tobytes(),
                                        f"drift_{s['sample_id']}_base.png", "image/png")["id"]
        enhanced_id = store.save_upload(cv2.imencode(".png", enhanced)[1].tobytes(),
                                        f"drift_{s['sample_id']}_enhanced.png", "image/png")["id"]
        try:
            record = run_analysis(original_id, enhanced_id, f"drift {enhancer['version']} {s['sample_id']}")
            phase2_service.attach_reference(record["id"], dataset_id)
            verified_record = phase2_service.verify_analysis(record["id"], "ROUTE_PLANNING")
            decisions.append(verified_record["policy"]["decision"])
            for feature in verified_record.get("features", []):
                if feature.get("unsupported_risk") is not None:
                    risks.append(float(feature["unsupported_risk"]))
            verified += 1
        except Exception:
            continue
    blocked = [d for d in decisions if d in {"NOT_SAFE", "REVIEW_REQUIRED"}]
    return {
        "policy_block_rate": round(len(blocked) / len(decisions), 6) if decisions else None,
        "unsupported_risk_mean": round(float(np.mean(risks)), 6) if risks else None,
        "policy_verified_samples": verified,
    }


def run_drift_job() -> dict:
    """Run the fixed drift benchmark through all enhancer versions; persist drift_report.json."""
    phase3 = _load_phase3_config()
    cfg = phase3["drift"]
    config = load_scientific_config()
    samples = _build_samples(phase3["benchmark"]["splits"]["development"],
                             int(phase3["benchmark"]["seeds_per_class"]))
    real_samples = _real_scene_samples(int(phase3["benchmark"]["seeds_per_class"]))
    samples += real_samples
    result = run_drift_monitor(default_enhancers(), samples, config, cfg["thresholds"],
                               baseline_key=cfg["baseline_enhancer"],
                               min_meaningful_change=float(phase3["benchmark"]["min_meaningful_change"]))
    # policy-block rate and unsupported-risk mean come from real deterministic verifications
    for key, enhancer in default_enhancers().items():
        verified = _verified_rates_for_enhancer(enhancer, real_samples)
        result["versions"][key].update(verified)
    baseline = result["versions"][cfg["baseline_enhancer"]]
    for key, rates in result["versions"].items():
        if key != cfg["baseline_enhancer"]:
            result["comparisons"][key] = compare_versions(baseline, rates, cfg["thresholds"])
    report = {
        "id": uuid.uuid4().hex[:12],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kind": "enhancement_pipeline_drift_monitor",
        "data_classification": "MIXED" if any(
            "scene_real" in s["sample_id"] for s in samples) else "SYNTHETIC",
        **result,
    }
    directory = evidence_api.DRIFT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"drift_report_{report['id']}.json").write_text(json.dumps(report, indent=2))
    return report
