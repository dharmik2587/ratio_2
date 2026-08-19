import copy, json
from pathlib import Path
import cv2
import numpy as np
import pytest
from ratio_core.evidence import analyze_image_pair, validate_config

CONFIG = json.loads((Path(__file__).parents[1] / "configs/stage1.json").read_text())


def scene(size=(256, 256), seed=4):
    h, w = size
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[:h, :w]
    image = 45 + 18 * np.sin(x / 31) + 13 * np.cos(y / 43)
    for cx, cy, radius, depth in [(w*.28,h*.31,w*.12,25),(w*.7,h*.65,w*.16,30),(w*.73,h*.2,w*.07,18)]:
        d = np.hypot(x-cx, y-cy)
        image += depth*np.exp(-((d-radius)/(max(2,w*.015)))**2) - depth*.55*np.exp(-(d/(radius*.7))**4)
    image += rng.normal(0, 1.5, image.shape)
    return np.uint8(np.clip(image, 0, 255))


def overlap_metrics(detected, truth):
    d, t = detected > 0, truth > 0
    intersection = np.logical_and(d, t).sum()
    union = np.logical_or(d, t).sum()
    return intersection / union, 2 * intersection / (d.sum() + t.sum())


def test_identical_invariant():
    im = scene(); result = analyze_image_pair(im, im.copy(), CONFIG)
    assert result.comparison.compatibility_score == 1
    assert result.comparison.comparison_status == "COMPARABLE"
    assert result.global_metrics == {"mean_visual_score": 0.0, "mean_absolute_residual": 0.0,
        "global_ssim": 1.0, "suspicious_area_pct": 0.0, "region_count": 0}
    assert result.regions == []


def test_same_scene_different_required_dimensions_is_normalized():
    original = cv2.resize(scene(), (1043, 1200), interpolation=cv2.INTER_CUBIC)
    enhanced = cv2.resize(original, (1170, 1345), interpolation=cv2.INTER_CUBIC)
    result = analyze_image_pair(original, enhanced, CONFIG)
    assert result.comparison.comparison_status == "COMPARABLE"
    assert result.comparison.compatibility_score > .95
    assert result.comparison.resize_applied is True
    assert result.comparison.analysis_dimensions == (1043, 1200)
    assert result.global_metrics["suspicious_area_pct"] < .1


def test_different_size_known_alteration_localizes():
    original = cv2.resize(scene(), (1043, 1200), interpolation=cv2.INTER_CUBIC)
    changed = original.copy(); truth = np.zeros_like(original)
    cv2.circle(changed, (780, 330), 55, 190, -1); cv2.circle(truth, (780, 330), 55, 255, -1)
    enhanced = cv2.resize(changed, (1170, 1345), interpolation=cv2.INTER_CUBIC)
    result = analyze_image_pair(original, enhanced, CONFIG)
    iou, dice = overlap_metrics(result.suspicious_mask, truth)
    assert result.comparison.compatibility_status == "HIGH"
    assert result.regions and iou > .60 and dice > .75


def test_crop_is_not_silently_compared():
    original = scene((400, 400))
    crop = original[45:-45, 35:-35]
    result = analyze_image_pair(original, crop, CONFIG)
    assert result.comparison.comparison_status == "REVIEW_COMPARABILITY"
    assert result.global_metrics is None and result.regions == []


def test_completely_unrelated_is_incomparable():
    a = scene(seed=1)
    b = np.random.default_rng(90).integers(0, 256, a.shape, dtype=np.uint8)
    result = analyze_image_pair(a, b, CONFIG)
    assert result.comparison.comparison_status == "INCOMPARABLE_IMAGES"
    assert result.global_metrics is None and result.visual_score_map is None


def test_unrelated_lunar_looking_scenes_are_not_accepted_as_comparable():
    a = scene(seed=2)
    b = np.rot90(scene(seed=71), 2).copy()
    result = analyze_image_pair(a, b, CONFIG)
    assert result.comparison.comparison_status in {"INCOMPARABLE_IMAGES", "REVIEW_COMPARABILITY"}
    assert result.global_metrics is None


@pytest.mark.parametrize("center", [(35,35),(221,35),(35,221),(221,221),(128,128)])
def test_alteration_location_follows_change(center):
    a = scene(); b = a.copy(); truth = np.zeros_like(a)
    cv2.circle(b, center, 12, 210, -1); cv2.circle(truth, center, 12, 255, -1)
    result = analyze_image_pair(a, b, CONFIG)
    iou, _ = overlap_metrics(result.suspicious_mask, truth)
    assert result.comparison.comparison_status == "COMPARABLE"
    assert iou > .55


def test_alteration_strength_response_is_sensible():
    a = scene(); means = []
    for value in (85, 145, 220):
        b = a.copy(); cv2.circle(b, (128,128), 14, value, -1)
        result = analyze_image_pair(a, b, CONFIG)
        yy, xx = np.ogrid[:256,:256]; region = (xx-128)**2+(yy-128)**2 <= 14**2
        means.append(float(result.visual_score_map[region].mean()))
    assert means[0] < means[1] < means[2]


@pytest.mark.parametrize("transform", [
    lambda a: cv2.addWeighted(a, 1.2, cv2.GaussianBlur(a,(0,0),1), -.2, 0),
    lambda a: cv2.GaussianBlur(a, (3,3), .5),
    lambda a: cv2.convertScaleAbs(a, alpha=1.08, beta=5),
])
def test_legitimate_global_transform_not_whole_image_suspicious(transform):
    a = scene(); result = analyze_image_pair(a, transform(a), CONFIG)
    assert result.comparison.comparison_status == "COMPARABLE"
    assert result.global_metrics["suspicious_area_pct"] < 10


@pytest.mark.parametrize("sigma", [0.5, 1.0, 2.0])
def test_small_noise_not_whole_image_suspicious(sigma):
    a = scene(); rng = np.random.default_rng(22)
    b = np.uint8(np.clip(a.astype(float) + rng.normal(0, sigma, a.shape), 0, 255))
    result = analyze_image_pair(a, b, CONFIG)
    assert result.comparison.comparison_status == "COMPARABLE"
    assert result.global_metrics["suspicious_area_pct"] < 5


def test_deterministic_scientific_output():
    a = scene(); b = a.copy(); cv2.rectangle(b,(30,40),(70,80),200,-1)
    one, two = analyze_image_pair(a,b,CONFIG), analyze_image_pair(a,b,CONFIG)
    assert one.comparison == two.comparison
    assert one.global_metrics == two.global_metrics
    assert one.regions == two.regions
    assert np.array_equal(one.visual_score_map, two.visual_score_map)
    assert np.array_equal(one.suspicious_mask, two.suspicious_mask)


@pytest.mark.parametrize("mutation,match", [
    (lambda c: c["visual_weights"].update(residual=-.1), "Visual weights"),
    (lambda c: c["visual_weights"].update(residual=.9), "sum to 1"),
    (lambda c: c["detection"].update(suspicious_threshold=-.1), "Suspicious threshold"),
    (lambda c: c["compatibility"].update(low_threshold=.9, high_threshold=.8), "less than"),
    (lambda c: c["compatibility"].update(low_threshold=-.1), "Low compatibility"),
    (lambda c: c["compatibility"]["weights"].update(coarse_ssim=2), "Compatibility weights"),
])
def test_invalid_configuration_rejected(mutation, match):
    config = copy.deepcopy(CONFIG); mutation(config)
    with pytest.raises(ValueError, match=match): validate_config(config)


def test_configuration_threshold_is_actually_used():
    a=scene(); b=a.copy(); cv2.circle(b,(128,128),12,150,-1)
    baseline=analyze_image_pair(a,b,CONFIG)
    changed=copy.deepcopy(CONFIG); changed["detection"]["suspicious_threshold"]=.9
    stricter=analyze_image_pair(a,b,changed)
    assert stricter.global_metrics["suspicious_area_pct"] < baseline.global_metrics["suspicious_area_pct"]


def test_visual_weights_are_actually_used():
    a=scene(); b=a.copy(); cv2.circle(b,(128,128),12,150,-1)
    baseline=analyze_image_pair(a,b,CONFIG)
    changed=copy.deepcopy(CONFIG)
    changed["visual_weights"]["residual"] += .10
    changed["visual_weights"]["ssim_change"] -= .10
    reweighted=analyze_image_pair(a,b,changed)
    assert not np.array_equal(baseline.visual_score_map,reweighted.visual_score_map)
    assert baseline.regions[0].visual_score != reweighted.regions[0].visual_score


def test_compatibility_threshold_is_actually_used():
    a=scene(); b=a.copy(); cv2.circle(b,(128,128),20,190,-1)
    baseline=analyze_image_pair(a,b,CONFIG)
    changed=copy.deepcopy(CONFIG); changed["compatibility"]["high_threshold"]=.99
    stricter=analyze_image_pair(a,b,changed)
    assert baseline.comparison.comparison_status=="COMPARABLE"
    assert stricter.comparison.comparison_status=="REVIEW_COMPARABILITY"


def test_aspect_ratio_tolerance_is_actually_used():
    a=scene(); b=cv2.resize(a,(220,256),interpolation=cv2.INTER_AREA)
    conservative=analyze_image_pair(a,b,CONFIG)
    permissive=copy.deepcopy(CONFIG); permissive["compatibility"]["maximum_aspect_ratio_difference"]=.20
    allowed=analyze_image_pair(a,b,permissive)
    assert conservative.comparison.comparison_status=="REVIEW_COMPARABILITY"
    assert allowed.comparison.comparison_status=="COMPARABLE"
