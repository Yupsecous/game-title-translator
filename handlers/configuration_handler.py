# handlers/configuration_handler.py
import os
import tkinter as tk
from tkinter import filedialog, messagebox
import re # Not used directly here, but ui_interaction_handler uses it
import sys
from logger import log_debug
from config_manager import load_main_window_geometry, save_main_window_geometry # Correct imports
from resource_handler import get_resource_path
# LanguageManager is used by app_logic which calls this handler, no direct import needed here for get_tesseract_lang_code

class ConfigurationHandler:
    def __init__(self, app):
        self.app = app
        
    def load_window_geometry(self):
        load_main_window_geometry(self.app.config, self.app.root, self.app.root.minsize())

    def on_window_configure(self, event):
        if event.widget == self.app.root:
            if self.app._save_timer:
                self.app.root.after_cancel(self.app._save_timer)
            self.app._save_timer = self.app.root.after(500, self.save_current_window_geometry)

    def save_current_window_geometry(self):
        save_main_window_geometry(self.app.config, self.app.root)

    # get_tesseract_lang_code is now a method in app_logic.py for direct access by worker_threads

    def load_marian_models(self, localize_names=True):
        models_dict = {}
        models_list = []
        models_file = self.app.models_file_var.get() 
        
        if not models_file or not os.path.exists(models_file):
            models_file = get_resource_path("resources/MarianMT_select_models.csv")
            self.app.models_file_var.set(models_file)
            log_debug(f"Using resource handler to locate MarianMT models file: {models_file}")

        try:
            if os.path.exists(models_file):
                with open(models_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and ',' in line:
                            parts = line.split(',', 1)
                            if len(parts) == 2:
                                model_name_path, display_name = parts[0].strip(), parts[1].strip()
                                if model_name_path and display_name: # Ensure not empty
                                    # Localize the display name if requested
                                    if localize_names and hasattr(self.app, 'language_manager'):
                                        current_ui_lang = self.app.ui_lang.current_lang if hasattr(self.app, 'ui_lang') else 'english'
                                        localized_name = self.app.language_manager.get_localized_marian_display_name(
                                            display_name, current_ui_lang
                                        )
                                        models_dict[localized_name] = model_name_path
                                        models_list.append(localized_name)
                                    else:
                                        models_dict[display_name] = model_name_path
                                        models_list.append(display_name)
                log_debug(f"Loaded {len(models_dict)} MarianMT models from {models_file}")
            else: # Fallback to defaults if file not found
                log_debug(f"MarianMT models file not found: {models_file}. Using minimal defaults.")
                default_models = {
                    "French to English": "Helsinki-NLP/opus-mt-fr-en",
                    "English to Polish": "Helsinki-NLP/opus-mt-en-pl",
                }
                # Localize default models if requested
                if localize_names and hasattr(self.app, 'language_manager'):
                    current_ui_lang = self.app.ui_lang.current_lang if hasattr(self.app, 'ui_lang') else 'english'
                    for eng_name, model_path in default_models.items():
                        localized_name = self.app.language_manager.get_localized_marian_display_name(
                            eng_name, current_ui_lang
                        )
                        models_dict[localized_name] = model_path
                        models_list.append(localized_name)
                else:
                    models_dict.update(default_models)
                    models_list.extend(default_models.keys())
        except Exception as e_lmm:
            log_debug(f"Error loading MarianMT models: {e_lmm}. Using minimal defaults.")
            models_dict = {"French to English": "Helsinki-NLP/opus-mt-fr-en"}
            models_list = ["French to English"]
        return models_dict, sorted(models_list)

    def browse_marian_models_file(self):
        current_path = self.app.models_file_var.get()
        initial_dir = os.path.dirname(os.path.abspath(__file__)) # Script dir
        initial_dir = os.path.dirname(initial_dir) # Parent of handlers (main app dir)
        
        if current_path and os.path.exists(os.path.dirname(current_path)):
            initial_dir = os.path.dirname(current_path)

        path = filedialog.askopenfilename(
            initialdir=initial_dir,
            title=self.app.ui_lang.get_label("browse_marian_models_title", "Select MarianMT Models CSV File"),
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
        )
        if path:
            path_norm = os.path.normpath(path) # os.path.normpath for OS consistency
            self.app.models_file_var.set(path_norm)
            log_debug(f"MarianMT models file path set to: {path_norm}")

            self.app.marian_models_dict, self.app.marian_models_list = self.load_marian_models(localize_names=True)

            if hasattr(self.app, 'marian_model_combobox') and self.app.marian_model_combobox.winfo_exists():
                self.app.marian_model_combobox['values'] = self.app.marian_models_list
                current_selected_display = self.app.marian_model_display_var.get()
                if self.app.marian_models_list: # If list is not empty
                    if current_selected_display not in self.app.marian_models_list:
                        self.app.marian_model_display_var.set(self.app.marian_models_list[0])
                else: # List is empty
                    self.app.marian_model_display_var.set("")
                self.app.on_marian_model_selection_changed() 
            else:
                log_debug("MarianMT combobox not found during models file browse.")

    def browse_tesseract(self):
        import pytesseract # Local import
        current_path = self.app.tesseract_path_var.get()
        initial_dir = os.path.dirname(current_path) if current_path and os.path.exists(os.path.dirname(current_path)) else "C:/"
        path = filedialog.askopenfilename(initialdir=initial_dir, title=self.app.ui_lang.get_label("browse_tesseract_title", "Select tesseract.exe"), 
                                          filetypes=[("Executable", "*.exe"), ("All Files", "*.*")])
        if path:
            path_norm = os.path.normpath(path)
            if os.path.basename(path_norm).lower() == 'tesseract.exe':
                self.app.tesseract_path_var.set(path_norm)
                if pytesseract.pytesseract.tesseract_cmd != path_norm:
                    pytesseract.pytesseract.tesseract_cmd = path_norm
                    log_debug(f"Runtime Tesseract command updated to: {path_norm}")
            else:
                messagebox.showwarning("Warning", f"Selected file '{os.path.basename(path_norm)}' does not appear to be 'tesseract.exe'. Please verify.", parent=self.app.root)
                self.app.tesseract_path_var.set(path_norm)
            log_debug(f"Tesseract path set to: {self.app.tesseract_path_var.get()}")