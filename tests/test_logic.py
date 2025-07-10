"""
Tests for the main application logic.
"""
import pytest
from queue import Queue
import threading
from src.logic import DownloaderLogic

# A dummy config that can be used for tests
@pytest.fixture
def test_config():
    return {
        'email': 'test@example.com',
        'password': 'password123',
        'download_path': '/fake/path',
        'headless': True
    }

@pytest.fixture
def mock_dependencies(mocker):
    """Mocks all external dependencies for DownloaderLogic."""
    # Mock the classes themselves
    mock_auth_class = mocker.patch('src.logic.TrackTitanAuth')
    mock_scraper_class = mocker.patch('src.logic.SetupScraper')
    
    # Mock the instances that will be created
    mock_auth_instance = mock_auth_class.return_value
    mock_scraper_instance = mock_scraper_class.return_value
    
    # Mock the return values of key methods
    mock_auth_instance.authenticate.return_value = 'mock_driver'
    mock_scraper_instance.get_setup_listings.return_value = ['setup1', 'setup2']
    
    mocker.patch('src.logic.create_directories')

    return {
        "auth_class": mock_auth_class,
        "scraper_class": mock_scraper_class,
        "auth_instance": mock_auth_instance,
        "scraper_instance": mock_scraper_instance
    }


def test_run_download_flow_success(test_config, mock_dependencies, mocker):
    """
    Tests the successful execution of the standard download flow.
    Verifies that authentication and scraping are called correctly.
    """
    # --- Arrange ---
    logic = DownloaderLogic(
        config=test_config,
        stop_event=threading.Event(),
        skip_event=threading.Event(),
        progress_queue=Queue()
    )
    
    # --- Act ---
    logic.run_download_flow()
    
    # --- Assert ---
    # Verify that TrackTitanAuth was initialized with the correct config
    mock_dependencies['auth_class'].assert_called_once_with(
        email=test_config['email'],
        password=test_config['password'],
        login_url=mocker.ANY,  # We don't need to check the default URL
        headless=test_config['headless'],
        download_path=test_config['download_path']
    )
    
    # Verify that the authentication process was started
    auth_instance = mock_dependencies['auth_instance']
    auth_instance.authenticate.assert_called_once()
    
    # Verify that the scraper was initialized with the authenticated driver
    mock_dependencies['scraper_class'].assert_called_once_with(
        session='mock_driver',
        setup_page=mocker.ANY,
        delay=mocker.ANY,
        download_path=test_config['download_path'],
        progress_queue=logic.progress_queue,
        stop_event=logic.stop_event,
        skip_event=logic.skip_event,
        garage61_folder=None
    )
    
    # Verify that the scraping process was started
    scraper_instance = mock_dependencies['scraper_instance']
    scraper_instance.get_setup_listings.assert_called_once()
    
    # Verify that the browser session was closed
    auth_instance.close.assert_called_once()


def test_run_download_flow_auth_failure(test_config, mock_dependencies):
    """
    Tests the download flow when authentication fails.
    Verifies that the scraper is never called if auth returns None.
    """
    # --- Arrange ---
    # Override the default mock to simulate auth failure
    mock_dependencies['auth_instance'].authenticate.return_value = None
    
    logic = DownloaderLogic(
        config=test_config,
        stop_event=threading.Event(),
        skip_event=threading.Event(),
        progress_queue=Queue()
    )
    
    # --- Act ---
    logic.run_download_flow()
    
    # --- Assert ---
    # Verify that authentication was attempted
    mock_dependencies['auth_instance'].authenticate.assert_called_once()
    
    # CRITICAL: Verify the scraper was never initialized or run
    mock_dependencies['scraper_class'].assert_not_called()
    mock_dependencies['scraper_instance'].get_setup_listings.assert_not_called()
    
    # Verify that the session is still closed even on failure
    mock_dependencies['auth_instance'].close.assert_called_once()


def test_run_discord_login_flow_success(test_config, mock_dependencies, mocker):
    """
    Tests the successful execution of the Discord login flow.
    Verifies that the scraper is called after the user successfully logs in.
    """
    # --- Arrange ---
    mock_dependencies['auth_instance'].wait_for_successful_login.return_value = True
    
    logic = DownloaderLogic(
        config=test_config,
        stop_event=threading.Event(),
        skip_event=threading.Event(),
        progress_queue=Queue()
    )
    
    # --- Act ---
    logic.run_discord_login_flow()
    
    # --- Assert ---
    # Verify that the manual login browser was initialized
    mock_dependencies['auth_instance'].init_browser_for_manual_login.assert_called_once()
    
    # Verify that the app waited for the user to log in
    mock_dependencies['auth_instance'].wait_for_successful_login.assert_called_once_with(success_url_part='/dashboard')
    
    # Verify that the scraper was started
    mock_dependencies['scraper_class'].assert_called_once()
    mock_dependencies['scraper_instance'].get_setup_listings.assert_called_once()
    
    # Verify the session was closed
    mock_dependencies['auth_instance'].close.assert_called_once()


def test_run_discord_login_flow_login_timeout(test_config, mock_dependencies):
    """
    Tests that the scraper is not run if the user fails to log in
    via the Discord flow in time.
    """
    # --- Arrange ---
    # Simulate the user never logging in successfully
    mock_dependencies['auth_instance'].wait_for_successful_login.return_value = False
    
    logic = DownloaderLogic(
        config=test_config,
        stop_event=threading.Event(),
        skip_event=threading.Event(),
        progress_queue=Queue()
    )
    
    # --- Act ---
    logic.run_discord_login_flow()
    
    # --- Assert ---
    # Verify that the app attempted to wait for login
    mock_dependencies['auth_instance'].wait_for_successful_login.assert_called_once()
    
    # CRITICAL: Verify the scraper was never run
    mock_dependencies['scraper_class'].assert_not_called()
    mock_dependencies['scraper_instance'].get_setup_listings.assert_not_called()
    
    # Verify the session was still closed
    mock_dependencies['auth_instance'].close.assert_called_once() 