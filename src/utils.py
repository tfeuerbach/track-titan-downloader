"""
General utility functions.
"""

from pathlib import Path
import re
import logging

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

def scan_for_garage61_folders(base_path_str: str) -> list[str]:
    """Scans for Garage 61 directories inside car folders."""
    base_path = Path(base_path_str)
    if not base_path.is_dir():
        return []

    g61_folders = set()
    try:
        # Assuming first level of subdirectories are car folders
        for car_folder in base_path.iterdir():
            if car_folder.is_dir():
                for sub_folder in car_folder.iterdir():
                    if sub_folder.is_dir() and sub_folder.name.startswith("Garage 61"):
                        g61_folders.add(sub_folder.name)
    except Exception as e:
        logging.warning(f"Could not scan for Garage 61 folders: {e}")

    return sorted(list(g61_folders))