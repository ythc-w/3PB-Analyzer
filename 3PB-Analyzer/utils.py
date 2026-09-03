"""
Utility functions module, providing some commonly used utility functions.
"""

import os
import sys
import logging


def get_resource_path(relative_path):
    """
    Gets the absolute path of a resource, compatible with development and packaged modes.

    Args:
        relative_path (str): The resource path relative to the program root directory.

    Returns:
        str: The absolute path of the resource.
    """
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    except Exception as e:
         logging.error(f"Error getting resource path: {e}")
         base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def get_writable_path(filename):
    """Return a per-user writable path suitable for logs in a packaged app."""
    base_path = os.environ.get("LOCALAPPDATA")
    if not base_path:
        base_path = os.path.expanduser("~")
    app_data_path = os.path.join(base_path, "3PB-Analyzer")
    os.makedirs(app_data_path, exist_ok=True)
    return os.path.join(app_data_path, filename)
