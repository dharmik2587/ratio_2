"""Phase 3B — independent registration validation point."""
import json

import numpy as np
import pytest

from ratio_core.registration import fit_affine, fit_affine_validated, transform_points

CONFIG = json.load(open("configs/phase2.json"))


def test_phase2_three_point_behavior_frozen():
    result = fit_affine([[30, 30], [480, 30], [30, 480]], [[21, 21], [337, 21], [21, 337]], (512, 512), CONFIG)
    assert result.validation_basis == "MINIMAL_EXACT_FIT"
    assert result.quality_score <= CONFIG["registration"]["minimal_fit_quality_cap"]
    assert result.fit_point_count == 0 and result.validation_point_count == 0


def test_validated_fit_good_independent_point_is_high_quality():
    result = fit_affine_validated([[30, 30], [480, 30], [30, 480]], [[21, 21], [337, 21], [21, 337]],
                                  (512, 512), CONFIG, [[255, 255]], [[180, 180]])
    assert result.validation_basis == "FIT_3_VALIDATE_INDEPENDENT"
    assert result.fit_rmse_px == 0.0  # by construction, not proof
    assert result.validation_point_count == 1
    assert result.validation_residuals_px[0] <= 2.0
    assert result.status == "REGISTRATION_SUCCESS"
    assert result.quality_score <= CONFIG["registration"]["minimal_fit_quality_cap"]


def test_validated_fit_wrong_correspondence_fails_independent_validation():
    result = fit_affine_validated([[30, 30], [480, 30], [30, 480]], [[21, 21], [337, 21], [21, 337]],
                                  (512, 512), CONFIG, [[255, 255]], [[21, 21]])
    assert result.validation_max_error_px > 5
    assert result.quality_label in {"LOW", "INVALID"}
    assert result.status in {"REGISTRATION_FAILED", "REGISTRATION_REVIEW"}


def test_fit_rmse_zero_never_upgrades_quality_on_bad_validation():
    result = fit_affine_validated([[30, 30], [480, 30], [30, 480]], [[21, 21], [337, 21], [21, 337]],
                                  (512, 512), CONFIG, [[255, 255]], [[21, 21]])
    assert result.fit_rmse_px == 0.0
    assert result.quality_label != "HIGH"
    assert result.quality_score <= 0.5


def test_degenerate_fit_points_still_rejected():
    with pytest.raises(ValueError, match="DEGENERATE_CONTROL_POINTS"):
        fit_affine_validated([[0, 0], [1, 1], [2, 2]], [[0, 0], [1, 1], [2, 2]], (512, 512), CONFIG,
                             [[3, 3]], [[3, 3]])


def test_invalid_validation_points_rejected():
    with pytest.raises(ValueError, match="INVALID_VALIDATION_POINTS"):
        fit_affine_validated([[30, 30], [480, 30], [30, 480]], [[21, 21], [337, 21], [21, 337]],
                             (512, 512), CONFIG, [[np.nan, 1]], [[2, 2]])


def test_transform_points_unchanged():
    matrix = [[1, 0, 10], [0, 1, 5], [0, 0, 1]]
    out = transform_points(matrix, [[0, 0], [1, 1]])
    assert np.allclose(out, [[10, 5], [11, 6]])
