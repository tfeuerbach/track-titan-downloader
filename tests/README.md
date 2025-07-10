# TrackTitan Downloader - Test Suite

This directory contains the automated test suite for the TrackTitan Downloader application.

## Running the Tests

To execute the test suite, install the required dependencies and run `pytest` from the project's root directory.

```bash
# Install dependencies
pip install -r requirements.txt

# Run all tests with verbose output
pytest -v
```

## Test Suite Breakdown

### `tests/test_logic.py`

-   **`test_run_download_flow_success`**: Mocks a successful authentication and asserts that the `SetupScraper` is initialized and its `get_setup_listings` method is called.
-   **`test_run_download_flow_auth_failure`**: Mocks a failed authentication and asserts that the `SetupScraper` is never initialized.
-   **`test_run_discord_login_flow_success`**: Mocks a successful manual Discord login by simulating a URL change and ensures the scraper is called.
-   **`test_run_discord_login_flow_login_timeout`**: Simulates a user failing to log in via Discord within the time limit and ensures the scraper is not called.

### `tests/test_scraper.py`

-   **`test_get_setup_listings_from_html`**: Uses a local, static HTML file (`tests/fixtures/setups_page.html`) to verify that the scraper's parsing logic correctly identifies and extracts setup links from "(Active)" sections while ignoring "(Inactive)" and paid bundle sections. This test validates the core CSS/XPath selectors.
-   **`test_organize_setup_files_standard`**: Verifies that a setup `.zip` file is correctly unzipped and its contents are moved to the standard `car/track/package` directory structure.
-   **`test_organize_setup_files_with_garage61_folder`**: Verifies that when a "Garage 61" folder name is provided, the setup files are moved to the correct nested directory (`car/Garage 61 - My Team/track/package`).

### `tests/test_utils.py`

-   **`test_sanitize_filename`**: A parameterized test validating the `sanitize_filename` function against various inputs.
    -   **Test Case 1**: Verifies that illegal characters (`<>:"/\\|?*`) are replaced with underscores.
    -   **Test Case 2**: Ensures leading/trailing whitespace and dots are stripped.
    -   **Test Case 3**: Confirms that an already-valid filename remains unchanged.
    -   **Test Case 4**: Checks for graceful handling of an empty string input.
    -   **Test Case 5**: Ensures a string containing only illegal characters is fully converted to underscores.
    -   **Test Case 6**: Confirms that filenames exceeding the length limit are truncated.
    -   **Test Case 7**: Verifies that Unicode characters are preserved.
    -   **Test Case 8**: Checks the sanitization of a realistic string with a mix of valid and invalid characters.
-   **`test_scan_for_garage61_folders`**: Validates the `scan_for_garage61_folders` function. It creates a temporary directory structure simulating car and setup folders, then asserts that the function correctly identifies and returns the unique names of directories that start with "Garage 61". 