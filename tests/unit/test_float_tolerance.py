"""Pure NumPy scan-kernel behavior for special float values."""

from __future__ import annotations

import numpy as np

from mempilot.core.scanner import ScanMode, kernel_compare, kernel_exact


def test_exact_float_tolerance_and_nan() -> None:
    values = np.asarray([1.0000005, 1.01, np.nan], dtype=np.float64)

    assert kernel_exact(values, 1.0, 1e-3).tolist() == [0]
    assert kernel_exact(values, np.nan, 1e-3).size == 0


def test_nan_pair_is_unchanged_and_not_changed() -> None:
    current = np.asarray([np.nan, np.nan, 3.0], dtype=np.float64)
    previous = np.asarray([np.nan, 2.0, 2.0], dtype=np.float64)

    unchanged = kernel_compare(current, previous, ScanMode.UNCHANGED, None, 1e-3)
    changed = kernel_compare(current, previous, ScanMode.CHANGED, None, 1e-3)

    assert unchanged.tolist() == [True, False, False]
    assert changed.tolist() == [False, True, True]


def test_infinities_compare_normally() -> None:
    values = np.asarray([np.inf, -np.inf, 1.0], dtype=np.float64)

    assert kernel_exact(values, np.inf, 1e-3).tolist() == [0]
    assert kernel_compare(values, values.copy(), ScanMode.UNCHANGED, None, 1e-3).tolist() == [
        True,
        True,
        True,
    ]
