"""
Tests for the SetupScraper class.
"""

import pytest
import zipfile
from pathlib import Path
from queue import Queue
import threading
from src.scraper import SetupScraper, SetupInfo
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

@pytest.fixture(scope="module")
def browser():
    """Provides a single, reusable headless Chrome browser for the test module."""
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=chrome_options)
    yield driver
    driver.quit()

@pytest.fixture
def create_test_zip(tmp_path: Path) -> Path:
    """Creates a realistic test zip file in a temporary directory."""
    zip_path = tmp_path / "test_setup.zip"
    car_dir = "ferrari296gt3"
    track_dir = "daytonaroad"
    setup_name = "HYMO_IMSA_25S3_F296_Daytona_sR"
    
    with zipfile.ZipFile(zip_path, 'w') as zf:
        # Create a nested structure inside the zip
        sto_path = Path(car_dir) / track_dir / f"{setup_name}.sto"
        rpy_path = Path(car_dir) / track_dir / f"{setup_name}.rpy"
        
        # Create dummy files to write into the zip
        zf.writestr(str(sto_path), "dummy sto data")
        zf.writestr(str(rpy_path), "dummy rpy data")
        
    return zip_path


def test_get_setup_listings_from_html(browser):
    """
    Verifies that the scraper can correctly parse setup links from a static HTML file.
    This test confirms that the CSS/XPath selectors are working as expected.
    """
    # --- Arrange ---
    # Path to our local HTML fixture
    fixture_path = Path(__file__).parent / "fixtures" / "setups_page.html"
    fixture_url = fixture_path.as_uri()

    # Navigate the browser to our local file
    browser.get(fixture_url)

    scraper = SetupScraper(
        session=browser,
        setup_page="", # Not used, since we navigate directly
        download_path="",
        progress_queue=Queue(),
        stop_event=threading.Event()
    )

    # --- Act ---
    found_urls = scraper._extract_setup_urls_from_page()

    # --- Assert ---
    assert len(found_urls) == 3
    assert "https://app.tracktitan.io/setups/active-setup-1" in found_urls
    assert "https://app.tracktitan.io/setups/active-setup-2" in found_urls
    assert "https://app.tracktitan.io/setups/active-setup-3" in found_urls

    # Ensure paid and inactive links were NOT processed
    assert "https://app.tracktitan.io/setups/paid-setup-1" not in found_urls
    assert "https://app.tracktitan.io/setups/inactive-setup-1" not in found_urls


def test_organize_setup_files_standard(tmp_path: Path, create_test_zip: Path):
    """
    Verifies that a standard zip file is unzipped and organized into the
    correct car/track/package directory structure.
    """
    # --- Arrange ---
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    
    scraper = SetupScraper(
        session=None,  # Not needed for this method
        setup_page="",
        download_path=str(download_dir),
        progress_queue=Queue(),
        stop_event=threading.Event(),
        skip_event=threading.Event(),
        garage61_folder=None
    )
    
    # --- Act ---
    setup_info = scraper._organize_setup_files(create_test_zip, "http://fake-url.com")
    
    # --- Assert ---
    # Check that the returned info is correct
    assert isinstance(setup_info, SetupInfo)
    assert setup_info.car == "ferrari296gt3"
    assert setup_info.track == "daytonaroad"
    
    # Check that the directory structure is correct
    expected_dir = (
        download_dir / "ferrari296gt3" / "daytonaroad" / "HYMO_IMSA_25S3_F296_Daytona_sR"
    )
    assert expected_dir.is_dir()
    
    # Check that the files were moved
    assert (expected_dir / "HYMO_IMSA_25S3_F296_Daytona_sR.sto").exists()
    assert (expected_dir / "HYMO_IMSA_25S3_F296_Daytona_sR.rpy").exists()
    
    # Check that the original zip was deleted
    assert not create_test_zip.exists()


def test_organize_setup_files_with_garage61_folder(tmp_path: Path, create_test_zip: Path):
    """
    Verifies that when a Garage 61 folder is specified, it is created as an
    intermediate directory in the final path.
    """
    # --- Arrange ---
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    g61_folder_name = "Garage 61 - My Team"
    
    scraper = SetupScraper(
        session=None,
        setup_page="",
        download_path=str(download_dir),
        progress_queue=Queue(),
        stop_event=threading.Event(),
        skip_event=threading.Event(),
        garage61_folder=g61_folder_name
    )
    
    # --- Act ---
    scraper._organize_setup_files(create_test_zip, "http://fake-url.com")
    
    # --- Assert ---
    # Check that the directory structure includes the G61 folder
    expected_dir = (
        download_dir / "ferrari296gt3" / g61_folder_name / "daytonaroad" / "HYMO_IMSA_25S3_F296_Daytona_sR"
    )
    assert expected_dir.is_dir()
    assert (expected_dir / "HYMO_IMSA_25S3_F296_Daytona_sR.sto").exists() 