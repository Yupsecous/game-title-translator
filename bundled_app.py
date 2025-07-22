#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Game-Changing Translator - All-in-one bundler for PyInstaller
This file imports all modules to make PyInstaller detect dependencies correctly.
The actual application structure is preserved.
"""

# Standard Library Imports
import os
import sys

# Add the current directory to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Now import standard libraries
import time
import re
import gc
import queue
import threading
import traceback
import hashlib
import html
import csv
import configparser
import json

# Explicitly import tkinter and all its submodules
import tkinter
import tkinter.ttk
import tkinter.messagebox
import tkinter.filedialog
import tkinter.colorchooser

# Import all third-party libraries with error handling for PyInstaller compatibility
try:
    import numpy
    import numpy.core._multiarray_umath  # Explicit import for PyInstaller
except ImportError as e:
    print(f"Warning: numpy import failed: {e}")
    numpy = None

try:
    import cv2
except ImportError as e:
    print(f"Warning: cv2 import failed: {e}")
    cv2 = None

try:
    import pytesseract
except ImportError as e:
    print(f"Warning: pytesseract import failed: {e}")
    pytesseract = None

try:
    import PIL
    from PIL import Image, ImageTk
except ImportError as e:
    print(f"Warning: PIL import failed: {e}")
    PIL = None

try:
    import pyautogui
except ImportError as e:
    print(f"Warning: pyautogui import failed: {e}")
    pyautogui = None

# Additional imports that might be needed by dependencies
try:
    import pkg_resources
except ImportError:
    pass

# Try importing optional libraries
try:
    import keyboard
except ImportError:
    pass

try:
    from google.cloud import translate_v2 as google_translate
except ImportError:
    pass

try:
    import google.generativeai
    # Pre-load critical Gemini modules for PyInstaller
    import google.generativeai.types
    import google.generativeai.client
    import google.ai.generativelanguage
except ImportError:
    pass

try:
    import deepl
except ImportError:
    pass

try:
    import torch
    import transformers
    from transformers import MarianMTModel, MarianTokenizer
    import sentencepiece
    # Additional transformers imports that may be needed
    from transformers import AutoTokenizer, AutoModel
except ImportError:
    pass

# Explicitly copy all application modules to this file to ensure PyInstaller includes them
# First, import them
from logger import log_debug
from constants import LANGUAGES
from resource_handler import get_resource_path
from unified_translation_cache import UnifiedTranslationCache
from marian_mt_translator import MarianMTTranslator, MARIANMT_AVAILABLE
from config_manager import load_app_config, save_app_config, load_main_window_geometry, save_main_window_geometry
from ocr_utils import preprocess_for_ocr, get_tesseract_model_params, ocr_region_with_confidence, post_process_ocr_text_general, remove_text_after_last_punctuation_mark
from translation_utils import get_lang_code_for_translation_api, post_process_translation_text
from gui_builder import create_main_tab, create_settings_tab, create_debug_tab
from overlay_manager import select_source_area_om, select_target_area_om, create_source_overlay_om, create_target_overlay_om, toggle_source_visibility_om, load_areas_from_config_om
from worker_threads import run_capture_thread, run_ocr_thread, run_translation_thread
from ui_elements import ResizableMovableFrame

# Language management imports
from language_manager import LanguageManager
from language_ui import UILanguageManager

# Handler imports
from handlers.cache_manager import CacheManager
from handlers.configuration_handler import ConfigurationHandler
from handlers.display_manager import DisplayManager
from handlers.hotkey_handler import HotkeyHandler
from handlers.translation_handler import TranslationHandler
from handlers.ui_interaction_handler import UIInteractionHandler

# Finally import the app_logic and main entry point
from app_logic import GameChangingTranslator
from main import main_entry_point

# When this file is run directly, start the application
if __name__ == "__main__":
    main_entry_point()
