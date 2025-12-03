# 4chan Media Scraper

![Python](https://img.shields.io/badge/python-3.7%2B-blue.svg?style=for-the-badge&logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-windows%20%7C%20linux%20%7C%20macos-lightgrey.svg?style=for-the-badge&logo=windows&logoColor=black)
![License](https://img.shields.io/badge/license-MIT-green.svg?style=for-the-badge)
![Version](https://img.shields.io/badge/version-1.0.0-purple?style=for-the-badge)

A sophisticated, asynchronous media scraper for 4chan threads. It features a modern native GUI, high-speed concurrent downloading, and a robust preview system that allows you to inspect full-resolution images before saving them.

## Features

* **Modern GUI**: Built with `tkinter` for a native look and feel on any operating system.
* **Asynchronous Downloading**: Powered by `aiohttp` for high-speed, non-blocking downloads.
* **Thumbnail Grid**: Visual grid layout to view all media in a thread before downloading.
* **Full-Res Previews**: **Right-click** any thumbnail to inspect the full-resolution image in a dedicated window.
* **Smart Selection**: Click to select specific images or use "Select All" for bulk actions.
* **Clipboard Integration**: Right-click the URL bar to paste, or enable **"Auto-load"** to load threads immediately upon pasting.
* **Directory Control**: Choose to organize downloads into thread-specific subfolders or dump them all into one location.
* **Progress Tracking**: Real-time visual progress bar and status updates.

## Prerequisites

* **Python 3.7+**: Ensure Python is installed and added to your system PATH.
* **OS**: Windows is recommended for the included batch launcher, but the script runs perfectly on Linux and macOS.

## Installation

1.  **Clone or Download** this repository.
2.  **Install Dependencies**:
    * **Windows (Easy)**: Just run `run_scraper.bat`. It handles everything.
    * **Manual**: Open a terminal and run `pip install -r requirements.txt`.

## Usage

### Starting the App

Double-click the **`run_scraper.bat`** file.
* It will automatically check for and install missing libraries (`aiohttp`, `Pillow`).
* It will launch the main application interface.

### Downloading Media

1.  **Copy URL**: Copy a thread URL (e.g., `https://boards.4chan.org/g/thread/123456`).
2.  **Paste**: Paste it into the **Thread URL** box.
    * *Tip: Right-click the text box to paste, or use Ctrl+V.*
3.  **Load**: Click **Load Thread** (or use Auto-load).
4.  **Select**: Wait for thumbnails to populate.
    * **Left-click** images to select them (Green border = Selected).
    * **Right-click** images to open a large, high-res preview.
5.  **Download**: Click **Download Selected** to save them to your chosen folder.

## Disclaimer

This tool is provided for educational purposes only. The developers are not affiliated with 4chan. Please respect the copyright and privacy of content creators and adhere to the website's terms of service.

## License

[MIT License](LICENSE)
