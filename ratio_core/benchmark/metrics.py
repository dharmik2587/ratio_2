"""Phase 3C — pixel- and region-level benchmark metrics against ground truth.

All metrics are deterministic. `None` is used when a metric is undefined for a
class (e.g. IoU when no ground-truth pixels exist in a false-positive control).
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np


def pixel_metrics(predicted_mask: np.ndarray | None, ground_truth_mask: np.ndarray | None) -> dict:
    """Pixel precision / recall / IoU / Dice / FPR / FNR.

    - ground_truth None: false-positive control (all positive predictions are FP).
    - predicted None or empty: nothing detected.
    """
    gt = np.asarray(ground_truth_mask, bool) if ground_truth_mask is not None else (np.zeros_like(np.asarray(predicted_mask, bool)) if predicted_mask is not None else None)
    pred = np.asarray(predicted_mask, bool) if predicted_mask is not None else None
    if pred is None:
        return {"pixel_precision": None, "pixel_recall": 0.0, "iou": 0.0, "dice": 0.0,
                "false_positive_rate": None, "false_negative_rate": 0.0, "detected_pixels": 0}
    if gt is None or not gt.any():
        tp = 0
        fp = int(pred.sum())
        fn = 0
        tn = int((~pred).sum())
        return {"pixel_precision": 0.0, "pixel_recall": None, "iou": 0.0, "dice": 0.0,
                "false_positive_rate": round(float(fp) / max(fp + tn, 1), 6),
                "false_negative_rate": None, "detected_pixels": int(pred.sum()),
                "note": "no ground-truth pixels; positive predictions counted as false alarms"}
    tp = int((pred & gt).sum())
    fp = int((pred & ~gt).sum())
    fn = int((~pred & gt).sum())
    tn = int((~pred & ~gt).sum())
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    inter = tp
    union = int((pred | gt).sum())
    iou = inter / max(union, 1)
    dice = 2 * inter / max(int(pred.sum()) + int(gt.sum()), 1)
    fpr = fp / max(fp + tn, 1)
    fnr = fn / max(fn + tp, 1)
    return {"pixel_precision": round(float(precision), 6), "pixel_recall": round(float(recall), 6),
            "iou": round(float(iou), 6), "dice": round(float(dice), 6),
            "false_positive_rate": round(float(fpr), 6), "false_negative_rate": round(float(fnr), 6),
            "detected_pixels": tp + fp}


def _region_mask_from_bboxes(bboxes, shape) -> np.ndarray:
    mask = np.zeros(shape, bool)
    for (x, y, w, h) in bboxes:
        x0, y0 = max(0, int(x)), max(0, int(y))
        x1, y1 = min(shape[1], int(x + w)), min(shape[0], int(y + h))
        if x1 > x0 and y1 > y0:
            mask[y0:y1, x0:x1] = True
    return mask


def region_detection(predicted_bboxes, ground_truth_mask, shape, iou_threshold: float = 0.3) -> dict:
    """Region-level detection: a predicted region counts as a detection when it
    overlaps the ground-truth mask with IoU >= threshold; otherwise false alarm."""
    gt = np.asarray(ground_truth_mask, bool) if ground_truth_mask is not None else None
    if gt is None or not gt.any():
        return {"region_detected": False, "region_false_alarm": len(predicted_bboxes) > 0,
                "region_iou": None, "regions_reported": len(predicted_bboxes)}
    pred = _region_mask_from_bboxes(predicted_bboxes, shape)
    inter = int((pred & gt).sum())
    union = int((pred | gt).sum())
    iou = inter / max(union, 1)
    return {"region_detected": iou >= iou_threshold, "region_false_alarm": len(predicted_bboxes) > 0 and iou < iou_threshold,
            "region_iou": round(float(iou), 6), "regions_reported": len(predicted_bboxes)}


@dataclass
class ClassSummary:
    hazard_type: str
    classification: str
    samples: int
    detected: int
    missed: int
    false_alarms: int
    average_iou: float | None
    median_iou: float | None
    average_pixel_precision: float | None
    average_pixel_recall: float | None
    average_false_positive_rate: float | None

    def to_dict(self):
        return {
            "hazard_type": self.hazard_type, "data_classification": self.classification,
            "number_of_samples": self.samples, "detected": self.detected, "missed": self.missed,
            "false_alarms": self.false_alarms,
            "average_iou": self.average_iou, "median_iou": self.median_iou,
            "average_pixel_precision": self.average_pixel_precision,
            "average_pixel_recall": self.average_pixel_recall,
            "average_false_positive_rate": self.average_false_positive_rate,
        }


def summarize_class(records: list[dict]) -> ClassSummary:
    """Aggregate per-sample metric records into a per-class summary.

    Each record must contain: hazard_type, classification, pixel metrics, region
    detection outcome and iou.
    """
    if not records:
        raise ValueError("no records")
    hazard = records[0]["hazard_type"]
    classification = records[0]["classification"]
    ious = [r["region"]["region_iou"] for r in records if r["region"]["region_iou"] is not None]
    precisions = [r["pixels"]["pixel_precision"] for r in records if r["pixels"]["pixel_precision"] is not None]
    recalls = [r["pixels"]["pixel_recall"] for r in records if r["pixels"]["pixel_recall"] is not None]
    fprs = [r["pixels"]["false_positive_rate"] for r in records if r["pixels"]["false_positive_rate"] is not None]
    detected = sum(1 for r in records if r["region"]["region_detected"])
    false_alarms = sum(1 for r in records if r["region"]["region_false_alarm"])
    missed = sum(1 for r in records if not r["region"]["region_detected"])
    return ClassSummary(
        hazard_type=hazard, classification=classification, samples=len(records),
        detected=detected, missed=missed, false_alarms=false_alarms,
        average_iou=round(float(np.mean(ious)), 6) if ious else None,
        median_iou=round(float(np.median(ious)), 6) if ious else None,
        average_pixel_precision=round(float(np.mean(precisions)), 6) if precisions else None,
        average_pixel_recall=round(float(np.mean(recalls)), 6) if recalls else None,
        average_false_positive_rate=round(float(np.mean(fprs)), 6) if fprs else None,
    )


def suspicious_area_error(predicted_mask, ground_truth_mask) -> float | None:
    """Absolute area-fraction error between predicted and ground-truth masks."""
    if predicted_mask is None or ground_truth_mask is None:
        return None
    pred = np.asarray(predicted_mask, bool)
    gt = np.asarray(ground_truth_mask, bool)
    if pred.shape != gt.shape:
        raise ValueError("mask shapes differ")
    return round(float(abs(pred.mean() - gt.mean())), 6)
