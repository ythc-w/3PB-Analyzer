"""
Main GUI module, responsible for creating and managing the graphical user interface.
"""

import logging
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from threading import Thread

# Import custom modules
from analysis import save_files  # Import analysis function
from utils import get_resource_path  # Import function to get resource path
from config import (WINDOW_TITLE, WINDOW_WIDTH, WINDOW_HEIGHT,  # Import window title, width, height
                    DEFAULT_MIN_WINDOW_SIZE, DEFAULT_MAX_WINDOW_SIZE, DEFAULT_Yield_Force_Constant,  DEFAULT_Displacement_Constant,
                    ICON_PATH, LOG_FILE, LOG_LEVEL, DEFAULT_PRELOAD)  # Import icon path, log file, log level

# Initialize logging
logging.basicConfig(filename=get_resource_path(LOG_FILE), level=LOG_LEVEL,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logging.info("Application started")


class AnalysisApp:
    """Main application class"""

    def __init__(self, root):
        """
        Initializes the application.

        Args:
            root (tk.Tk): Main window instance.
        """
        self.root = root
        self.root.title(WINDOW_TITLE)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        try:
            self.root.iconbitmap(get_resource_path(ICON_PATH))
        except Exception as e:
            logging.error(f"Error setting icon: {e}")

        self._create_widgets()

    def _create_widgets(self):
        """Creates GUI widgets"""
        # --- Dummy Columns ---
        self.root.grid_columnconfigure(0, weight=1)  # Left dummy column, will expand/contract to push content to center
        self.root.grid_columnconfigure(7, weight=1)  # Right dummy column, will expand/contract to push content to center

        # Create widgets
        self.folder_label = tk.Label(self.root, width=60, relief='sunken')
        self.folder_label.grid(row=0, column=1, columnspan=5, pady=(5, 0), sticky="ew")  # shifted content columns + 1

        tk.Button(self.root, text="Select Original Folder", command=self.select_directory).grid(row=1, column=1, columnspan=4,
                                                                                                pady=5)  # shifted content columns + 1

        # Window Size Label on its own line
        tk.Label(self.root, text="Window Size").grid(row=2, column=1, sticky=tk.W, pady=5)  # shifted content columns + 1

        # Min label and entry
        tk.Label(self.root, text="Min: ").grid(row=3, column=1, sticky=tk.W, pady=5, padx=(50, 50))  # shifted content columns + 1
        self.min_window_entry = tk.Entry(self.root, width=5)
        self.min_window_entry.insert(0, str(DEFAULT_MIN_WINDOW_SIZE))
        self.min_window_entry.grid(row=3, column=1, padx=(10, 0), sticky=tk.E)  # shifted content columns + 1

        # Max label and entry
        tk.Label(self.root, text="Max: ").grid(row=3, column=3, sticky=tk.W, pady=5, padx=(50, 50))  # shifted content columns + 1
        self.max_window_entry = tk.Entry(self.root, width=5)
        self.max_window_entry.insert(0, str(DEFAULT_MAX_WINDOW_SIZE))
        self.max_window_entry.grid(row=3, column=3, padx=(10, 0), sticky=tk.E)  # shifted content columns + 1

        # Other Constant Label on its own line
        tk.Label(self.root, text="Other Parameter").grid(row=4, column=1, sticky=tk.W, pady=5)  # shifted content columns + 1

        # Preload Label and entry
        tk.Label(self.root, text="Preload:").grid(row=5, column=1, sticky=tk.W, pady=5, padx=(50, 50))  # shifted content columns + 1
        self.preload_entry = tk.Entry(self.root, width=5)
        self.preload_entry.insert(0, str(DEFAULT_PRELOAD))
        self.preload_entry.grid(row=5, column=1, padx=(90, 0), sticky=tk.E)  # shifted content columns + 1

        # Yield Force Label and entry
        tk.Label(self.root, text="Yf_Constant:").grid(row=5, column=2, sticky=tk.W, pady=5, padx=(50, 60))  # shifted content columns + 1
        self.yield_force_Constant = tk.Entry(self.root, width=5)
        self.yield_force_Constant.insert(0, str(DEFAULT_Yield_Force_Constant))
        self.yield_force_Constant.grid(row=5, column=2, padx=(20, 0), sticky=tk.E)  # shifted content columns + 1

        # Displacement Label and entry
        tk.Label(self.root, text="Disp_Constant:").grid(row=5, column=3, sticky=tk.W, pady=5, padx=(50, 50))  # shifted content columns + 1
        self.displacement_Constant = tk.Entry(self.root, width=5)
        self.displacement_Constant.insert(0, str(DEFAULT_Displacement_Constant))
        self.displacement_Constant.grid(row=5, column=3, padx=(20, 0), sticky=tk.E)  # shifted content columns + 1

        self.progress_bar = ttk.Progressbar(self.root, length=425, mode='determinate')
        self.progress_bar.grid(row=6, column=1, columnspan=4, pady=10, sticky="ew")  # shifted content columns + 1

        tk.Button(self.root, text="Generate Excel And Png", command=self.run_analysis).grid(row=7, column=1, columnspan=4,
                                                                                            pady=5)  # shifted content columns + 1

        self.failed_files_text = tk.Text(self.root, height=5, width=60)
        self.failed_files_text.grid(row=8, column=1, columnspan=4, pady=10, sticky="ew")  # shifted content columns + 1

    def run_analysis(self):
        """Starts the analysis thread"""
        directory = self.folder_label.cget("text")
        min_window_size = int(self.min_window_entry.get())
        max_window_size = int(self.max_window_entry.get())
        preload = float(self.preload_entry.get())
        yfc = float(self.yield_force_Constant.get())
        dispc = float(self.displacement_Constant.get())
        self.progress_bar["value"] = 0
        self.failed_files_text.delete(1.0, tk.END)
        Thread(target=save_files,
               args=(directory, self.update_progress, self.show_completion_message,
                     min_window_size, max_window_size, self.update_failed_files, preload, yfc, dispc)).start()
        logging.info(f"Analysis started with min_window_size: {min_window_size}, max_window_size: {max_window_size}, preload: {preload}, yield_force_constant: {yfc}, displacement_constant: {dispc}")

    def update_progress(self, current_step, max_steps):
        """Updates the progress bar"""
        self.progress_bar["value"] = current_step
        self.progress_bar["maximum"] = max_steps
        self.root.update_idletasks()

    def show_completion_message(self):
        """Displays the completion message"""
        messagebox.showinfo("Finish", "File has been generated!")
        logging.info("Analysis completed.")

    def select_directory(self):
        """Selects a directory"""
        directory = filedialog.askdirectory(title="Browse")
        if directory:
            self.folder_label.config(text=directory)
            logging.info(f"Directory selected: {directory}")

    def update_failed_files(self, failed_files):
        """Updates the failed file list"""
        if failed_files:
            self.failed_files_text.insert(tk.END, "Processing failed files:\n")
            for file_name in failed_files:
                self.failed_files_text.insert(tk.END, f"- {file_name}\n")


def main():
    """Main function, creates and runs the GUI"""
    root = tk.Tk()
    app = AnalysisApp(root)
    root.mainloop()
    logging.info("Application closed")


if __name__ == "__main__":
    main()
