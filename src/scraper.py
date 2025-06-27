"""
Scrapes and downloads setup files from TrackTitan.
"""

import logging
import re
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
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
                 stop_event: Optional[threading.Event] = None):
        self.session = session
        self.setup_page = setup_page
        self.delay = delay
        self.download_path = download_path
        self.progress_queue = progress_queue
        self.stop_event = stop_event
    
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

            # Scroll to the bottom of the page to ensure all lazy-loaded setups are visible.
            logger.info("Scrolling to bottom of page...")
            last_height = self.session.execute_script("return document.body.scrollHeight")
            
            while True:
                self.session.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(self.delay + 1)
                
                new_height = self.session.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
            
            logger.info("Finished scrolling.")

            try:
                # After scrolling, find the fully loaded active container.
                active_span = wait.until(EC.visibility_of_element_located(
                    (By.CSS_SELECTOR, "span.text-green-500")
                ))

                # Navigate from the '(Active)' span to the div containing the setup cards.
                header_div = active_span.find_element(By.XPATH, "./parent::div")
                active_container = header_div.find_element(By.XPATH, "./following-sibling::div")

            except Exception as e:
                page_source = self.session.page_source
                with open('debug_selenium_page.html', 'w', encoding='utf-8') as f:
                    f.write(page_source)
                logger.error(f"Could not find the '(Active)' setups section after scrolling. Error: {e}. Saved page HTML for debugging.")
                return []
            
            # Find setup links only within that active container.
            setup_links = active_container.find_elements(By.TAG_NAME, 'a')
        
            if not setup_links:
                logger.warning("No setup links found within the 'Active' section.")
                return []
        
            logger.info(f"Found {len(setup_links)} setup links in the 'Active' section.")
        
            # Get all hrefs first to prevent the page from going stale during iteration.
            setup_page_urls = [link.get_attribute('href') for link in setup_links]
            
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
            # Save page source on other exceptions too
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
        try:
            # Parse Car/Track from URL to determine destination folder
            parts = setup_page_url.strip('/').split('/')
            name_part = parts[-2]
            
            car_track_parts = name_part.split('-')
            track_keywords = ['brands', 'hatch', 'silverstone', 'zolder', 'watkins', 'glen']
            split_index = -1
            for i, part in enumerate(car_track_parts):
                if part in track_keywords:
                    split_index = i
                    break
            
            if split_index != -1:
                car = " ".join(car_track_parts[:split_index]).title()
                track = " ".join(car_track_parts[split_index:]).title().replace("E Sports", "E-Sports")
            else: # Fallback
                car = " ".join(car_track_parts[:-2]).title()
                track = " ".join(car_track_parts[-2:]).title().replace("E Sports", "E-Sports")

            name = f"{car} - {track}"
            
            # Sanitize car name for folder path, removing series suffixes.
            base_car_name = car.lower().replace(' ', '').replace('.', '')

            suffixes_to_remove = ['imsa', 'gts', 'ftsc', 'tcr']
            
            # Regex to remove any of these suffixes from the end of the string.
            pattern = f"({'|'.join(suffixes_to_remove)})*$"
            iracing_car_name = re.sub(pattern, '', base_car_name)

        except Exception as e:
            logger.warning(f"Could not parse car/track from URL {setup_page_url}: {e}")
            return None

        # Trigger the download
        download_dir = Path(self.download_path)
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
                logger.warning("Did not find the 'Download Manually' button. Assuming direct download.")
                pass

        except Exception as e:
            logger.error(f"Could not trigger download for {name} at {setup_page_url}: {e}")
            return None

        # Wait for the new file to appear in the downloads folder.
        latest_zip_file = None
        try:
            end_time = time.time() + 60  # Wait up to 60 seconds
            new_file_appeared = False
            while time.time() < end_time:
                files_after = set(download_dir.glob('*.zip'))
                if files_after - files_before:
                    new_file_appeared = True
                    break
                time.sleep(0.5)

            if not new_file_appeared:
                raise TimeoutException(f"Download did not appear in '{download_dir}' after 60s for {name}")

            # Wait for file to be fully written to disk.
            time.sleep(2)

            # Identify the newest file in the directory.
            files_after = download_dir.glob('*.zip')
            new_files = [f for f in files_after if f not in files_before]
            if not new_files:
                raise FileNotFoundError(f"Could not identify the new downloaded file for {name}.")

            latest_zip_file = max(new_files, key=lambda f: f.stat().st_mtime)
            logger.info(f"Identified new download: {latest_zip_file.name} for setup {name}")

        except (TimeoutException, FileNotFoundError) as e:
            logger.error(f"Error while waiting for download of {name}: {e}")
            return None
            
        # Unzip and organize the setup files.
        try:
            car_dir = download_dir / sanitize_filename(iracing_car_name)
            car_dir.mkdir(parents=True, exist_ok=True)

            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                with zipfile.ZipFile(latest_zip_file, 'r') as zip_ref:
                    zip_ref.extractall(temp_path)
                
                extracted_items = list(temp_path.iterdir())
                source_dir_to_move = temp_path
                if len(extracted_items) == 1 and extracted_items[0].is_dir():
                    source_dir_to_move = extracted_items[0]

                for item in source_dir_to_move.iterdir():
                    dest_path = car_dir / item.name
                    if dest_path.exists():
                        if dest_path.is_dir():
                            shutil.rmtree(dest_path)
                        else:
                            dest_path.unlink()
                    shutil.move(str(item), str(car_dir))
            
            logger.info(f"Unzipped and organized setup for '{name}' into '{car_dir.name}'")
            latest_zip_file.unlink() # Clean up zip

            return SetupInfo(name=name, track=track, car=car, download_url=setup_page_url)

        except Exception as e:
            logger.error(f"Error organizing file for {name}: {e}", exc_info=True)
            if latest_zip_file and latest_zip_file.exists():
                latest_zip_file.unlink() # Attempt to clean up failed download
            return None