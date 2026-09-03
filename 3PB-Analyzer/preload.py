"""Robust preload detection and quality control for 3PB data.

The detector keeps the application's original absolute-force preload meaning.
Its main correction is to search after the final return to the pre-peak baseline,
instead of accepting an earlier isolated loading excursion.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Iterable

import numpy as np


@dataclass
class PreloadDetection:
    """Traceable result of preload/contact detection."""

    found: bool
    threshold: float
    index: int | None
    force: float | None
    displacement: float | None
    peak_index: int | None
    search_start_index: int | None
    last_baseline_index: int | None
    baseline_force: float | None
    baseline_mad: float | None
    confirm_points: int
    baseline_fallback_used: bool = False
    local_trend_slope: float | None = None
    ignored_excursion_max_run: int = 0
    removed_nonfinite_points: int = 0
    zero_reset: bool = False
    qc_status: str = "PASS"
    qc_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def correct_baseline(
    force: Iterable[float], baseline_force: float | None, enabled: bool = False
) -> np.ndarray:
    """Optionally subtract a measured baseline; disabled by default for compatibility."""
    values = np.asarray(force, dtype=float).copy()
    if enabled and baseline_force is not None and np.isfinite(baseline_force):
        values -= baseline_force
    return values


def _longest_true_run(mask: np.ndarray) -> int:
    longest = current = 0
    for value in mask:
        if value:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _candidate_starts(mask: np.ndarray, count: int) -> np.ndarray:
    if len(mask) < count:
        return np.array([], dtype=int)
    hits = np.convolve(mask.astype(int), np.ones(count, dtype=int), mode="valid")
    return np.flatnonzero(hits == count)


def _trend_slope(x: np.ndarray, y: np.ndarray) -> float | None:
    valid = np.isfinite(x) & np.isfinite(y)
    if int(valid.sum()) < 2 or np.ptp(x[valid]) <= 0:
        return None
    return float(np.polyfit(x[valid], y[valid], 1)[0])


def detect_preload(
    force: Iterable[float],
    displacement: Iterable[float],
    threshold: float,
    *,
    confirm_points: int = 5,
    trend_points: int = 10,
    min_trend_slope: float = 0.0,
    baseline_points: int = 50,
    baseline_abs_tolerance: float = 0.1,
) -> PreloadDetection:
    """Detect preload after the final pre-peak return to baseline.

    The preload threshold remains an absolute Force_N threshold.  The baseline
    estimate is used for diagnostics and as a fallback only when no non-positive
    pre-peak force exists.
    """
    force_values = np.asarray(force, dtype=float)
    displacement_values = np.asarray(displacement, dtype=float)
    if force_values.shape != displacement_values.shape:
        raise ValueError("force and displacement must have the same shape")
    if confirm_points < 1 or trend_points < confirm_points:
        raise ValueError("trend_points must be >= confirm_points >= 1")

    valid = np.isfinite(force_values) & np.isfinite(displacement_values)
    removed = int((~valid).sum())
    valid_indices = np.flatnonzero(valid)
    if not len(valid_indices):
        return PreloadDetection(
            False,
            threshold,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            confirm_points,
            removed_nonfinite_points=removed,
            qc_status="FAIL",
            qc_reasons=["No finite Force_N/Displacement_mm data points."],
        )

    peak_index = int(valid_indices[np.argmax(force_values[valid])])
    prepeak_valid = valid & (np.arange(len(force_values)) < peak_index)
    prepeak_indices = np.flatnonzero(prepeak_valid)
    if not len(prepeak_indices):
        return PreloadDetection(
            False,
            threshold,
            None,
            None,
            None,
            peak_index,
            None,
            None,
            None,
            None,
            confirm_points,
            removed_nonfinite_points=removed,
            qc_status="FAIL",
            qc_reasons=["No finite data exists before the maximum force."],
        )

    non_positive = prepeak_indices[force_values[prepeak_indices] <= 0]
    baseline_fallback_used = not len(non_positive)
    if len(non_positive):
        last_baseline = int(non_positive[-1])
        baseline_samples = force_values[non_positive]
    else:
        # Limit the fallback to the early pre-peak portion so a long loading ramp
        # cannot inflate a positive baseline estimate.
        prefix_count = min(
            baseline_points,
            max(confirm_points * 2, int(np.ceil(0.2 * len(prepeak_indices)))),
        )
        finite_prefix = prepeak_indices[:prefix_count]
        baseline_samples = force_values[finite_prefix]
        baseline_center = float(np.median(baseline_samples))
        baseline_mad = float(np.median(np.abs(baseline_samples - baseline_center)))
        tolerance = max(baseline_abs_tolerance, 6.0 * baseline_mad)
        baseline_like = prepeak_indices[
            force_values[prepeak_indices] <= baseline_center + tolerance
        ]
        last_baseline = int(baseline_like[-1]) if len(baseline_like) else None

    baseline_force = float(np.median(baseline_samples))
    baseline_mad = float(np.median(np.abs(baseline_samples - baseline_force)))
    search_start = (
        int(prepeak_indices[0]) if last_baseline is None else last_baseline + 1
    )

    false_region_end = max(search_start, 0)
    excursion_level = max(float(threshold), baseline_force + baseline_abs_tolerance)
    ignored_excursion_max_run = _longest_true_run(
        valid[:false_region_end] & (force_values[:false_region_end] > excursion_level)
    )

    search_stop = peak_index + 1
    candidate_mask = valid[search_start:search_stop] & (
        force_values[search_start:search_stop] >= threshold
    )
    candidates = _candidate_starts(candidate_mask, confirm_points)
    selected: int | None = None
    selected_slope: float | None = None
    for relative in candidates:
        candidate = search_start + int(relative)
        trend_end = min(search_stop, candidate + trend_points)
        slope = _trend_slope(
            displacement_values[candidate:trend_end], force_values[candidate:trend_end]
        )
        finite_force = force_values[candidate:trend_end][
            np.isfinite(force_values[candidate:trend_end])
        ]
        net_rise = (
            float(finite_force[-1] - finite_force[0]) if len(finite_force) >= 2 else 0.0
        )
        if slope is not None and slope > min_trend_slope and net_rise > 0:
            selected = candidate
            selected_slope = slope
            break

    reasons: list[str] = []
    status = "PASS"
    if baseline_fallback_used:
        status = "WARNING"
        reasons.append(
            "No non-positive pre-peak force was available; a positive-offset "
            "baseline fallback was used."
        )
    if removed:
        status = "WARNING"
        reasons.append(f"Ignored {removed} non-finite force/displacement rows.")
    if ignored_excursion_max_run > 0:
        status = "WARNING"
        reasons.append(
            "A preload-like excursion returned to baseline before the final loading run "
            f"(maximum run {ignored_excursion_max_run} points); it was ignored."
        )
    if selected is None:
        status = "FAIL"
        reasons.append(
            "No sustained preload crossing with a positive local loading trend was found."
        )
    if not reasons and selected is not None:
        reasons.append("Preload crossing and local loading trend are stable.")

    return PreloadDetection(
        found=selected is not None,
        threshold=float(threshold),
        index=selected,
        force=float(force_values[selected]) if selected is not None else None,
        displacement=float(displacement_values[selected])
        if selected is not None
        else None,
        peak_index=peak_index,
        search_start_index=search_start,
        last_baseline_index=last_baseline,
        baseline_force=baseline_force,
        baseline_mad=baseline_mad,
        confirm_points=confirm_points,
        baseline_fallback_used=baseline_fallback_used,
        local_trend_slope=selected_slope,
        ignored_excursion_max_run=ignored_excursion_max_run,
        removed_nonfinite_points=removed,
        qc_status=status,
        qc_reasons=reasons,
    )


def preload_quality_control(
    detection: PreloadDetection,
    force: Iterable[float],
    displacement: Iterable[float],
    *,
    min_points_after_preload: int = 30,
    max_expected_force: float = 20_000.0,
    max_expected_displacement: float = 100.0,
) -> PreloadDetection:
    """Add data-length, continuity, displacement, and unit plausibility checks."""
    force_values = np.asarray(force, dtype=float)
    displacement_values = np.asarray(displacement, dtype=float)
    reasons = list(detection.qc_reasons)
    status = detection.qc_status

    def warn(message: str) -> None:
        nonlocal status
        if status == "PASS":
            status = "WARNING"
        reasons.append(message)

    if not detection.found or detection.index is None:
        detection.qc_status = "FAIL"
        detection.qc_reasons = reasons
        return detection

    finite_after = np.isfinite(force_values[detection.index:]) & np.isfinite(
        displacement_values[detection.index:]
    )
    if int(finite_after.sum()) < min_points_after_preload:
        status = "FAIL"
        reasons.append(
            f"Only {int(finite_after.sum())} finite points remain after preload; "
            f"at least {min_points_after_preload} are required."
        )

    prepeak_end = detection.peak_index + 1 if detection.peak_index is not None else len(force_values)
    x = displacement_values[detection.index:prepeak_end]
    finite_x = x[np.isfinite(x)]
    if len(finite_x) >= 2 and np.any(np.diff(finite_x) <= 0):
        warn("Displacement is not strictly increasing between preload and peak force.")

    finite_force = force_values[np.isfinite(force_values)]
    finite_displacement = displacement_values[np.isfinite(displacement_values)]
    if len(finite_force) and np.max(np.abs(finite_force)) > max_expected_force:
        warn("Force magnitude exceeds the configured unit-plausibility limit.")
    if len(finite_displacement) and np.ptp(finite_displacement) > max_expected_displacement:
        warn("Displacement range exceeds the configured unit-plausibility limit.")

    detection.qc_status = status
    detection.qc_reasons = reasons
    return detection
