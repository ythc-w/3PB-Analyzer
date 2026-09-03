"""
Configuration module, used to store the application's configuration information.
"""

import os

# GUI Configuration
WINDOW_TITLE = "3PB-Analyzer"
"""The title of the application window."""
WINDOW_WIDTH = 650
"""The width of the application window."""
WINDOW_HEIGHT = 450
"""The height of the application window."""
ICON_PATH = "icon.ico"
"""The relative path to the application icon."""

# Analysis Configuration
DEFAULT_MIN_WINDOW_SIZE = 10
"""The default minimum size for the linear regression analysis window."""
DEFAULT_MAX_WINDOW_SIZE = 20
"""The default maximum size for the linear regression analysis window."""
DEFAULT_Yield_Force_Constant = 1.0
DEFAULT_Displacement_Constant = 0.002
"""The default Yield Force Constant (YFC) and the default displacement constant (dispc) used in the equation y = YFC * a * (x - maxdisp * dispc) + b."""


DEFAULT_X_COLUMN = 'Displacement_mm'
"""The default column name for the X-axis data."""
DEFAULT_Y_COLUMN = 'Force_N'
"""The default column name for the Y-axis data."""
OUTPUT_IMAGE_DIR = "png"
"""The default directory for output images."""

# Logging Configuration
LOG_FILE = '3PB.log'
"""The name of the log file."""
LOG_LEVEL = 'DEBUG'

# Default preload value
DEFAULT_PRELOAD = 0
"""The default preload value."""

# Robust preload and QC configuration
DEFAULT_PRELOAD_METHOD = "robust"
"""Use ``robust`` by default; ``legacy`` remains available for comparison."""
PRELOAD_CONFIRM_POINTS = 5
"""Required consecutive points at or above the preload threshold."""
PRELOAD_TREND_POINTS = 10
"""Number of points used to confirm a positive local loading trend."""
PRELOAD_MIN_TREND_SLOPE = 0.0
"""Local Force_N/Displacement_mm slope must be strictly greater than this."""
PRELOAD_BASELINE_POINTS = 50
"""Fallback baseline sample count when no non-positive pre-peak force exists."""
PRELOAD_BASELINE_ABS_TOLERANCE_N = 0.1
"""Absolute noise tolerance used only for baseline/QC diagnostics."""
PRELOAD_MIN_POINTS_AFTER = 30
"""Minimum finite points required after the detected preload point."""
PRELOAD_ZERO_DISPLACEMENT = False
"""Keep original displacement coordinates unless explicitly enabled."""
PRELOAD_CORRECT_FORCE_BASELINE = False
"""Keep original Force_N values unless explicitly enabled."""

# Stiffness-window safeguards. The regression formula itself is unchanged.
STIFFNESS_MIN_POSITIVE_SLOPE = 1e-9
STIFFNESS_MIN_FORCE_SPAN_N = 1.0
STIFFNESS_MIN_FORCE_SPAN_FRACTION = 0.02
STIFFNESS_MIN_MONOTONIC_FRACTION = 0.6

# The original fracture definition is retained: first post-peak point below 50%.
POSTPEAK_FORCE_FRACTION = 0.5
POSTPEAK_GRADUAL_MIN_POINTS = 8

# Broad plausibility limits produce warnings; they never auto-delete a sample.
QC_MAX_EXPECTED_FORCE_N = 20000.0
QC_MAX_EXPECTED_DISPLACEMENT_MM = 100.0

# Excel cell formats
Excel_Type = [15, 20, 15, 30, 30, 25]
"""Corresponds to columns A, B, C, D, E, and F in the Excel sheet."""
