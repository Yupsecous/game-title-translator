# handlers/translation_handler.py
import re
import os
import gc
import sys
import time
import html
import hashlib # Not used here directly, but good for consistency
import traceback
# Removed lru_cache import - replaced with unified cache

from logger import log_debug
# from translation_utils import get_lang_code_for_translation_api # Replaced by direct use of API codes
from marian_mt_translator import MarianMTTranslator # Already imported
from unified_translation_cache import UnifiedTranslationCache

class TranslationHandler:
    def __init__(self, app):
        self.app = app
        # Initialize unified translation cache (replaces all individual LRU caches)
        self.unified_cache = UnifiedTranslationCache(max_size=1000)
        log_debug("Translation handler initialized with unified cache")
    
    def _google_translate(self, text_to_translate_gt, source_lang_gt, target_lang_gt):
        """Google Translate API call using REST API with API key."""
        log_debug(f"Google Translate API call for: {text_to_translate_gt}")
        
        api_key_google = self.app.google_api_key_var.get().strip()
        if not api_key_google:
            return "Google Translate API key missing"
        
        # Check file cache if enabled
        if self.app.google_file_cache_var.get():
            cache_key_gt = f"google:{source_lang_gt}:{target_lang_gt}:{text_to_translate_gt}"
            file_cached_gt = self.app.cache_manager.check_file_cache('google', cache_key_gt)
            if file_cached_gt:
                log_debug(f"Found in Google file cache: {text_to_translate_gt}")
                return file_cached_gt
        
        try:
            import requests
            import urllib.parse
            
            api_call_start_time = time.time()
            
            # Google Translate REST API endpoint
            url = "https://translation.googleapis.com/language/translate/v2"
            
            # Prepare request parameters
            params = {
                'key': api_key_google,
                'q': text_to_translate_gt,
                'target': target_lang_gt,
                'format': 'text'
            }
            
            # Add source language if not auto-detect
            if source_lang_gt and source_lang_gt.lower() != 'auto':
                params['source'] = source_lang_gt
            
            # Make the API request
            response = requests.post(url, data=params, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            log_debug(f"Google Translate API call took {time.time() - api_call_start_time:.2f}s.")

            if result and 'data' in result and 'translations' in result['data']:
                translated_text_gt = result['data']['translations'][0]['translatedText']
                # Unescape HTML entities
                import html
                translated_text_gt = html.unescape(translated_text_gt)
                return translated_text_gt
            else:
                return f"Google Translate API returned unexpected result: {result}"
                
        except requests.exceptions.RequestException as e_req:
            return f"Google Translate API request error: {str(e_req)}"
        except Exception as e_cgt:
            return f"Google Translate API error: {type(e_cgt).__name__} - {str(e_cgt)}"

    def _deepl_translate(self, text_to_translate_dl, source_lang_dl, target_lang_dl):
        """DeepL API call with automatic fallback from quality_optimized to latency_optimized."""
        model_type = self.app.deepl_model_type_var.get()
        log_debug(f"DeepL API call for: {text_to_translate_dl} using model_type={model_type}")
        
        if not self.app.deepl_api_client:
            return "DeepL API client not initialized"
        
        # Check file cache if enabled (include model_type in cache key)
        if self.app.deepl_file_cache_var.get():
            cache_key_dl = f"deepl:{source_lang_dl}:{target_lang_dl}:{model_type}:{text_to_translate_dl}"
            file_cached_dl = self.app.cache_manager.check_file_cache('deepl', cache_key_dl)
            if file_cached_dl:
                log_debug(f"Found in DeepL file cache: {text_to_translate_dl}")
                return file_cached_dl
        
        try:
            api_call_start_time_dl = time.time()
            deepl_source_param = source_lang_dl if source_lang_dl and source_lang_dl.lower() != 'auto' else None
            
            # First attempt with selected model type
            try:
                result_dl = self.app.deepl_api_client.translate_text(
                    text_to_translate_dl,
                    target_lang=target_lang_dl, 
                    source_lang=deepl_source_param,
                    model_type=model_type
                )
                log_debug(f"DeepL API call took {time.time() - api_call_start_time_dl:.2f}s using {model_type}")
                
                if result_dl and hasattr(result_dl, 'text') and result_dl.text:
                    translated_text = result_dl.text
                    
                    # Save to file cache if successful and file caching enabled
                    if self.app.deepl_file_cache_var.get():
                        self.app.cache_manager.save_to_file_cache('deepl', cache_key_dl, translated_text)
                    
                    return translated_text
                else:
                    return "DeepL API returned empty or invalid result"
                    
            except Exception as quality_error:
                # Check if this is a language pair not supported by quality_optimized models
                if (model_type == "quality_optimized" and 
                    ("language pair" in str(quality_error).lower() or 
                     "not supported" in str(quality_error).lower() or
                     "unsupported" in str(quality_error).lower())):
                    
                    log_debug(f"DeepL quality_optimized failed for language pair {source_lang_dl}->{target_lang_dl}, falling back to latency_optimized: {quality_error}")
                    
                    # Automatic fallback to latency_optimized
                    try:
                        fallback_start_time = time.time()
                        result_dl_fallback = self.app.deepl_api_client.translate_text(
                            text_to_translate_dl,
                            target_lang=target_lang_dl, 
                            source_lang=deepl_source_param,
                            model_type="latency_optimized"
                        )
                        log_debug(f"DeepL fallback API call took {time.time() - fallback_start_time:.2f}s using latency_optimized")
                        
                        if result_dl_fallback and hasattr(result_dl_fallback, 'text') and result_dl_fallback.text:
                            translated_text = result_dl_fallback.text
                            
                            # Save fallback result to cache with fallback model type
                            if self.app.deepl_file_cache_var.get():
                                fallback_cache_key = f"deepl:{source_lang_dl}:{target_lang_dl}:latency_optimized:{text_to_translate_dl}"
                                self.app.cache_manager.save_to_file_cache('deepl', fallback_cache_key, translated_text)
                            
                            return translated_text
                        else:
                            return "DeepL API fallback returned empty or invalid result"
                            
                    except Exception as fallback_error:
                        return f"DeepL API fallback error: {type(fallback_error).__name__} - {str(fallback_error)}"
                else:
                    # Re-raise the original error if it's not a language pair issue
                    raise quality_error
                    
        except Exception as e_cdl:
            return f"DeepL API error: {type(e_cdl).__name__} - {str(e_cdl)}"

    def _marian_translate(self, text_to_translate_mm, source_lang_mm, target_lang_mm, beam_value_mm):
        """MarianMT translation call (no longer cached here - handled by unified cache)."""
        log_debug(f"MarianMT translation call for: {text_to_translate_mm} (beam={beam_value_mm})")
        if self.app.marian_translator is None:
            return "MarianMT translator not initialized"
        
        text_to_translate_cleaned = re.sub(r'\s+', ' ', text_to_translate_mm).strip()
        if not text_to_translate_cleaned: return ""
        
        try:
            api_call_start_time_mm = time.monotonic()
            # Ensure the MarianMTTranslator instance has the correct beam value
            self.app.marian_translator.num_beams = beam_value_mm
            
            result_mm = self.app.marian_translator.translate(text_to_translate_cleaned, source_lang_mm, target_lang_mm)
            log_debug(f"MarianMT translation took {time.monotonic() - api_call_start_time_mm:.3f}s.")
            return result_mm
        except Exception as e_cmm:
            return f"MarianMT translation error: {type(e_cmm).__name__} - {str(e_cmm)}"

    def translate_text(self, text_content_main):
        cleaned_text_main = text_content_main.strip() if text_content_main else ""
        if not cleaned_text_main or len(cleaned_text_main) < 1: return None 
        if self.is_placeholder_text(cleaned_text_main): return None

        translation_start_monotonic = time.monotonic()
        selected_translation_model = self.app.translation_model_var.get()
        log_debug(f"Translate request for \"{cleaned_text_main}\" using {selected_translation_model}")
        
        # Determine source and target languages and provider-specific parameters
        if selected_translation_model == 'marianmt':
            if not self.app.MARIANMT_AVAILABLE:
                return "MarianMT libraries not available."
            elif self.app.marian_translator is None:
                self.initialize_marian_translator() # Attempt init
                if self.app.marian_translator is None:
                    return "MarianMT initialization failed."
            
            if self.app.marian_translator:
                source_lang = self.app.marian_source_lang
                target_lang = self.app.marian_target_lang
                if not source_lang or not target_lang:
                    return "MarianMT source/target language not determined. Select a model."
                
                beam_val = self.app.num_beams_var.get()
                extra_params = {"beam_size": beam_val}
            else:
                return "MarianMT translator initialization failed."
        
        elif selected_translation_model == 'google_api':
            api_key_google = self.app.google_api_key_var.get().strip()
            if not api_key_google:
                return "Google Translate API key missing."
            
            source_lang = self.app.google_source_lang
            target_lang = self.app.google_target_lang
            extra_params = {}
        
        elif selected_translation_model == 'deepl_api':
            if not self.app.DEEPL_API_AVAILABLE:
                return "DeepL API libraries not available."
            
            api_key_deepl = self.app.deepl_api_key_var.get().strip()
            if not api_key_deepl:
                return "DeepL API key missing."
            
            if self.app.deepl_api_client is None:
                try:
                    import deepl
                    self.app.deepl_api_client = deepl.Translator(api_key_deepl)
                except Exception as e:
                    return f"DeepL Client init error: {e}"
            
            source_lang = self.app.deepl_source_lang 
            target_lang = self.app.deepl_target_lang
            model_type = self.app.deepl_model_type_var.get()
            log_debug(f"DeepL translation request with model_type={model_type}, {source_lang}->{target_lang}")
            extra_params = {"model_type": model_type}
        
        else:
            return f"Error: Unknown translation model '{selected_translation_model}'"
        
        # Check unified cache first
        cached_result = self.unified_cache.get(
            cleaned_text_main, source_lang, target_lang, 
            selected_translation_model, **extra_params
        )
        if cached_result:
            if selected_translation_model == 'deepl_api':
                log_debug(f"Translation \"{cleaned_text_main}\" -> \"{cached_result}\" from unified cache (DeepL model_type={extra_params.get('model_type', 'unknown')})")
            else:
                log_debug(f"Translation \"{cleaned_text_main}\" -> \"{cached_result}\" from unified cache")
            return cached_result
        
        # Cache miss - perform actual translation
        if selected_translation_model == 'marianmt':
            translated_api_text = self._marian_translate(cleaned_text_main, source_lang, target_lang, beam_val)
        elif selected_translation_model == 'google_api':
            translated_api_text = self._google_translate(cleaned_text_main, source_lang, target_lang)
            # Save to file cache if successful and file caching enabled
            if (not (isinstance(translated_api_text, str) and translated_api_text.startswith("Google Translate API error")) 
                and self.app.google_file_cache_var.get()):
                cache_key_google = f"google:{source_lang}:{target_lang}:{cleaned_text_main}"
                self.app.cache_manager.save_to_file_cache('google', cache_key_google, translated_api_text)
        elif selected_translation_model == 'deepl_api':
            translated_api_text = self._deepl_translate(cleaned_text_main, source_lang, target_lang)
            # File cache is handled inside _deepl_translate method to include model_type
        
        # Store successful translation in unified cache
        if translated_api_text and not self._is_error_message(translated_api_text):
            self.unified_cache.store(
                cleaned_text_main, source_lang, target_lang,
                selected_translation_model, translated_api_text, **extra_params
            )
        
        log_debug(f"Translation \"{cleaned_text_main}\" -> \"{str(translated_api_text)}\" took {time.monotonic() - translation_start_monotonic:.3f}s")
        return translated_api_text
    
    def _is_error_message(self, text):
        """Check if a translation result is an error message."""
        if not isinstance(text, str):
            return True
        error_indicators = [
            "error:", "api error", "not initialized", "missing", "failed",
            "not available", "not supported", "invalid result", "empty result"
        ]
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in error_indicators)
    
    def clear_cache(self):
        """Clear the unified translation cache."""
        self.unified_cache.clear_all()
        log_debug("Cleared unified translation cache")

    def is_placeholder_text(self, text_content):
        if not text_content: return True
        text_lower_content = text_content.lower().strip()
        placeholders_list = [
            "source text will appear here", "translation will appear here",
            "translation...", "ocr source", "source text", "loading...",
            "translating...", "", "translation", "...", "translation error:"
        ]
        if text_lower_content in placeholders_list or text_lower_content.startswith("translation error:"):
            return True
        ui_patterns_list = [
            r'^[_\-=<>/\s\.\\|\[\]\{\}]+$', r'^ocr\s+source', r'^source\s+text', 
            r'^translat(ion|ing)', r'appear\s+here$', r'[×✖️]', r'^\d{1,2}:\d{2}(:\d{2})?$'
        ]
        for pattern_re in ui_patterns_list:
            try:
                if (pattern_re.startswith('^') and re.match(pattern_re, text_content, re.IGNORECASE)) or \
                   (not pattern_re.startswith('^') and re.search(pattern_re, text_content, re.IGNORECASE)):
                    return True
            except re.error as e_re:
                 log_debug(f"Regex error in is_placeholder_text with pattern '{pattern_re}': {e_re}")
        return False

    def calculate_text_similarity(self, text1_sim, text2_sim):
        if not text1_sim or not text2_sim: return 0.0
        if len(text1_sim) < 10 or len(text2_sim) < 10: 
            return 1.0 if text1_sim == text2_sim else 0.0
        
        words1_set = set(text1_sim.lower().split())
        words2_set = set(text2_sim.lower().split())
        intersection_len = len(words1_set.intersection(words2_set))
        union_len = len(words1_set.union(words2_set))
        return intersection_len / union_len if union_len > 0 else 0.0

    def initialize_marian_translator(self):
        if self.app.marian_translator is not None: return
        if not self.app.MARIANMT_AVAILABLE:
            log_debug("Attempted to initialize MarianMT, but library is not available.")
            return
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # Main app dir
            cache_dir_name = "marian_models_cache"
            if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
                 executable_dir = os.path.dirname(sys.executable)
                 cache_dir = os.path.join(executable_dir, "_internal", cache_dir_name) # Bundled
            else:
                 cache_dir = os.path.join(base_dir, cache_dir_name) # Script run
            os.makedirs(cache_dir, exist_ok=True)

            if hasattr(MarianMTTranslator, 'torch') and MarianMTTranslator.torch:
                torch_module = MarianMTTranslator.torch
                if hasattr(torch_module, 'set_num_threads'):
                    num_cores = max(1, os.cpu_count() - 1 if os.cpu_count() else 4)
                    torch_module.set_num_threads(num_cores)
                    if hasattr(torch_module, 'set_num_interop_threads'):
                        interop_threads = max(1, min(4, os.cpu_count() // 2 if os.cpu_count() else 2))
                        torch_module.set_num_interop_threads(interop_threads)
            
            current_beam_value = self.app.num_beams_var.get()
            self.app.marian_translator = MarianMTTranslator(cache_dir=cache_dir, num_beams=current_beam_value)
            log_debug(f"MarianMT translator initialized (cache: {cache_dir}, beams: {current_beam_value})")

            # Preload if MarianMT is the active model and a specific model is selected
            if self.app.translation_model_var.get() == 'marianmt' and self.app.marian_model_var.get():
                log_debug("MarianMT is active model, attempting to preload selected Marian model.")
                # This will call on_marian_model_selection_changed which handles parsing and loading
                self.app.ui_interaction_handler.on_marian_model_selection_changed(preload=True)
        except ImportError as e_imt_imp:
            log_debug(f"MarianMT initialization failed - missing dependencies: {e_imt_imp}")
            # Error shown by ui_interaction_handler if MarianMT is selected
        except Exception as e_imt:
            log_debug(f"Error initializing MarianMT translator: {e_imt}\n{traceback.format_exc()}")
            # Error shown by ui_interaction_handler

    def update_marian_active_model(self, model_name_uam, source_lang_uam=None, target_lang_uam=None):
        if self.app.marian_translator is None:
            # Try to initialize if not already
            self.initialize_marian_translator()
            if self.app.marian_translator is None: # Still None after attempt
                log_debug("Cannot update MarianMT model - translator not initialized and init failed.")
                return False
        
        try:
            # Source/target langs should have been parsed by ui_interaction_handler.on_marian_model_selection_changed
            # and stored in self.app.marian_source_lang / self.app.marian_target_lang
            # If they are passed explicitly here, use them.
            final_source_lang = source_lang_uam if source_lang_uam else self.app.marian_source_lang
            final_target_lang = target_lang_uam if target_lang_uam else self.app.marian_target_lang

            if not final_source_lang or not final_target_lang:
                log_debug(f"Cannot update MarianMT model '{model_name_uam}': source/target language not determined.")
                return False
            
            log_debug(f"Attempting to make MarianMT model active: {model_name_uam} for {final_source_lang}->{final_target_lang}")

            if hasattr(self.app.marian_translator, '_unload_current_model'):
                self.app.marian_translator._unload_current_model()
            
            if hasattr(self.app.marian_translator, 'direct_pairs'):
                self.app.marian_translator.direct_pairs[(final_source_lang, final_target_lang)] = model_name_uam
            
            # Clear unified cache for MarianMT instead of specific method cache
            self.unified_cache.clear_provider('marianmt')

            if hasattr(self.app.marian_translator, '_try_load_direct_model'):
                load_success = self.app.marian_translator._try_load_direct_model(final_source_lang, final_target_lang)
                if load_success:
                    log_debug(f"Successfully loaded MarianMT model for {final_source_lang}->{final_target_lang}")
                    return True
                else:
                    log_debug(f"Failed to load MarianMT model for {final_source_lang}->{final_target_lang}")
                    return False
            return False
        except Exception as e_umam:
            log_debug(f"Error updating MarianMT active model: {e_umam}")
            return False

    def update_marian_beam_value(self):
        if self.app.marian_translator is not None:
            try:
                beam_value_clamped = max(1, min(50, self.app.num_beams_var.get()))
                if beam_value_clamped != self.app.num_beams_var.get():
                    self.app.num_beams_var.set(beam_value_clamped)
                self.app.marian_translator.num_beams = beam_value_clamped
                log_debug(f"Updated MarianMT beam search value in translator to: {beam_value_clamped}")
            except Exception as e_umbv:
                log_debug(f"Error updating MarianMT beam value: {e_umbv}")
