# TrackTitan Setup Downloader

A GUI application to download the latest "Active" HYMO setups for the week off of TrackTitan.io all at once. The Track Titan desktop app only downloads setups for a given car as you join a race with one. While, this is generally a non-issue for 90% of users, I like to get 100% of what I pay for when I'm subscribing to a service like this. For that reason, I created this so that I didn't need to manually download every setup or join a session for every car in that season/week.

TrackTitan doesn't provide any sort of API so this tool leverages Selenium to mock user interaction with a headless browser. An option to view the browser and what its doing is present.

## Disclaimer

**This tool is for personal, non-commercial use only.**

In accordance with the [TrackTitan Terms and Conditions](https://www.tracktitan.io/terms-and-conditions), you are explicitly prohibited from sharing, distributing, or using for commercial purposes any car setups downloaded from their service. This tool is intended solely for downloading all the setups up front/in bulk for a week.

## Features

- Simple GUI for easy operation.
- Login with your TrackTitan credentials or via Discord.

---

## Usage

This section provides instructions for the recommended method for most users.

### Installation & Usage

1.  **Download the Executable:** Go to the [**project's Releases page**](https://github.com/tfeuerbach/track-titan-downloader/releases) and download the latest `TrackTitan-Downloader.exe` file.
2.  **Run the App:** Double-click `TrackTitan-Downloader.exe` to start the application.

### File Organization

Downloads are organized into your chosen folder by car, then track, and finally by the setup package name. For example, if you choose `Documents/iRacing/setups` as your download folder, setups will be placed like this:
```
Documents/iRacing/setups/
└── ferrari296gt3/
    └── daytonaroad/
        └── HYMO_IMSA_25S3_F296_Daytona_Road/
            ├── setup_file_1.sto
            └── setup_file_2.rpy
```

### Notes

- This tool scrapes the TrackTitan website. Changes to the website's structure may break the tool.
- The browser window can be shown (by unchecking the box) to help debug login issues.

---

## For Developers & Contributors

These instructions are for developers who want to run the application from the source code or contribute to the project.

### 1. Setup

**A. Clone the Repository**
```bash
git clone https://github.com/tfeuerbach/track-titan-downloader.git
cd track-titan-downloader
```

**B. Install Dependencies**

-   **On Windows:** Double-click `install.bat`. This script will install Python packages and create a `.env` file from the `env.example` template.
-   **On Linux / macOS:** Open a terminal and run `bash install.sh`.

After running the installer, open the new `.env` file and enter your TrackTitan credentials.

### 2. Run the Application
```bash
python tracktitan_downloader.py
```

### 3. Running Tests
This project uses `tox` to run tests against multiple Python versions, mirroring the CI setup. To run the tests locally, you must have Python 3.8 and 3.11 installed.

1.  **Install `tox`:**
    ```bash
    pip install tox
    ```
2.  **Run Tests:**
    ```bash
    tox
    ```