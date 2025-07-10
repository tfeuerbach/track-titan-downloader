"""
Handles the core business logic for the TrackTitan Downloader,
separating it from the GUI.
"""

import logging
import os
from pathlib import Path
import threading
from typing import Optional

from .auth import TrackTitanAuth
from .scraper import SetupScraper
from .utils import create_directories
from . import constants

class DownloaderLogic:
    """
    Manages the application's core workflow: authentication, scraping,
    and file organization.
    """
    def __init__(self, config, stop_event: threading.Event, skip_event: threading.Event, progress_queue):
        self.config = config
        self.stop_event = stop_event
        self.skip_event = skip_event
        self.progress_queue = progress_queue
        self.auth_session = None

    def _run_scraper(self, driver, setup_page, download_path, garage61_folder: Optional[str] = None):
        """Initializes and runs the SetupScraper."""
        scraper = SetupScraper(
            session=driver,
            setup_page=setup_page,
            delay=1.0,
            download_path=download_path,
            progress_queue=self.progress_queue,
            stop_event=self.stop_event,
            skip_event=self.skip_event,
            garage61_folder=garage61_folder
        )
        
        logging.info("Scraping and downloading setup listings...")
        setups = scraper.get_setup_listings()
        
        if self.stop_event.is_set():
            logging.warning("Download process stopped by user.")
        elif not setups:
            logging.warning("No new active setups found!")
        else:
            logging.info(f"Process complete! {len(setups)} setups downloaded successfully.")

    def run_download_flow(self, garage61_folder: Optional[str] = None):
        """Handles the standard email/password authentication and download workflow."""
        try:
            email = self.config.get('email')
            password = self.config.get('password')
            download_path = self.config.get('download_path')
            
            if not all([email, password, download_path]):
                logging.error("Email, password, and download folder cannot be empty.")
                return

            setup_page = os.getenv('TRACK_TITAN_SETUP_PAGE', constants.SETUP_PAGE_URL)
            login_url = os.getenv('TRACK_TITAN_LOGIN_URL', constants.LOGIN_URL)

            create_directories(Path(download_path))

            logging.info("Starting Track Titan setup downloader...")
            self.auth_session = TrackTitanAuth(
                email=email,
                password=password,
                login_url=login_url,
                headless=self.config.get('headless', True),
                download_path=download_path
            )
        
            logging.info("Authenticating with Track Titan...")
            driver = self.auth_session.authenticate()
            if not driver:
                logging.error("Authentication failed! Check credentials and network.")
                return
            
            logging.info("Authentication successful!")
            self._run_scraper(driver, setup_page, download_path, garage61_folder)
        
        finally:
            if self.auth_session:
                self.auth_session.close()

    def run_discord_login_flow(self, garage61_folder: Optional[str] = None):
        """Handles the user-assisted Discord login, then scraping."""
        try:
            download_path = self.config.get('download_path')
            if not download_path:
                logging.error("Download folder cannot be empty.")
                return

            setup_page = os.getenv('TRACK_TITAN_SETUP_PAGE', constants.SETUP_PAGE_URL)
            login_url = os.getenv('TRACK_TITAN_LOGIN_URL', constants.LOGIN_URL)

            create_directories(Path(download_path))

            logging.info("Initializing browser for manual Discord login...")
            self.auth_session = TrackTitanAuth(
                email="", password="",
                login_url=login_url,
                download_path=download_path
            )

            driver = self.auth_session.init_browser_for_manual_login()
            if not driver:
                logging.error("Failed to open browser for manual login.")
                return
            
            logging.info("Browser opened. Please complete the login process...")
            
            is_logged_in = self.auth_session.wait_for_successful_login(success_url_part='/dashboard')
            
            if not is_logged_in:
                logging.error("Login was not completed successfully.")
                return

            logging.info("Manual login successful! Starting scraper...")
            # Signal to the GUI to switch to an indeterminate progress bar
            self.progress_queue.put({'indeterminate': True, 'label': "Scanning for setups..."})
            
            self._run_scraper(driver, setup_page, download_path, garage61_folder)
        
        finally:
            if self.auth_session:
                self.auth_session.close() 