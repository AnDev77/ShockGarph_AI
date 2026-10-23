from __future__ import annotations

import pytest

from scripts.analyze_alpaca_history import _diagnose_paired_differences, _serial_correlation


def test_lag_correlation_and_phase_slices_are_not_independent_row_counts() -> None:
    differences = [float(index) for index in range(1, 19)]
    assert _serial_correlation(differences, 1) == pytest.approx(1.0)
    report = _diagnose_paired_differences(differences, horizon=3)
    assert report["nonoverlap_phase_count"] == 3
    assert report["nonoverlap_phase_mean_range_percentage_points"] == [850.0, 1050.0]
    assert report["nonoverlap_phase_negative_count"] == 0
    assert report["block_2h_ci_percentage_points"] is not None


def test_constant_errors_have_no_defined_correlation() -> None:
    assert _serial_correlation([1.0] * 12, 1) is None
    report = _diagnose_paired_differences([1.0] * 12, horizon=3)
    assert report["lag_one_correlation"] is None
    assert report["nonoverlap_phase_mean_range_percentage_points"] == [100.0, 100.0]


def test_daily_average_can_hide_opposite_nonoverlapping_phase_results() -> None:
    report = _diagnose_paired_differences([-0.01, 0.01] * 8, horizon=2)
    assert report["nonoverlap_phase_count"] == 2
    assert report["nonoverlap_phase_negative_count"] == 1
    assert report["nonoverlap_phase_mean_range_percentage_points"] == [-1.0, 1.0]
