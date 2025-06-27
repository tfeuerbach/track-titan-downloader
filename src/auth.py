"""
Handles Selenium-based browser authentication for TrackTitan.
"""

import logging
import time
from typing import Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import os
from pathlib import Path

logger = logging.getLogger(__name__)

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
    
    def authenticate(self) -> Optional[webdriver.Chrome]:
        """Performs authentication and returns the webdriver instance."""
        return self._authenticate_with_selenium()
    
    def _authenticate_with_selenium(self) -> Optional[webdriver.Chrome]:
        """Logs into TrackTitan using a Selenium WebDriver."""
        logger.info("Attempting Selenium-based authentication...")
        
        try:
            chrome_options = Options()
            if self.headless:
                chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
            
            chrome_options.add_argument('--disable-web-security')
            chrome_options.add_argument('--allow-running-insecure-content')
            chrome_options.add_argument('--disable-features=VizDisplayCompositor')
            
            download_dir_str = self.download_path or os.getenv('DOWNLOAD_PATH')
            default_download_dir = Path('~/Downloads').expanduser()

            if not download_dir_str:
                logger.warning("DOWNLOAD_PATH environment variable not set. Defaulting to ~/Downloads.")
                download_path = default_download_dir
            else:
                download_path = Path(download_dir_str).expanduser().resolve()

            try:
                download_path.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                logger.error(f"Permission denied to create specified download directory: {download_path}")
                logger.warning(f"Falling back to default download directory: {default_download_dir}")
                download_path = default_download_dir
                try:
                    download_path.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    raise Exception(f"Could not create fallback download directory at {download_path}. Please check your permissions.") from e

            logger.info(f"Setting browser download directory to: {download_path}")
            
            prefs = {
                "download.default_directory": str(download_path),
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True,
                "plugins.always_open_pdf_externally": True,
                "profile.default_content_setting_values.automatic_downloads": 1
            }
            chrome_options.add_experimental_option("prefs", prefs)
            
            service = Service()
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            
            self.driver.get(self.login_url)
            time.sleep(2)
            
            wait = WebDriverWait(self.driver, 10)
            
            email_selectors = ['input[type="email"]', 'input[name="email"]', '#email']
            email_field = None
            for selector in email_selectors:
                try:
                    email_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    break
                except:
                    continue
            
            if not email_field:
                raise Exception("Could not find email field")
            
            email_field.clear()
            email_field.send_keys(self.email)
            
            password_selectors = ['input[type="password"]', 'input[name="password"]', '#password']
            password_field = None
            for selector in password_selectors:
                try:
                    password_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    break
                except:
                    continue
            
            if not password_field:
                raise Exception("Could not find password field")
            
            password_field.clear()
            password_field.send_keys(self.password)
            
            login_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:contains("Login")',
                'button:contains("Sign In")',
                '.login-button',
                '#login-button'
            ]
            
            login_button = None
            for selector in login_selectors:
                try:
                    login_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                    break
                except:
                    continue
            
            if not login_button:
                # Fallback: try to find any button and click it
                buttons = self.driver.find_elements(By.TAG_NAME, 'button')
                if buttons:
                    login_button = buttons[0]
                else:
                    raise Exception("Could not find login button")
            
            login_button.click()
            
            # Wait for redirect
            time.sleep(3)
            
            if self._is_authenticated_selenium():
                logger.info("Selenium-based authentication successful!")
                return self.driver
            else:
                logger.error("Selenium-based authentication failed!")
                return None
                
        except Exception as e:
            logger.error(f"Selenium-based authentication failed: {e}")
            if self.driver:
                self.driver.quit()
            return None
    
    def _is_authenticated_selenium(self) -> bool:
        """Verifies authentication status by checking for common dashboard elements."""
        if not self.driver:
            return False
        try:
            page_source = self.driver.page_source.lower()
            auth_indicators = [
                'dashboard',
                'logout',
                'profile',
                'account',
                'welcome'
            ]
            
            return any(indicator in page_source for indicator in auth_indicators)
        except:
            return False
    
    def close(self):
        """Closes the Selenium WebDriver session."""
        if self.driver:
            self.driver.quit()