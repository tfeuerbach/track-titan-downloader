#!/usr/bin/env python3
"""
A GUI for downloading simracing setups from TrackTitan.io.
"""

import os
import sys
import logging
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
from queue import Queue, Empty
import time
import webbrowser
from tkinter import font as tkfont

# Optional: python-dotenv for .env file support
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass # Silently ignore if not installed

# Optional: sv-ttk for a modern look and feel
try:
    import sv_ttk
except ImportError:
    sv_ttk = None

from src.auth import TrackTitanAuth
from src.scraper import SetupScraper
from src.utils import create_directories
from src.__version__ import __version__ as APP_VERSION

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # Not in a bundle, so use the script's directory
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

class QueueHandler(logging.Handler):
    """A logging handler that directs records to a queue."""
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put(record)

class DownloaderApp(tk.Tk):
    """Main GUI application for the TrackTitan Downloader."""
    
    def __init__(self):
        super().__init__()
        self.withdraw() # Hide window to prevent pop-in effect
        
        self.APP_VERSION = APP_VERSION
        self.title(f"TrackTitan Setup Downloader - {self.APP_VERSION}")
        self.geometry("800x750") # Increased height for footer

        # Set application icon for window and Windows taskbar
        if sys.platform.startswith('win'):
            try:
                # Set AppUserModelID to ensure the taskbar icon is correct on Windows.
                # This is a unique identifier for the application.
                import ctypes
                app_id = "Feuerbach.TrackTitanDownloader.1" 
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
            except ImportError:
                logging.warning("Could not import ctypes. Skipping taskbar icon setup.")
            except Exception as e:
                logging.warning(f"Could not set AppUserModelID: {e}")
            
            try:
                icon_path = resource_path("src/assets/icon.ico")
                self.iconbitmap(icon_path)
            except tk.TclError:
                logging.warning("Could not load application icon at 'src/assets/icon.ico'. Using default.")
        
        # --- Member variables ---
        self.email_var = tk.StringVar(value=os.getenv('TRACK_TITAN_EMAIL', ''))
        self.password_var = tk.StringVar(value=os.getenv('TRACK_TITAN_PASSWORD', ''))
        
        default_path = Path(os.path.expanduser("~")) / "Documents" / "iRacing" / "setups"
        if not default_path.exists():
            default_path = Path.cwd() / "downloads"
        self.download_path_var = tk.StringVar(value=os.getenv('DOWNLOAD_PATH', str(default_path)))
        self.headless_var = tk.BooleanVar(value=True)
        
        self.thread = None
        self.auth_session = None
        self.stop_event = threading.Event()
        self.progress_max = 0
        self.progress_label_var = tk.StringVar(value="")

        # --- Page Frames ---
        self.downloader_page = None
        self.about_page = None
        self.about_button = None

        # --- Queues for Thread Communication ---
        self.log_queue = Queue()
        self.progress_queue = Queue()
        
        # --- UI Styling ---
        self.apply_styles()

        # --- UI Layout ---
        self.create_master_layout()
        
        # --- Logging & Progress Updates ---
        self.configure_logging()
        self.process_log_queue()
        self.process_progress_queue()

        # Force layout calculations before showing
        self.update_idletasks()
        # Schedule the window to appear after a short delay to ensure a smooth launch
        self.after(20, self.deiconify)

    def apply_styles(self):
        """Configures the application's visual theme and styles."""
        if sv_ttk:
            sv_ttk.set_theme("dark")

        # A more vibrant, custom color palette
        self.BG_COLOR = "#1c1c1e" 
        self.FRAME_COLOR = "#2c2c2e"
        self.ACCENT_COLOR = "#0A84FF" # A brighter, more electric blue
        self.TEXT_COLOR = "#ffffff"
        self.SUBTLE_TEXT_COLOR = "#a1a1a6" # Brighter for better contrast
        self.ERROR_COLOR = "#ff453a"
        self.WARNING_COLOR = "#ff9f0a"
        self.SUCCESS_COLOR = "#32d74b" # A more vibrant green
        
        style = ttk.Style(self)
        
        # Configure root window
        self.configure(background=self.BG_COLOR)

        # Base widget configurations
        font_family = 'Segoe UI' if sys.platform == "win32" else 'Helvetica'
        self.font_family = font_family
        
        style.configure('TFrame', background=self.BG_COLOR)
        style.configure('TLabelframe', background=self.BG_COLOR, borderwidth=0)
        style.configure('TLabelframe.Label', background=self.BG_COLOR, foreground=self.SUBTLE_TEXT_COLOR, font=(font_family, 12, 'italic'))
        style.configure('TLabel', background=self.BG_COLOR, foreground=self.TEXT_COLOR, font=(font_family, 10))
        
        style.configure('TEntry', fieldbackground=self.FRAME_COLOR, foreground=self.TEXT_COLOR, borderwidth=0, insertcolor=self.TEXT_COLOR)
        style.map('TEntry', fieldbackground=[('focus', '#3a3a3c')]) # Highlight on focus
        
        style.configure('TButton', background=self.ACCENT_COLOR, foreground=self.TEXT_COLOR, font=(font_family, 11, 'bold'), borderwidth=0, padding=10)
        style.map('TButton', background=[('active', '#007BE0')]) # Darker shade on hover/press
        
        style.configure('TCheckbutton', background=self.BG_COLOR, foreground=self.TEXT_COLOR, font=(font_family, 10))
        style.map('TCheckbutton',
            indicatorcolor=[('selected', self.ACCENT_COLOR), ('!selected', self.FRAME_COLOR)],
            background=[('active', self.BG_COLOR)])

        # Style the Treeview for logs
        style.configure("Treeview",
            background=self.FRAME_COLOR,
            foreground=self.TEXT_COLOR,
            fieldbackground=self.FRAME_COLOR,
            borderwidth=0,
            rowheight=30) # Increased row height for breathing room
        style.map("Treeview", background=[('selected', self.ACCENT_COLOR)])
        style.configure("Treeview.Heading",
            background=self.BG_COLOR,
            foreground=self.SUBTLE_TEXT_COLOR,
            font=(font_family, 9, 'bold'),
            borderwidth=0)
        style.map("Treeview.Heading", background=[('active', self.BG_COLOR)])
        
        # Style the progress bar
        style.configure("slick.Horizontal.TProgressbar", 
                        troughcolor=self.BG_COLOR,  # Make trough invisible
                        background=self.SUCCESS_COLOR, 
                        borderwidth=0,
                        thickness=12) # Make the bar thicker

        # Footer styles
        footer_font = tkfont.Font(family=font_family, size=9)
        footer_font_underlined = tkfont.Font(family=font_family, size=9, underline=True)
        
        style.configure("Footer.TLabel", font=footer_font, background=self.BG_COLOR, foreground=self.TEXT_COLOR)
        style.configure("Footer.TButton", font=footer_font, background=self.BG_COLOR, foreground=self.TEXT_COLOR, borderwidth=0, padding=(6, 2))
        style.map("Footer.TButton", 
            foreground=[
                ('disabled', self.BG_COLOR), # Make text and background
                ('active', self.ACCENT_COLOR)
            ],
            background=[
                ('disabled', self.BG_COLOR), # invisible when disabled
                ('active', self.BG_COLOR)
            ]
        )
        
        style.configure("Footer.Hyperlink.TLabel", font=footer_font_underlined, background=self.BG_COLOR, foreground=self.ACCENT_COLOR)
        style.map("Footer.Hyperlink.TLabel", foreground=[('active', self.SUCCESS_COLOR)])

        # About page styles
        style.configure("About.Header.TLabel", font=(font_family, 18, 'bold'), background=self.BG_COLOR)
        style.configure("About.TLabel", font=(font_family, 11), background=self.BG_COLOR)

    def create_master_layout(self):
        """Creates the main window structure, including pages and the footer."""
        
        footer_frame = ttk.Frame(self)
        footer_frame.pack(side=tk.BOTTOM, fill=tk.X, expand=False, pady=(5, 10))

        self.about_button = ttk.Button(footer_frame, text="About", style="Footer.TButton", command=lambda: self.show_page(self.about_page))
        self.about_button.pack(side=tk.LEFT, padx=20)

        page_container = ttk.Frame(self)
        page_container.pack(fill=tk.BOTH, expand=True)

        self.downloader_page = ttk.Frame(page_container)
        self.about_page = ttk.Frame(page_container)

        for frame in (self.downloader_page, self.about_page):
            frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Populate the pages with widgets
        self.create_downloader_page(self.downloader_page)
        self.create_about_page(self.about_page)

        self.show_page(self.downloader_page)

    def create_downloader_page(self, parent):
        """Initializes and places all widgets for the main downloader UI."""
        main_frame = ttk.Frame(parent, padding=(25, 25, 25, 5))
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # --- Input Fields ---
        input_frame = ttk.LabelFrame(main_frame, text="CONFIGURATION", padding="20")
        input_frame.pack(fill=tk.X, expand=False, pady=(0, 25))
        input_frame.columnconfigure(1, weight=1)

        pad_y = 8
        ttk.Label(input_frame, text="TrackTitan Email:").grid(row=0, column=0, sticky=tk.W, pady=pad_y)
        self.email_entry = ttk.Entry(input_frame, textvariable=self.email_var, width=50)
        self.email_entry.grid(row=0, column=1, columnspan=2, sticky=tk.EW, padx=10, pady=pad_y)

        ttk.Label(input_frame, text="TrackTitan Password:").grid(row=1, column=0, sticky=tk.W, pady=pad_y)
        self.password_entry = ttk.Entry(input_frame, textvariable=self.password_var, show="*", width=50)
        self.password_entry.grid(row=1, column=1, columnspan=2, sticky=tk.EW, padx=10, pady=pad_y)

        ttk.Label(input_frame, text="Download Folder:").grid(row=2, column=0, sticky=tk.W, pady=pad_y)
        self.path_entry = ttk.Entry(input_frame, textvariable=self.download_path_var, width=50)
        self.path_entry.grid(row=2, column=1, sticky=tk.EW, padx=10, pady=pad_y)
        self.browse_button = ttk.Button(input_frame, text="Browse...", command=self.browse_folder)
        self.browse_button.grid(row=2, column=2, sticky=tk.E, padx=(0, 10), pady=pad_y)

        self.headless_var.set(True)
        self.show_browser_check = ttk.Checkbutton(
            input_frame,
            text="Show Browser (uncheck for debug or if login fails)",
            variable=self.headless_var,
            onvalue=False,
            offvalue=True
        )
        self.show_browser_check.grid(row=3, column=0, columnspan=3, sticky=tk.W, pady=(15, 5))

        # --- Control & Progress ---
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, expand=False, pady=(0, 20))
        control_frame.columnconfigure(2, weight=1) # Make progress bar expand

        self.start_button = ttk.Button(control_frame, text="Start Download", command=self.start_download)
        self.start_button.grid(row=0, column=0, padx=(0, 5))
        
        self.stop_button = ttk.Button(control_frame, text="Stop", command=self.stop_download)
        self.stop_button.grid(row=0, column=1, padx=(0, 15))
        self.stop_button.grid_remove() # Hide it initially

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(control_frame, variable=self.progress_var, maximum=100, style="slick.Horizontal.TProgressbar")
        self.progress_bar.grid(row=0, column=2, sticky=tk.EW)
        
        self.progress_label = ttk.Label(control_frame, textvariable=self.progress_label_var, font=(self.font_family, 10, 'italic'), anchor='e')
        self.progress_label.grid(row=0, column=3, sticky=tk.E, padx=(10, 0))

        # Hide progress elements initially
        self.progress_bar.grid_remove()
        self.progress_label.grid_remove()

        # --- Log Viewer ---
        log_frame = ttk.LabelFrame(main_frame, text="LOG", padding="20")
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_tree = ttk.Treeview(log_frame, columns=('Time', 'Level', 'Message'), show='headings')
        self.log_tree.heading('Time', text='Time')
        self.log_tree.heading('Level', text='Level')
        self.log_tree.heading('Message', text='Message')
        self.log_tree.column('Time', width=120, stretch=tk.NO, anchor='w')
        self.log_tree.column('Level', width=100, stretch=tk.NO, anchor='w')
        self.log_tree.column('Message', width=550)
        
        vsb = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_tree.yview)
        vsb.pack(side='right', fill='y')
        self.log_tree.configure(yscrollcommand=vsb.set)
        
        self.log_tree.pack(fill=tk.BOTH, expand=True)

        # Tags for coloring
        self.log_tree.tag_configure('INFO', foreground=self.TEXT_COLOR)
        self.log_tree.tag_configure('WARNING', foreground=self.WARNING_COLOR)
        self.log_tree.tag_configure('ERROR', foreground=self.ERROR_COLOR)
        self.log_tree.tag_configure('CRITICAL', foreground=self.ERROR_COLOR, font=(self.font_family, 9, 'bold'))
        self.log_tree.tag_configure('SUCCESS', foreground=self.SUCCESS_COLOR)

    def create_about_page(self, parent):
        """Populates the 'About' page with credits and links."""
        about_frame = ttk.Frame(parent, padding=40)
        about_frame.pack(fill=tk.BOTH, expand=True)
        
        center_frame = ttk.Frame(about_frame)
        center_frame.pack(expand=True)

        header = ttk.Label(center_frame, text="TrackTitan Downloader", style="About.Header.TLabel")
        header.pack(pady=(0, 5))
        
        version_label = ttk.Label(center_frame, text=f"Version {self.APP_VERSION}", foreground=self.SUBTLE_TEXT_COLOR, style="About.TLabel")
        version_label.pack(pady=(0, 25))

        # Credits
        ttk.Label(center_frame, text="Created by Thomas Feuerbach", style="About.TLabel").pack(pady=(10, 2))

        # Links
        links_frame = ttk.Frame(center_frame)
        links_frame.pack(pady=(2, 20))
        self.create_hyperlink(links_frame, "GitHub Repo", "https://github.com/your-username/track-titan-downloader")
        self.create_hyperlink(links_frame, "Website", "https://your-website.com")

        # Back button
        back_button = ttk.Button(center_frame, text="< Back to Downloader", command=lambda: self.show_page(self.downloader_page))
        back_button.pack(pady=20)

    def show_page(self, page_to_show):
        """Raises the specified frame and manages footer button visibility."""
        if page_to_show == self.about_page:
            self.about_button.config(state='disabled')
        else:
            self.about_button.config(state='normal')
        page_to_show.tkraise()

    def create_hyperlink(self, parent, text, url):
        """Creates a clickable hyperlink label."""
        link = ttk.Label(parent, text=text, cursor="hand2", style="Footer.Hyperlink.TLabel")
        link.pack(side=tk.LEFT, padx=10)
        link.bind("<Button-1>", lambda e: self.open_link(url))

    def open_link(self, url):
        """Opens a URL in the default web browser."""
        webbrowser.open_new(url)

    def browse_folder(self):
        """Opens a file dialog to choose a download directory."""
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.download_path_var.set(folder_selected)
    
    def configure_logging(self):
        """Redirects Python's logging to the GUI's log view."""
        log_handler = QueueHandler(self.log_queue)
        # We don't set a formatter, as we'll format it in the GUI
        logging.getLogger().addHandler(log_handler)
        logging.getLogger().setLevel(logging.INFO)

    def process_log_queue(self):
        """Polls the log queue and displays new records in the log view."""
        try:
            while True:
                record = self.log_queue.get_nowait()
                log_time = time.strftime('%H:%M:%S', time.localtime(record.created))
                level = record.levelname
                msg = record.getMessage()

                tag = level
                if "Process complete!" in msg or "Authentication successful!" in msg:
                    tag = "SUCCESS"

                self.log_tree.insert('', tk.END, values=(f'  {log_time}', f'  {level}', f'  {msg}'), tags=(tag,))
                self.log_tree.yview_moveto(1.0)
        except Empty:
            pass # The queue is empty
        self.after(100, self.process_log_queue)
        
    def process_progress_queue(self):
        """Polls the progress queue to update the progress bar."""
        try:
            while True:
                progress_update = self.progress_queue.get_nowait()

                # If we get a max value, we switch from indeterminate to determinate
                if 'max' in progress_update:
                    self.progress_bar.stop()
                    self.progress_bar.config(mode='determinate')
                    new_max = progress_update['max']
                    self.progress_max = new_max
                    self.progress_bar.config(maximum=new_max if new_max > 0 else 1) # Dummy max
                    if new_max == 0:
                        self.progress_label_var.set("No new setups found.")

                if 'value' in progress_update:
                    current_val = progress_update['value']
                    self.progress_var.set(current_val)
                    # Only update the label if we know the max value
                    if self.progress_max > 0:
                        percent = (current_val / self.progress_max) * 100
                        if current_val == self.progress_max:
                             self.progress_label_var.set(f"Finalizing...")
                        else:
                            self.progress_label_var.set(f"{current_val}/{self.progress_max} ({percent:.0f}%)")
                
                if progress_update.get('reset'):
                    self.progress_var.set(0)
                    self.progress_label_var.set("")
                    self.progress_max = 0 # Reset max
                    self.progress_bar.stop()
                    self.progress_bar.config(mode='determinate')
        except Empty:
            pass
        self.after(100, self.process_progress_queue)

    def set_ui_state(self, is_running):
        """Toggles the state of UI controls based on download status."""
        state = 'disabled' if is_running else 'normal'
        for widget in (self.email_entry, self.password_entry, self.path_entry, self.browse_button, self.show_browser_check):
            widget.config(state=state)
        
        self.start_button.config(state=state)
        
        if is_running:
            self.stop_button.grid() # Show stop button
            self.start_button.grid_remove() # Hide start
            self.progress_bar.grid()
            self.progress_label.grid()
        else:
            self.stop_button.grid_remove() # Hide stop
            self.start_button.grid() # Show start
            self.stop_button.config(state='normal') # Re-enable for next run
            self.progress_bar.grid_remove()
            self.progress_label.grid_remove()
            self.progress_bar.stop()
            self.progress_bar.config(mode='determinate')

    def start_download(self):
        """Initiates the download process in a background thread."""
        self.set_ui_state(is_running=True)
        self.stop_event.clear()
        self.progress_label_var.set("Scanning for setups...")
        self.progress_var.set(0)
        self.progress_bar.config(mode='indeterminate')
        self.progress_bar.start(10)
        self.thread = threading.Thread(target=self.run_download_flow, daemon=True)
        self.thread.start()

    def stop_download(self):
        """Sets an event to signal the download thread to terminate."""
        if self.thread and self.thread.is_alive():
            logging.warning("Stop request received. Finishing current file then stopping...")
            self.stop_event.set()
            self.stop_button.config(state='disabled') # Prevent multiple clicks
            self.progress_label_var.set("Stopping...")
    
    def run_download_flow(self):
        """Handles the core download workflow: auth, scraping, and cleanup."""
        try:
            email = self.email_var.get()
            password = self.password_var.get()
            download_path = self.download_path_var.get()
            
            if not all([email, password, download_path]):
                logging.error("Email, password, and download folder cannot be empty.")
                return

            setup_page = os.getenv('TRACK_TITAN_SETUP_PAGE', "https://app.tracktitan.io/setups")
            login_url = os.getenv('TRACK_TITAN_LOGIN_URL', "https://app.tracktitan.io/login")

            create_directories(Path(download_path))

            logging.info("Starting TrackTitan setup downloader...")
            self.auth_session = TrackTitanAuth(
                email=email,
                password=password,
                login_url=login_url,
                headless=self.headless_var.get(),
                download_path=download_path
            )
        
            logging.info("Authenticating with TrackTitan...")
            driver = self.auth_session.authenticate()
            if not driver:
                logging.error("Authentication failed! Check credentials and network.")
                return
            
            logging.info("Authentication successful!")
            
            scraper = SetupScraper(
                session=driver,
                setup_page=setup_page,
                delay=1.0,
                download_path=download_path,
                progress_queue=self.progress_queue,
                stop_event=self.stop_event
            )
            
            logging.info("Scraping and downloading setup listings...")
            setups = scraper.get_setup_listings()
            
            if self.stop_event.is_set():
                logging.warning("Download process stopped by user.")
            elif not setups:
                logging.warning("No new active setups found!")
            else:
                logging.info(f"Process complete! {len(setups)} setups downloaded successfully.")
        
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}", exc_info=True)
        finally:
            if self.auth_session:
                self.auth_session.close()
            # Defer UI updates to the main thread.
            self.after(0, self.set_ui_state, False)
            self.progress_queue.put({'reset': True})


if __name__ == '__main__':
    app = DownloaderApp()
    app.mainloop() 