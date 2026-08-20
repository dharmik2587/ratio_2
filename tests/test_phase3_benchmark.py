"""Phase 3C/3D — synthetic hazard range, ground truth, metrics, drift monitor."""
import json

import numpy as np

from ratio_core.benchmark import (BENIGN_TYPES, GENERATION_VERSION, HAZARD_TYPES,
                                  SCENE_REGISTRY, generate_benign_sample, generate_hazard_sample,
                                  make_procedural_scene, pixel_metrics, region_detection,
                                  summarize_class)
from ratio_core.benchmark.runner import compare_versions, drift_decision, evaluate_sample

CONFIG = json.load(open("configs/stage1.json"))
PHASE3 = json.load(open("configs/phase3.json"))


def test_hazard_generation_is_reproducible_and_labeled():
    base = make_procedural_scene(11)
    a = generate_hazard_sample(base, "scene_test", "fake_boulder", 7, scale=18, strength=0.5, location=(80, 90))
    b = generate_hazard_sample(base, "scene_test", "fake_boulder", 7, scale=18, strength=0.5, location=(80, 90))
    assert a.sample_id == b.sample_id
    assert a.modified_image_id == b.modified_image_id
    assert a.classification == "SYNTHETIC_BENCHMARK"
    assert a.generation_version == GENERATION_VERSION
    assert np.array_equal(a.ground_truth_mask, b.ground_truth_mask)


def test_every_hazard_type_changes_pixels_and_has_mask():
    base = make_procedural_scene(12)
    for hazard in HAZARD_TYPES:
        sample = generate_hazard_sample(base, "scene_test", hazard, 3)
        assert sample.ground_truth_mask is not None
        assert sample.ground_truth_mask.sum() > 0
        assert not np.array_equal(base, sample.modified_image)


def test_benign_perturbations_have_no_ground_truth_mask():
    base = make_procedural_scene(13)
    for benign in BENIGN_TYPES:
        sample = generate_benign_sample(base, "scene_test", benign, 3)
        assert sample.ground_truth_mask is None
        assert sample.classification == "SYNTHETIC_BENCHMARK"


def test_pixel_metrics_known_masks():
    gt = np.zeros((20, 20), bool); gt[5:15, 5:15] = True
    pred = np.zeros((20, 20), bool); pred[6:14, 6:14] = True
    m = pixel_metrics(pred, gt)
    assert m["iou"] > 0.5 and m["dice"] > 0.5
    assert m["pixel_precision"] == 1.0  # prediction fully inside ground truth
    assert m["false_positive_rate"] == 0.0


def test_pixel_metrics_false_positive_control():
    pred = np.zeros((20, 20), bool); pred[0:2, 0:2] = True
    m = pixel_metrics(pred, None)
    assert m["pixel_precision"] == 0.0
    assert m["false_positive_rate"] > 0.0
    assert m["pixel_recall"] is None


def test_region_detection_iou_threshold():
    gt = np.zeros((40, 40), bool); gt[10:30, 10:30] = True
    hit = region_detection([(12, 12, 16, 16)], gt, (40, 40), iou_threshold=0.3)
    miss = region_detection([(0, 0, 5, 5)], gt, (40, 40), iou_threshold=0.3)
    assert hit["region_detected"] and not hit["region_false_alarm"]
    assert not miss["region_detected"] and miss["region_false_alarm"]


def test_class_summary_aggregation():
    records = [
        {"hazard_type": "fake_boulder", "classification": "SYNTHETIC_BENCHMARK",
         "pixels": {"pixel_precision": 1.0, "pixel_recall": 0.8, "false_positive_rate": 0.0,
                    "false_negative_rate": 0.2},
         "region": {"region_detected": True, "region_false_alarm": False, "region_iou": 0.9}},
        {"hazard_type": "fake_boulder", "classification": "SYNTHETIC_BENCHMARK",
         "pixels": {"pixel_precision": 0.9, "pixel_recall": 0.6, "false_positive_rate": 0.001,
                    "false_negative_rate": 0.4},
         "region": {"region_detected": False, "region_false_alarm": True, "region_iou": 0.1}},
    ]
    summary = summarize_class(records).to_dict()
    assert summary["number_of_samples"] == 2
    assert summary["detected"] == 1 and summary["missed"] == 1 and summary["false_alarms"] == 1
    assert abs(summary["average_iou"] - 0.5) < 1e-6
    assert summary["median_iou"] == 0.5


def test_scene_level_split_separation():
    dev = set(PHASE3["benchmark"]["splits"]["development"])
    held = set(PHASE3["benchmark"]["splits"]["held_out"])
    assert not (dev & held), "scene-level leakage between splits"


def test_visual_pipeline_detects_hazard_not_benign_perturbation():
    base = make_procedural_scene(21)
    hazard = generate_hazard_sample(base, "scene_test", "fake_boulder", 5, scale=16, strength=0.7)
    benign = generate_benign_sample(base, "scene_test", "mild_sharpening", 5, strength=0.4)
    h = evaluate_sample(base, hazard.modified_image, {
        "sample_id": hazard.sample_id, "hazard_type": "fake_boulder",
        "ground_truth_mask": hazard.ground_truth_mask, "sample_kind": "hazard",
        "classification": "SYNTHETIC_BENCHMARK"}, CONFIG)
    b = evaluate_sample(base, benign.modified_image, {
        "sample_id": benign.sample_id, "hazard_type": "mild_sharpening",
        "ground_truth_mask": None, "sample_kind": "benign",
        "classification": "SYNTHETIC_BENCHMARK"}, CONFIG)
    assert h["region"]["region_detected"], "injected boulder must be detected at region level"
    assert not b["unsupported_terrain_candidate"], "mild sharpening must not produce an unsupported-terrain candidate"


def test_drift_decision_pass_review_quarantine():
    thresholds = {"visual_change_rate": {"review": 20.0, "quarantine": 45.0,
                                         "review_abs": 0.02, "quarantine_abs": 0.05}}
    baseline = {"visual_change_rate": 0.4, "version": "v1"}
    assert drift_decision(baseline, {"visual_change_rate": 0.4}, thresholds)["decision"] == "PASS"
    assert drift_decision(baseline, {"visual_change_rate": 0.43}, thresholds)["decision"] == "REVIEW"
    assert drift_decision(baseline, {"visual_change_rate": 0.6}, thresholds)["decision"] == "QUARANTINE"


def test_tiny_baseline_relative_spike_does_not_trigger():
    # a huge relative change on a ~zero baseline must not quarantine by itself
    thresholds = {"false_positive_rate": {"review": 15.0, "quarantine": 35.0,
                                          "review_abs": 0.01, "quarantine_abs": 0.05}}
    baseline = {"false_positive_rate": 0.0001, "version": "v1"}
    decision = drift_decision(baseline, {"false_positive_rate": 0.002}, thresholds)
    assert decision["decision"] != "QUARANTINE"


def test_compare_versions_records_actual_changes():
    thresholds = PHASE3["drift"]["thresholds"]
    out = compare_versions({"version": "v1", "visual_change_rate": 0.4, "false_positive_rate": 0.001},
                           {"version": "v2", "visual_change_rate": 0.5, "false_positive_rate": 0.002},
                           thresholds)
    assert out["percentage_changes"]["visual_change_rate"] == 25.0
    assert out["absolute_changes"]["false_positive_rate"] == 0.001
    assert out["baseline_version"] == "v1" and out["candidate_version"] == "v2"


def test_scenes_are_deterministic():
    a = SCENE_REGISTRY["scene_alpha"]()
    b = SCENE_REGISTRY["scene_alpha"]()
    assert np.array_equal(a, b)
