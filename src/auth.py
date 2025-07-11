"""
Handles Selenium-based browser authentication for TrackTitan.
"""

import logging
import time
import os
from pathlib import Path
import threading
from typing import Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException

from . import constants

class TrackTitanAuth:
    """Manages the Selenium browser session for TrackTitan login."""
    
    def __init__(self, email: str, password: str, login_url: str, 
                 headless: bool = True, download_path: Optional[str] = None):
        self.email = email
        self.password = password
        self.login_url = login_url
        self.headless = headless
        self.download_path = download_path
        self.driver: Optional[webdriver.Chrome] = None
        self.chrome_options: Options = self._configure_chrome_options()
    
    def _configure_chrome_options(self) -> Options:
        """Configures and returns Chrome options for Selenium."""
        chrome_options = Options()

        # Suppress console logs from Chrome/ChromeDriver
        chrome_options.add_argument('--log-level=3')
        # This combination is most effective at suppressing unwanted messages
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])

        # General browser settings
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        chrome_options.add_argument(f"user-agent={user_agent}")

        # Configure download path
        download_dir_str = self.download_path or os.getenv('DOWNLOAD_PATH')
        # Fallback to a sensible default if no path is provided
        default_download_dir = Path.home() / "Documents" / "iRacing" / "setups"

        download_path = Path(download_dir_str) if download_dir_str else default_download_dir

        try:
            download_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logging.warning(f"Could not create specified download directory '{download_path}': {e}. Defaulting to '{default_download_dir}'")
            download_path = default_download_dir
            download_path.mkdir(parents=True, exist_ok=True)

        logging.info(f"Setting browser download directory to: {download_path}")
        prefs = {
            "download.default_directory": str(download_path.resolve()),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True
        }
        chrome_options.add_experimental_option("prefs", prefs)
        return chrome_options

    def _get_driver(self, use_headless: bool) -> Optional[webdriver.Chrome]:
        """Initializes and returns a WebDriver instance with the correct settings."""
        if use_headless and "--headless=new" not in self.chrome_options.arguments:
             self.chrome_options.add_argument("--headless=new")
        elif not use_headless and any("--headless" in arg for arg in self.chrome_options.arguments):
             self.chrome_options.arguments = [arg for arg in self.chrome_options.arguments if not arg.startswith("--headless")]
        
        try:
            # Service object to disable console logging from chromedriver.exe
            service_args = ['--log-level=OFF']
            service = Service(service_args=service_args)
            driver = webdriver.Chrome(service=service, options=self.chrome_options)
            return driver
        except WebDriverException as e:
            logging.error(f"Failed to initialize browser. Ensure Chrome is installed and chromedriver is accessible. Error: {e}")
            return None

    def init_browser_for_manual_login(self):
        """Initializes a visible browser instance for the user to log in manually."""
        logging.info("Initializing browser for manual login...")
        self.driver = self._get_driver(use_headless=False)
        if self.driver:
            self.driver.get(self.login_url)
        return self.driver
    
    def authenticate(self) -> Optional[webdriver.Chrome]:
        """Initializes WebDriver, logs in automatically, and returns the authenticated driver."""
        logging.info("Initializing browser for automatic login...")
        self.driver = self._get_driver(use_headless=self.headless)
        if not self.driver:
            return None

        self.driver.get(self.login_url)
        return self._perform_login_flow()

    def _perform_login_flow(self) -> Optional[webdriver.Chrome]:
        """Handles the actual login steps after the browser is initialized."""
        if not self.driver:
            return None
        try:
            wait = WebDriverWait(self.driver, 10)
            
            # --- Email Field ---
            email_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email']")))
            email_field.clear()
            email_field.send_keys(self.email)
            
            # --- Password Field ---
            password_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
            password_field.clear()
            password_field.send_keys(self.password)
            
            # --- Login Button ---
            login_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Log in')]")))
            login_button.click()
            
            # Wait for redirect and check for dashboard element
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Dashboard')] | //*[contains(text(), 'dashboard')]"))
            )
            logging.info("Authentication successful!")
            return self.driver
                
        except TimeoutException:
            logging.error("Authentication failed. A login element was not found or the page timed out.")
            self.close()
            return None
        except Exception as e:
            logging.error(f"An unexpected error occurred during login: {e}")
            self.close()
            return None
    
    def wait_for_successful_login(self, success_url_part: str, stop_event: threading.Event) -> bool:
        """Waits for the user to complete login, checking for a URL change."""
        if not self.driver:
            return False
        logging.info("Waiting for user to complete manual login in the browser...")
        wait_time_seconds = 120  # 2 minutes
        start_time = time.time()
        
        while time.time() - start_time < wait_time_seconds:
            if stop_event.is_set():
                logging.warning("Stop event received while waiting for manual login. Aborting.")
                return False
            try:
                if success_url_part in self.driver.current_url:
                    logging.info("Successful login detected by URL change.")
                    time.sleep(2) # Allow page to fully load
                    return True
            except WebDriverException:
                logging.warning("Browser window was closed by the user.")
                return False
            
            time.sleep(1) # Poll every second
        
        logging.error("Timed out waiting for successful login.")
        return False
    
    def close(self):
        """Closes the Selenium WebDriver session if it exists."""
        if self.driver:
            self.driver.quit()
            self.driver = None