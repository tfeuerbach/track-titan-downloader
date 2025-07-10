# Track Titan Downloader - Test Suite

This directory contains the automated test suite for the Track Titan Downloader application.

## Running the Tests

This project uses `tox` to run the test suite against multiple Python versions (3.8 and 3.11), which mirrors the setup used in the Continuous Integration (CI) pipeline. This is the recommended way to run tests to ensure compatibility.

You must have both Python 3.8 and Python 3.11 installed and available in your system's PATH for `tox` to run successfully.

1.  **Install `tox`:**
    ```bash
    pip install tox
    ```
2.  **Run the Test Suite:**
    ```bash
    tox
    ```
This command will create isolated virtual environments for each Python version, install the necessary dependencies, and run `pytest`.

## Test Suite Breakdown

This test suite is organized by the module being tested. It also contains a `fixtures` directory.

-   **`fixtures/`**: This directory contains static data used as inputs for tests, such as the `setups_page.html` file, which simulates the Track Titan setups page. This allows for testing parsing logic without making live web requests.

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