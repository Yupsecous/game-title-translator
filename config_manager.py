# config_manager.py
import configparser
import os
import sys
from logger import log_debug
from resource_handler import get_resource_path

DEFAULT_CONFIG_SETTINGS = {
    'tesseract_path': r'C:\Program Files\Tesseract-OCR\tesseract.exe',
    'scan_interval': '300', 
    'stability_threshold': '0',
    'clear_translation_timeout': '3',
    'image_preprocessing_mode': 'none',
    'ocr_debugging': 'True',
    'confidence_threshold': '50',
    'remove_trailing_garbage': 'True',
    'source_area_x1': '334',
    'source_area_y1': '856',
    'source_area_x2': '1579',
    'source_area_y2': '1041',
    'source_area_visible': '0', # Changed to string 'False' or 'True' later
    'target_area_x1': '717',
    'target_area_y1': '17',
    'target_area_x2': '1612',
    'target_area_y2': '178',
    'source_area_colour': '#FFFF99',
    'target_area_colour': '#162c43',
    'target_text_colour': '#ffffff',
    'target_font_size': '18',
    'num_beams': '2',
    'google_translate_api_key': '',
    'deepl_api_key': '',
    'main_window_geometry': '619x728+6+23', # This seems to be a complete geometry string
    'main_window_width': '619',   # Keep these for individual component loading
    'main_window_height': '728',
    'main_window_x': '6',
    'main_window_y': '23',
    'translation_model': 'marianmt', # Default model
    'marian_models_file': '', # Will be set dynamically in load_app_config
    'marian_model': 'Helsinki-NLP/opus-mt-fr-en', # Default MarianMT model
    'google_file_cache': 'True',
    'deepl_file_cache': 'True',
    'debug_logging_enabled': 'False',
    # Model-specific language defaults
    'google_source_lang': 'pl',
    'google_target_lang': 'en',
    'deepl_source_lang': 'DE',
    'deepl_target_lang': 'EN-GB', # DeepL's code for English (British)
    'deepl_model_type': 'latency_optimized', # Default to classic model for compatibility
    'gui_language':'English',
    # OCR Model Selection (Phase 1 - Gemini OCR)
    'ocr_model': 'tesseract',  # 'tesseract' or 'gemini'
    # Adaptive thresholding parameters
    'adaptive_block_size': '41',
    'adaptive_c': '-60',
    # OCR Preview window geometry
    'ocr_preview_geometry': '600x800+100+100',
    'ocr_preview_width': '600',
    'ocr_preview_height': '800',
    'ocr_preview_x': '100',
    'ocr_preview_y': '100',
    # Gemini API settings
    'gemini_model_name': 'gemini-2.5-flash-lite',
    'gemini_model_temp': '0.0',
    'input_token_cost': '0.1',
    'output_token_cost': '0.4'
}


def load_app_config():
    """Loads configuration from INI file or creates default values."""
    config_path = 'ocr_translator_config.ini'
    config = configparser.ConfigParser()
    
    default_marian_models_path_val = get_resource_path("resources/MarianMT_select_models.csv")
    log_debug(f"Default MarianMT models path set to: {default_marian_models_path_val}")

    dynamic_defaults = DEFAULT_CONFIG_SETTINGS.copy()
    dynamic_defaults['marian_models_file'] = default_marian_models_path_val

    if os.path.exists(config_path):
        try:
            config.read(config_path, encoding='utf-8')
            if 'Settings' not in config:
                log_debug("Config file loaded but missing [Settings] section. Adding.")
                config['Settings'] = {}
        except Exception as e:
            log_debug(f"Error reading config file {config_path}: {e}. Using defaults.")
            config['Settings'] = {} 
    else:
         log_debug(f"Config file {config_path} not found. Creating with defaults.")
         config['Settings'] = {}

    settings_changed = False
    config_settings = config['Settings']

    # Obsolete keys check (add 'source_lang', 'target_lang', 'ocr_lang' if you are sure to remove them)
    obsolete_keys = ['api_key', 'gpu_enabled', 'spell_check_enabled', 'word_segmentation_enabled',
                    'spell_check_language', 'subtitle_mode', 'parallel_processing', 'target_text_bg_color',
                    'nllb_beam_size', 'source_lang', 'target_lang', 'ocr_lang', 'gemini_fuzzy_detection'] 
    for key in obsolete_keys:
        if key in config_settings:
            del config_settings[key]
            settings_changed = True
            log_debug(f"Config: Removed obsolete '{key}' setting.")

    for key, value in dynamic_defaults.items():
        if key not in config_settings:
            config_settings[key] = value
            settings_changed = True
            log_debug(f"Config: Added missing key '{key}' with default value '{value}'.")

    current_mode = config_settings.get('image_preprocessing_mode', 'none')
    if current_mode not in ['none', 'binary', 'binary_inv', 'adaptive']:
        config_settings['image_preprocessing_mode'] = 'none'
        settings_changed = True
        log_debug(f"Config: Invalid preprocessing mode '{current_mode}' changed to 'none'")

    if settings_changed or not os.path.exists(config_path):
         try:
            with open(config_path, 'w', encoding='utf-8') as f:
                config.write(f)
            log_debug("Config file saved/updated with defaults.")
         except Exception as e:
             log_debug(f"Error writing config file {config_path}: {e}")
    return config

def save_app_config(config_object):
    config_path = 'ocr_translator_config.ini'
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            config_object.write(f)
        log_debug(f"Settings saved successfully to {config_path}")
        return True
    except Exception as file_err:
        log_debug(f"Error writing settings to file: {file_err}")
        return False

def load_main_window_geometry(app_config, root_window, min_size):
    try:
        # Try loading from individual components first, then full geometry string
        width_str = app_config['Settings'].get('main_window_width')
        height_str = app_config['Settings'].get('main_window_height')
        x_str = app_config['Settings'].get('main_window_x')
        y_str = app_config['Settings'].get('main_window_y')

        if all([width_str, height_str, x_str, y_str]):
            width = int(width_str)
            height = int(height_str)
            x = int(x_str)
            y = int(y_str)
        else: # Fallback to full geometry string
            geometry_str = app_config['Settings'].get('main_window_geometry', '600x480+100+100')
            parts = geometry_str.split('+')[0].split('x') + geometry_str.split('+')[1:]
            width, height, x, y = map(int, parts)

        width = max(min_size[0], width)
        height = max(min_size[1], height)
        root_window.geometry(f"{width}x{height}+{x}+{y}")
        log_debug(f"Loaded window geometry: {width}x{height}+{x}+{y}")
    except Exception as e:
        log_debug(f"Error loading window geometry: {e}. Using default 600x480+100+100.")
        root_window.geometry("600x480+100+100")


def save_main_window_geometry(app_config, root_window):
    try:
        if not root_window or not root_window.winfo_exists():
            log_debug("Window does not exist, cannot save geometry.")
            return
            
        geometry = root_window.geometry() # Full string e.g. "680x927+15+14"
        width = root_window.winfo_width()
        height = root_window.winfo_height()
        x = root_window.winfo_x()
        y = root_window.winfo_y()

        if width > 0 and height > 0:
            app_config['Settings']['main_window_geometry'] = geometry
            app_config['Settings']['main_window_width'] = str(width)
            app_config['Settings']['main_window_height'] = str(height)
            app_config['Settings']['main_window_x'] = str(x)
            app_config['Settings']['main_window_y'] = str(y)
            log_debug(f"Updated geometry in config object: {geometry}")
        else:
             log_debug(f"Skipping geometry save due to invalid dimensions: W={width}, H={height}")
    except Exception as e:
        log_debug(f"Error updating window geometry in config object: {e}")


def load_ocr_preview_geometry(app_config, preview_window, min_size=(400, 500)):
    """Load OCR Preview window geometry from config"""
    try:
        # Try loading from individual components first, then full geometry string
        width_str = app_config['Settings'].get('ocr_preview_width')
        height_str = app_config['Settings'].get('ocr_preview_height')
        x_str = app_config['Settings'].get('ocr_preview_x')
        y_str = app_config['Settings'].get('ocr_preview_y')

        if all([width_str, height_str, x_str, y_str]):
            width = int(width_str)
            height = int(height_str)
            x = int(x_str)
            y = int(y_str)
        else: # Fallback to full geometry string
            geometry_str = app_config['Settings'].get('ocr_preview_geometry', '600x800+100+100')
            parts = geometry_str.split('+')[0].split('x') + geometry_str.split('+')[1:]
            width, height, x, y = map(int, parts)

        width = max(min_size[0], width)
        height = max(min_size[1], height)
        preview_window.geometry(f"{width}x{height}+{x}+{y}")
        log_debug(f"Loaded OCR Preview window geometry: {width}x{height}+{x}+{y}")
    except Exception as e:
        log_debug(f"Error loading OCR Preview window geometry: {e}. Using default 600x800+100+100.")
        preview_window.geometry("600x800+100+100")


def save_ocr_preview_geometry(app_config, preview_window):
    """Save OCR Preview window geometry to config"""
    try:
        if not preview_window or not preview_window.winfo_exists():
            log_debug("OCR Preview window does not exist, cannot save geometry.")
            return
            
        geometry = preview_window.geometry() # Full string e.g. "680x927+15+14"
        width = preview_window.winfo_width()
        height = preview_window.winfo_height()
        x = preview_window.winfo_x()
        y = preview_window.winfo_y()

        if width > 0 and height > 0:
            app_config['Settings']['ocr_preview_geometry'] = geometry
            app_config['Settings']['ocr_preview_width'] = str(width)
            app_config['Settings']['ocr_preview_height'] = str(height)
            app_config['Settings']['ocr_preview_x'] = str(x)
            app_config['Settings']['ocr_preview_y'] = str(y)
            log_debug(f"Updated OCR Preview geometry in config object: {geometry}")
        else:
             log_debug(f"Skipping OCR Preview geometry save due to invalid dimensions: W={width}, H={height}")
    except Exception as e:
        log_debug(f"Error updating OCR Preview window geometry in config object: {e}")