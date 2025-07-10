"""
Tests for the utility functions.
"""

import pytest
from src.utils import sanitize_filename, scan_for_garage61_folders
import tempfile
from pathlib import Path

@pytest.mark.parametrize("original, expected", [
    # Test case 1: Basic sanitization of illegal characters
    ('file<name>: with"illegal/chars\\|?*', 'file_name__ with_illegal_chars____'),
    
    # Test case 2: Leading and trailing whitespace and dots
    ('  .a valid name.  ', 'a valid name'),
    
    # Test case 3: String with no illegal characters
    ('a-perfectly-valid-filename_123', 'a-perfectly-valid-filename_123'),
    
    # Test case 4: Empty string
    ('', ''),
    
    # Test case 5: String with only illegal characters
    ('<>:"/\\|?*', '_________'),
    
    # Test case 6: Filename that is too long (over 200 chars)
    ('a' * 250, 'a' * 200),
    
    # Test case 7: Japanese characters (should be preserved)
    ('ファイル名', 'ファイル名'),
    
    # Test case 8: Mix of valid and invalid
    ('my/test:file<name>.txt', 'my_test_file_name_.txt'),
])
def test_sanitize_filename(original, expected):
    """
    Tests that sanitize_filename correctly removes illegal characters,
    strips whitespace, and truncates long filenames.
    """
    assert sanitize_filename(original) == expected 

def test_scan_for_garage61_folders():
    """
    Tests that scan_for_garage61_folders correctly finds directories
    that start with 'Garage 61'.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)
        
        # --- Arrange ---
        # Create a structure that mimics the iRacing setups folder
        (base_path / "ferrari296gt3" / "Garage 61 - Team A").mkdir(parents=True)
        (base_path / "ferrari296gt3" / "some_other_setup").mkdir()
        (base_path / "porsche992gt3r" / "Garage 61 - Team B").mkdir(parents=True)
        (base_path / "porsche992gt3r" / "Garage 61 - Team A").mkdir() # Duplicate name
        (base_path / "bmwm4gt3" / "not_a_g61_folder").mkdir(parents=True)
        
        # Create a file that shouldn't be picked up
        (base_path / "mercedesamggt3").mkdir()
        (base_path / "mercedesamggt3" / "Garage 61 - File.txt").touch()

        # --- Act ---
        found_folders = scan_for_garage61_folders(str(base_path))
        
        # --- Assert ---
        # Should find unique folder names, sorted alphabetically
        assert found_folders == ["Garage 61 - Team A", "Garage 61 - Team B"] 