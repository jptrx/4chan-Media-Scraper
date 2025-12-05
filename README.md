# 4chan Media Scraper

![Python](https://img.shields.io/badge/python-3.7%2B-blue.svg?style=for-the-badge&logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-windows%20%7C%20linux%20%7C%20macos-lightgrey.svg?style=for-the-badge&logo=windows&logoColor=black)
![License](https://img.shields.io/badge/license-MIT-green.svg?style=for-the-badge)
![Version](https://img.shields.io/badge/version-1.2.0-purple?style=for-the-badge)

A sophisticated, asynchronous media scraper for 4chan threads. Version 1.2.0 introduces a native VLC-based video player, automatic updates, and persistent user settings.

## Features

* **Modern GUI**: Built with `ttkbootstrap` for a clean, flat, modern aesthetic.
* **Native Video Player (VLC)**: Embeds the **VLC Media Player** engine directly into the app for high-performance playback of WebM and MP4 files with full audio support.
* **GIF Support**: Full animated preview support for GIF files.
* **Auto-Updater**: Automatically checks for new releases on startup (configurable) and can self-update both the Script and Executable versions.
* **Persistent Settings**: Remembers your download path, auto-load preference, and folder structure settings between sessions.
* **Asynchronous Downloading**: Powered by `aiohttp` for high-speed, non-blocking downloads.
* **Smart Selection**:
    * **Visual Grid**: View thumbnails of all media.
    * **Right-Click**: Open full-resolution preview.
    * **Left-Click**: Select/Deselect for download.
* **Clipboard Integration**: Right-click the URL bar to paste, or enable **"Auto-load"** to load threads immediately.
* **Quick Navigation**: "Open Thread in Browser" option to quickly view the original thread.

## Prerequisites

* **OS**: Windows 10/11 Recommended.
* **VLC Media Player**: Required for the in-app video preview to function (audio/video). [Download VLC here](https://www.videolan.org/).
* **Python 3.7+**: (Only if running from source).

## Installation

### Option 1: Windows Installer (Recommended)
Download `4chan_Media_Scraper_Setup_v1.2.0.exe` from the Releases page.
* Installs the application to your system (Program Files).
* Creates a **Start Menu Program Group** and Desktop shortcut.
* Includes a clean uninstaller.

### Option 2: Portable (Standalone)
Download `4ChanScraper.exe`.
* No installation required.
* Runs immediately (Great for USB drives).

### Option 3: Run from Source
1.  Clone the repository:
    ```bash
    git clone [https://github.com/jptrx/4chan-Media-Scraper.git](https://github.com/jptrx/4chan-Media-Scraper.git)
    ```
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
    *Note: If on Windows, run `run_scraper.bat` to handle dependencies automatically.*
3.  Run the app:
    ```bash
    python chan_scraper.py
    ```

## Usage

1.  **Copy URL**: Copy a thread URL (e.g., `https://boards.4chan.org/g/thread/123456`).
2.  **Paste**: Right-click the **Thread URL** box to paste.
3.  **Preview**:
    * **Images/GIFs**: Right-click to view.
    * **Videos**: Right-click to play with sound (requires VLC).
4.  **Download**: Click **Download Selected** to save them to your chosen folder.

### Menu Options
* **File > Open Thread in Browser**: Opens the current thread in your default web browser.
* **Help > Check for Updates**: Manually check for new versions.
* **Help > Check on Startup**: Toggle whether the app automatically checks for updates when launched.

## Troubleshooting

* **"VLC Media Player not found"**: Ensure you have the standard 64-bit VLC Media Player installed on your PC.
* **Antivirus Warnings**: If the standalone `.exe` is flagged, this is a generic "False Positive" common with unsigned open-source software. You can safely whitelist it or run the Python source code directly if you prefer.

## Disclaimer

This tool is provided for educational purposes only. The developers are not affiliated with 4chan. Please respect the copyright and privacy of content creators and adhere to the website's terms of service.

## License

[MIT License](LICENSE)
