import tkinter as tk
from tkinter import ttk
import os
from typing import Optional

try:
    import sv_ttk
except ImportError:
    sv_ttk = None

class Garage61Dialog(tk.Toplevel):
    """
    A dialog window to prompt the user about using a Garage 61 folder.
    """
    _CANCELLED = object()  # Sentinel value for cancellation

    def __init__(self, parent, g61_folders, icon_path: Optional[str] = None):
        super().__init__(parent)
        self.transient(parent)
        self.title("Garage 61 Option")
        self.parent = parent
        self.result = None  # This will store the chosen folder name or None

        # Basic styling from parent
        self.BG_COLOR = parent.BG_COLOR
        self.FRAME_COLOR = parent.FRAME_COLOR
        self.TEXT_COLOR = parent.TEXT_COLOR
        self.ACCENT_COLOR = parent.ACCENT_COLOR
        self.font_family = parent.font_family

        self.configure(background=self.BG_COLOR)
        
        # Set icon if provided and valid
        if icon_path:
            try:
                self.iconbitmap(icon_path)
            except tk.TclError:
                # Silently ignore if the icon can't be set
                pass

        # Inherit styles
        style = ttk.Style(self)
        style.configure('TFrame', background=self.BG_COLOR)
        style.configure('TLabel', background=self.BG_COLOR, foreground=self.TEXT_COLOR)
        style.configure('TButton', background=self.ACCENT_COLOR, foreground=self.TEXT_COLOR, font=(self.font_family, 10, 'bold'))
        style.map('TButton', background=[('active', '#007BE0')])

        # Ensure combobox popdown has the correct theme
        if sv_ttk:
            try:
                sv_ttk_path = os.path.dirname(sv_ttk.__file__)
                tcl_file_path = os.path.join(sv_ttk_path, "sv.tcl")
                self.tk.call("source", tcl_file_path)
                
                if self.parent.tk.call("ttk::style", "theme", "use") == "sv-dark":
                    self.tk.call("set_theme", "dark")
                else:
                    self.tk.call("set_theme", "light")
            except (AttributeError, tk.TclError):
                # Silently fail if theming isn't possible for any reason
                pass
        
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.create_widgets(g61_folders)
        
        self.update_idletasks()
        
        # Center the dialog on the parent window
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        dialog_width = self.winfo_width()
        dialog_height = self.winfo_height()
        
        center_x = parent_x + (parent_width - dialog_width) // 2
        center_y = parent_y + (parent_height - dialog_height) // 2
        self.geometry(f"+{center_x}+{center_y}")

        self.grab_set() # Make modal

    def create_widgets(self, g61_folders):
        """Creates and lays out the widgets for the dialog."""
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.columnconfigure(0, weight=1)

        header_label = ttk.Label(main_frame, text="Garage 61 Folder Detected", font=(self.font_family, 12, 'bold'))
        header_label.grid(row=0, column=0, columnspan=2, pady=(0, 10), sticky='w')

        info_text = (
            "This will create a folder with the chosen name inside each car's setup directory "
            "(e.g., 'ferrari296gt3/Garage 61 - My Team/').\n\n"
            "Select an existing folder, type a new name, or choose 'Do not use' to disable."
        )
        info_label = ttk.Label(main_frame, text=info_text, wraplength=460)
        info_label.grid(row=1, column=0, columnspan=2, pady=(0, 20), sticky='w')

        self.combo_var = tk.StringVar()
        
        # Options for the combobox
        options = ["(Do not use Garage 61 folder)"] + g61_folders
        
        self.g61_combobox = ttk.Combobox(main_frame, textvariable=self.combo_var, values=options, width=50)
        self.g61_combobox.set(options[0]) # Default to not using it
        self.g61_combobox.grid(row=2, column=0, columnspan=2, sticky='ew', pady=(0, 20))

        # --- Buttons ---
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, columnspan=2, sticky='e')

        self.ok_button = ttk.Button(button_frame, text="OK", command=self._on_ok)
        self.ok_button.pack(side=tk.LEFT, padx=(0, 10))

        self.cancel_button = ttk.Button(button_frame, text="Cancel", command=self._on_cancel)
        self.cancel_button.pack(side=tk.LEFT)

    def _on_ok(self):
        """Handles the OK button click."""
        choice = self.combo_var.get()
        if choice and choice != "(Do not use Garage 61 folder)":
            self.result = choice.strip()
        else:
            self.result = None
        self.destroy()

    def _on_cancel(self):
        """Handles the Cancel button click or window close."""
        self.result = self._CANCELLED
        self.destroy()

    def show(self):
        """Shows the dialog and waits for it to close, then returns the result."""
        self.wait_window(self)
        return self.result 