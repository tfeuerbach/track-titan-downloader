"""
Centralized constants for the application.
This includes URLs, and selectors that are subject to change if the
TrackTitan website is updated.
"""

# --- URLs ---
BASE_URL = "https://app.tracktitan.io"
LOGIN_URL = f"{BASE_URL}/login"
SETUP_PAGE_URL = f"{BASE_URL}/setups"

# --- Selectors for Authentication (auth.py) ---
# Using a dictionary to group related selectors for clarity
AUTH_SELECTORS = {
    "popup_close_button": (
        "//div[contains(@class, 'Modal_ModalContent')]/button[.//*[local-name()='svg']] | "
        "//button[@aria-label='Close' or @aria-label='close'] | "
        "//button[normalize-space()='X' or normalize-space()='×'] | "
        "//button[contains(., 'Accept') or contains(., 'Agree') or contains(., 'Dismiss') or contains(., 'Got it')]"
    ),
    "email_fields": ['input[type="email"]', 'input[name="email"]', '#email'],
    "password_fields": ['input[type="password"]', 'input[name="password"]', '#password'],
    "login_buttons": {
        "css": [
            'button[type="submit"]',
            '.login-button',
            '#login-button'
        ],
        "xpath": [
            "//button[contains(., 'Login')]",
            "//button[contains(., 'Sign In')]",
            "//input[@type='submit']"
        ]
    }
}

# --- Selectors for Scraping (scraper.py) ---
SCRAPER_SELECTORS = {
    "active_section_span": "span.text-green-500",
    "inactive_section_header": "//div[contains(@class, 'text-2xl') and contains(., '(Inactive)')]",
    "paid_bundle_section_text": "HYMO iRacing Bundles",
    "download_latest_button": "//button[contains(text(), 'Download Latest Version')]",
    "download_manually_button": "//button[contains(text(), 'Download Manually')]",
    "download_error_notification": "//div[contains(text(), 'There was an issue downloading this setup')]"
} 