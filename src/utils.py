"""
General utility functions.
"""

from pathlib import Path
import re

def create_directories(path: Path) -> None:
    """Ensures a directory path exists, creating it if necessary."""
    path.mkdir(parents=True, exist_ok=True)

def sanitize_filename(filename: str) -> str:
    """Removes characters from a string that are invalid for file paths."""
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = filename.strip(' .')
    
    if len(filename) > 200:
        filename = filename[:200]
    return filename