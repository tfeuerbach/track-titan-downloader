# TrackTitan Setup Downloader

A GUI application to download the latest "Active" HYMO setups for the week off of TrackTitan.io.

## Features

- Modern, easy-to-use graphical interface.
- Authenticates with your TrackTitan account.
- Downloads all of the current week's active setups for iRacing.
- Automatically organizes downloads by car into your selected folder.
- Live progress bar with a setup counter and percentage.
- Detailed logging view with color-coded message levels.
- Ability to gracefully stop the download process.
- Simple, one-click installers for Windows and Linux/macOS.

## Installation & Usage

This application is a GUI tool and can be run from source on both Windows and Linux/macOS.

### Windows

1.  **Run the Installer:** Double-click on `install.bat`. This script will automatically install the necessary Python packages and create a `.env` file for your configuration.
2.  **Edit Configuration:** Open the new `.env` file in a text editor and enter your TrackTitan email and password.
3.  **Run the App:** Double-click `tracktitan_downloader.py` to start the application.

### Linux / MacOS

1.  **Run the Installer:** Open a terminal in the project directory and run the command:
```bash
    bash install.sh
```
This will install dependencies and create your `.env` configuration file.

2.  **Edit Configuration:** Open the new `.env` file in a text editor and enter your TrackTitan credentials.
3.  **Run the App:** In your terminal, run the command:
```bash
    python3 tracktitan_downloader.py
```

## File Organization

Downloads are organized into your chosen folder by car name. For example, if you choose `Documents/iRacing/setups` as your download folder, setups will be placed like this:
```
Documents/iRacing/setups/
├── ferrari296gt3/
│   ├── setup_file_1.sto
│   └── setup_file_2.sto
├── porsche992gt3r/
│   ├── setup_file_3.sto
│   └── setup_file_4.sto
└── mercedesamggt3evo/
```

## Notes

- This tool scrapes the TrackTitan website. Changes to the website's structure may break the tool.
- Always ensure you have the correct login credentials and download path set in the application.
- The browser window can be shown (by unchecking the box) to help debug login issues. 