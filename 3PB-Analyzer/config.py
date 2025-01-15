"""
Configuration module, used to store the application's configuration information.
"""

import os

# GUI Configuration
WINDOW_TITLE = "3PB-Analyzer"
"""The title of the application window."""
WINDOW_WIDTH = 650
"""The width of the application window."""
WINDOW_HEIGHT = 400
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

# Excel cell formats
Excel_Type = [15, 20, 15, 30, 30, 25]
"""Corresponds to columns A, B, C, D, E, and F in the Excel sheet."""
