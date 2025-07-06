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
                 garage61_folder: Optional[str] = None):
        self.session = session
        self.setup_page = setup_page
        self.delay = delay
        self.download_path = download_path
        self.progress_queue = progress_queue
        self.stop_event = stop_event
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
            inactive_header_xpath = "//div[contains(@class, 'text-2xl') and contains(., '(Inactive)')]"
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

                # If no inactive headers yet or we decided to continue, fall through to the height check below.
                
                # Fall through to normal height check if we haven't stopped yet.

                new_height = self.session.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
            
            logger.info("Finished scrolling.")

            # Find all 'Active' sections and collect setup links from each.
            setup_page_urls = []
            try:
                active_spans = self.session.find_elements(By.CSS_SELECTOR, "span.text-green-500")
                if not active_spans:
                     logger.warning("No '(Active)' sections found on the page.")
                     return []
                
                logger.info(f"Found {len(active_spans)} '(Active)' sections. Collecting links from each.")

                for active_span in active_spans:
                    # Navigate from the '(Active)' span to the div containing the setup cards.
                    header_div = active_span.find_element(By.XPATH, "./parent::div")
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
                logger.error(f"Could not find or process the '(Active)' setups sections after scrolling. Error: {e}. Saved page HTML for debugging.")
                return []
            
            if not setup_page_urls:
                logger.warning("No setup links found within any 'Active' sections.")
                return []
        
            logger.info(f"Found a total of {len(setup_page_urls)} setup links across all 'Active' sections.")
            
            setups = []
            total_setups = len(setup_page_urls)
            self._report_progress(max_val=total_setups, value=0)

            for i, url in enumerate(setup_page_urls):
                if self.stop_event and self.stop_event.is_set():
                    logger.info("Stop event received, halting setup downloads.")
                    break

                if not url:
                    self._report_progress(value=i + 1)
                    continue
                
                setup_info = self._download_and_organize_one_setup(url)
                if setup_info:
                    setups.append(setup_info)
                
                self._report_progress(value=i + 1)
                time.sleep(self.delay)

            logger.info(f"Successfully downloaded and organized {len(setups)} setups from the active section.")
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
    
    def _download_and_organize_one_setup(self, setup_page_url: str) -> Optional[SetupInfo]:
        """
        Handles the download and file organization for a single setup.
        """
        download_dir = Path(self.download_path)

        # Trigger the download
        files_before = set(download_dir.glob('*.zip'))

        try:
            self.session.get(setup_page_url)
            wait = WebDriverWait(self.session, 10)
            
            download_button = wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(text(), 'Download Latest Version')]")
            ))
            self.session.execute_script("arguments[0].click();", download_button)
            
            try:
                manual_download_wait = WebDriverWait(self.session, 10)
                manual_download_button = manual_download_wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(text(), 'Download Manually')]")
                ))
                self.session.execute_script("arguments[0].click();", manual_download_button)
            except (NoSuchElementException, TimeoutException):
                logger.debug("Did not find 'Download Manually' button, assuming direct download.")
                pass

        except Exception as e:
            logger.error(f"Could not trigger download for setup at {setup_page_url}: {e}")
            return None

        # Wait for the new file to appear in the downloads folder.
        latest_zip_file = None
        try:
            end_time = time.time() + 60  # Wait 60 seconds
            new_file_appeared = False
            while time.time() < end_time:
                files_after = set(download_dir.glob('*.zip'))
                new_files = files_after - files_before
                if new_files:
                    # Handle cases where multiple zips appear
                    latest_zip_file = max(new_files, key=lambda f: f.stat().st_mtime)
                    new_file_appeared = True
                    break
                time.sleep(0.5)

            if not new_file_appeared:
                raise TimeoutException(f"Download did not appear in '{download_dir}' after 60s for setup from {setup_page_url}")

            # Wait for file to be written to disk.
            time.sleep(2)
            logger.info(f"Identified new download: {latest_zip_file.name}")

        except (TimeoutException, FileNotFoundError) as e:
            logger.error(f"Error while waiting for download: {e}")
            return None
            
        # Unzip and organize the file based on its internal structure.
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                with zipfile.ZipFile(latest_zip_file, 'r') as zip_ref:
                    zip_ref.extractall(temp_path)
                
                # Find any .sto file to determine the directory structure.
                sto_files = list(temp_path.rglob('*.sto'))
                if not sto_files:
                     raise Exception(f"No .sto setup files found in the zip: {latest_zip_file.name}")

                # The path inside the zip is expected to be 'car-name/track-name/setup.sto'
                first_sto_file = sto_files[0]
                relative_sto_path = first_sto_file.relative_to(temp_path)
                
                if len(relative_sto_path.parts) < 3:
                    # Sometimes the zip might have an extra top-level folder
                    # 'setups/car-name/track-name/setup.sto'
                    # Find the car/track folders by searching for a directory that contains a directory.
                    
                    potential_car_dirs = [d for d in temp_path.rglob('*') if d.is_dir() and any(sd.is_dir() for sd in d.iterdir())]
                    if not potential_car_dirs:
                        raise Exception(f"Could not determine car/track folder structure in {latest_zip_file.name}")

                    base_dir = potential_car_dirs[0]
                    relative_sto_path = first_sto_file.relative_to(base_dir)

                car_name_raw = relative_sto_path.parts[0]
                track_name_raw = relative_sto_path.parts[1]
                
                # The source directory for all setup files is temp_path/car/track
                setup_source_dir = temp_path / relative_sto_path.parent

                # Grab a setup name from one of the .sto files (e.g., the race setup)
                race_setup = next((s for s in sto_files if '_sR' in s.name), sto_files[0])
                setup_package_name = race_setup.stem

                # Sanitize names for folder paths.
                sanitized_car = sanitize_filename(car_name_raw)
                sanitized_track = sanitize_filename(track_name_raw)
                sanitized_package = sanitize_filename(setup_package_name)

                # Construct the final destination directory: download_dir/car/track/package/
                dest_path = download_dir / sanitized_car
                if self.garage61_folder:
                    dest_path = dest_path / self.garage61_folder
                final_dir = dest_path / sanitized_track / sanitized_package

                if final_dir.exists():
                    logger.info(f"'{final_dir.relative_to(download_dir)}' already exists. Replacing.")
                    shutil.rmtree(final_dir)
                final_dir.mkdir(parents=True)

                # Move all contents from the unzipped source directory.
                for item in setup_source_dir.iterdir():
                    shutil.move(str(item), str(final_dir))
            
            car_name_display = car_name_raw.replace('-', ' ').title()
            track_name_display = track_name_raw.replace('-', ' ').title()
            name = f"{car_name_display} - {track_name_display}"

            logger.info(f"Unzipped and organized '{name}' into '{final_dir.relative_to(download_dir)}'")
            latest_zip_file.unlink() # Clean up

            return SetupInfo(name=name, track=track_name_display, car=car_name_display, download_url=setup_page_url)

        except Exception as e:
            logger.error(f"Error organizing file for setup from {setup_page_url}: {e}", exc_info=True)
            if latest_zip_file and latest_zip_file.exists():
                # Don't delete the zip on failure to organize, user might want it.
                logger.warning(f"Failed to organize {latest_zip_file.name}. The zip file has been kept.")
            return None