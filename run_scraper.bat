@echo off
setlocal
title 4chan Media Scraper Launcher

:: Ensure we are running from the script's directory
cd /d "%~dp0"

echo ========================================================
echo        4chan Media Scraper - GUI Edition
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

:: 2. Install Dependencies (Added Pillow)
echo [INFO] Verifying dependencies (aiohttp, Pillow)...
pip install aiohttp Pillow --disable-pip-version-check
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to install dependencies. 
    echo Please check your internet connection.
    echo.
    pause
    exit /b
)

:: 3. Run the GUI
echo [OK] Launching Application...
python chan_scraper.py

exit