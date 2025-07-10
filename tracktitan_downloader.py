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
from tkinter import ttk, filedialog
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

try:
    import sv_ttk
except ImportError:
    sv_ttk = None

from src.auth import TrackTitanAuth
from src.scraper import SetupScraper
from src.utils import create_directories, scan_for_garage61_folders
from src.__version__ import __version__ as APP_VERSION
from src.g61_dialog import Garage61Dialog
from src.logic import DownloaderLogic

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
        self.withdraw()
        
        self.APP_VERSION = APP_VERSION
        self.title(f"Track Titan Setup Downloader - {self.APP_VERSION}")
        self.geometry("800x850")

        # Set application icon for window and Windows taskbar
        if sys.platform.startswith('win'):
            try:
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
                self.icon_path = icon_path # Store for later use
            except tk.TclError:
                logging.warning("Could not load application icon at 'src/assets/icon.ico'. Using default.")
        
        # --- Member variables ---
        self.email_var = tk.StringVar(value=os.getenv('TRACK_TITAN_EMAIL', ''))
        self.password_var = tk.StringVar(value=os.getenv('TRACK_TITAN_PASSWORD', ''))
        self.icon_path = None
        
        default_path = Path(os.path.expanduser("~")) / "Documents" / "iRacing" / "setups"
        if not default_path.exists():
            default_path = Path.cwd() / "downloads"
        self.download_path_var = tk.StringVar(value=os.getenv('DOWNLOAD_PATH', str(default_path)))
        self.headless_var = tk.BooleanVar(value=True)
        
        # --- Image Resources ---
        try:
            discord_logo_path = resource_path("src/assets/discord_logo.png")
            self.discord_logo_image = tk.PhotoImage(file=discord_logo_path)
        except tk.TclError:
            self.discord_logo_image = None
            logging.warning("Could not load discord_logo.png. Button will be text-only.")

        self.thread = None
        self.stop_event = threading.Event()
        self.skip_event = threading.Event()
        self.progress_max = 0
        self.progress_label_var = tk.StringVar(value="")

        # --- Page Frames ---
        self.downloader_page = None
        self.about_page = None
        self.about_button = None

        # --- Queues for Thread Communication ---
        self.log_queue = Queue()
        self.progress_queue = Queue()
        
        # Track resize state to avoid heavy UI updates while the user drags the sash
        self._is_resizing = False
        # Accumulate log records so we can insert them in batches for better performance
        self._pending_log_records = []
        self._garage61_folder_to_use = None
        
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

        self.BG_COLOR = "#1c1c1e" 
        self.FRAME_COLOR = "#2c2c2e"
        self.ACCENT_COLOR = "#0A84FF"
        self.DISCORD_COLOR = "#5865F2"
        self.TEXT_COLOR = "#ffffff"
        self.SUBTLE_TEXT_COLOR = "#a1a1a6"
        self.ERROR_COLOR = "#ff453a"
        self.WARNING_COLOR = "#ff9f0a"
        self.SUCCESS_COLOR = "#32d74b"
        
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
        
        # Add style for the PanedWindow sash
        style.configure('TPanedwindow', background=self.BG_COLOR)
        style.configure('TPanedwindow.Sash', sashthickness=6, background=self.FRAME_COLOR, borderwidth=0)
        style.map('TPanedwindow.Sash', background=[('active', self.ACCENT_COLOR)])
        
        style.configure('TEntry', fieldbackground=self.FRAME_COLOR, foreground=self.TEXT_COLOR, borderwidth=0, insertcolor=self.TEXT_COLOR)
        style.map('TEntry', fieldbackground=[('focus', '#3a3a3c')]) # Highlight on focus
        
        style.configure('TButton', background=self.ACCENT_COLOR, foreground=self.TEXT_COLOR, font=(font_family, 11, 'bold'), borderwidth=0, padding=10)
        style.map('TButton', background=[('active', '#007BE0')]) # Darker shade on hover/press
        
        style.configure('Discord.TButton', background=self.DISCORD_COLOR, foreground=self.TEXT_COLOR, font=(font_family, 11, 'bold'), borderwidth=0, padding=10)
        style.map('Discord.TButton', background=[('active', '#4752C4')]) # Darker shade on hover/press

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
            rowheight=30)
        style.map("Treeview", background=[('selected', self.ACCENT_COLOR)])
        style.configure("Treeview.Heading",
            background=self.BG_COLOR,
            foreground=self.SUBTLE_TEXT_COLOR,
            font=(font_family, 9, 'bold'),
            borderwidth=0)
        style.map("Treeview.Heading", background=[('active', self.BG_COLOR)])
        
        # Style the progress bar
        style.configure("slick.Horizontal.TProgressbar", 
                        troughcolor=self.BG_COLOR,
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
                ('disabled', self.BG_COLOR),
                ('active', self.ACCENT_COLOR)
            ],
            background=[
                ('disabled', self.BG_COLOR),
                ('active', self.BG_COLOR)
            ]
        )
        
        style.configure("Footer.Hyperlink.TLabel", font=footer_font_underlined, background=self.BG_COLOR, foreground=self.ACCENT_COLOR)
        style.map("Footer.Hyperlink.TLabel", foreground=[('active', self.SUCCESS_COLOR)])

        # About page styles
        style.configure("About.Header.TLabel", font=(font_family, 18, 'bold'), background=self.BG_COLOR)
        style.configure("About.TLabel", font=(font_family, 11), background=self.BG_COLOR)
        style.configure("Disclaimer.TLabel",
            font=(font_family, 10, 'italic'),
            foreground=self.SUBTLE_TEXT_COLOR,
            background=self.BG_COLOR)

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

        # Create a PanedWindow to allow resizing of the log section
        paned_window = ttk.PanedWindow(main_frame, orient=tk.VERTICAL)
        paned_window.pack(fill=tk.BOTH, expand=True)

        # Attempt to style the sash; fall back silently if the option isn't available
        try:
            paned_window.configure(sashrelief=tk.RAISED)
        except tk.TclError:
            pass  # Ignore if the underlying Tk implementation does not recognise this option

        # Detect when the user starts or stops dragging the sash so we can pause heavy UI updates
        paned_window.bind("<ButtonPress-1>", lambda e: setattr(self, "_is_resizing", True))
        paned_window.bind("<ButtonRelease-1>", lambda e: setattr(self, "_is_resizing", False))

        # A frame to hold the non-resizable top section
        top_section_frame = ttk.Frame(paned_window)
        paned_window.add(top_section_frame, weight=0)
        
        # --- Input Fields ---
        input_frame = ttk.LabelFrame(top_section_frame, text="CONFIGURATION", padding="20")
        input_frame.pack(fill=tk.X, expand=False, pady=(0, 25))
        input_frame.columnconfigure(1, weight=1)

        pad_y = 8
        ttk.Label(input_frame, text="Track Titan Email:").grid(row=0, column=0, sticky=tk.W, pady=pad_y)
        self.email_entry = ttk.Entry(input_frame, textvariable=self.email_var, width=50)
        self.email_entry.grid(row=0, column=1, columnspan=2, sticky=tk.EW, padx=10, pady=pad_y)

        ttk.Label(input_frame, text="Track Titan Password:").grid(row=1, column=0, sticky=tk.W, pady=pad_y)
        self.password_entry = ttk.Entry(input_frame, textvariable=self.password_var, show="*", width=50)
        self.password_entry.grid(row=1, column=1, columnspan=2, sticky=tk.EW, padx=10, pady=pad_y)
        
        # --- Separator and Discord Button ---
        separator_frame = ttk.Frame(input_frame)
        separator_frame.grid(row=2, column=0, columnspan=3, sticky=tk.EW, pady=10)
        ttk.Separator(separator_frame).pack(fill=tk.X, expand=True, side=tk.LEFT, padx=10)
        ttk.Label(separator_frame, text="OR", foreground=self.SUBTLE_TEXT_COLOR).pack(side=tk.LEFT)
        ttk.Separator(separator_frame).pack(fill=tk.X, expand=True, side=tk.LEFT, padx=10)

        self.discord_button = ttk.Button(
            input_frame,
            text="  Login with Discord",
            image=self.discord_logo_image,
            compound=tk.LEFT,
            style="Discord.TButton",
            command=self.start_discord_login
        )
        self.discord_button.grid(row=3, column=0, columnspan=3, sticky=tk.EW, padx=10, pady=pad_y)

        ttk.Label(input_frame, text="Download Folder:").grid(row=4, column=0, sticky=tk.W, pady=pad_y)
        self.path_entry = ttk.Entry(input_frame, textvariable=self.download_path_var, width=50)
        self.path_entry.grid(row=4, column=1, sticky=tk.EW, padx=10, pady=pad_y)
        self.browse_button = ttk.Button(input_frame, text="Browse...", command=self.browse_folder)
        self.browse_button.grid(row=4, column=2, sticky=tk.E, padx=(0, 10), pady=pad_y)

        self.headless_var.set(True)
        self.show_browser_check = ttk.Checkbutton(
            input_frame,
            text="Show Browser (uncheck for debug or if login fails)",
            variable=self.headless_var,
            onvalue=False,
            offvalue=True
        )
        self.show_browser_check.grid(row=5, column=0, columnspan=3, sticky=tk.W, pady=(15, 5))

        # --- Control & Progress ---
        control_frame = ttk.Frame(top_section_frame)
        control_frame.pack(fill=tk.X, expand=False, pady=(0, 20))
        control_frame.columnconfigure(3, weight=1) # Make progress bar expand

        self.start_button = ttk.Button(control_frame, text="Start Download", command=self.start_download)
        self.start_button.grid(row=0, column=0, padx=(0, 5))
        
        self.stop_button = ttk.Button(control_frame, text="Stop", command=self.stop_download)
        self.stop_button.grid(row=0, column=1, padx=(0, 5))
        self.stop_button.grid_remove() # Hide it initially

        self.skip_button = ttk.Button(control_frame, text="Skip", command=self.skip_setup)
        self.skip_button.grid(row=0, column=2, padx=(0, 15))
        self.skip_button.grid_remove()

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(control_frame, variable=self.progress_var, maximum=100, style="slick.Horizontal.TProgressbar")
        self.progress_bar.grid(row=0, column=3, sticky=tk.EW)
        
        self.progress_label = ttk.Label(control_frame, textvariable=self.progress_label_var, font=(self.font_family, 10, 'italic'), anchor='e')
        self.progress_label.grid(row=0, column=4, sticky=tk.E, padx=(10, 0))

        # Hide progress elements initially
        self.progress_bar.grid_remove()
        self.progress_label.grid_remove()

        # --- Log Viewer ---
        log_frame = ttk.LabelFrame(paned_window, text="LOG", padding="20")
        paned_window.add(log_frame, weight=1) # Add to paned window as the bottom, resizable pane
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log_tree = ttk.Treeview(log_frame, columns=('Time', 'Level', 'Message'), show='headings')
        self.log_tree.heading('Time', text='Time')
        self.log_tree.heading('Level', text='Level')
        self.log_tree.heading('Message', text='Message')
        self.log_tree.column('Time', width=120, stretch=tk.NO, anchor='w')
        self.log_tree.column('Level', width=100, stretch=tk.NO, anchor='w')
        self.log_tree.column('Message', width=400)
        
        vsb = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_tree.yview)
        vsb.grid(row=0, column=1, sticky='ns')
        self.log_tree.configure(yscrollcommand=vsb.set)
        
        self.log_tree.grid(row=0, column=0, sticky='nsew')

        # Adjust the 'Message' column width when the widget is resized.
        self.log_tree.bind('<Configure>', self._adjust_log_columns)

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

        header = ttk.Label(center_frame, text="Track Titan Downloader", style="About.Header.TLabel")
        header.pack(pady=(0, 5))
        
        version_label = ttk.Label(center_frame, text=f"Version {self.APP_VERSION}", foreground=self.SUBTLE_TEXT_COLOR, style="About.TLabel")
        version_label.pack(pady=(0, 25))

        # Disclaimer
        disclaimer_frame = ttk.Frame(center_frame)
        disclaimer_frame.pack(fill=tk.X, expand=True, pady=(10, 20))

        disclaimer_text = (
            "This tool is for personal, non-commercial use, intended as a means to download all setups in bulk. "
            "In accordance with the Track Titan Terms and Conditions, you are prohibited from sharing or "
            "distributing any downloaded setups.\n\n"
        )
        disclaimer_label = ttk.Label(disclaimer_frame, text=disclaimer_text, wraplength=450, justify=tk.CENTER, style="Disclaimer.TLabel")
        disclaimer_label.pack(fill=tk.X)

        # Credits
        ttk.Label(center_frame, text="Created by Thomas Feuerbach", style="About.TLabel").pack(pady=(10, 2))

        # Links
        links_frame = ttk.Frame(center_frame)
        links_frame.pack(pady=(2, 20))
        self.create_hyperlink(links_frame, "GitHub Repo", "https://github.com/tfeuerbach/track-titan-downloader")
        self.create_hyperlink(links_frame, "Website", "https://tfeuerbach.dev")

        # Back button
        back_button = ttk.Button(center_frame, text="< Back to Downloader", command=lambda: self.show_page(self.downloader_page))
        back_button.pack(pady=20)

    def show_page(self, page_to_show):
        """Raises the specified frame and manages footer button visibility."""
        if page_to_show == self.about_page:
            self.about_button.pack_forget()
        else:
            # Ensure the button is not already visible to avoid re-packing it.
            if not self.about_button.winfo_ismapped():
                self.about_button.pack(side=tk.LEFT, padx=20)
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
        logging.getLogger().addHandler(log_handler)
        logging.getLogger().setLevel(logging.INFO)

    def process_log_queue(self):
        """Polls the log queue and displays new records in the log view."""
        # Drain the queue first
        try:
            while True:
                record = self.log_queue.get_nowait()
                self._pending_log_records.append(record)
        except Empty:
            pass  # Nothing left

        # Insert batched records only if we are not currently dragging the sash
        if not self._is_resizing and self._pending_log_records:
            for record in self._pending_log_records:
                log_time = time.strftime('%H:%M:%S', time.localtime(record.created))
                level = record.levelname
                msg = record.getMessage()

                tag = level
                if "Process complete!" in msg or "Authentication successful!" in msg:
                    tag = "SUCCESS"

                self.log_tree.insert('', tk.END, values=(f'  {log_time}', f'  {level}', f'  {msg}'), tags=(tag,))
            # Auto-scroll once per batch instead of per line
            self.log_tree.yview_moveto(1.0)
            self._pending_log_records.clear()

        # Re-schedule after a short delay to keep UI responsive without hogging the event loop
        self.after(150, self.process_log_queue)

    def process_progress_queue(self):
        """Polls the progress queue to update the progress bar."""
        try:
            while True:
                progress_update = self.progress_queue.get_nowait()

                # If max value, switch from indeterminate to determinate
                if 'max' in progress_update:
                    self.progress_bar.stop()
                    self.progress_bar.config(mode='determinate')
                    new_max = progress_update['max']
                    self.progress_max = new_max
                    self.progress_bar.config(maximum=new_max if new_max > 0 else 1)  # Dummy max
                    if new_max == 0:
                        self.progress_label_var.set("No new setups found.")

                if 'value' in progress_update:
                    current_val = progress_update['value']
                    self.progress_var.set(current_val)
                    # Only update the label if the max value is known
                    if self.progress_max > 0:
                        percent = (current_val / self.progress_max) * 100
                        if current_val == self.progress_max:
                            self.progress_label_var.set("Finalizing...")
                        else:
                            self.progress_label_var.set(f"{current_val}/{self.progress_max} ({percent:.0f}%)")
                
                if progress_update.get('indeterminate'):
                    self.progress_bar.config(mode='indeterminate')
                    self.progress_bar.start(10)
                    if 'label' in progress_update:
                        self.progress_label_var.set(progress_update['label'])

                if progress_update.get('reset'):
                    self.progress_var.set(0)
                    self.progress_label_var.set("")
                    self.progress_max = 0  # Reset max
                    self.progress_bar.stop()
                    self.progress_bar.config(mode='determinate')
        except Empty:
            pass

        # Re-schedule after a short delay to keep UI responsive without hogging the event loop
        self.after(150, self.process_progress_queue)

    def set_ui_state(self, is_running):
        """Toggles the state of UI controls based on download status."""
        state = 'disabled' if is_running else 'normal'
        for widget in (self.email_entry, self.password_entry, self.path_entry, self.browse_button, self.show_browser_check, self.discord_button):
            widget.config(state=state)
        
        self.start_button.config(state=state)
        
        if is_running:
            self.stop_button.grid() # Show stop button
            self.skip_button.grid() # Show skip button
            self.start_button.grid_remove() # Hide start
            self.progress_bar.grid()
            self.progress_label.grid()
        else:
            self.stop_button.grid_remove() # Hide stop
            self.skip_button.grid_remove() # Hide skip button
            self.start_button.grid() # Show start
            self.stop_button.config(state='normal') # Re-enable for next run
            self.progress_bar.grid_remove()
            self.progress_label.grid_remove()
            self.progress_bar.stop()
            self.progress_bar.config(mode='determinate')

    def start_download(self):
        """Initiates the download process in a background thread."""
        self._check_for_g61_and_start_flow(self.run_download_flow)

    def start_discord_login(self):
        """Starts the user-assisted Discord login flow."""
        self._check_for_g61_and_start_flow(self.run_discord_login_flow)

    def _check_for_g61_and_start_flow(self, target_flow):
        """Scans for G61 folders and starts the specified download flow."""
        download_path = self.download_path_var.get()
        g61_folders = scan_for_garage61_folders(download_path)

        garage61_folder_to_use = None
        if g61_folders:
            dialog = Garage61Dialog(self, g61_folders, icon_path=self.icon_path)
            result = dialog.show()
            
            if result is Garage61Dialog._CANCELLED:
                logging.info("Operation cancelled by user from Garage 61 dialog.")
                return # Abort the download/login flow

            garage61_folder_to_use = result

        self.set_ui_state(is_running=True)
        self.stop_event.clear()
        self.skip_event.clear()

        self._start_thread(target_flow, garage61_folder_to_use)

    def _start_thread(self, target_method, garage61_folder: str | None):
        """Creates a thread to run a method from the DownloaderLogic class."""
        
        def thread_wrapper():
            """The actual function that runs in the new thread."""
            try:
                config = {
                    'email': self.email_var.get(),
                    'password': self.password_var.get(),
                    'download_path': self.download_path_var.get(),
                    'headless': self.headless_var.get()
                }
                logic_instance = DownloaderLogic(config, self.stop_event, self.skip_event, self.progress_queue)
                
                target_method(logic_instance, garage61_folder=garage61_folder)

            except Exception as e:
                logging.error(f"An unexpected error occurred in the worker thread: {e}", exc_info=True)
            finally:
                # Defer UI updates to the main thread.
                self.after(0, self.set_ui_state, False)
                self.progress_queue.put({'reset': True})

        self.thread = threading.Thread(target=thread_wrapper, daemon=True)
        self.thread.start()

    def stop_download(self):
        """Sets an event to signal the download thread to terminate."""
        if self.thread and self.thread.is_alive():
            logging.warning("Stop request received. Finishing current file then stopping...")
            self.stop_event.set()
            self.stop_button.config(state='disabled') # Prevent multiple clicks
            self.progress_label_var.set("Stopping...")
    
    def skip_setup(self):
        """Sets an event to signal the download thread to skip the current setup."""
        if self.thread and self.thread.is_alive():
            logging.info("Skip request received. Moving to the next setup...")
            self.skip_event.set()

    def run_download_flow(self, garage61_folder: str | None = None):
        """Handles the core download workflow: auth, scraping, and cleanup."""
        self.progress_label_var.set("Scanning for setups...")
        self.progress_bar.config(mode='indeterminate')
        self.progress_bar.start(10)
        self._start_thread(DownloaderLogic.run_download_flow, garage61_folder)

    def run_discord_login_flow(self, garage61_folder: str | None = None):
        """Handles the user-assisted Discord login, then scraping."""
        self._start_thread(DownloaderLogic.run_discord_login_flow, garage61_folder)

    def _adjust_log_columns(self, event=None):
        """Adjusts the 'Message' column width to fill available space."""
        # Guard against firing during initial widget creation before it has a size.
        if self.log_tree.winfo_width() <= 1:
            return

        total_width = self.log_tree.winfo_width()
        
        # Get the width of the other columns.
        time_width = self.log_tree.column('Time', 'width')
        level_width = self.log_tree.column('Level', 'width')
        
        # Buffer for scrollbar and internal padding.
        scrollbar_buffer = 25
        
        # Calculate the remaining space for the 'Message' column.
        new_message_width = total_width - time_width - level_width - scrollbar_buffer
        
        min_width = 200
        if new_message_width < min_width:
            new_message_width = min_width
            
        self.log_tree.column('Message', width=new_message_width)


if __name__ == '__main__':
    app = DownloaderApp()
    app.mainloop()