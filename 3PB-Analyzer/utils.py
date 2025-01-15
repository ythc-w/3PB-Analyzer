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
