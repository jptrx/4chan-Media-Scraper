@echo off
setlocal
title 4chan Media Scraper Launcher v1.2.0

:: Ensure we are running from the script's directory
cd /d "%~dp0"

echo ========================================================
echo      4chan Media Scraper v1.2.0 - GUI Edition
echo ========================================================

:: 1. Check for Python
echo [INFO] Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Python is not found! 
    echo Please install Python 3.7+ from https://www.python.org/
    echo.
    pause
    exit /b
)

:: 2. Upgrade PIP
echo [INFO] Updating pip...
python -m pip install --upgrade pip >nul 2>&1

:: 3. Clean up old dependencies (if present)
echo [INFO] Cleaning up old libraries...
python -m pip uninstall -y tkvideoplayer av opencv-python >nul 2>&1

:: 4. Install Dependencies
echo [INFO] Verifying dependencies...
python -m pip install aiohttp Pillow ttkbootstrap python-vlc --disable-pip-version-check
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to install dependencies. 
    echo Please check your internet connection.
    echo.
    pause
    exit /b
)

:: 5. Run the GUI
echo [OK] Launching Application...
echo.
python chan_scraper.py

:: 6. Error Handling
if %errorlevel% neq 0 (
    echo.
    echo ========================================================
    echo [ERROR] The application crashed!
    echo See the error message above for details.
    echo ========================================================
    pause
)