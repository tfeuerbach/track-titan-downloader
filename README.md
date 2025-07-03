# TrackTitan Setup Downloader

A GUI application to download the latest "Active" HYMO setups for the week off of TrackTitan.io all at once. The Track Titan desktop app only downloads setups for a given car as you join a race with one. While, this is generally a non-issue for 90% of users, I like to get 100% of what I pay for when I'm subscribing to a service like this. For that reason, I created this so that I didn't need to manually download every setup or join a session for every car in that season/week.

TrackTitan doesn't provide any sort of API so this tool leverages Selenium to mock user interaction with a headless browser. An option to view the browser and what its doing is present.

## Installation & Usage

This application is a GUI tool and can be run from source or as an executible on both Windows and Linux/macOS.

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

Downloads are organized into your chosen folder by car, then track, and finally by the setup package name. For example, if you choose `Documents/iRacing/setups` as your download folder, setups will be placed like this:
```
Documents/iRacing/setups/
└── ferrari296gt3/
    └── daytonaroad/
        └── HYMO_IMSA_25S3_F296_Daytona_Road/
            ├── setup_file_1.sto
            └── setup_file_2.rpy
```

## Notes

- This tool scrapes the TrackTitan website. Changes to the website's structure may break the tool.
- The browser window can be shown (by unchecking the box) to help debug login issues.