"""
Scrapes and downloads setup files from TrackTitan.
"""

import logging
from typing import List, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from .utils import sanitize_filename
import time
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from pathlib import Path
import zipfile
import tempfile
import shutil
from queue import Queue
import threading
from . import constants

logger = logging.getLogger(__name__)

class SetupInfo:
    """A data container for a single setup's metadata."""
    def __init__(self, name: str, track: str, car: str, download_url: str, 
                 author: str = "", description: str = "", rating: float = 0.0):
        self.name = name
        self.track = track
        self.car = car
        self.download_url = download_url
        self.author = author
        self.description = description
        self.rating = rating
    
    def __repr__(self):
        return f"SetupInfo(name='{self.name}', track='{self.track}', car='{self.car}')"

class SetupScraper:
    """Handles scraping and downloading of setups from TrackTitan."""
    
    def __init__(self, session: webdriver.Chrome, 
                 setup_page: str, delay: float = 1.0, 
                 download_path: Optional[str] = None,
                 progress_queue: Optional[Queue] = None,
                 stop_event: Optional[threading.Event] = None,
                 skip_event: Optional[threading.Event] = None,
                 garage61_folder: Optional[str] = None):
        self.session = session
        self.setup_page = setup_page
        self.delay = delay
        self.download_path = download_path
        self.progress_queue = progress_queue
        self.stop_event = stop_event
        self.skip_event = skip_event
        self.garage61_folder = garage61_folder
    
    def _report_progress(self, value: Optional[int] = None, max_val: Optional[int] = None):
        """Sends progress updates to the main GUI thread."""
        if self.progress_queue:
            update = {}
            if value is not None:
                update['value'] = value
            if max_val is not None:
                update['max'] = max_val
            self.progress_queue.put(update)
    
    def get_setup_listings(self) -> List[SetupInfo]:
        """Finds and downloads all available setups."""
        logger.info("Scraping and downloading setup listings with Selenium...")
        return self._scrape_with_selenium()
    
    def _scrape_with_selenium(self) -> List[SetupInfo]:
        """Uses Selenium to scrape setup data from the 'Active' weekly section."""
        logger.info("Scraping with Selenium...")
        try:
            self.session.get(self.setup_page)
            wait = WebDriverWait(self.session, 20)

            logger.info("Waiting for the '(Active)' setups section...")
            try:
                wait.until(EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "span.text-green-500")
                ))
                logger.info("Located '(Active)' section. Now scrolling to load all setups.")
            except TimeoutException:
                logger.error("Timed out waiting for the active section to appear. Cannot proceed.")
                page_source = self.session.page_source
                with open('debug_selenium_page_no_active_section.html', 'w', encoding='utf-8') as f:
                    f.write(page_source)
                return []

            # Scroll until an '(Inactive)' section header is visible, or we reach the page bottom.
            logger.info("Scrolling to load all setups...")
            last_height = self.session.execute_script("return document.body.scrollHeight")
            
            # Track inactive section headers
            first_inactive_seen = False
            inactive_header_xpath = constants.SCRAPER_SELECTORS['inactive_section_header']
            prev_inactive_count = 0
            # Stop after this many extra inactive sections appear.
            extra_inactive_sections_needed = 2

            while True:
                self.session.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(self.delay + 2)
                
                # Current inactive headers on the page
                inactive_headers = self.session.find_elements(By.XPATH, inactive_header_xpath)

                # First inactive header
                if inactive_headers and not first_inactive_seen:
                    first_inactive_seen = True
                    prev_inactive_count = len(inactive_headers)

                    # Give the UI a moment to finish rendering any late active setups.
                    logger.info("First inactive section header is visible. Waiting a short grace period to allow any remaining active setups to render …")
                    time.sleep(self.delay + 1)  # Give the frontend JS a second to finish rendering

                    # After the wait, decide whether to keep scrolling.
                    new_height_after_wait = self.session.execute_script("return document.body.scrollHeight")
                    if new_height_after_wait <= last_height:
                        logger.info("No additional content detected after grace period. Stopping scroll.")
                        break
                    else:
                        logger.info("Additional content detected after grace period. Continuing scroll.")
                        last_height = new_height_after_wait
                        continue

                # Additional inactive headers
                if first_inactive_seen and inactive_headers:
                    current_inactive_count = len(inactive_headers)
                    if current_inactive_count - prev_inactive_count >= extra_inactive_sections_needed:
                        logger.info(f"{extra_inactive_sections_needed} additional '(Inactive)' sections detected while scrolling. Stopping scroll.")
                        break
                    # Keep original count to detect cumulative extras.

                # If no inactive headers yet or decided to continue, fall through to the height check.
                

                new_height = self.session.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
            
            logger.info("Finished scrolling.")

            setups = self._extract_and_process_setups()
            return setups

        except Exception as e:
            logger.error(f"Selenium scraping failed: {e}", exc_info=True)
            # Save page source on other exceptions
            try:
                page_source = self.session.page_source
                with open('debug_selenium_page_error.html', 'w', encoding='utf-8') as f:
                    f.write(page_source)
                logger.info("Saved page HTML to debug_selenium_page_error.html")
            except Exception as save_e:
                logger.error(f"Could not save debug HTML: {save_e}")
            return []

    def _extract_and_process_setups(self) -> List[SetupInfo]:
        """
        Extracts setup URLs from the current page, then downloads and processes each one.
        """
        setup_page_urls = self._extract_setup_urls_from_page()
        
        if not setup_page_urls:
            logger.warning("No setup links found within any 'Active' sections.")
            return []
    
        logger.info(f"Found a total of {len(setup_page_urls)} setup links across all 'Active' sections.")
        
        setups = []
        failed_downloads = []
        total_setups = len(setup_page_urls)
        self._report_progress(max_val=total_setups, value=0)

        for i, url in enumerate(setup_page_urls):
            if self.stop_event and self.stop_event.is_set():
                logger.info("Stop event received, halting setup downloads.")
                break
            
            if self.skip_event:
                self.skip_event.clear() # Reset for the current item.

            if not url:
                self._report_progress(value=i + 1)
                continue
            
            setup_info = self._download_and_organize_one_setup(url)
            if setup_info:
                setups.append(setup_info)
            else:
                failed_downloads.append(url)
            
            self._report_progress(value=i + 1)
            time.sleep(self.delay)

        if failed_downloads:
            logger.warning(f"{len(failed_downloads)} setup(s) could not be downloaded:")
            for failed_url in failed_downloads:
                logger.warning(f"  - {failed_url}")

        logger.info(f"Successfully downloaded and organized {len(setups)} setups from the active section.")
        return setups

    def _extract_setup_urls_from_page(self) -> List[str]:
        """
        Finds all 'Active' sections on the current page and collects setup links from each.
        """
        setup_page_urls = []
        try:
            active_spans = self.session.find_elements(By.CSS_SELECTOR, constants.SCRAPER_SELECTORS['active_section_span'])
            if not active_spans:
                    logger.warning("No '(Active)' sections found on the page.")
                    return []
            
            logger.info(f"Found {len(active_spans)} '(Active)' sections. Collecting links from each.")

            for active_span in active_spans:
                # Navigate from the '(Active)' span to the div containing the setup cards.
                header_div = active_span.find_element(By.XPATH, "ancestor::div[1]")
                
                # Check the header text to exclude specific paid sections.
                header_text = header_div.text
                if constants.SCRAPER_SELECTORS['paid_bundle_section_text'] in header_text:
                    logger.info(f"Skipping paid bundle section: '{header_text.strip()}'")
                    continue

                active_container = header_div.find_element(By.XPATH, "./following-sibling::div")
                
                # Find setup links only within that active container.
                setup_links = active_container.find_elements(By.TAG_NAME, 'a')
                
                for link in setup_links:
                    url = link.get_attribute('href')
                    if url:
                        setup_page_urls.append(url)

        except Exception as e:
            page_source = self.session.page_source
            with open('debug_selenium_page.html', 'w', encoding='utf-8') as f:
                f.write(page_source)
            logger.error(f"Could not find or process the '(Active)' sections after scrolling. Error: {e}. Saved page HTML for debugging.")
            return []
        
        return setup_page_urls
    
    def _trigger_download(self, setup_page_url: str) -> bool:
        """Navigates to the setup page and clicks the necessary buttons to start the download."""
        MAX_ATTEMPTS = 2
        for attempt in range(MAX_ATTEMPTS):
            if self.skip_event and self.skip_event.is_set():
                logger.warning(f"Skipping download for {setup_page_url} due to user request.")
                return False

            try:
                if attempt > 0:
                    logger.info(f"Retrying download for {setup_page_url} (Attempt {attempt + 1}/{MAX_ATTEMPTS})")
                
                self.session.get(setup_page_url)
                wait = WebDriverWait(self.session, 10)
                
                download_button = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, constants.SCRAPER_SELECTORS['download_latest_button'])
                ))
                self.session.execute_script("arguments[0].click();", download_button)
                
                try:
                    manual_download_wait = WebDriverWait(self.session, 10)
                    manual_download_button = manual_download_wait.until(EC.element_to_be_clickable(
                        (By.XPATH, constants.SCRAPER_SELECTORS['download_manually_button'])
                    ))
                    self.session.execute_script("arguments[0].click();", manual_download_button)
                except (NoSuchElementException, TimeoutException):
                    logger.debug("Did not find 'Download Manually' button, assuming direct download.")
                    pass

                # Check for a specific failure notification from the website.
                try:
                    error_notification_xpath = constants.SCRAPER_SELECTORS['download_error_notification']
                    error_wait = WebDriverWait(self.session, 5) # Short wait, it appears fast.
                    error_wait.until(EC.presence_of_element_located((By.XPATH, error_notification_xpath)))
                    
                    if attempt < MAX_ATTEMPTS - 1:
                        continue
                    else:
                        logger.error(f"Download failed for {setup_page_url} after {MAX_ATTEMPTS} attempts due to site error.")
                        return False
                except TimeoutException:
                    return True

            except Exception as e:
                logger.error(f"Could not trigger download for {setup_page_url} on attempt {attempt + 1}: {e}")
                if attempt < MAX_ATTEMPTS - 1:
                    time.sleep(2) # Wait a moment before retrying
                else:
                    return False
        return False

    def _wait_for_new_zip_file(self, files_before: set, setup_page_url: str) -> Optional[Path]:
        """Waits for a new .zip file to appear in the download directory."""
        download_dir = Path(self.download_path)
        try:
            end_time = time.time() + 60  # Wait 60 seconds
            while time.time() < end_time:
                if self.skip_event and self.skip_event.is_set():
                    logger.warning(f"Skipping download for {setup_page_url} due to user request.")
                    return None

                files_after = set(download_dir.glob('*.zip'))
                new_files = files_after - files_before
                if new_files:
                    latest_zip_file = max(new_files, key=lambda f: f.stat().st_mtime)
                    time.sleep(2) # Wait for file to be fully written
                    logger.info(f"Identified new download: {latest_zip_file.name}")
                    return latest_zip_file
                time.sleep(0.5)

            raise TimeoutException(f"Download did not appear in '{download_dir}' after 60s for setup from {setup_page_url}")

        except (TimeoutException, FileNotFoundError) as e:
            logger.error(f"Error while waiting for download: {e}")
            return None

    def _organize_setup_files(self, zip_file: Path, setup_page_url: str) -> Optional[SetupInfo]:
        """Unzips and organizes the setup files into the correct directory structure."""
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                    zip_ref.extractall(temp_path)
                
                sto_files = list(temp_path.rglob('*.sto'))
                if not sto_files:
                     raise Exception(f"No .sto setup files found in the zip: {zip_file.name}")

                first_sto_file = sto_files[0]
                relative_sto_path = first_sto_file.relative_to(temp_path)
                
                if len(relative_sto_path.parts) < 3:
                    potential_car_dirs = [d for d in temp_path.rglob('*') if d.is_dir() and any(sd.is_dir() for sd in d.iterdir())]
                    if not potential_car_dirs:
                        raise Exception(f"Could not determine car/track folder structure in {zip_file.name}")
                    base_dir = potential_car_dirs[0]
                    relative_sto_path = first_sto_file.relative_to(base_dir)

                car_name_raw = relative_sto_path.parts[0]
                track_name_raw = relative_sto_path.parts[1]
                
                setup_source_dir = temp_path / relative_sto_path.parent
                race_setup = next((s for s in sto_files if '_sR' in s.name), sto_files[0])
                setup_package_name = race_setup.stem

                sanitized_car = sanitize_filename(car_name_raw)
                sanitized_track = sanitize_filename(track_name_raw)
                sanitized_package = sanitize_filename(setup_package_name)

                dest_path = Path(self.download_path) / sanitized_car
                if self.garage61_folder:
                    dest_path = dest_path / self.garage61_folder
                final_dir = dest_path / sanitized_track / sanitized_package

                if final_dir.exists():
                    logger.info(f"'{final_dir.relative_to(Path(self.download_path))}' already exists. Replacing.")
                    shutil.rmtree(final_dir)
                final_dir.mkdir(parents=True)

                for item in setup_source_dir.iterdir():
                    shutil.move(str(item), str(final_dir))
            
            car_name_display = car_name_raw.replace('-', ' ')
            track_name_display = track_name_raw.replace('-', ' ')
            name = f"{car_name_display} - {track_name_display}"

            logger.info(f"Unzipped and organized '{name}' into '{final_dir.relative_to(Path(self.download_path))}'")
            zip_file.unlink()

            return SetupInfo(name=name, track=track_name_display, car=car_name_display, download_url=setup_page_url)

        except Exception as e:
            logger.error(f"Error organizing file for setup from {setup_page_url}: {e}", exc_info=True)
            if zip_file and zip_file.exists():
                logger.warning(f"Failed to organize {zip_file.name}. The zip file has been kept.")
            return None

    def _download_and_organize_one_setup(self, setup_page_url: str) -> Optional[SetupInfo]:
        """
        Handles the download and file organization for a single setup.
        """
        download_dir = Path(self.download_path)
        files_before = set(download_dir.glob('*.zip'))

        # Step 1: Trigger the download in the browser.
        if not self._trigger_download(setup_page_url):
            return None

        # Step 2: Wait for the new .zip file to appear.
        latest_zip_file = self._wait_for_new_zip_file(files_before, setup_page_url)
        if not latest_zip_file:
            return None # Download timed out or was skipped.

        # Step 3: Unzip and organize the files.
        return self._organize_setup_files(latest_zip_file, setup_page_url)