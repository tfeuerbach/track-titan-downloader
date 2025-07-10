@echo off
REM Track Titan Downloader Installation Script for Windows

echo Track Titan Downloader - Installation Script for Windows
echo ======================================================

REM Check if Python is installed
python --version >nul 2>nul
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Python is not installed or not found in your system's PATH.
    echo Please install Python 3.8 or higher and ensure it's added to your PATH.
    echo.
    pause
    exit /b 1
)

echo.
echo Found Python installation.
echo.

echo Installing required Python packages...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to install one or more packages. Please check your connection and try again.
    echo.
    pause
    exit /b 1
)
echo.
echo Packages installed successfully.
echo.

REM Check if .env file exists and create it if not
if not exist .env (
    echo.
    echo '.env' file not found.
    if exist env.example (
        echo Creating .env file from the template...
        copy env.example .env
        echo.
        echo '.env' file created successfully.
        echo [IMPORTANT] Please open the .env file and enter your Track Titan credentials.
    ) else (
        echo.
        echo [ERROR] 'env.example' not found. Cannot create .env file.
        echo Please create a .env file manually with your credentials.
        echo.
        pause
        exit /b 1
    )
) else (
    echo.
    echo '.env' file already exists. Skipping creation.
)

echo.
echo =================================
echo      Installation complete!
echo =================================
echo.
echo Next Steps:
echo 1. Open the '.env' file in a text editor and add your Track Titan credentials.
echo 2. Run the application by double-clicking 'tracktitan_downloader.py' or by running this command in your terminal:
echo    python tracktitan_downloader.py
echo.
pause