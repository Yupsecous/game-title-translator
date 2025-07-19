# app_logic.py

# --- Configuration ---
ENABLE_PROCESS_CPU_AFFINITY = False  # Set to False to disable process-level CPU core limiting

import tkinter as tk
from tkinter import ttk, messagebox
import numpy as np
import cv2
import pytesseract
import threading
import time
import queue
import sys
from PIL import Image, ImageTk
import os
import re
import gc
import traceback
import io
import base64

from logger import log_debug, set_debug_logging_enabled, is_debug_logging_enabled
from resource_handler import get_resource_path
from marian_mt_translator import MarianMTTranslator, MARIANMT_AVAILABLE as MARIANMT_LIB_AVAILABLE
from config_manager import load_app_config, save_app_config, load_ocr_preview_geometry, save_ocr_preview_geometry
from gui_builder import create_main_tab, create_settings_tab, create_api_usage_tab, create_debug_tab
from ui_elements import create_scrollable_tab
from overlay_manager import (
    select_source_area_om, select_target_area_om,
    create_source_overlay_om, create_target_overlay_om,
    toggle_source_visibility_om, toggle_target_visibility_om, load_areas_from_config_om
)
from worker_threads import run_capture_thread, run_ocr_thread, run_translation_thread
from language_manager import LanguageManager
from language_ui import UILanguageManager

from handlers import (
    CacheManager, 
    ConfigurationHandler, 
    DisplayManager, 
    HotkeyHandler, 
    StatisticsHandler,
    TranslationHandler, 
    UIInteractionHandler
)

KEYBOARD_AVAILABLE = False
try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    pass 

GOOGLE_TRANSLATE_API_AVAILABLE = False
try:
    from google.cloud import translate_v2 as google_translate
    GOOGLE_TRANSLATE_API_AVAILABLE = True
except ImportError:
    pass

DEEPL_API_AVAILABLE = False
try:
    import deepl
    DEEPL_API_AVAILABLE = True
except ImportError:
    pass

GEMINI_API_AVAILABLE = False
try:
    import google.generativeai as genai
    GEMINI_API_AVAILABLE = True
except ImportError:
    pass

MARIANMT_AVAILABLE = MARIANMT_LIB_AVAILABLE

class GameChangingTranslator:
    def __init__(self, root):
        self.root = root
        self.root.title("Game-Changing Translator")
        self.root.geometry("600x480") 
        self.root.minsize(500, 430)
        self.root.resizable(True, True)
        
        self._fully_initialized = False # Flag for settings save callback

        self.KEYBOARD_AVAILABLE = KEYBOARD_AVAILABLE
        self.GOOGLE_TRANSLATE_API_AVAILABLE = GOOGLE_TRANSLATE_API_AVAILABLE
        self.DEEPL_API_AVAILABLE = DEEPL_API_AVAILABLE
        self.GEMINI_API_AVAILABLE = GEMINI_API_AVAILABLE
        self.MARIANMT_AVAILABLE = MARIANMT_AVAILABLE
        
        if not KEYBOARD_AVAILABLE: log_debug("Keyboard library not available. Hotkeys disabled.")
        if not GOOGLE_TRANSLATE_API_AVAILABLE: log_debug("Google Translate API libraries not available.")
        if not DEEPL_API_AVAILABLE: log_debug("DeepL API libraries not available.")
        if not GEMINI_API_AVAILABLE: log_debug("Gemini API libraries not available.")
        if not MARIANMT_AVAILABLE: log_debug("MarianMT libraries not available.")

        # Process-Level CPU Affinity: Limit application to exactly 3 cores
        if ENABLE_PROCESS_CPU_AFFINITY:
            try:
                import psutil
                cpu_count = os.cpu_count() or 2
                if cpu_count >= 3:  # Only limit if system has 3+ cores
                    # Use exactly 3 cores: [0, 1, 2]
                    available_cores = [0, 1, 2]
                    psutil.Process().cpu_affinity(available_cores)
                    
                    # Also set environment variable for OpenMP (Tesseract) thread limiting
                    os.environ['OMP_NUM_THREADS'] = '3'
                    
                    log_debug(f"Limited application to exactly 3 CPU cores: {available_cores} (out of {cpu_count} total)")
                    log_debug(f"Set OMP_NUM_THREADS=3 for Tesseract thread limiting")
                else:
                    log_debug(f"System has {cpu_count} cores - no CPU limiting applied (need 3+ cores)")
            except ImportError:
                log_debug("psutil not available - CPU affinity not set. Install psutil for CPU core limiting.")
            except Exception as e_cpu:
                log_debug(f"Error setting CPU affinity: {e_cpu}")
        else:
            log_debug("Process-level CPU affinity DISABLED via configuration flag")

        self.source_area = None 
        self.target_area = None 
        self.is_running = False 
        self.threads = [] 
        self.last_image_hash = None 
        self.source_overlay = None
        self.target_overlay = None
        self.translation_text = None
        self.text_stability_counter = 0 
        self.previous_text = "" 
        self.last_screenshot = None 
        self.last_processed_image = None 
        self.raw_image_for_gemini = None  # WebP bytes ready for Gemini API 
        
        # Gemini OCR Batch Infrastructure (Phase 1)
        self.last_processed_subtitle = None  # Store last processed subtitle for successive comparison
        self.batch_sequence_counter = 0  # Track batch sequence numbers
        self.clear_timeout_timer_start = None  # Timer for clear translation timeout
        self.active_ocr_calls = set()  # Track active async OCR calls
        self.max_concurrent_ocr_calls = 10  # Limit concurrent OCR API calls (10 for Gemini)
        
        # Gemini OCR Simple Management (No Queue for Gemini)
        self.last_displayed_batch_sequence = 0  # Track chronological order
        
        # Translation Async Processing Infrastructure (Phase 2)
        self.translation_sequence_counter = 0  # Track translation sequence numbers
        self.last_displayed_translation_sequence = 0  # Track chronological order for translations
        self.active_translation_calls = set()  # Track active async translation calls
        self.max_concurrent_translation_calls = 5  # Limit concurrent translation API calls
        
        # OCR Preview window
        self.ocr_preview_window = None

        self.config = load_app_config()
        self.language_manager = LanguageManager()
        
        # Initialize UI language manager with the saved language if available
        saved_language_display = self.config['Settings'].get('gui_language', 'English')
        self.ui_lang = UILanguageManager()
        if saved_language_display != 'English':
            lang_code = self.ui_lang.get_language_code_from_name(saved_language_display)
            if lang_code:
                self.ui_lang.load_language(lang_code)
                log_debug(f"Loaded UI language from config: {lang_code}")

        self.root.bind('<Configure>', self.on_window_configure)
        self._save_timer = None
        self._save_settings_timer = None

        # Initialize Tkinter Variables FIRST ---
        self.source_colour_var = tk.StringVar(value=self.config['Settings'].get('source_area_colour', '#FFFF99'))
        self.target_colour_var = tk.StringVar(value=self.config['Settings'].get('target_area_colour', '#663399'))
        self.target_text_colour_var = tk.StringVar(value=self.config['Settings'].get('target_text_colour', '#FFFFFF'))
        self.remove_trailing_garbage_var = tk.BooleanVar(value=self.config.getboolean('Settings', 'remove_trailing_garbage', fallback=False))
        self.debug_logging_enabled_var = tk.BooleanVar(value=self.config.getboolean('Settings', 'debug_logging_enabled', fallback=True))
        self.gui_language_var = tk.StringVar(value=self.config['Settings'].get('gui_language', 'English'))
        
        # OCR Model Selection (Phase 1 - Gemini OCR)
        self.ocr_model_var = tk.StringVar(value=self.config['Settings'].get('ocr_model', 'tesseract'))
        
        self.google_api_key_var = tk.StringVar(value=self.config['Settings'].get('google_translate_api_key', ''))
        self.deepl_api_key_var = tk.StringVar(value=self.config['Settings'].get('deepl_api_key', ''))
        self.gemini_api_key_var = tk.StringVar(value=self.config['Settings'].get('gemini_api_key', ''))
        self.deepl_model_type_var = tk.StringVar(value=self.config['Settings'].get('deepl_model_type', 'latency_optimized'))
        self.deepl_usage_var = tk.StringVar(value="Loading...")
        
        translation_model_val = self.config['Settings'].get('translation_model', 'gemini_api')
        # Fallback logic if configured model's library is not available
        if translation_model_val == 'gemini_api' and not self.GEMINI_API_AVAILABLE:
            log_debug("Configured Gemini API but library not available. Falling back...")
            if self.GOOGLE_TRANSLATE_API_AVAILABLE: translation_model_val = 'google_api'
            elif self.DEEPL_API_AVAILABLE: translation_model_val = 'deepl_api'
            elif self.MARIANMT_AVAILABLE: translation_model_val = 'marianmt'
            else: log_debug("No other translation libraries available for Gemini API fallback.")
        elif translation_model_val == 'marianmt' and not self.MARIANMT_AVAILABLE:
            log_debug("Configured MarianMT but library not available. Falling back...")
            if self.GEMINI_API_AVAILABLE: translation_model_val = 'gemini_api'
            elif self.GOOGLE_TRANSLATE_API_AVAILABLE: translation_model_val = 'google_api'
            elif self.DEEPL_API_AVAILABLE: translation_model_val = 'deepl_api'
            else: log_debug("No other translation libraries available, MarianMT will show error if selected.")
        elif translation_model_val == 'google_api' and not self.GOOGLE_TRANSLATE_API_AVAILABLE:
            log_debug("Configured Google API but library not available. Falling back...")
            if self.GEMINI_API_AVAILABLE: translation_model_val = 'gemini_api'
            elif self.DEEPL_API_AVAILABLE: translation_model_val = 'deepl_api'
            elif self.MARIANMT_AVAILABLE: translation_model_val = 'marianmt'
            else: log_debug("No other translation libraries available for Google API fallback.")
        elif translation_model_val == 'deepl_api' and not self.DEEPL_API_AVAILABLE:
            log_debug("Configured DeepL API but library not available. Falling back...")
            if self.GEMINI_API_AVAILABLE: translation_model_val = 'gemini_api'
            elif self.GOOGLE_TRANSLATE_API_AVAILABLE: translation_model_val = 'google_api'
            elif self.MARIANMT_AVAILABLE: translation_model_val = 'marianmt'
            else: log_debug("No other translation libraries available for DeepL API fallback.")
        self.translation_model_var = tk.StringVar(value=translation_model_val)

        # Define translation model names and values earlier
        # Initialize with default values, will be updated with localized versions
        self.translation_model_names = {
            'gemini_api': 'Gemini 2.5 Flash-Lite',
            'google_api': 'Google Translate API',
            'deepl_api': 'DeepL API',
            'marianmt': 'MarianMT (offline and free)'
        }
        # Update with localized names after UI language is loaded
        self.update_translation_model_names()
        self.translation_model_values = {v: k for k, v in self.translation_model_names.items()}

        self.models_file_var = tk.StringVar(value=self.config['Settings'].get('marian_models_file'))
        self.num_beams_var = tk.IntVar(value=int(self.config['Settings'].get('num_beams', '2')))
        self.marian_model_var = tk.StringVar(value=self.config['Settings'].get('marian_model', '')) # Stores path
        
        self.google_file_cache_var = tk.BooleanVar(value=self.config.getboolean('Settings', 'google_file_cache', fallback=True))
        self.deepl_file_cache_var = tk.BooleanVar(value=self.config.getboolean('Settings', 'deepl_file_cache', fallback=True))
        self.gemini_file_cache_var = tk.BooleanVar(value=self.config.getboolean('Settings', 'gemini_file_cache', fallback=True))
        self.gemini_context_window_var = tk.IntVar(value=int(self.config['Settings'].get('gemini_context_window', '1')))
        self.gemini_api_log_enabled_var = tk.BooleanVar(value=self.config.getboolean('Settings', 'gemini_api_log_enabled', fallback=True))
        
        # Gemini statistics variables (initialized by GUI builder)
        self.gemini_total_words_var = None
        self.gemini_total_cost_var = None

        tesseract_path_from_config = self.config['Settings'].get('tesseract_path', r'C:\Program Files\Tesseract-OCR\tesseract.exe')
        self.tesseract_path_var = tk.StringVar(value=tesseract_path_from_config)

        self.scan_interval_var = tk.IntVar(value=int(self.config['Settings'].get('scan_interval', '100')))
        self.clear_translation_timeout_var = tk.IntVar(value=int(self.config['Settings'].get('clear_translation_timeout', '3')))
        self.stability_var = tk.IntVar(value=int(self.config['Settings'].get('stability_threshold', '2')))
        self.confidence_var = tk.IntVar(value=int(self.config['Settings'].get('confidence_threshold', '60')))
        self.preprocessing_mode_var = tk.StringVar(value=self.config['Settings'].get('image_preprocessing_mode', 'none'))
        
        # Adaptive thresholding parameters
        self.adaptive_block_size_var = tk.IntVar(value=int(self.config['Settings'].get('adaptive_block_size', '41')))
        self.adaptive_c_var = tk.IntVar(value=int(self.config['Settings'].get('adaptive_c', '-60')))
        
        # Create a translated display variable for preprocessing mode
        self.preprocessing_display_var = tk.StringVar()
        
        self.ocr_debugging_var = tk.BooleanVar(value=self.config.getboolean('Settings', 'ocr_debugging', fallback=False))
        self.target_font_size_var = tk.IntVar(value=int(self.config['Settings'].get('target_font_size', '12')))
        
        # Initialize Handlers
        # self.cache_manager = CacheManager(self)
        self.configuration_handler = ConfigurationHandler(self)
        self.display_manager = DisplayManager(self)
        self.hotkey_handler = HotkeyHandler(self)
        self.statistics_handler = StatisticsHandler(self)
        self.translation_handler = TranslationHandler(self)
        self.ui_interaction_handler = UIInteractionHandler(self) # Needs self.translation_model_names

        # Initialize trace suppression mechanism and UI update detection
        self._suppress_traces = False
        self._ui_update_in_progress = False
        
        def _settings_changed_callback_internal(*args, **kwargs):
            if self._fully_initialized and not self._suppress_traces and not self._ui_update_in_progress:
                self.save_settings()
            elif self._suppress_traces:
                log_debug("StringVar trace suppressed during UI update")
            elif self._ui_update_in_progress:
                log_debug("StringVar trace suppressed during UI update operation")

        self.settings_changed_callback = _settings_changed_callback_internal

        # Scan interval validation callback for Gemini OCR minimum
        def _scan_interval_changed_callback(*args, **kwargs):
            if self._fully_initialized and not self._suppress_traces and not self._ui_update_in_progress:
                # Validate minimum scan interval for Gemini OCR
                if self.get_ocr_model_setting() == 'gemini':
                    current_value = self.scan_interval_var.get()
                    if current_value < 500:
                        log_debug(f"Scan interval {current_value}ms too low for Gemini OCR, setting to 500ms minimum")
                        self.scan_interval_var.set(500)
                        return  # Skip save_settings since we just changed the value
                self.save_settings()
            elif self._suppress_traces:
                log_debug("Scan interval trace suppressed during UI update")
            elif self._ui_update_in_progress:
                log_debug("Scan interval trace suppressed during UI update operation")

        self.scan_interval_changed_callback = _scan_interval_changed_callback

        # Add traces
        self.source_colour_var.trace_add("write", self.settings_changed_callback)
        self.target_colour_var.trace_add("write", self.settings_changed_callback)
        self.target_text_colour_var.trace_add("write", self.settings_changed_callback)
        self.remove_trailing_garbage_var.trace_add("write", self.settings_changed_callback)
        self.debug_logging_enabled_var.trace_add("write", self.settings_changed_callback)
        self.google_api_key_var.trace_add("write", self.settings_changed_callback)
        self.deepl_api_key_var.trace_add("write", self.settings_changed_callback)
        self.deepl_model_type_var.trace_add("write", self.settings_changed_callback)
        self.models_file_var.trace_add("write", self.settings_changed_callback)
        self.google_file_cache_var.trace_add("write", self.settings_changed_callback)
        self.deepl_file_cache_var.trace_add("write", self.settings_changed_callback)
        self.preprocessing_mode_var.trace_add("write", self.settings_changed_callback)
        self.preprocessing_mode_var.trace_add("write", self.on_ocr_parameter_change)
        self.adaptive_block_size_var.trace_add("write", self.settings_changed_callback)
        self.adaptive_block_size_var.trace_add("write", self.on_ocr_parameter_change)
        self.adaptive_c_var.trace_add("write", self.settings_changed_callback)
        self.adaptive_c_var.trace_add("write", self.on_ocr_parameter_change)
        self.ocr_debugging_var.trace_add("write", self.settings_changed_callback)
        self.tesseract_path_var.trace_add("write", self.settings_changed_callback)
        self.scan_interval_var.trace_add("write", self.scan_interval_changed_callback)  # Special validation callback
        self.clear_translation_timeout_var.trace_add("write", self.settings_changed_callback)
        self.stability_var.trace_add("write", self.settings_changed_callback)
        self.confidence_var.trace_add("write", self.settings_changed_callback)
        self.target_font_size_var.trace_add("write", self.settings_changed_callback)
        self.num_beams_var.trace_add("write", self.settings_changed_callback)
        self.marian_model_var.trace_add("write", self.settings_changed_callback) 
        self.gui_language_var.trace_add("write", self.settings_changed_callback)
        self.ocr_model_var.trace_add("write", self.settings_changed_callback)
        self.ocr_model_var.trace_add("write", self.on_ocr_model_change)

        # Other instance variables
        # Increased queue sizes from 4/3 to 8/6 to reduce queue management overhead
        self.ocr_queue = queue.Queue(maxsize=8)  # Increased from 4 for better buffering
        self.translation_queue = queue.Queue(maxsize=6)  # Increased from 3 for better buffering
        self.last_successful_translation_time = 0.0
        self.min_translation_interval = 0.3
        self.last_translation_time = time.monotonic()
        self.google_api_client = None
        self.deepl_api_client = None
        self.google_api_key_visible = False
        self.deepl_api_key_visible = False
        self.gemini_api_key_visible = False
        self.marian_translator = None
        self.marian_source_lang = None 
        self.marian_target_lang = None 
        
        self.google_source_lang = self.config['Settings'].get('google_source_lang', 'auto')
        self.google_target_lang = self.config['Settings'].get('google_target_lang', 'en')
        self.deepl_source_lang = self.config['Settings'].get('deepl_source_lang', 'auto')
        self.deepl_target_lang = self.config['Settings'].get('deepl_target_lang', 'EN-GB')
        self.gemini_source_lang = self.config['Settings'].get('gemini_source_lang', 'en')
        self.gemini_target_lang = self.config['Settings'].get('gemini_target_lang', 'pl')
        
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.google_cache_file = os.path.join(base_dir, "googletrans_cache.txt")
        self.deepl_cache_file = os.path.join(base_dir, "deepl_cache.txt")
        self.gemini_cache_file = os.path.join(base_dir, "gemini_cache.txt")
        log_debug(f"Cache file paths: Google: {self.google_cache_file}, DeepL: {self.deepl_cache_file}, Gemini: {self.gemini_cache_file}")
        
        self.google_file_cache = {}
        self.deepl_file_cache = {}
        self.gemini_file_cache = {}
        self.translation_cache = {}
        
        self.cache_manager = CacheManager(self)

        pytesseract.pytesseract.tesseract_cmd = self.tesseract_path_var.get()

        self.stable_threshold = self.stability_var.get()
        self.confidence_threshold = self.confidence_var.get()
        self.clear_translation_timeout = self.clear_translation_timeout_var.get()

        if not self.google_source_lang: self.google_source_lang = 'auto'
        if not self.google_target_lang: self.google_target_lang = 'en'
        if not self.deepl_source_lang: self.deepl_source_lang = 'auto'
        if not self.deepl_target_lang: self.deepl_target_lang = 'EN-GB'

        self.cache_manager.load_file_caches()
        
        # Initialize debug logging state
        set_debug_logging_enabled(self.debug_logging_enabled_var.get())
        
        self.marian_models_dict, self.marian_models_list = self.configuration_handler.load_marian_models(localize_names=True)
        self.configuration_handler.load_window_geometry()

        # Initialize UI display StringVars here so they exist before create_settings_tab
        self.source_display_var = tk.StringVar() 
        self.target_display_var = tk.StringVar()
        
        configured_marian_path = self.marian_model_var.get() 
        initial_marian_display_name = ""
        if configured_marian_path:
            for display_name_iter, path_iter in self.marian_models_dict.items():
                if path_iter == configured_marian_path:
                    initial_marian_display_name = display_name_iter
                    break
        if not initial_marian_display_name and self.marian_models_list: 
            initial_marian_display_name = self.marian_models_list[0]
            fallback_path = self.marian_models_dict.get(initial_marian_display_name, "")
            if self.marian_model_var.get() != fallback_path : 
                 self.marian_model_var.set(fallback_path) 
        self.marian_model_display_var = tk.StringVar(value=initial_marian_display_name)

        # This uses self.translation_model_names, so it must be after its definition
        initial_model_code_for_display = self.translation_model_var.get()
        initial_display_name_for_model_combo = self.translation_model_names.get(initial_model_code_for_display, list(self.translation_model_names.values())[0])
        self.translation_model_display_var = tk.StringVar(value=initial_display_name_for_model_combo)


        self.tab_control = ttk.Notebook(root)
        self.tab_control.pack(expand=True, fill="both", padx=5, pady=5)
        
        # The tab frames will be created and assigned in the create_*_tab functions
        # We'll temporarily set them to None
        self.tab_main = None
        self.tab_settings = None
        self.tab_debug = None
        self.tab_about = None
        
        active_model_for_init = self.translation_model_var.get()
        initial_source_val, initial_target_val = 'auto', 'en' 

        if active_model_for_init == 'google_api':
            initial_source_val = self.google_source_lang
            initial_target_val = self.google_target_lang
        elif active_model_for_init == 'deepl_api':
            initial_source_val = self.deepl_source_lang
            initial_target_val = self.deepl_target_lang
        elif active_model_for_init == 'gemini_api':
            initial_source_val = self.gemini_source_lang
            initial_target_val = self.gemini_target_lang
        elif active_model_for_init == 'marianmt':
            if self.marian_model_display_var.get(): 
                # ui_interaction_handler is now defined
                parsed_marian_langs_init = self.ui_interaction_handler.parse_marian_model_for_langs(self.marian_model_display_var.get()) or \
                                           self.ui_interaction_handler.parse_marian_model_for_langs(self.marian_model_var.get()) 
                if parsed_marian_langs_init:
                    initial_source_val = parsed_marian_langs_init[0]
                    initial_target_val = parsed_marian_langs_init[1]
                    self.marian_source_lang = initial_source_val 
                    self.marian_target_lang = initial_target_val
                else:
                    initial_source_val, initial_target_val = '', ''
            else:
                 initial_source_val, initial_target_val = '', ''


        self.source_lang_var = tk.StringVar(value=initial_source_val) 
        self.target_lang_var = tk.StringVar(value=initial_target_val)
        
        self.lang_code_to_name = self.language_manager 

        # Create the main tabs
        create_main_tab(self)
        create_settings_tab(self)
        create_api_usage_tab(self)
        create_debug_tab(self)
        
        # Create About tab with scrollable content
        scrollable_about = create_scrollable_tab(self.tab_control, self.ui_lang.get_label("about_tab_title", "About"))
        self.tab_about = scrollable_about
        
        # Create the about frame inside the scrollable area
        about_frame = ttk.LabelFrame(scrollable_about, text=self.ui_lang.get_label("about_tab_title", "About"))
        about_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Hard-coded About content based on language
        if self.ui_lang.current_lang == 'pol':
            about_text = """Copyright © 2025 Tomasz Kamiński

Game-Changing Translator to program komputerowy, który automatycznie przechwytuje tekst z\u00a0dowolnego fragmentu ekranu, przeprowadza optyczne rozpoznawanie znaków (OCR) i\u00a0tłumaczy tekst w\u00a0czasie rzeczywistym. Może służyć do tłumaczenia napisów w\u00a0grach lub dowolnego innego tekstu, którego nie można łatwo skopiować.

Program został napisany w\u00a0języku Python przy użyciu następujących modeli sztucznej inteligencji: Claude\u00a03.7\u00a0Sonnet, Claude\u00a0Sonnet\u00a04 i\u00a0Gemini\u00a02.5\u00a0Pro.

Więcej informacji zawiera instrukcja obsługi."""
        else:
            about_text = """Copyright © 2025 Tomasz Kamiński

Game-Changing Translator is a desktop application that automatically captures text from any area of your screen, performs optical character recognition (OCR), and translates the text in real-time. You can use it for translating video game subtitles or any other text that you can't easily copy.

This application was developed in Python using the following AI models: Claude\u00a03.7\u00a0Sonnet, Claude\u00a0Sonnet\u00a04 and Gemini\u00a02.5\u00a0Pro.

For more information, see the user manual."""
        
        # Use Text widget for proper wrapping
        about_text_widget = tk.Text(about_frame, wrap=tk.WORD, relief="flat", 
                                   borderwidth=0, highlightthickness=0)
        about_text_widget.pack(fill="both", expand=True, padx=20, pady=20)
        about_text_widget.insert(tk.END, about_text)
        about_text_widget.config(state=tk.DISABLED)  # Make it read-only

        # Handle tab change events to set focus appropriately
        def on_tab_changed(event):
            selected_tab_index = self.tab_control.index(self.tab_control.select())
            if selected_tab_index == 0 and hasattr(self, 'main_tab_start_button') and self.main_tab_start_button.winfo_exists():
                self.main_tab_start_button.focus_set()
            elif selected_tab_index == 1 and hasattr(self, 'settings_tab_save_button') and self.settings_tab_save_button.winfo_exists():
                self.settings_tab_save_button.focus_set()
            elif selected_tab_index == 2 and hasattr(self, 'refresh_api_statistics'):
                # API Usage tab - refresh statistics when accessed
                self.root.after(100, self.refresh_api_statistics)
        
        self.tab_control.bind("<<NotebookTabChanged>>", on_tab_changed)
        
        self.ui_interaction_handler.on_translation_model_selection_changed(initial_setup=True)
        
        # Initialize localized dropdowns after everything is set up
        self.root.after(50, self.ui_interaction_handler.update_all_dropdowns_for_language_change)

        self.root.after(100, self.load_initial_overlay_areas)
        self.root.after(200, self.ensure_window_visible)
        self.hotkey_handler.setup_hotkeys()
        
        log_debug(f"Application initialized. Stability: {self.stable_threshold}, Confidence: {self.confidence_threshold}")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self._fully_initialized = True
        log_debug("GameChangingTranslator fully initialized.")
        
        # Ensure OCR model UI is correctly set up on initial load
        if hasattr(self, 'ui_interaction_handler'):
            self.ui_interaction_handler.update_ocr_model_ui()
        
        # Update usage statistics for selected models - use after_idle to ensure GUI is ready
        if hasattr(self, 'translation_model_var'):
            selected_model = self.translation_model_var.get()
            if selected_model == 'gemini_api':
                self.root.after_idle(lambda: self._delayed_gemini_stats_update())
            elif selected_model == 'deepl_api':
                self.root.after_idle(lambda: self._delayed_deepl_usage_update())
        
        # Always update DeepL usage since it's now always visible in API Usage tab
        self.root.after_idle(lambda: self._delayed_deepl_usage_update())
        
        # Refresh API statistics for the new API Usage tab
        self.root.after_idle(lambda: self._delayed_api_stats_refresh())

    def _delayed_api_stats_refresh(self):
        """Delayed API statistics refresh to ensure GUI is fully ready."""
        try:
            self.refresh_api_statistics()
        except Exception as e:
            log_debug(f"Error in delayed API statistics refresh: {e}")

    def update_api_usage_tab_for_language(self):
        """Update API Usage tab labels when language changes."""
        try:
            # Update section labels
            if hasattr(self, 'tab_api_usage'):
                # Refresh the entire tab content since section labels are hard to update individually
                # The next time the user clicks on the tab, the labels will be updated
                log_debug("API Usage tab language update requested - will update on next tab access")
            
            # Update button labels if they exist
            if hasattr(self, 'refresh_stats_button') and self.refresh_stats_button.winfo_exists():
                self.refresh_stats_button.config(text=self.ui_lang.get_label("api_usage_refresh_btn", "Refresh Statistics"))
            if hasattr(self, 'export_csv_button') and self.export_csv_button.winfo_exists():
                self.export_csv_button.config(text=self.ui_lang.get_label("api_usage_export_csv_btn", "Export to CSV"))
            if hasattr(self, 'export_text_button') and self.export_text_button.winfo_exists():
                self.export_text_button.config(text=self.ui_lang.get_label("api_usage_export_text_btn", "Export to Text"))
            if hasattr(self, 'copy_stats_button') and self.copy_stats_button.winfo_exists():
                self.copy_stats_button.config(text=self.ui_lang.get_label("api_usage_copy_btn", "Copy"))
            
            # Update statistic labels if they exist
            if hasattr(self, 'ocr_stat_labels'):
                ocr_labels = [
                    ("api_usage_total_ocr_calls", "Total OCR Calls:"),
                    ("api_usage_avg_cost_per_call", "Average Cost per Call:"),
                    ("api_usage_avg_cost_per_minute", "Average Cost per Minute:"),
                    ("api_usage_avg_cost_per_hour", "Average Cost per Hour:"),
                    ("api_usage_total_ocr_cost", "Total OCR Cost:")
                ]
                for label_key, fallback_text in ocr_labels:
                    if label_key in self.ocr_stat_labels and self.ocr_stat_labels[label_key].winfo_exists():
                        self.ocr_stat_labels[label_key].config(text=self.ui_lang.get_label(label_key, fallback_text))
            
            if hasattr(self, 'translation_stat_labels'):
                translation_labels = [
                    ("api_usage_total_translation_calls", "Total Translation Calls:"),
                    ("api_usage_total_words_translated", "Total Words Translated:"),
                    ("api_usage_words_per_minute", "Average Words per Minute:"),
                    ("api_usage_avg_cost_per_word", "Average Cost per Word:"),
                    ("api_usage_avg_cost_per_minute", "Average Cost per Minute:"),
                    ("api_usage_avg_cost_per_hour", "Average Cost per Hour:"),
                    ("api_usage_total_translation_cost", "Total Translation Cost:")
                ]
                for label_key, fallback_text in translation_labels:
                    if label_key in self.translation_stat_labels and self.translation_stat_labels[label_key].winfo_exists():
                        self.translation_stat_labels[label_key].config(text=self.ui_lang.get_label(label_key, fallback_text))
            
            if hasattr(self, 'combined_stat_labels'):
                combined_labels = [
                    ("api_usage_total_api_cost", "Total API Cost:"),
                    ("api_usage_combined_cost_per_minute", "Combined Cost per Minute:"),
                    ("api_usage_combined_cost_per_hour", "Combined Cost per Hour:")
                ]
                for label_key, fallback_text in combined_labels:
                    if label_key in self.combined_stat_labels and self.combined_stat_labels[label_key].winfo_exists():
                        self.combined_stat_labels[label_key].config(text=self.ui_lang.get_label(label_key, fallback_text))
            
            log_debug("Updated API Usage tab labels for language change")
        except Exception as e:
            log_debug(f"Error updating API Usage tab for language change: {e}")

    def ensure_window_visible(self):
        """Ensure the main window is visible after all initialization is complete."""
        try:
            if self.root.winfo_exists():
                self.root.deiconify()
                self.root.lift()
                log_debug("Main window visibility ensured after initialization")
        except Exception as e:
            log_debug(f"Error ensuring window visibility: {e}")

    def on_ocr_parameter_change(self, *args):
        """Called when OCR parameters change to refresh preview if it's open."""
        if self.ocr_preview_window is not None:
            try:
                if self.ocr_preview_window.winfo_exists():
                    # Delay the refresh slightly to avoid too frequent updates
                    if hasattr(self, '_preview_refresh_timer'):
                        self.root.after_cancel(self._preview_refresh_timer)
                    self._preview_refresh_timer = self.root.after(200, self.refresh_ocr_preview)
                else:
                    # Window was destroyed but reference wasn't cleared
                    self.ocr_preview_window = None
            except tk.TclError:
                # Window was destroyed
                self.ocr_preview_window = None

    def on_ocr_model_change(self, *args):
        """Called when OCR model selection changes to update UI visibility."""
        try:
            # End OCR session if switching away from Gemini and translation is running
            if (hasattr(self, 'translation_handler') and self.is_running and 
                self.get_ocr_model_setting() != 'gemini'):
                self.translation_handler.request_end_ocr_session()
            
            # Start OCR session if switching to Gemini and translation is running
            if (hasattr(self, 'translation_handler') and self.is_running and 
                self.get_ocr_model_setting() == 'gemini'):
                self.translation_handler.start_ocr_session()
            
            # Update UI to show/hide Tesseract-specific fields
            if hasattr(self, 'ui_interaction_handler'):
                self.ui_interaction_handler.update_ocr_model_ui()
            
            # Update adaptive fields visibility based on new OCR model
            if hasattr(self, 'update_adaptive_fields_visibility'):
                self.update_adaptive_fields_visibility()
            
            # Validate scan interval when switching to Gemini OCR
            if self.get_ocr_model_setting() == 'gemini':
                current_value = self.scan_interval_var.get()
                if current_value < 500:
                    log_debug(f"OCR model changed to Gemini: updating scan interval from {current_value}ms to 500ms minimum")
                    self.scan_interval_var.set(500)
            
            # Refresh OCR preview if it's open to use the new OCR model
            if self.ocr_preview_window is not None:
                try:
                    if self.ocr_preview_window.winfo_exists():
                        if hasattr(self, '_preview_refresh_timer'):
                            self.root.after_cancel(self._preview_refresh_timer)
                        self._preview_refresh_timer = self.root.after(200, self.refresh_ocr_preview)
                    else:
                        self.ocr_preview_window = None
                except tk.TclError:
                    self.ocr_preview_window = None
                    
            log_debug(f"OCR model changed to: {self.ocr_model_var.get()}")
        except Exception as e:
            log_debug(f"Error in OCR model change callback: {e}")

    def save_settings(self):
        if self._fully_initialized:
            return self.ui_interaction_handler.save_settings()
        log_debug("Attempted to save settings before full initialization.")
        return False

    def suppress_traces(self):
        """Suppress StringVar traces during UI updates to prevent cascading saves"""
        self._suppress_traces = True
        log_debug("StringVar traces suppressed")

    def restore_traces(self):
        """Restore StringVar traces after UI updates complete"""
        self._suppress_traces = False
        log_debug("StringVar traces restored")
        
    def start_ui_update(self):
        """Mark the start of a UI update operation to suppress all saves"""
        self._ui_update_in_progress = True
        self.suppress_traces()
        log_debug("UI update operation started - all saves suppressed")
        
    def end_ui_update(self):
        """Mark the end of a UI update operation and restore normal save behavior"""
        self._ui_update_in_progress = False
        self.restore_traces()
        log_debug("UI update operation ended - saves restored")

    def on_window_configure(self, event):
        self.configuration_handler.on_window_configure(event)

    def save_current_window_geometry(self):
        self.configuration_handler.save_current_window_geometry()

    def get_tesseract_lang_code(self):
        api_source_code = self.source_lang_var.get()
        current_model = self.translation_model_var.get()
        if current_model == 'marianmt' and self.marian_source_lang:
            api_source_code = self.marian_source_lang
            
        return self.language_manager.get_tesseract_code(api_source_code, current_model)

    def browse_tesseract(self):
        self.configuration_handler.browse_tesseract()

    def browse_marian_models_file(self):
        self.configuration_handler.browse_marian_models_file()

    def update_translation_text(self, text_to_display):
        self.display_manager.update_translation_text(text_to_display)

    def update_debug_display(self, original_img_pil, processed_img_cv, ocr_text_content):
        self.display_manager.update_debug_display(original_img_pil, processed_img_cv, ocr_text_content)

    def convert_to_webp_for_gemini(self, pil_image):
        """Convert PIL image to lossless WebP bytes for Gemini API."""
        try:
            # Optimize image for OCR if needed
            if pil_image.mode in ('RGBA', 'LA'):
                rgb_img = Image.new('RGB', pil_image.size, (255, 255, 255))
                if pil_image.mode == 'RGBA':
                    rgb_img.paste(pil_image, mask=pil_image.split()[-1])
                else:
                    rgb_img.paste(pil_image)
                pil_image = rgb_img
            
            # Create memory buffer
            buffer = io.BytesIO()
            
            # Save as WebP lossless in memory
            pil_image.save(
                buffer, 
                format='WebP', 
                lossless=True, 
                method=0,
                exact=True
            )
            
            # Get bytes and encode to base64
            webp_bytes = buffer.getvalue()
            webp_base64 = base64.b64encode(webp_bytes).decode('utf-8')
            
            log_debug(f"Converted PIL image to WebP for Gemini: {len(webp_bytes)} bytes")
            return webp_base64
            
        except Exception as e:
            log_debug(f"Error converting image to WebP for Gemini: {e}")
            return None

    # Gemini OCR Batch Processing Methods (Phase 1)
    def get_ocr_model_setting(self):
        """Get the current OCR model setting."""
        return self.ocr_model_var.get()
    
    def handle_empty_ocr_result(self):
        """Handle <EMPTY> OCR result and manage clear translation timeout."""
        current_time = time.monotonic()
        
        # Only start timeout if we have a timeout value configured
        if self.clear_translation_timeout_var.get() <= 0:
            return  # Timeout disabled, do nothing
        
        if self.clear_timeout_timer_start is None:
            # First EMPTY result - start timer
            self.clear_timeout_timer_start = current_time
            log_debug("Clear timeout timer started for <EMPTY> OCR result")
        else:
            # Check if timeout period exceeded
            elapsed = current_time - self.clear_timeout_timer_start
            timeout_seconds = self.clear_translation_timeout_var.get()
            
            if elapsed >= timeout_seconds:
                # Clear the translation display
                self.update_translation_text("")
                self.reset_clear_timeout()
                log_debug(f"Translation cleared after {elapsed:.1f}s timeout")
    
    def handle_successive_identical_subtitle(self, reason):
        """Handle identical subtitles that are the SAME as the immediately previous one."""
        # 1. Do NOT update caches (LRU, file cache) - no new content
        # 2. Do NOT update context window - successive identical subtitle
        # 3. Keep displaying last translation (no API call needed)
        # 4. Reset clear timeout (text is still present)
        
        self.reset_clear_timeout()  # Text still present
        # Display remains unchanged (last translation stays)
        # self.last_processed_subtitle stays the same (no change)
        log_debug(f"Successive identical subtitle detected ({reason}), maintaining current translation")
        # No context window update - subtitle hasn't changed
    
    def reset_clear_timeout(self):
        """Reset clear translation timeout timer."""
        self.clear_timeout_timer_start = None
        log_debug("Clear timeout timer reset - text detected")
    
    def initialize_async_translation_infrastructure(self):
        """Initialize async translation infrastructure if not already present."""
        if not hasattr(self, 'translation_sequence_counter'):
            self.translation_sequence_counter = 0
            log_debug("Initialized translation_sequence_counter")
        
        if not hasattr(self, 'last_displayed_translation_sequence'):
            self.last_displayed_translation_sequence = 0
            log_debug("Initialized last_displayed_translation_sequence")
        
        if not hasattr(self, 'active_translation_calls'):
            self.active_translation_calls = set()
            log_debug("Initialized active_translation_calls")
        
        if not hasattr(self, 'max_concurrent_translation_calls'):
            self.max_concurrent_translation_calls = 5
            log_debug("Initialized max_concurrent_translation_calls")
    
    def check_clear_timeout(self):
        """Check if clear timeout should be triggered and return True if timeout exceeded."""
        if self.clear_timeout_timer_start is None:
            return False
            
        if self.clear_translation_timeout_var.get() <= 0:
            return False  # Timeout disabled
            
        current_time = time.monotonic()
        elapsed = current_time - self.clear_timeout_timer_start
        timeout_seconds = self.clear_translation_timeout_var.get()
        
        return elapsed >= timeout_seconds

    def translate_text(self, text_content):
        return self.translation_handler.translate_text(text_content)

    def is_placeholder_text(self, text_content):
        return self.translation_handler.is_placeholder_text(text_content)

    def calculate_text_similarity(self, text1, text2):
        return self.translation_handler.calculate_text_similarity(text1, text2)

    def update_marian_active_model(self, model_name, source_lang=None, target_lang=None):
        return self.translation_handler.update_marian_active_model(model_name, source_lang, target_lang)

    def update_marian_beam_value(self):
        self.translation_handler.update_marian_beam_value()

    def choose_color_for_settings(self, color_type):
        self.ui_interaction_handler.choose_color_for_settings(color_type)

    def update_stability_from_spinbox(self):
        self.ui_interaction_handler.update_stability_from_spinbox()

    def update_target_font_size(self):
        self.ui_interaction_handler.update_target_font_size()

    def refresh_debug_log(self):
        self.ui_interaction_handler.refresh_debug_log()

    def save_debug_images(self):
        self.ui_interaction_handler.save_debug_images()

    def toggle_api_key_visibility(self, api_type):
        self.ui_interaction_handler.toggle_api_key_visibility(api_type)

    def update_translation_model_ui(self): 
        self.ui_interaction_handler.update_translation_model_ui()

    def on_marian_model_selection_changed(self, event=None, preload=False, initial_setup=False):
        self.ui_interaction_handler.on_marian_model_selection_changed(event, preload, initial_setup)
        if not initial_setup and self._fully_initialized : 
             self.save_settings()


    def on_translation_model_selection_changed(self, event=None, initial_setup=False):
        # Handle session management for translation method changes
        if (hasattr(self, 'translation_handler') and self.is_running and not initial_setup):
            current_model = self.translation_model_var.get()
            
            # End translation session if switching away from Gemini
            if current_model != 'gemini_api':
                self.translation_handler.request_end_translation_session()
            
            # Start translation session if switching to Gemini
            if current_model == 'gemini_api':
                self.translation_handler.start_translation_session()
        
        self.ui_interaction_handler.on_translation_model_selection_changed(event, initial_setup)
        if not initial_setup and self._fully_initialized: 
            self.save_settings()

    def clear_debug_log(self):
        self.ui_interaction_handler.clear_debug_log()

    def reset_gemini_api_log(self):
        """Reset/clear the Gemini API call log file."""
        try:
            if hasattr(self.translation_handler, 'gemini_log_file'):
                log_file_path = self.translation_handler.gemini_log_file
                
                # Clear the file by truncating it
                if os.path.exists(log_file_path):
                    with open(log_file_path, 'w', encoding='utf-8') as f:
                        f.write('')  # Clear the file
                    log_debug(f"Gemini API log file cleared: {log_file_path}")
                    
                    # Reinitialize the log with header
                    if hasattr(self.translation_handler, '_initialize_gemini_log'):
                        self.translation_handler._initialize_gemini_log()
                    
                    # Update the GUI fields
                    self.update_gemini_stats()
                    
                    messagebox.showinfo("Success", "Gemini API log has been reset.")
                else:
                    log_debug(f"Gemini API log file does not exist: {log_file_path}")
                    messagebox.showwarning("Warning", "Gemini API log file does not exist.")
            else:
                log_debug("Gemini log file path not available")
                messagebox.showerror("Error", "Could not access Gemini log file.")
        except Exception as e:
            log_debug(f"Error resetting Gemini API log: {e}")
            messagebox.showerror("Error", f"Failed to reset Gemini API log: {str(e)}")

    def format_currency_for_display(self, amount, unit_suffix=""):
        """Format currency amount according to current UI language."""
        try:
            if self.ui_lang.current_lang == 'pol':
                # Polish format: "0,04941340 USD/min" 
                amount_str = f"{amount:.8f}"
                amount_str = amount_str.replace('.', ',')  # Replace decimal point with comma
                
                # Add thousand separators (space) for large numbers
                parts = amount_str.split(',')
                integer_part = parts[0]
                decimal_part = parts[1] if len(parts) > 1 else ""
                
                # Add space thousand separators to integer part
                if len(integer_part) > 3:
                    formatted_integer = ""
                    for i, digit in enumerate(reversed(integer_part)):
                        if i > 0 and i % 3 == 0:
                            formatted_integer = " " + formatted_integer
                        formatted_integer = digit + formatted_integer
                    integer_part = formatted_integer
                
                if decimal_part:
                    amount_str = f"{integer_part},{decimal_part}"
                else:
                    amount_str = integer_part
                
                # Translate unit suffixes for Polish
                if unit_suffix == "/min":
                    unit_suffix = " USD/min"
                elif unit_suffix == "/hr":
                    unit_suffix = " USD/godz."
                elif unit_suffix == "":
                    unit_suffix = " USD"
                
                return f"{amount_str}{unit_suffix}"
            else:
                # English format: "$0.04941340/min"
                prefix = "$" if not unit_suffix else "$"
                return f"{prefix}{amount:.8f}{unit_suffix}"
        except Exception as e:
            log_debug(f"Error formatting currency: {e}")
            return f"${amount:.8f}{unit_suffix}"  # Fallback to English format

    def format_cost_for_display(self, cost_value):
        """Format cost value according to current UI language (legacy method)."""
        return self.format_currency_for_display(cost_value, " USD" if self.ui_lang.current_lang == 'pol' else "")

    def update_gemini_stats(self):
        """Update the Gemini statistics fields by reading the log file."""
        try:
            # Check if all required components are available
            if not hasattr(self.translation_handler, '_get_cumulative_totals'):
                log_debug("TranslationHandler._get_cumulative_totals method not available")
                return
                
            if not (hasattr(self, 'gemini_total_words_var') and 
                    hasattr(self, 'gemini_total_cost_var') and
                    self.gemini_total_words_var is not None and 
                    self.gemini_total_cost_var is not None):
                log_debug("Gemini stats variables not initialized yet")
                return
                
            total_words, total_input, total_output = self.translation_handler._get_cumulative_totals()
            
            # Calculate total cost using the same logic as the translation handler
            # Get token costs from config
            input_cost_per_million = float(self.config['Settings'].get('input_token_cost', '0.1'))
            output_cost_per_million = float(self.config['Settings'].get('output_token_cost', '0.4'))
            
            total_input_cost = (total_input / 1_000_000) * input_cost_per_million
            total_output_cost = (total_output / 1_000_000) * output_cost_per_million
            total_cost = total_input_cost + total_output_cost
            
            # Update GUI fields
            self.gemini_total_words_var.set(str(total_words))
            self.gemini_total_cost_var.set(self.format_cost_for_display(total_cost))
            
            log_debug(f"Updated Gemini stats: {total_words} words, ${total_cost:.8f}")
        except Exception as e:
            log_debug(f"Error updating Gemini stats: {e}")
            # Set default values if there's an error
            if hasattr(self, 'gemini_total_words_var') and self.gemini_total_words_var is not None:
                self.gemini_total_words_var.set("0")
            if hasattr(self, 'gemini_total_cost_var') and self.gemini_total_cost_var is not None:
                self.gemini_total_cost_var.set(self.format_cost_for_display(0.0))

    def _delayed_gemini_stats_update(self):
        """Delayed stats update to ensure GUI is fully ready."""
        try:
            self.update_gemini_stats()
        except Exception as e:
            log_debug(f"Error in delayed Gemini stats update: {e}")

    def update_deepl_usage(self):
        """Update the DeepL usage display by calling the usage API."""
        try:
            # Check if all required components are available
            if not hasattr(self, 'deepl_usage_var') or self.deepl_usage_var is None:
                log_debug("DeepL usage variable not initialized yet")
                return
            
            # Only check usage if DeepL is available and we have translation handler
            if not hasattr(self, 'translation_handler') or not hasattr(self.translation_handler, 'get_deepl_usage'):
                log_debug("DeepL usage checking not available")
                self.deepl_usage_var.set("N/A")
                return
            
            usage_data = self.translation_handler.get_deepl_usage()
            
            if usage_data and isinstance(usage_data, dict):
                character_count = usage_data.get('character_count', 0)
                character_limit = usage_data.get('character_limit', 0)
                
                # Calculate usage percentage
                if character_limit > 0:
                    usage_percentage = (character_count / character_limit) * 100
                else:
                    usage_percentage = 0
                
                # Format according to UI language
                if self.ui_lang.current_lang == 'pol':
                    # Polish format: "Darmowy limit: 1 445 / 500 000 znaków (0,3%)"
                    used_formatted = f"{character_count:,}".replace(',', ' ')
                    limit_formatted = f"{character_limit:,}".replace(',', ' ')
                    percentage_formatted = f"{usage_percentage:.1f}".replace('.', ',')
                    usage_text = f"{used_formatted} / {limit_formatted} znaków ({percentage_formatted}%)"
                else:
                    # English format: "Free usage: 1,445 / 500,000 characters (0.3%)"
                    usage_text = f"{character_count:,} / {character_limit:,} characters ({usage_percentage:.1f}%)"
                
                self.deepl_usage_var.set(usage_text)
                log_debug(f"Updated DeepL usage: {character_count}/{character_limit} characters ({usage_percentage:.1f}%)")
            else:
                # Set fallback message if API call failed
                if self.ui_lang.current_lang == 'pol':
                    self.deepl_usage_var.set("Nie można pobrać danych użycia")
                else:
                    self.deepl_usage_var.set("Unable to retrieve usage data")
                log_debug("DeepL usage API call failed or returned invalid data")
        except Exception as e:
            log_debug(f"Error updating DeepL usage: {e}")
            # Set error fallback
            if hasattr(self, 'deepl_usage_var') and self.deepl_usage_var is not None:
                if hasattr(self, 'ui_lang') and self.ui_lang.current_lang == 'pol':
                    self.deepl_usage_var.set("Błąd podczas pobierania danych")
                else:
                    self.deepl_usage_var.set("Error retrieving usage data")

    def _delayed_deepl_usage_update(self):
        """Delayed DeepL usage update to ensure GUI is fully ready."""
        try:
            self.update_deepl_usage()
        except Exception as e:
            log_debug(f"Error in delayed DeepL usage update: {e}")

    def refresh_api_statistics(self):
        """Refresh and update API usage statistics display."""
        try:
            if hasattr(self, 'statistics_handler'):
                stats = self.statistics_handler.get_statistics()
                
                # Update OCR statistics
                ocr = stats['ocr']
                if hasattr(self, 'ocr_stat_vars'):
                    self.ocr_stat_vars['api_usage_total_ocr_cost'].set(self.format_currency_for_display(ocr['total_cost']))
                    self.ocr_stat_vars['api_usage_total_ocr_calls'].set(str(ocr['total_calls']))
                    self.ocr_stat_vars['api_usage_avg_cost_per_call'].set(self.format_currency_for_display(ocr['avg_cost_per_call']))
                    self.ocr_stat_vars['api_usage_avg_cost_per_minute'].set(self.format_currency_for_display(ocr['avg_cost_per_minute'], "/min"))
                    self.ocr_stat_vars['api_usage_avg_cost_per_hour'].set(self.format_currency_for_display(ocr['avg_cost_per_minute'] * 60, "/hr"))
                
                # Update Translation statistics
                trans = stats['translation']
                if hasattr(self, 'translation_stat_vars'):
                    self.translation_stat_vars['api_usage_total_translation_cost'].set(self.format_currency_for_display(trans['total_cost']))
                    self.translation_stat_vars['api_usage_total_words_translated'].set(str(trans['total_words']))
                    self.translation_stat_vars['api_usage_total_translation_calls'].set(str(trans['total_calls']))
                    self.translation_stat_vars['api_usage_avg_cost_per_word'].set(self.format_currency_for_display(trans['avg_cost_per_word']))
                    self.translation_stat_vars['api_usage_avg_cost_per_minute'].set(self.format_currency_for_display(trans['avg_cost_per_minute'], "/min"))
                    self.translation_stat_vars['api_usage_avg_cost_per_hour'].set(self.format_currency_for_display(trans['avg_cost_per_minute'] * 60, "/hr"))
                    
                    # Format words per minute with proper decimal separator
                    wpm_str = f"{trans['words_per_minute']:.2f}"
                    if self.ui_lang.current_lang == 'pol':
                        wpm_str = wpm_str.replace('.', ',')
                    self.translation_stat_vars['api_usage_words_per_minute'].set(wpm_str)
                
                # Update Combined statistics
                combined = stats['combined']
                if hasattr(self, 'combined_stat_vars'):
                    self.combined_stat_vars['api_usage_total_api_cost'].set(self.format_currency_for_display(combined['total_cost']))
                    self.combined_stat_vars['api_usage_combined_cost_per_minute'].set(self.format_currency_for_display(combined['combined_cost_per_minute'], "/min"))
                    self.combined_stat_vars['api_usage_combined_cost_per_hour'].set(self.format_currency_for_display(combined['combined_cost_per_minute'] * 60, "/hr"))
                
                log_debug("API statistics refreshed successfully")
            else:
                log_debug("Statistics handler not available")
        except Exception as e:
            log_debug(f"Error refreshing API statistics: {e}")
    
    def copy_statistics_to_clipboard(self):
        """Copy current API usage statistics to clipboard."""
        try:
            if hasattr(self, 'statistics_handler'):
                stats = self.statistics_handler.get_statistics()
                
                # Build formatted text matching the GUI layout exactly
                if self.ui_lang.current_lang == 'pol':
                    clipboard_text = "Game-Changing Translator - Statystyki użycia API\n"
                    clipboard_text += "=" * 50 + "\n\n"
                    
                    # OCR Statistics - match GUI order
                    clipboard_text += "📊 Statystyki Gemini OCR\n"
                    clipboard_text += "-" * 25 + "\n"
                    ocr = stats['ocr']
                    clipboard_text += f"Łączne wywołania OCR: {ocr['total_calls']}\n"
                    clipboard_text += f"Średni koszt na wywołanie: {self.format_currency_for_display(ocr['avg_cost_per_call'])}\n"
                    clipboard_text += f"Średni koszt na minutę: {self.format_currency_for_display(ocr['avg_cost_per_minute'], '/min')}\n"
                    clipboard_text += f"Średni koszt na godzinę: {self.format_currency_for_display(ocr['avg_cost_per_minute'] * 60, '/hr')}\n"
                    clipboard_text += f"Łączny koszt OCR: {self.format_currency_for_display(ocr['total_cost'])}\n\n"
                    
                    # Translation Statistics - match GUI order
                    clipboard_text += "🔄 Statystyki tłumaczenia Gemini\n"
                    clipboard_text += "-" * 30 + "\n"
                    trans = stats['translation']
                    clipboard_text += f"Łączne wywołania tłumaczenia: {trans['total_calls']}\n"
                    clipboard_text += f"Łącznie słów przetłumaczonych: {trans['total_words']}\n"
                    wpm_str = f"{trans['words_per_minute']:.2f}".replace('.', ',')
                    clipboard_text += f"Średnia słów na minutę: {wpm_str}\n"
                    clipboard_text += f"Średni koszt na słowo: {self.format_currency_for_display(trans['avg_cost_per_word'])}\n"
                    clipboard_text += f"Średni koszt na minutę: {self.format_currency_for_display(trans['avg_cost_per_minute'], '/min')}\n"
                    clipboard_text += f"Średni koszt na godzinę: {self.format_currency_for_display(trans['avg_cost_per_minute'] * 60, '/hr')}\n"
                    clipboard_text += f"Łączny koszt tłumaczenia: {self.format_currency_for_display(trans['total_cost'])}\n\n"
                    
                    # Combined Statistics - match GUI order
                    clipboard_text += "💰 Łączne statystyki API\n"
                    clipboard_text += "-" * 25 + "\n"
                    combined = stats['combined']
                    clipboard_text += f"Łączny koszt API: {self.format_currency_for_display(combined['total_cost'])}\n"
                    clipboard_text += f"Łączny koszt na minutę: {self.format_currency_for_display(combined['combined_cost_per_minute'], '/min')}\n"
                    clipboard_text += f"Łączny koszt na godzinę: {self.format_currency_for_display(combined['combined_cost_per_minute'] * 60, '/hr')}\n\n"
                    
                    # DeepL Usage Monitor
                    clipboard_text += "📈 Monitor użycia DeepL\n"
                    clipboard_text += "-" * 25 + "\n"
                    if hasattr(self, 'deepl_usage_var'):
                        deepl_usage = self.deepl_usage_var.get()
                        clipboard_text += f"Darmowy miesięczny limit: {deepl_usage}\n"
                    else:
                        clipboard_text += "Darmowy miesięczny limit: N/A\n"
                else:
                    clipboard_text = "Game-Changing Translator - API Usage Statistics\n"
                    clipboard_text += "=" * 50 + "\n\n"
                    
                    # OCR Statistics - match GUI order
                    clipboard_text += "📊 Gemini OCR Statistics\n"
                    clipboard_text += "-" * 25 + "\n"
                    ocr = stats['ocr']
                    clipboard_text += f"Total OCR Calls: {ocr['total_calls']}\n"
                    clipboard_text += f"Average Cost per Call: {self.format_currency_for_display(ocr['avg_cost_per_call'])}\n"
                    clipboard_text += f"Average Cost per Minute: {self.format_currency_for_display(ocr['avg_cost_per_minute'], '/min')}\n"
                    clipboard_text += f"Average Cost per Hour: {self.format_currency_for_display(ocr['avg_cost_per_minute'] * 60, '/hr')}\n"
                    clipboard_text += f"Total OCR Cost: {self.format_currency_for_display(ocr['total_cost'])}\n\n"
                    
                    # Translation Statistics - match GUI order
                    clipboard_text += "🔄 Gemini Translation Statistics\n"
                    clipboard_text += "-" * 30 + "\n"
                    trans = stats['translation']
                    clipboard_text += f"Total Translation Calls: {trans['total_calls']}\n"
                    clipboard_text += f"Total Words Translated: {trans['total_words']}\n"
                    clipboard_text += f"Average Words per Minute: {trans['words_per_minute']:.2f}\n"
                    clipboard_text += f"Average Cost per Word: {self.format_currency_for_display(trans['avg_cost_per_word'])}\n"
                    clipboard_text += f"Average Cost per Minute: {self.format_currency_for_display(trans['avg_cost_per_minute'], '/min')}\n"
                    clipboard_text += f"Average Cost per Hour: {self.format_currency_for_display(trans['avg_cost_per_minute'] * 60, '/hr')}\n"
                    clipboard_text += f"Total Translation Cost: {self.format_currency_for_display(trans['total_cost'])}\n\n"
                    
                    # Combined Statistics - match GUI order
                    clipboard_text += "💰 Combined API Statistics\n"
                    clipboard_text += "-" * 25 + "\n"
                    combined = stats['combined']
                    clipboard_text += f"Total API Cost: {self.format_currency_for_display(combined['total_cost'])}\n"
                    clipboard_text += f"Combined Cost per Minute: {self.format_currency_for_display(combined['combined_cost_per_minute'], '/min')}\n"
                    clipboard_text += f"Combined Cost per Hour: {self.format_currency_for_display(combined['combined_cost_per_minute'] * 60, '/hr')}\n\n"
                    
                    # DeepL Usage Monitor
                    clipboard_text += "📈 DeepL Usage Monitor\n"
                    clipboard_text += "-" * 25 + "\n"
                    if hasattr(self, 'deepl_usage_var'):
                        deepl_usage = self.deepl_usage_var.get()
                        clipboard_text += f"Free Monthly Limit: {deepl_usage}\n"
                    else:
                        clipboard_text += "Free Monthly Limit: N/A\n"
                
                # Copy to clipboard
                self.root.clipboard_clear()
                self.root.clipboard_append(clipboard_text)
                self.root.update()  # Update clipboard
                
                # Show confirmation
                if self.ui_lang.current_lang == 'pol':
                    messagebox.showinfo("Skopiowano", "Statystyki zostały skopiowane do schowka.")
                else:
                    messagebox.showinfo("Copied", "Statistics copied to clipboard.")
                
                log_debug("Statistics copied to clipboard")
            else:
                log_debug("Statistics handler not available for clipboard copy")
                
        except Exception as e:
            log_debug(f"Error copying statistics to clipboard: {e}")
            error_msg = "Błąd podczas kopiowania do schowka." if self.ui_lang.current_lang == 'pol' else "Error copying to clipboard."
            messagebox.showerror("Error", f"{error_msg}\n{str(e)}")

    def export_statistics_csv(self):
        """Export API usage statistics to CSV file."""
        try:
            from tkinter import filedialog
            
            # Ask user for file location
            file_path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                title="Export Statistics to CSV"
            )
            
            if file_path and hasattr(self, 'statistics_handler'):
                success = self.statistics_handler.export_statistics_csv(file_path)
                if success:
                    messagebox.showinfo("Export Successful", f"Statistics exported to:\n{file_path}")
                else:
                    messagebox.showerror("Export Failed", "Failed to export statistics to CSV.")
            
        except Exception as e:
            log_debug(f"Error exporting statistics to CSV: {e}")
            messagebox.showerror("Export Error", f"Error exporting statistics: {str(e)}")
    
    def export_statistics_text(self):
        """Export API usage statistics to text file."""
        try:
            from tkinter import filedialog
            
            # Ask user for file location
            file_path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
                title="Export Statistics to Text"
            )
            
            if file_path and hasattr(self, 'statistics_handler'):
                success = self.statistics_handler.export_statistics_text(file_path, self.ui_lang)
                if success:
                    messagebox.showinfo("Export Successful", f"Statistics exported to:\n{file_path}")
                else:
                    messagebox.showerror("Export Failed", "Failed to export statistics to text.")
            
        except Exception as e:
            log_debug(f"Error exporting statistics to text: {e}")
            messagebox.showerror("Export Error", f"Error exporting statistics: {str(e)}")

    def toggle_debug_logging(self):
        """Toggle debug logging on/off and update button text."""
        current_state = self.debug_logging_enabled_var.get()
        new_state = not current_state
        
        # Log state change before changing the state
        if current_state:
            log_debug("Debug logging disabled by user")
        
        # Update the state
        self.debug_logging_enabled_var.set(new_state)
        set_debug_logging_enabled(new_state)
        
        # Log state change after enabling (if we're enabling)
        if new_state:
            log_debug("Debug logging enabled by user")
        
        # Update button text
        if hasattr(self, 'debug_log_toggle_btn') and self.debug_log_toggle_btn.winfo_exists():
            if new_state:
                button_text = self.ui_lang.get_label("toggle_debug_log_disable_btn")
            else:
                button_text = self.ui_lang.get_label("toggle_debug_log_enable_btn")
            self.debug_log_toggle_btn.config(text=button_text)
            
        # Save settings
        if self._fully_initialized:
            self.save_settings()

    def show_ocr_preview(self):
        """Show/create the OCR Preview window."""
        # Check if window already exists and is valid
        if self.ocr_preview_window is not None:
            try:
                if self.ocr_preview_window.winfo_exists():
                    # Window already exists, just bring to front
                    self.ocr_preview_window.lift()
                    self.ocr_preview_window.attributes('-topmost', True)
                    self.ocr_preview_window.after(100, lambda: self.ocr_preview_window.attributes('-topmost', False))
                    return
            except tk.TclError:
                # Window was destroyed but variable wasn't cleared
                self.ocr_preview_window = None
        
        # Create new preview window
        self.ocr_preview_window = tk.Toplevel(self.root)
        self.ocr_preview_window.title(self.ui_lang.get_label("ocr_preview_title", "OCR Preview"))
        self.ocr_preview_window.minsize(400, 500)
        
        # Load window geometry from config
        load_ocr_preview_geometry(self.config, self.ocr_preview_window)
        
        # Create main frame
        main_frame = ttk.Frame(self.ocr_preview_window)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Image section - with horizontal scrollbar (no extra space) - NEW APPROACH
        image_frame = ttk.LabelFrame(main_frame, text=self.ui_lang.get_label("processed_image_preview", "Processed Image (1:1 scale)"))
        image_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Create frame for image content that won't expand
        content_frame = ttk.Frame(image_frame)
        content_frame.pack(fill="x", padx=5, pady=5)
        
        # Create canvas with scrollbars - but don't let it expand vertically
        image_canvas = tk.Canvas(content_frame, bd=0, highlightthickness=0, relief='flat', height=200)
        h_scrollbar = ttk.Scrollbar(content_frame, orient="horizontal", command=image_canvas.xview)
        v_scrollbar = ttk.Scrollbar(content_frame, orient="vertical", command=image_canvas.yview)
        
        image_canvas.configure(xscrollcommand=h_scrollbar.set, yscrollcommand=v_scrollbar.set)
        
        # Pack with no expand for vertical
        v_scrollbar.pack(side="right", fill="y")
        h_scrollbar.pack(side="bottom", fill="x")
        image_canvas.pack(side="left", fill="both", expand=True)
        
        # Create label inside canvas for image display
        self.preview_image_label = ttk.Label(image_canvas, text=self.ui_lang.get_label("no_image_processed", "No image processed yet"), 
                                            anchor="center", justify="center")
        
        # Add label to canvas
        self.preview_image_canvas_item = image_canvas.create_window(0, 0, anchor="nw", window=self.preview_image_label)
        
        # Store canvas reference for updating scroll region
        self.preview_image_canvas = image_canvas
        
        # Bind canvas resize to update scroll region
        def on_canvas_configure(event):
            # Update the scroll region to encompass the image
            image_canvas.configure(scrollregion=image_canvas.bbox("all"))
        
        image_canvas.bind('<Configure>', on_canvas_configure)
        
        # Text section
        text_frame = ttk.LabelFrame(main_frame, text=self.ui_lang.get_label("recognized_text_preview", "Recognized Text"))
        text_frame.pack(fill="x", padx=5, pady=5)
        
        self.preview_text_widget = tk.Text(text_frame, height=8, wrap=tk.WORD)
        text_scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.preview_text_widget.yview)
        self.preview_text_widget.configure(yscrollcommand=text_scrollbar.set)
        
        text_scrollbar.pack(side="right", fill="y")
        self.preview_text_widget.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        
        # Control buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=5)
        
        ttk.Button(button_frame, text=self.ui_lang.get_label("refresh_preview", "Refresh Preview"), 
                  command=self.refresh_ocr_preview).pack(side="left", padx=5)
        ttk.Button(button_frame, text=self.ui_lang.get_label("close_btn", "Close"), 
                  command=self.close_ocr_preview).pack(side="right", padx=5)
        
        # Set up proper window close protocol
        self.ocr_preview_window.protocol("WM_DELETE_WINDOW", self.close_ocr_preview)
        
        # Set up window geometry saving on window events
        def on_preview_configure(event):
            if event.widget == self.ocr_preview_window:
                # Save geometry when window is moved or resized
                if hasattr(self, '_preview_geometry_timer'):
                    self.root.after_cancel(self._preview_geometry_timer)
                self._preview_geometry_timer = self.root.after(500, self.save_preview_geometry)
        
        self.ocr_preview_window.bind('<Configure>', on_preview_configure)
        
        # Start continuous real-time updates (regardless of translation state)
        self.start_preview_realtime_updates()
        
        # Initial preview update
        self.refresh_ocr_preview()

    def close_ocr_preview(self):
        """Properly close the OCR Preview window."""
        if self.ocr_preview_window is not None:
            try:
                # Save window geometry before closing
                self.save_preview_geometry()
                
                # Cancel any pending refresh timer
                if hasattr(self, '_preview_refresh_timer'):
                    self.root.after_cancel(self._preview_refresh_timer)
                
                # Cancel geometry save timer
                if hasattr(self, '_preview_geometry_timer'):
                    self.root.after_cancel(self._preview_geometry_timer)
                
                # Stop real-time updates
                self.stop_preview_realtime_updates()
                
                # Destroy the window
                self.ocr_preview_window.destroy()
            except tk.TclError:
                # Window might already be destroyed
                pass
            finally:
                # Always clear the reference
                self.ocr_preview_window = None

    def save_preview_geometry(self):
        """Save OCR Preview window geometry to config."""
        if self.ocr_preview_window is not None:
            try:
                save_ocr_preview_geometry(self.config, self.ocr_preview_window)
                save_app_config(self.config)
            except Exception as e:
                log_debug(f"Error saving OCR Preview geometry: {e}")
    
    def start_preview_realtime_updates(self):
        """Start continuous real-time updates for OCR Preview window regardless of translation state."""
        if self.ocr_preview_window is not None:
            try:
                if self.ocr_preview_window.winfo_exists():
                    # Update every 500ms continuously (both when translation is running and stopped)
                    self._preview_realtime_timer = self.root.after(500, self.preview_realtime_update)
                else:
                    self.ocr_preview_window = None
            except tk.TclError:
                self.ocr_preview_window = None
    
    def stop_preview_realtime_updates(self):
        """Stop real-time updates for OCR Preview window."""
        if hasattr(self, '_preview_realtime_timer'):
            self.root.after_cancel(self._preview_realtime_timer)
            delattr(self, '_preview_realtime_timer')
    
    def preview_realtime_update(self):
        """Real-time update function for OCR Preview window - works regardless of translation state."""
        if self.ocr_preview_window is not None:
            try:
                if self.ocr_preview_window.winfo_exists():
                    # Refresh preview with current data (works both when translation is on/off)
                    self.refresh_ocr_preview()
                    # Schedule next update
                    self._preview_realtime_timer = self.root.after(500, self.preview_realtime_update)
                else:
                    self.ocr_preview_window = None
            except tk.TclError:
                self.ocr_preview_window = None

    def refresh_ocr_preview(self):
        """Refresh the OCR preview with current settings and captured image."""
        # Check if window still exists
        if self.ocr_preview_window is None:
            return
            
        try:
            if not self.ocr_preview_window.winfo_exists():
                self.ocr_preview_window = None
                return
        except tk.TclError:
            # Window was destroyed
            self.ocr_preview_window = None
            return
        
        try:
            # Get current settings
            prep_mode = self.preprocessing_mode_var.get()
            block_size = self.adaptive_block_size_var.get()
            c_value = self.adaptive_c_var.get()
            
            # Always try to capture from source area for real-time preview (independent of translation state)
            screenshot_pil = None
            if self.source_overlay and self.source_overlay.winfo_exists():
                try:
                    area = self.source_overlay.get_geometry()
                    if area:
                        x1, y1, x2, y2 = map(int, area)
                        width, height = x2-x1, y2-y1
                        if width > 0 and height > 0:
                            import pyautogui
                            screenshot_pil = pyautogui.screenshot(region=(x1, y1, width, height))
                        else:
                            screenshot_pil = None
                    else:
                        screenshot_pil = None
                except Exception as e:
                    log_debug(f"Error capturing for preview: {e}")
                    screenshot_pil = None
            
            # Fallback to using last_screenshot only if direct capture failed
            if screenshot_pil is None and hasattr(self, 'last_screenshot') and self.last_screenshot:
                screenshot_pil = self.last_screenshot
            
            if screenshot_pil:
                # Optimized image processing: Direct PIL to OpenCV conversion
                img_np = np.array(screenshot_pil)
                img_shape = img_np.shape
                
                # Optimized conversion based on common cases (avoid repeated checks)
                if len(img_shape) == 3:
                    if img_shape[2] == 3:  # RGB - most common case
                        img_cv_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
                    elif img_shape[2] == 4:  # RGBA
                        img_cv_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGBA2BGR)
                    else:
                        raise ValueError(f"Unexpected 3D image channels: {img_shape[2]}")
                elif len(img_shape) == 2:  # Grayscale
                    img_cv_bgr = cv2.cvtColor(img_np, cv2.COLOR_GRAY2BGR)
                else:
                    raise ValueError(f"Unexpected image dimensions: {len(img_shape)}D")
                
                # Process image
                from ocr_utils import preprocess_for_ocr
                processed_cv_img = preprocess_for_ocr(img_cv_bgr, prep_mode, block_size, c_value)
                
                # Convert processed image to PIL for display
                processed_pil = Image.fromarray(processed_cv_img)
                processed_tk = ImageTk.PhotoImage(processed_pil)
                
                # Update image display in canvas
                self.preview_image_label.configure(image=processed_tk, text="")
                self.preview_image_label.image = processed_tk  # Keep reference
                
                # Update canvas scroll region to fit the image
                self.preview_image_label.update_idletasks()  # Ensure label has correct size
                image_width = processed_tk.width()
                image_height = processed_tk.height()
                
                # Adjust canvas height to fit image (with reasonable limits)
                canvas_height = min(image_height, 400)  # Max height of 400 pixels
                self.preview_image_canvas.configure(height=canvas_height)
                
                # Update the canvas window size and scroll region
                self.preview_image_canvas.itemconfig(self.preview_image_canvas_item, width=image_width, height=image_height)
                self.preview_image_canvas.configure(scrollregion=(0, 0, image_width, image_height))
                
                # Perform OCR on processed image with all post-processing steps
                tess_langs = self.get_tesseract_lang_code()
                from ocr_utils import get_tesseract_model_params, ocr_region_with_confidence, post_process_ocr_text_general, remove_text_after_last_punctuation_mark
                
                tess_params = get_tesseract_model_params('general')
                full_img_region = (0, 0, processed_cv_img.shape[1], processed_cv_img.shape[0])
                confidence_threshold = self.confidence_var.get()
                
                ocr_raw_text = ocr_region_with_confidence(processed_cv_img, full_img_region, tess_langs, tess_params, confidence_threshold)
                ocr_cleaned_text = post_process_ocr_text_general(ocr_raw_text, tess_langs)
                
                # Apply post-processing steps including "Remove Trailing Garbage" if enabled
                if self.remove_trailing_garbage_var.get() and ocr_cleaned_text:
                    ocr_cleaned_text = remove_text_after_last_punctuation_mark(ocr_cleaned_text)
                
                # Update text display
                self.preview_text_widget.config(state=tk.NORMAL)
                self.preview_text_widget.delete(1.0, tk.END)
                self.preview_text_widget.insert(tk.END, ocr_cleaned_text if ocr_cleaned_text else self.ui_lang.get_label("no_text_recognized", "No text recognized"))
                self.preview_text_widget.config(state=tk.DISABLED)
                
            else:
                # No image available
                self.preview_image_label.configure(image="", text=self.ui_lang.get_label("no_image_captured", "No image captured yet"))
                self.preview_image_label.image = None
                
                # Reset canvas to default size for text display
                self.preview_image_canvas.configure(height=100)  # Small height for text
                
                # Reset canvas scroll region for text display
                self.preview_image_label.update_idletasks()
                label_width = self.preview_image_label.winfo_reqwidth()
                label_height = self.preview_image_label.winfo_reqheight()
                
                self.preview_image_canvas.itemconfig(self.preview_image_canvas_item, width=label_width, height=label_height)
                self.preview_image_canvas.configure(scrollregion=(0, 0, label_width, label_height))
                
                self.preview_text_widget.config(state=tk.NORMAL)
                self.preview_text_widget.delete(1.0, tk.END)
                self.preview_text_widget.insert(tk.END, self.ui_lang.get_label("no_image_for_ocr", "No image available for OCR"))
                self.preview_text_widget.config(state=tk.DISABLED)
                
        except Exception as e:
            log_debug(f"Error refreshing OCR preview: {e}")
            # Show error in preview
            if hasattr(self, 'preview_text_widget') and self.preview_text_widget.winfo_exists():
                self.preview_text_widget.config(state=tk.NORMAL)
                self.preview_text_widget.delete(1.0, tk.END)
                self.preview_text_widget.insert(tk.END, f"Error: {str(e)}")
                self.preview_text_widget.config(state=tk.DISABLED)

    def load_initial_overlay_areas(self):
        load_areas_from_config_om(self)

    def select_source_area(self):
        select_source_area_om(self)
        self.save_settings() 

    def select_target_area(self):
        select_target_area_om(self)
        self.save_settings() 

    def create_source_overlay(self):
        create_source_overlay_om(self)

    def create_target_overlay(self):
        create_target_overlay_om(self)

    def toggle_source_visibility(self):
        toggle_source_visibility_om(self)
        self.save_settings() 

    def toggle_target_visibility(self):
        toggle_target_visibility_om(self)

    def clear_file_caches(self):
        self.cache_manager.clear_file_caches()

    def clear_cache(self):
        """Clear unified translation cache - FIXED VERSION (No pause/resume needed)."""
        try:
            log_debug("Clearing unified translation cache...")
            
            # Notify MarianMT translator about cache clearing FIRST
            if hasattr(self, 'marian_translator') and self.marian_translator:
                try:
                    if hasattr(self.marian_translator, 'notify_cache_cleared'):
                        self.marian_translator.notify_cache_cleared()
                        log_debug("Notified MarianMT translator about cache clearing.")
                    else:
                        log_debug("MarianMT translator does not have notify_cache_cleared method.")
                except Exception as e_notify:
                    log_debug(f"Error notifying MarianMT about cache clearing: {e_notify}")
            
            # Clear unified cache (thread-safe, no need to pause translation)
            self.translation_handler.clear_cache()
            
            # Clear in-memory file cache representations (Level 2 persistence remains)
            self.google_file_cache.clear()
            self.deepl_file_cache.clear()
            log_debug("Cleared in-memory representations of file caches.")

            # Clear queues
            self._clear_queue(self.ocr_queue)
            self._clear_queue(self.translation_queue)
            log_debug("Cleared OCR and translation queues.")

            # Reset text processing state
            self.text_stability_counter = 0
            self.previous_text = ""
            self.translation_cache.clear()
            log_debug("Unified translation cache and related states cleared successfully.")

            # Update status briefly
            original_status_text = self.status_label.cget("text")
            self.status_label.config(text="Status: Cache cleared")
            if self.root.winfo_exists():
                self.root.after(2000, lambda: self.status_label.config(text=original_status_text) if self.status_label.winfo_exists() else None)
                    
        except Exception as e_cc:
            log_debug(f"Error clearing unified cache: {e_cc}")
            if self.root.winfo_exists():
                messagebox.showerror("Error", f"Failed to clear cache: {e_cc}", parent=self.root)
            original_status_text = self.status_label.cget("text")
            self.status_label.config(text="Status: Cache clearing failed")
            self.root.after(2000, lambda: self.status_label.config(text=original_status_text) if self.status_label.winfo_exists() else None)

    def _clear_queue(self, q_to_clear):
        items_cleared_count = 0
        while not q_to_clear.empty():
            try:
                q_to_clear.get_nowait()
                items_cleared_count += 1
            except queue.Empty:
                break 
            except Exception as e_cq:
                log_debug(f"Error clearing queue {type(q_to_clear).__name__}: {e_cq}")
                break 
        if items_cleared_count > 0:
            log_debug(f"Cleared {items_cleared_count} items from {type(q_to_clear).__name__}.")

    def _reset_gemini_batch_state(self):
        """Reset Gemini OCR batch management state for clean start."""
        self.batch_sequence_counter = 0
        self.last_displayed_batch_sequence = 0
        self.active_ocr_calls = set()
        self.last_processed_subtitle = None
        self.clear_timeout_timer_start = None
        log_debug("Gemini OCR batch state reset")

    def toggle_translation(self):
        if self.is_running:
            log_debug("Stopping translation process requested by user.")
            self.is_running = False
            
            # End sessions if they are active
            if hasattr(self, 'translation_handler'):
                self.translation_handler.request_end_ocr_session()
                self.translation_handler.request_end_translation_session()
            
            # Clear Gemini context when translation is stopped
            if (hasattr(self, 'translation_handler') and 
                hasattr(self.translation_handler, '_clear_gemini_context')):
                self.translation_handler._clear_gemini_context()
            
            # Update usage statistics when translation stops
            if hasattr(self, 'update_gemini_stats'):
                self.update_gemini_stats()
            if hasattr(self, 'update_deepl_usage'):
                self.update_deepl_usage()
            
            self.start_stop_btn.config(text="Start", state=tk.DISABLED)
            self.status_label.config(text="Status: Stopping...")
            self.root.update_idletasks()

            active_threads_copy = self.threads[:]
            self.threads.clear()

            thread_stop_start_time = time.monotonic()
            log_debug(f"Waiting for threads to join: {[t.name for t in active_threads_copy if t.is_alive()]}")

            for thread_obj in active_threads_copy:
                if thread_obj.is_alive():
                    try:
                        thread_obj.join(timeout=1.0)
                        if thread_obj.is_alive():
                             log_debug(f"Warning: Thread {thread_obj.name} did not terminate within timeout.")
                    except Exception as join_err_tt:
                        log_debug(f"Error joining thread {thread_obj.name}: {join_err_tt}")

            log_debug(f"Thread joining process completed in {time.monotonic() - thread_stop_start_time:.2f}s.")

            self._clear_queue(self.ocr_queue)
            self._clear_queue(self.translation_queue)

            if self.translation_text and self.translation_text.winfo_exists():
                try:
                    self.translation_text.config(state=tk.NORMAL)
                    self.translation_text.delete(1.0, tk.END)
                    self.translation_text.config(state=tk.DISABLED)
                except tk.TclError as e_ctt:
                    log_debug(f"Error clearing translation text on stop: {e_ctt}")
            
            if self.source_overlay and self.source_overlay.winfo_exists() and self.source_overlay.winfo_viewable():
                try: self.source_overlay.hide()
                except tk.TclError: log_debug("Error hiding source overlay on stop (likely closed).")
            
            if self.target_overlay and self.target_overlay.winfo_exists() and self.target_overlay.winfo_viewable():
                try: self.target_overlay.hide()
                except tk.TclError: log_debug("Error hiding target overlay on stop (likely closed).")
            
            # Stop OCR Preview real-time updates - REMOVED, now runs continuously
            
            self.start_stop_btn.config(state=tk.NORMAL)
            status_text_stopped = "Status: " + self.ui_lang.get_label("status_stopped", "Stopped (Press ~ to Start)")
            self.status_label.config(text=status_text_stopped)
            log_debug("Translation process stopped.")
        else: 
            log_debug("Starting translation process requested by user...")
            self.start_stop_btn.config(state=tk.DISABLED) 
            self.status_label.config(text="Status: Initializing...")
            self.root.update_idletasks()

            valid_start_flag = True 
            if not self.source_overlay or not self.source_overlay.winfo_exists():
                messagebox.showerror("Start Error", "Source area overlay missing. Select source area.", parent=self.root)
                valid_start_flag = False
            if valid_start_flag and (not self.target_overlay or not self.target_overlay.winfo_exists()):
                messagebox.showerror("Start Error", "Target area overlay missing. Select target area.", parent=self.root)
                valid_start_flag = False
            if valid_start_flag and (not self.translation_text or not self.translation_text.winfo_exists()):
                 messagebox.showerror("Start Error", "Target text display widget missing. Reselect target area.", parent=self.root)
                 valid_start_flag = False
            
            tesseract_exe_path = self.tesseract_path_var.get()
            if valid_start_flag and (not tesseract_exe_path or not os.path.isfile(tesseract_exe_path)):
                messagebox.showerror("Start Error", f"Tesseract path invalid:\n{tesseract_exe_path}\nCheck Settings.", parent=self.root)
                valid_start_flag = False
            elif valid_start_flag and pytesseract.pytesseract.tesseract_cmd != tesseract_exe_path:
                 pytesseract.pytesseract.tesseract_cmd = tesseract_exe_path
                 log_debug(f"Runtime Tesseract path updated to: {tesseract_exe_path}")
            
            if valid_start_flag:
                 try:
                     self.source_area = self.source_overlay.get_geometry()
                     self.target_area = self.target_overlay.get_geometry()
                     if not self._validate_area_coords(self.source_area, "source"): valid_start_flag = False
                     if valid_start_flag and not self._validate_area_coords(self.target_area, "target"): valid_start_flag = False
                 except (tk.TclError, AttributeError) as e_gog:
                     messagebox.showerror("Start Error", f"Could not get overlay geometry: {e_gog}", parent=self.root)
                     valid_start_flag = False
            
            if not valid_start_flag:
                self.start_stop_btn.config(state=tk.NORMAL)
                status_text_failed = "Status: Start Failed"
                if self.KEYBOARD_AVAILABLE: status_text_failed += " (Press ~ to Retry)"
                self.status_label.config(text=status_text_failed)
                log_debug("Start aborted due to failed pre-start validation checks.")
                return
            
            log_debug("Pre-start checks passed. Preparing to start threads...")
            self.text_stability_counter = 0
            self.previous_text = ""
            self.last_image_hash = None
            self.last_screenshot = None 
            self.last_processed_image = None 
            
            # Reset Gemini OCR batch management state
            self._reset_gemini_batch_state() 

            try:
                if self.target_overlay and self.target_overlay.winfo_exists() and not self.target_overlay.winfo_viewable():
                    self.target_overlay.show()
            except tk.TclError:
                log_debug("Warning: Error ensuring target overlay visibility at start (likely closed).")

            self._clear_queue(self.ocr_queue)
            self._clear_queue(self.translation_queue)

            # Reload file caches to ensure we have the most up-to-date cached translations
            log_debug("Reloading file caches to ensure up-to-date translations...")
            self.cache_manager.load_file_caches()

            self.is_running = True 
            
            # Start appropriate sessions based on settings
            if hasattr(self, 'translation_handler'):
                # Start OCR session if using Gemini OCR
                if self.get_ocr_model_setting() == 'gemini':
                    self.translation_handler.start_ocr_session()
                
                # Start translation session if using Gemini translation
                if self.translation_model_var.get() == 'gemini_api':
                    self.translation_handler.start_translation_session()
            
            self.start_stop_btn.config(text="Stop", state=tk.NORMAL)
            status_text_running = "Status: " + self.ui_lang.get_label("status_running", "Running (Press ~ to Stop)")
            self.status_label.config(text=status_text_running)
            self.root.update_idletasks()
            
            capture_thread_instance = threading.Thread(target=run_capture_thread, args=(self,), name="CaptureThread", daemon=True)
            ocr_thread_instance = threading.Thread(target=run_ocr_thread, args=(self,), name="OCRThread", daemon=True)
            translation_thread_instance = threading.Thread(target=run_translation_thread, args=(self,), name="TranslationThread", daemon=True)

            self.threads = [capture_thread_instance, ocr_thread_instance, translation_thread_instance]
            for t_obj in self.threads:
                t_obj.start()
            log_debug(f"Threads started: {[t.name for t in self.threads]}")
            
            # OCR Preview real-time updates run continuously, no need to start/stop with translation

    def _validate_area_coords(self, area_coordinates, area_type_str):
        min_dimension = 10 
        if not area_coordinates or len(area_coordinates) != 4:
            messagebox.showerror("Area Validation Error", f"Invalid {area_type_str} area data: {area_coordinates}.", parent=self.root)
            return False
        try:
            x1_val, y1_val, x2_val, y2_val = map(int, area_coordinates)
            width_val = x2_val - x1_val
            height_val = y2_val - y1_val
            if width_val < min_dimension or height_val < min_dimension:
                messagebox.showerror("Area Validation Error",
                                     f"{area_type_str.capitalize()} area too small ({width_val}x{height_val}). Min {min_dimension}x{min_dimension}.",
                                     parent=self.root)
                return False
            return True
        except (ValueError, TypeError) as e_vac:
            messagebox.showerror("Area Validation Error", f"Invalid coordinates in {area_type_str} area: {area_coordinates}. Error: {e_vac}", parent=self.root)
            return False

    def stop_translation_from_thread(self):
        if self.is_running:
            log_debug("Requesting stop translation from worker thread.")
            if self.root.winfo_exists():
                self.root.after(0, self.toggle_translation)

    def update_translation_model_names(self):
        """Update translation model names with localized strings from CSV files."""
        self.translation_model_names = {
            'gemini_api': 'Gemini 2.5 Flash-Lite',  # Keep English as these are API names
            'google_api': 'Google Translate API',  # Keep English as these are API names
            'deepl_api': 'DeepL API',  # Keep English as these are API names
            'marianmt': self.ui_lang.get_label('translation_model_marianmt_offline', 'MarianMT (offline and free)')
        }
        # Update the reverse mapping as well
        self.translation_model_values = {v: k for k, v in self.translation_model_names.items()}
        log_debug(f"Updated translation model names: {self.translation_model_names}")

    def update_ui_language(self):
        """Update all UI elements to reflect the selected language"""
        try:
            # Start comprehensive UI update - suppresses all saves and traces
            self.start_ui_update()
            
            # Update translation model names with new language
            self.update_translation_model_names()
            
            # The most comprehensive way to fully update the UI is to destroy and recreate all tabs
            # First, save the current tab selection
            selected_tab = self.tab_control.select()
            
            # First, destroy all existing tabs
            for i in range(self.tab_control.index('end')-1, -1, -1):
                self.tab_control.forget(i)
            
            # The tabs will be created and assigned in the create_*_tab functions
            self.tab_main = None
            self.tab_settings = None
            self.tab_api_usage = None
            self.tab_debug = None
            self.tab_about = None
            
            # Recreate all tabs with the new language
            from gui_builder import create_main_tab, create_settings_tab, create_api_usage_tab, create_debug_tab
            from ui_elements import create_scrollable_tab
            
            # Rebuild all tabs with the new language
            create_main_tab(self)
            create_settings_tab(self)
            create_api_usage_tab(self)
            create_debug_tab(self)
            
            # Recreate About tab with scrollable content
            scrollable_about = create_scrollable_tab(self.tab_control, self.ui_lang.get_label("about_tab_title", "About"))
            self.tab_about = scrollable_about
            
            # Create the about frame inside the scrollable area
            about_frame = ttk.LabelFrame(scrollable_about, text=self.ui_lang.get_label("about_tab_title", "About"))
            about_frame.pack(fill="both", expand=True, padx=10, pady=10)
            
            # Hard-coded About content based on language
            if self.ui_lang.current_lang == 'pol':
                about_text = """Copyright © 2025 Tomasz Kamiński

Game-Changing Translator to program komputerowy, który automatycznie przechwytuje tekst z\u00a0dowolnego fragmentu ekranu, przeprowadza optyczne rozpoznawanie znaków (OCR) i\u00a0tłumaczy tekst w\u00a0czasie rzeczywistym. Może służyć do tłumaczenia napisów w\u00a0grach lub dowolnego innego tekstu, którego nie można łatwo skopiować.

Program został napisany w\u00a0języku Python przy użyciu następujących modeli sztucznej inteligencji: Claude\u00a03.7\u00a0Sonnet, Claude\u00a0Sonnet\u00a04 i\u00a0Gemini\u00a02.5\u00a0Pro.

Więcej informacji zawiera instrukcja obsługi."""
            else:
                about_text = """Copyright © 2025 Tomasz Kamiński

Game-Changing Translator is a desktop application that automatically captures text from any area of your screen, performs optical character recognition (OCR), and translates the text in real-time. You can use it for translating video game subtitles or any other text that you can't easily copy.

This application was developed in Python using the following AI models: Claude\u00a03.7\u00a0Sonnet, Claude\u00a0Sonnet\u00a04 and Gemini\u00a02.5\u00a0Pro.

For more information, see the user manual."""
            
            # Use Text widget for proper wrapping
            about_text_widget = tk.Text(about_frame, wrap=tk.WORD, relief="flat", 
                                       borderwidth=0, highlightthickness=0)
            about_text_widget.pack(fill="both", expand=True, padx=20, pady=20)
            about_text_widget.insert(tk.END, about_text)
            about_text_widget.config(state=tk.DISABLED)  # Make it read-only
            
            # Update translation model UI visibility based on current selection
            self.ui_interaction_handler.update_translation_model_ui()
            
            # Update OCR model UI visibility based on current selection
            self.ui_interaction_handler.update_ocr_model_ui()
            
            # Schedule a delayed OCR model UI update to ensure it takes effect after language change
            self.root.after_idle(lambda: self.ui_interaction_handler.update_ocr_model_ui())
            
            # Update adaptive fields visibility based on current preprocessing mode
            if hasattr(self, 'update_adaptive_fields_visibility'):
                self.update_adaptive_fields_visibility()
            
            # Update translation model display variable with new localized name
            current_model_code = self.translation_model_var.get()
            new_display_name = self.translation_model_names.get(current_model_code, list(self.translation_model_names.values())[0])
            self.translation_model_display_var.set(new_display_name)
            
            # Update all dropdowns with localized names for current language
            self.ui_interaction_handler.update_all_dropdowns_for_language_change()
            
            # Update DeepL model type dropdown if it exists
            if hasattr(self, 'update_deepl_model_type_for_language'):
                self.update_deepl_model_type_for_language()
            
            # Update Gemini context window dropdown if it exists
            if hasattr(self, 'update_gemini_context_window_for_language'):
                self.update_gemini_context_window_for_language()
            
            # Update Gemini labels if they exist
            if hasattr(self, 'update_gemini_labels_for_language'):
                self.update_gemini_labels_for_language()
            
            # Update DeepL usage labels if they exist
            if hasattr(self, 'update_deepl_usage_for_language'):
                self.update_deepl_usage_for_language()
            
            # Update API Usage tab labels if they exist
            if hasattr(self, 'update_api_usage_tab_for_language'):
                self.update_api_usage_tab_for_language()
            
            # Restore the tab change handler for focus behavior
            def on_tab_changed(event):
                selected_tab_index = self.tab_control.index(self.tab_control.select())
                if selected_tab_index == 0 and hasattr(self, 'main_tab_start_button') and self.main_tab_start_button.winfo_exists():
                    self.main_tab_start_button.focus_set()
                elif selected_tab_index == 1 and hasattr(self, 'settings_tab_save_button') and self.settings_tab_save_button.winfo_exists():
                    self.settings_tab_save_button.focus_set()
                elif selected_tab_index == 2 and hasattr(self, 'refresh_api_statistics'):
                    # API Usage tab - refresh statistics when accessed
                    self.root.after(100, self.refresh_api_statistics)
            
            self.tab_control.bind("<<NotebookTabChanged>>", on_tab_changed)
            
            # Set back to the corresponding tab index that was selected before
            if selected_tab:
                try:
                    # Since we've recreated all tabs, we need to find the index
                    # where the tab was before.
                    tab_index = int(selected_tab.split('.')[-1])
                    if 0 <= tab_index < self.tab_control.index('end'):
                        self.tab_control.select(tab_index)
                except Exception as e:
                    log_debug(f"Error restoring tab selection: {e}")
                    # Default to first tab
                    if self.tab_control.index('end') > 0:
                        self.tab_control.select(0)
            
            # Update status label based on current state
            if self.is_running:
                status_text = "Status: " + self.ui_lang.get_label("status_running", "Running (Press ~ to Stop)")
            else:
                status_text = "Status: " + self.ui_lang.get_label("status_stopped", "Stopped (Press ~ to Start)")
                if not self.KEYBOARD_AVAILABLE:
                    status_text = self.ui_lang.get_label("status_ready", "Status: Ready")
            self.status_label.config(text=status_text)
            
            # Update button state if translation is running
            if self.is_running:
                self.start_stop_btn.config(text=self.ui_lang.get_label("stop_btn"))
            
            # Update debug log toggle button text
            if hasattr(self, 'debug_log_toggle_btn') and hasattr(self.debug_log_toggle_btn, 'winfo_exists') and self.debug_log_toggle_btn.winfo_exists():
                if self.debug_logging_enabled_var.get():
                    self.debug_log_toggle_btn.config(text=self.ui_lang.get_label("toggle_debug_log_disable_btn"))
                else:
                    self.debug_log_toggle_btn.config(text=self.ui_lang.get_label("toggle_debug_log_enable_btn"))
            
            log_debug(f"UI language completely rebuilt for: {self.ui_lang.current_lang}")
        except Exception as e:
            log_debug(f"Error updating UI language: {e}")
        finally:
            # Always end UI update operation to restore saves and traces
            self.end_ui_update()

    def on_closing(self):
        log_debug("Main window close requested. Initiating shutdown...")
        
        # Close OCR Preview window if open
        if self.ocr_preview_window is not None:
            try:
                log_debug("Closing OCR Preview window...")
                self.close_ocr_preview()
            except Exception as e:
                log_debug(f"Error closing OCR Preview window: {e}")
        
        if self.is_running:
            log_debug("Stopping running OCR/translation process before closing...")
            self.toggle_translation()
        else:
             log_debug("Process was not running at close time.")

        # Force end any remaining sessions when application closes
        if hasattr(self, 'translation_handler'):
            try:
                self.translation_handler.force_end_sessions_on_app_close()
            except Exception as e:
                log_debug(f"Error ending sessions on app close: {e}")

        if hasattr(self, 'marian_translator') and self.marian_translator and hasattr(self.marian_translator, 'thread_pool'):
            try:
                log_debug("Shutting down MarianMT thread pool...")
                self.marian_translator.thread_pool.shutdown(wait=True, cancel_futures=True)
                log_debug("MarianMT thread pool shutdown complete.")
            except Exception as e_mtps:
                log_debug(f"Error shutting down MarianMT thread pool: {e_mtps}")
        try:
            log_debug("Saving final settings before closing...")
            if self._fully_initialized:
                # Save OCR Preview geometry if window is open
                if self.ocr_preview_window is not None:
                    self.save_preview_geometry()
                self.save_settings() 
            else: 
                # Save OCR Preview geometry even if not fully initialized
                if self.ocr_preview_window is not None:
                    self.save_preview_geometry()
                self.configuration_handler.save_current_window_geometry()
                save_app_config(self.config)
        except Exception as e_ssc:
            log_debug(f"Error saving settings during closing: {e_ssc}")

        if self.KEYBOARD_AVAILABLE:
            try:
                import keyboard
                keyboard.unhook_all()
                log_debug("Unhooked all keyboard shortcuts.")
            except Exception as e_uhk:
                log_debug(f"Error unhooking keyboard shortcuts: {e_uhk}")

        log_debug("Destroying overlay windows if they exist...")
        for overlay_attr_name in ['source_overlay', 'target_overlay']:
            overlay_widget = getattr(self, overlay_attr_name, None)
            if overlay_widget and hasattr(overlay_widget, 'winfo_exists') and overlay_widget.winfo_exists():
                try:
                    overlay_widget.destroy()
                except Exception as e_dow:
                    log_debug(f"Error destroying {overlay_attr_name}: {e_dow}")
            setattr(self, overlay_attr_name, None)
        self.translation_text = None

        log_debug("Destroying root window...")
        try:
            if self.root and hasattr(self.root, 'winfo_exists') and self.root.winfo_exists():
                self.root.destroy()
            log_debug("Root window destroyed.")
        except Exception as e_drw:
             log_debug(f"Error destroying root window: {e_drw}")
        log_debug("Application shutdown sequence complete.")