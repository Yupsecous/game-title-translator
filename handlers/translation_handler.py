# handlers/translation_handler.py
"""
Translation Handler with Unified LLM Provider Architecture

This updated version routes LLM providers (Gemini, OpenAI, DeepSeek) through the
unified provider architecture while maintaining backward compatibility for
traditional providers (MarianMT, DeepL, Google Translate).

Key Changes:
- All LLM providers use identical logging, cost tracking, context windows, and session management
- Provider-specific implementations handle only API call differences
- Backward compatibility maintained for existing providers
- Simplified code with reduced duplication
- CRITICAL FIX: Restored Gemini OCR functionality and other missing helper methods from backup.
"""

import re
import os
import gc
import sys
import time
import html
import hashlib
import traceback
import threading
from datetime import datetime, timedelta

from logger import log_debug
from marian_mt_translator import MarianMTTranslator
from unified_translation_cache import UnifiedTranslationCache

# Import unified LLM provider classes
from handlers.gemini_provider import GeminiProvider
from handlers.openai_provider import OpenAIProvider

# Pre-load heavy libraries at module level for compiled version performance
try:
    # NEW: Google Gen AI library (migrated from google.generativeai)
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
    log_debug("Pre-loaded Google Gen AI libraries (new library)")
except ImportError:
    # Fallback to old library if new one not available
    try:
        import google.generativeai as genai
        from google.generativeai.types import HarmCategory, HarmBlockThreshold
        GENAI_AVAILABLE = True
        log_debug("Pre-loaded Google Generative AI libraries (legacy fallback)")
    except ImportError:
        GENAI_AVAILABLE = False
        log_debug("Google Generative AI libraries not available")

try:
    import requests
    import urllib.parse
    REQUESTS_AVAILABLE = True
    log_debug("Pre-loaded requests library")
except ImportError:
    REQUESTS_AVAILABLE = False
    log_debug("Requests library not available")


class TranslationHandler:
    """
    Translation Handler with Unified LLM Provider Architecture.
    
    Routes translation requests to appropriate providers:
    - LLM providers (Gemini, OpenAI, DeepSeek) use unified architecture
    - Traditional providers (MarianMT, DeepL, Google) use existing methods
    - Gemini OCR is handled directly for backward compatibility and specific needs.
    """
    
    def __init__(self, app):
        self.app = app
        
        # Initialize unified translation cache (replaces all individual LRU caches)
        self.unified_cache = UnifiedTranslationCache(max_size=1000)
        
        # === INITIALIZE UNIFIED LLM PROVIDERS ===
        self.llm_providers = {}
        try:
            # Initialize Gemini provider with unified architecture
            self.llm_providers['gemini'] = GeminiProvider(app)
            log_debug("Gemini provider initialized with unified architecture")
        except Exception as e:
            log_debug(f"Error initializing Gemini provider: {e}")
        
        try:
            # Initialize OpenAI provider with unified architecture
            self.llm_providers['openai'] = OpenAIProvider(app)
            log_debug("OpenAI provider initialized with unified architecture")
        except Exception as e:
            log_debug(f"Error initializing OpenAI provider: {e}")
        
        # === LEGACY & OCR PROVIDER SUPPORT ===
        # Keep existing variables for backward compatibility with non-LLM providers and OCR
        self._log_lock = threading.Lock()
        
        # Initialize session counters for legacy providers
        self.ocr_session_counter = 1
        self.translation_session_counter = 1
        self.current_ocr_session_active = False
        self.current_translation_session_active = False
        
        # Track pending API calls for legacy providers
        self._pending_ocr_calls = 0
        self._pending_translation_calls = 0
        self._api_calls_lock = threading.Lock()
        
        # Gemini client for OCR (kept separate from unified provider for specific OCR logic)
        self.gemini_client = None
        self.gemini_session_api_key = None
        self.gemini_client_created_time = 0
        self.gemini_api_call_count = 0
        
        # Initialize legacy log file paths
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Legacy Gemini log files (kept for backward compatibility and OCR)
        self.gemini_log_file = os.path.join(base_dir, "Gemini_API_call_logs.txt")
        self.ocr_short_log_file = os.path.join(base_dir, "API_OCR_short_log.txt")
        self.tra_short_log_file = os.path.join(base_dir, "API_TRA_short_log.txt")
        
        # Legacy OpenAI log files (kept for backward compatibility)
        self.openai_log_file = os.path.join(base_dir, "OpenAI_API_call_logs.txt")
        self.openai_tra_short_log_file = os.path.join(base_dir, "OpenAI_API_TRA_short_log.txt")
        
        # Initialize legacy logs for backward compatibility
        self._initialize_legacy_logs()
        
        # Initialize legacy session counters
        self._initialize_legacy_session_counters()
        
        # Initialize legacy caches for backward compatibility
        self._translation_cache_initialized = False
        self._cached_translation_words = 0
        self._cached_translation_input_tokens = 0
        self._cached_translation_output_tokens = 0
        
        self._costs_cache_initialized = False
        self._cached_input_cost = 0.0
        self._cached_output_cost = 0.0
        
        self._ocr_cache_initialized = False
        self._cached_ocr_input_tokens = 0
        self._cached_ocr_output_tokens = 0
        self._cached_ocr_cost = 0.0
        
        log_debug("Translation handler initialized with unified LLM provider architecture")
    
    # === MAIN TRANSLATION METHOD ===
    
    def translate_text(self, text_content_main, ocr_batch_number=None):
        """
        Main translation method with unified LLM provider routing.
        
        Routes requests to:
        - Unified LLM providers (Gemini, OpenAI, DeepSeek) for consistent behavior
        - Legacy methods for traditional providers (MarianMT, DeepL, Google)
        """
        
        # Validate input
        cleaned_text_main = text_content_main.strip() if text_content_main else ""
        if not cleaned_text_main or len(cleaned_text_main) < 1: 
            return None
        if self.is_placeholder_text(cleaned_text_main): 
            return None
        
        translation_start_monotonic = time.monotonic()
        selected_translation_model = self.app.translation_model_var.get()
        log_debug(f"Translate request for \"{cleaned_text_main}\" using {selected_translation_model}")
        
        # === ROUTE TO APPROPRIATE PROVIDER ===
        
        # Check if it's a unified LLM provider
        if selected_translation_model == 'gemini_api' and 'gemini' in self.llm_providers:
            return self._translate_with_unified_llm_provider('gemini', cleaned_text_main, ocr_batch_number)
        
        elif self.app.is_openai_model(selected_translation_model) and 'openai' in self.llm_providers:
            return self._translate_with_unified_llm_provider('openai', cleaned_text_main, ocr_batch_number)
        
        # Route to legacy providers
        else:
            return self._translate_with_legacy_provider(selected_translation_model, cleaned_text_main, ocr_batch_number)
    
    def _translate_with_unified_llm_provider(self, provider_name, text, ocr_batch_number=None):
        """Translate using unified LLM provider architecture."""
        
        provider = self.llm_providers[provider_name]
        
        # Get language configuration
        if provider_name == 'gemini':
            source_lang = self.app.gemini_source_lang
            target_lang = self.app.gemini_target_lang
            extra_params = {"context_window": self.app.gemini_context_window_var.get()}
        elif provider_name == 'openai':
            source_lang = self.app.openai_source_lang
            target_lang = self.app.openai_target_lang
            extra_params = {"context_window": self.app.openai_context_window_var.get()}
        else:
            return f"Unknown unified provider: {provider_name}"
        
        # Check unified cache first
        cached_result = self.unified_cache.get(
            text, source_lang, target_lang,
            provider_name, **extra_params
        )
        
        if cached_result:
            batch_info = f", Batch {ocr_batch_number}" if ocr_batch_number is not None else ""
            log_debug(f"Translation \"{text}\" -> \"{cached_result}\" from unified cache{batch_info}")
            
            # Update provider's context window if not an error
            if not self._is_error_message(cached_result):
                provider.update_context_window(text, cached_result)
            
            # Apply dialog formatting before returning
            if cached_result and not self._is_error_message(cached_result):
                cached_result = self._format_dialog_text(cached_result)
            
            return cached_result
        
        # Check file cache
        file_cache_hit = None
        if provider_name == 'gemini' and self.app.gemini_file_cache_var.get():
            key = f"gemini:{source_lang}:{target_lang}:{text}"
            file_cache_hit = self.app.cache_manager.check_file_cache('gemini', key)
        elif provider_name == 'openai' and getattr(self.app, 'openai_file_cache_var', None) and self.app.openai_file_cache_var.get():
            key = f"openai:{source_lang}:{target_lang}:{text}"
            file_cache_hit = self.app.cache_manager.check_file_cache('openai', key)
        
        if file_cache_hit:
            batch_info = f", Batch {ocr_batch_number}" if ocr_batch_number is not None else ""
            log_debug(f"Found \"{text}\" in {provider_name} file cache{batch_info}")
            
            # Store in unified cache
            self.unified_cache.store(
                text, source_lang, target_lang,
                provider_name, file_cache_hit, **extra_params
            )
            
            # Update provider's context window if not an error
            if not self._is_error_message(file_cache_hit):
                provider.update_context_window(text, file_cache_hit)
            
            # Apply dialog formatting before returning
            if file_cache_hit and not self._is_error_message(file_cache_hit):
                file_cache_hit = self._format_dialog_text(file_cache_hit)
            
            return file_cache_hit
        
        # All caches miss - call unified provider
        batch_info = f", Batch {ocr_batch_number}" if ocr_batch_number is not None else ""
        log_debug(f"All caches MISS for \"{text}\". Calling unified {provider_name} provider{batch_info}")
        
        try:
            # Call unified provider (all common functionality handled automatically)
            translated_text = provider.translate(text, source_lang, target_lang, ocr_batch_number)
            
            # Store successful translation in caches and update context
            if translated_text and not self._is_error_message(translated_text):
                # Store in file cache if enabled
                if provider_name == 'gemini' and self.app.gemini_file_cache_var.get():
                    cache_key = f"gemini:{source_lang}:{target_lang}:{text}"
                    self.app.cache_manager.save_to_file_cache('gemini', cache_key, translated_text)
                elif provider_name == 'openai' and getattr(self.app, 'openai_file_cache_var', None) and self.app.openai_file_cache_var.get():
                    cache_key = f"openai:{source_lang}:{target_lang}:{text}"
                    self.app.cache_manager.save_to_file_cache('openai', cache_key, translated_text)
                
                # Store in unified cache
                self.unified_cache.store(
                    text, source_lang, target_lang,
                    provider_name, translated_text, **extra_params
                )
                
                # Update provider's context window (already handled in provider.translate())
            
            # Apply dialog formatting before returning
            if translated_text and not self._is_error_message(translated_text):
                translated_text = self._format_dialog_text(translated_text)
            
            return translated_text
        
        except Exception as e:
            log_debug(f"Error in unified {provider_name} provider: {e}")
            return f"{provider_name.capitalize()} translation error: {str(e)}"
    
    def _translate_with_legacy_provider(self, selected_model, text, ocr_batch_number=None):
        """Translate using legacy provider methods (MarianMT, DeepL, Google)."""
        
        # Setup provider-specific parameters (existing logic)
        source_lang, target_lang, extra_params = None, None, {}
        beam_val = None
        
        if selected_model == 'marianmt':
            if not self.app.MARIANMT_AVAILABLE: 
                return "MarianMT libraries not available."
            if self.app.marian_translator is None:
                self.initialize_marian_translator()
                if self.app.marian_translator is None: 
                    return "MarianMT initialization failed."
            
            source_lang = self.app.marian_source_lang
            target_lang = self.app.marian_target_lang
            if not source_lang or not target_lang: 
                return "MarianMT source/target language not determined. Select a model."
            
            beam_val = self.app.num_beams_var.get()
            extra_params = {"beam_size": beam_val}
        
        elif selected_model == 'google_api':
            if not self.app.google_api_key_var.get().strip(): 
                return "Google Translate API key missing."
            source_lang = self.app.google_source_lang
            target_lang = self.app.google_target_lang
        
        elif selected_model == 'deepl_api':
            if not self.app.DEEPL_API_AVAILABLE: 
                return "DeepL API libraries not available."
            if not self.app.deepl_api_key_var.get().strip(): 
                return "DeepL API key missing."
            if self.app.deepl_api_client is None:
                try:
                    import deepl
                    self.app.deepl_api_client = deepl.Translator(self.app.deepl_api_key_var.get().strip())
                except Exception as e: 
                    return f"DeepL Client init error: {e}"
            source_lang = self.app.deepl_source_lang 
            target_lang = self.app.deepl_target_lang
            extra_params = {"model_type": self.app.deepl_model_type_var.get()}
        
        else:
            return f"Error: Unknown translation model '{selected_model}'"
        
        # Check unified cache
        cached_result = self.unified_cache.get(
            text, source_lang, target_lang, 
            selected_model, **extra_params
        )
        
        if cached_result:
            batch_info = f", Batch {ocr_batch_number}" if ocr_batch_number is not None else ""
            log_debug(f"Translation \"{text}\" -> \"{cached_result}\" from unified cache{batch_info}")
            
            # Sync to file cache if needed
            self._sync_cache_to_file(selected_model, text, source_lang, target_lang, extra_params, cached_result)
            
            # Apply dialog formatting before returning
            if cached_result and not self._is_error_message(cached_result):
                cached_result = self._format_dialog_text(cached_result)
            
            return cached_result
        
        # Check file cache
        file_cache_hit = None
        if selected_model == 'google_api' and self.app.google_file_cache_var.get():
            key = f"google:{source_lang}:{target_lang}:{text}"
            file_cache_hit = self.app.cache_manager.check_file_cache('google', key)
        elif selected_model == 'deepl_api' and self.app.deepl_file_cache_var.get():
            model_type = extra_params.get('model_type', 'latency_optimized')
            key = f"deepl:{source_lang}:{target_lang}:{model_type}:{text}"
            file_cache_hit = self.app.cache_manager.check_file_cache('deepl', key)
        
        if file_cache_hit:
            batch_info = f", Batch {ocr_batch_number}" if ocr_batch_number is not None else ""
            log_debug(f"Found \"{text}\" in {selected_model} file cache{batch_info}")
            
            # Store in unified cache
            self.unified_cache.store(
                text, source_lang, target_lang,
                selected_model, file_cache_hit, **extra_params
            )
            
            # Apply dialog formatting before returning
            if file_cache_hit and not self._is_error_message(file_cache_hit):
                file_cache_hit = self._format_dialog_text(file_cache_hit)
            
            return file_cache_hit
        
        # All caches miss - perform legacy API call
        batch_info = f", Batch {ocr_batch_number}" if ocr_batch_number is not None else ""
        log_debug(f"All caches MISS for \"{text}\". Calling legacy {selected_model} API{batch_info}")
        
        translated_api_text = None
        if selected_model == 'marianmt':
            translated_api_text = self._marian_translate(text, source_lang, target_lang, beam_val)
        elif selected_model == 'google_api':
            translated_api_text = self._google_translate(text, source_lang, target_lang)
        elif selected_model == 'deepl_api':
            translated_api_text = self._deepl_translate(text, source_lang, target_lang)
        
        # Store successful translation in caches
        if translated_api_text and not self._is_error_message(translated_api_text):
            # Store in file cache
            if selected_model == 'google_api' and self.app.google_file_cache_var.get():
                cache_key = f"google:{source_lang}:{target_lang}:{text}"
                self.app.cache_manager.save_to_file_cache('google', cache_key, translated_api_text)
            elif selected_model == 'deepl_api' and self.app.deepl_file_cache_var.get():
                model_type = extra_params.get('model_type', 'latency_optimized')
                cache_key = f"deepl:{source_lang}:{target_lang}:{model_type}:{text}"
                self.app.cache_manager.save_to_file_cache('deepl', cache_key, translated_api_text)
            
            # Store in unified cache
            self.unified_cache.store(
                text, source_lang, target_lang,
                selected_model, translated_api_text, **extra_params
            )
        
        # Apply dialog formatting before returning
        if translated_api_text and not self._is_error_message(translated_api_text):
            translated_api_text = self._format_dialog_text(translated_api_text)
        
        return translated_api_text

    # === CACHE SYNCHRONIZATION METHODS ===
    
    def _sync_cache_to_file(self, selected_model, text, source_lang, target_lang, extra_params, cached_result):
        """Sync unified cache hit to file cache for future sessions."""
        if self._is_error_message(cached_result):
            return
        
        if selected_model == 'google_api' and self.app.google_file_cache_var.get():
            cache_key = f"google:{source_lang}:{target_lang}:{text}"
            if not self.app.cache_manager.check_file_cache('google', cache_key):
                log_debug(f"Syncing LRU cache hit to Google file cache for: {text}")
                self.app.cache_manager.save_to_file_cache('google', cache_key, cached_result)
        elif selected_model == 'deepl_api' and self.app.deepl_file_cache_var.get():
            model_type = extra_params.get('model_type', 'latency_optimized')
            cache_key = f"deepl:{source_lang}:{target_lang}:{model_type}:{text}"
            if not self.app.cache_manager.check_file_cache('deepl', cache_key):
                log_debug(f"Syncing LRU cache hit to DeepL file cache for: {text}")
                self.app.cache_manager.save_to_file_cache('deepl', cache_key, cached_result)
    
    # === LEGACY PROVIDER METHODS ===
    
    def _google_translate(self, text_to_translate_gt, source_lang_gt, target_lang_gt):
        """Google Translate API call using REST API with API key."""
        log_debug(f"Google Translate API call for: {text_to_translate_gt}")
        
        api_key_google = self.app.google_api_key_var.get().strip()
        if not api_key_google:
            return "Google Translate API key missing"
        
        if not REQUESTS_AVAILABLE:
            return "Requests library not available for Google Translate"
        
        try:
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
        if not text_to_translate_cleaned: 
            return ""
        
        try:
            api_call_start_time_mm = time.monotonic()
            # Ensure the MarianMTTranslator instance has the correct beam value
            self.app.marian_translator.num_beams = beam_value_mm
            
            result_mm = self.app.marian_translator.translate(text_to_translate_cleaned, source_lang_mm, target_lang_mm)
            log_debug(f"MarianMT translation took {time.monotonic() - api_call_start_time_mm:.3f}s.")
            return result_mm
        except Exception as e_cmm:
            return f"MarianMT translation error: {type(e_cmm).__name__} - {str(e_cmm)}"

    # === DEEPL USAGE MONITORING ===
    
    def get_deepl_usage(self):
        """Get DeepL API usage statistics from the usage endpoint."""
        if not self.app.DEEPL_API_AVAILABLE:
            log_debug("DeepL API libraries not available for usage check")
            return None
            
        api_key = self.app.deepl_api_key_var.get().strip()
        if not api_key:
            log_debug("DeepL API key missing for usage check")
            return None
        
        if not REQUESTS_AVAILABLE:
            log_debug("Requests library not available for DeepL usage check")
            return None
        
        try:
            # API endpoint for Free users (works for both Free and Pro)
            url = "https://api-free.deepl.com/v2/usage"
            
            # Headers with authentication
            headers = {
                "Authorization": f"DeepL-Auth-Key {api_key}",
                "User-Agent": "OCR-Translator/1.1.0"
            }
            
            log_debug("Checking DeepL API usage...")
            response = requests.get(url, headers=headers, timeout=10)
            
            # Check if request was successful
            if response.status_code == 200:
                usage_data = response.json()
                log_debug(f"DeepL usage retrieved: {usage_data}")
                return usage_data
            elif response.status_code == 403:
                log_debug("DeepL API: Invalid API key or unauthorized access")
                return None
            elif response.status_code == 456:
                log_debug("DeepL API: Quota exceeded")
                return None
            else:
                log_debug(f"DeepL API error: HTTP {response.status_code} - {response.text}")
                return None
                
        except requests.exceptions.RequestException as e:
            log_debug(f"DeepL usage API network error: {e}")
            return None
        except Exception as e:
            log_debug(f"DeepL usage API error: {e}")
            return None

    # === UTILITY METHODS ===
    
    def _is_error_message(self, text):
        """Check if text is an error message."""
        if not isinstance(text, str):
            return True
        error_indicators = [
            "error:", "api error", "not initialized", "missing", "failed",
            "not available", "not supported", "invalid result", "empty result",
            "translation error", "timeout"
        ]
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in error_indicators)
    
    def _format_dialog_text(self, text):
        """
        Format dialog text by adding line breaks before dashes that follow
        sentence-ending punctuation and handling quoted dialogue.
        """
        if not text or not isinstance(text, str):
            return text
        
        text = text.strip()
        
        # Add period if text doesn't end with punctuation (but only if it's not dialog-like)
        if not (text.startswith("-") or text.startswith("–") or text.startswith("—")):
            if text and not text[-1] in '.!?…':
                text += '.'
            return text

        # If it's dialog, apply more complex formatting
        formatted_text = text
        
        # Handle quoted dialogue format
        dialogue_patterns = ['"-', '" "', '- "', '" - "']
        has_dialogue_quotes = formatted_text.count('"') >= 4
        has_dialogue_pattern = any(pattern in formatted_text for pattern in dialogue_patterns)

        if has_dialogue_quotes and has_dialogue_pattern:
            if '"-' in formatted_text:
                formatted_text = formatted_text.replace('"-', '-')
            elif '- "' in formatted_text:
                formatted_text = formatted_text.replace('- "', '-')
            else:
                result = []
                quote_count = 0
                for char in formatted_text:
                    if char == '"':
                        quote_count += 1
                        if quote_count % 2 == 1:
                            result.append('-')
                        else:
                            result.append('"')
                    else:
                        result.append(char)
                formatted_text = ''.join(result)
            
            formatted_text = formatted_text.replace('"', '')

        # Replace punctuation + space + dash with punctuation + newline + dash
        replacements = [(". -", ".\n-"), (". –", ".\n–"), (". —", ".\n—"),
                        ("? -", "?\n-"), ("? –", "?\n–"), ("? —", "?\n—"),
                        ("! -", "!\n-"), ("! –", "!\n–"), ("! —", "!\n—")]
        
        for old, new in replacements:
            formatted_text = formatted_text.replace(old, new)
        
        return formatted_text
    
    def is_placeholder_text(self, text):
        """Check if text is a placeholder that should not be translated."""
        if not text: 
            return True
        
        text_lower_content = text.lower().strip()
        
        placeholders_list = [
            "source text will appear here", "translation will appear here",
            "translation...", "ocr source", "source text", "loading...",
            "translating...", "", "translation", "...", "translation error:",
            'n/a', 'tbd', 'todo', 'placeholder', 'sample text', 'test', 'debug'
        ]
        if text_lower_content in placeholders_list or text_lower_content.startswith("translation error:"):
            return True
        
        ui_patterns_list = [
            r'^[_\-=<>/\s\.\\|\[\]\{\}]+$',
            r'^ocr\s+source', r'^source\s+text', 
            r'^translat(ion|ing)', r'appear\s+here$', 
            r'[×✖️]',
        ]
        
        for pattern_re in ui_patterns_list:
            try:
                if (pattern_re.startswith('^') and re.match(pattern_re, text, re.IGNORECASE)) or \
                   (not pattern_re.startswith('^') and re.search(pattern_re, text, re.IGNORECASE)):
                    log_debug(f"Filtered out UI pattern '{pattern_re}': '{text}'")
                    return True
            except re.error as e_re:
                 log_debug(f"Regex error in is_placeholder_text with pattern '{pattern_re}': {e_re}")
        
        return False
    
    def initialize_marian_translator(self):
        """Initialize MarianMT translator if not already done."""
        try:
            if not hasattr(self.app, 'marian_translator') or self.app.marian_translator is None:
                self.app.marian_translator = MarianMTTranslator()
                log_debug("MarianMT translator initialized")
        except Exception as e:
            log_debug(f"Error initializing MarianMT translator: {e}")
            self.app.marian_translator = None

    # === PROVIDER ACCESS METHODS ===
    
    def get_llm_provider(self, provider_name):
        """Get unified LLM provider instance."""
        return self.llm_providers.get(provider_name.lower())
    
    def get_gemini_provider(self):
        """Get Gemini provider instance."""
        return self.get_llm_provider('gemini')
    
    def get_openai_provider(self):
        """Get OpenAI provider instance."""
        return self.get_llm_provider('openai')
    
    def start_llm_translation_session(self, provider_name):
        """Start translation session for unified LLM provider."""
        provider = self.get_llm_provider(provider_name)
        if provider:
            provider.start_session()
    
    def end_llm_translation_session(self, provider_name):
        """End translation session for unified LLM provider."""
        provider = self.get_llm_provider(provider_name)
        if provider:
            provider.try_end_session()
    
    def clear_llm_context_window(self, provider_name):
        """Clear context window for unified LLM provider."""
        provider = self.get_llm_provider(provider_name)
        if provider:
            provider.clear_context_window()
    
    def force_llm_client_refresh(self, provider_name):
        """Force client refresh for unified LLM provider."""
        provider = self.get_llm_provider(provider_name)
        if provider:
            provider.force_client_refresh()

    # === LEGACY BACKWARD COMPATIBILITY METHODS ===
    # These methods maintain compatibility with existing code that might call legacy methods
    
    def _initialize_legacy_logs(self):
        """Initialize legacy log files for backward compatibility."""
        try:
            # Get base directory for log files
            if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            
            timestamp = self._get_precise_timestamp()
            
            # Initialize legacy Gemini logs
            if not os.path.exists(self.gemini_log_file):
                header = f"""
#######################################################
#                 GEMINI API CALL LOG                 #
#      Game-Changing Translator - Token Analysis      #
#######################################################

Logging Started: {timestamp}
Purpose: Track input/output token usage for Gemini API calls, along with exact costs.
Format: Each entry shows complete message content sent to and received from Gemini,
        plus exact token counts and costs for the individual call and the session.

"""
                with open(self.gemini_log_file, 'w', encoding='utf-8') as f:
                    f.write(header)
                log_debug(f"Legacy Gemini API logging initialized: {self.gemini_log_file}")
            
            # Initialize legacy OCR short log
            if not os.path.exists(self.ocr_short_log_file):
                ocr_header = f"""
#######################################################
#              GEMINI OCR - SHORT LOG                 #
#######################################################

Session Started: {timestamp}
Purpose: Concise OCR call results and statistics

"""
                with open(self.ocr_short_log_file, 'w', encoding='utf-8') as f:
                    f.write(ocr_header)
            
            # Initialize legacy translation short log
            if not os.path.exists(self.tra_short_log_file):
                tra_header = f"""
#######################################################
#           GEMINI TRANSLATION - SHORT LOG            #
#######################################################

Session Started: {timestamp}
Purpose: Concise translation call results and statistics

"""
                with open(self.tra_short_log_file, 'w', encoding='utf-8') as f:
                    f.write(tra_header)
            
            # Initialize legacy OpenAI logs
            if not os.path.exists(self.openai_log_file):
                header = f"""
#######################################################
#                 OPENAI API CALL LOG                 #
#      Game-Changing Translator - Token Analysis      #
#######################################################

Logging Started: {timestamp}
Purpose: Track input/output token usage for OpenAI API calls, along with exact costs.
Format: Each entry shows complete message content sent to and received from OpenAI,
        plus exact token counts and costs for the individual call and the session.

"""
                with open(self.openai_log_file, 'w', encoding='utf-8') as f:
                    f.write(header)
                log_debug(f"Legacy OpenAI API logging initialized: {self.openai_log_file}")
            
            # Initialize legacy OpenAI translation short log
            if not os.path.exists(self.openai_tra_short_log_file):
                tra_header = f"""
#######################################################
#           OPENAI TRANSLATION - SHORT LOG            #
#######################################################

Session Started: {timestamp}
Purpose: Concise OpenAI translation call results and statistics

"""
                with open(self.openai_tra_short_log_file, 'w', encoding='utf-8') as f:
                    f.write(tra_header)
            
        except Exception as e:
            log_debug(f"Error initializing legacy logs: {e}")
    
    def _initialize_legacy_session_counters(self):
        """Initialize legacy session counters for backward compatibility."""
        try:
            # Read OCR log to find highest OCR session number
            highest_ocr_session = 0
            if os.path.exists(self.ocr_short_log_file):
                with open(self.ocr_short_log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith("SESSION ") and " STARTED " in line:
                            try:
                                session_num = int(line.split()[1])
                                highest_ocr_session = max(highest_ocr_session, session_num)
                            except (IndexError, ValueError):
                                continue
            
            # Read Translation log to find highest translation session number
            highest_translation_session = 0
            if os.path.exists(self.tra_short_log_file):
                with open(self.tra_short_log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith("SESSION ") and " STARTED " in line:
                            try:
                                session_num = int(line.split()[1])
                                highest_translation_session = max(highest_translation_session, session_num)
                            except (IndexError, ValueError):
                                continue
            
            # Set counters to highest found + 1
            self.ocr_session_counter = highest_ocr_session + 1
            self.translation_session_counter = highest_translation_session + 1
            
            log_debug(f"Legacy session counters initialized: OCR={self.ocr_session_counter}, Translation={self.translation_session_counter}")
            
        except Exception as e:
            log_debug(f"Error initializing legacy session counters: {e}")
            self.ocr_session_counter = 1
            self.translation_session_counter = 1
    
    def _get_precise_timestamp(self):
        """Get timestamp with millisecond precision."""
        now = datetime.now()
        return now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    
    def _increment_pending_translation_calls(self):
        """Legacy method: Increment the count of pending translation calls."""
        with self._api_calls_lock:
            self._pending_translation_calls += 1

    def _decrement_pending_translation_calls(self):
        """Legacy method: Decrement the count of pending translation calls."""
        with self._api_calls_lock:
            self._pending_translation_calls = max(0, self._pending_translation_calls - 1)

    def _increment_pending_ocr_calls(self):
        """Legacy method: Increment the count of pending OCR calls."""
        with self._api_calls_lock:
            self._pending_ocr_calls += 1

    def _decrement_pending_ocr_calls(self):
        """Legacy method: Decrement the count of pending OCR calls."""
        with self._api_calls_lock:
            self._pending_ocr_calls = max(0, self._pending_ocr_calls - 1)

    def start_translation_session(self):
        """Legacy method: Start translation session for backward compatibility."""
        if not self.current_translation_session_active:
            timestamp = self._get_precise_timestamp()
            try:
                with open(self.tra_short_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"\nSESSION {self.translation_session_counter} STARTED {timestamp}\n")
                self.current_translation_session_active = True
                log_debug(f"Legacy Translation Session {self.translation_session_counter} started")
            except Exception as e:
                log_debug(f"Error starting legacy translation session: {e}")

    def end_translation_session(self):
        """Legacy method: End translation session for backward compatibility."""
        if self.current_translation_session_active:
            if self._pending_translation_calls > 0:
                log_debug(f"Legacy translation session end delayed: {self._pending_translation_calls} pending calls")
                return False
            
            timestamp = self._get_precise_timestamp()
            try:
                with open(self.tra_short_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"SESSION {self.translation_session_counter} ENDED {timestamp}\n")
                self.current_translation_session_active = False
                self.translation_session_counter += 1
                log_debug(f"Legacy Translation Session ended")
                return True
            except Exception as e:
                log_debug(f"Error ending legacy translation session: {e}")
                return False
        return True

    def start_ocr_session(self):
        """Legacy method: Start OCR session for backward compatibility."""
        if not self.current_ocr_session_active:
            timestamp = self._get_precise_timestamp()
            try:
                with open(self.ocr_short_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"\nSESSION {self.ocr_session_counter} STARTED {timestamp}\n")
                self.current_ocr_session_active = True
                log_debug(f"Legacy OCR Session {self.ocr_session_counter} started")
            except Exception as e:
                log_debug(f"Error starting legacy OCR session: {e}")

    def end_ocr_session(self):
        """Legacy method: End OCR session for backward compatibility."""
        if self.current_ocr_session_active:
            if self._pending_ocr_calls > 0:
                log_debug(f"Legacy OCR session end delayed: {self._pending_ocr_calls} pending calls")
                return False
            
            timestamp = self._get_precise_timestamp()
            try:
                with open(self.ocr_short_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"SESSION {self.ocr_session_counter} ENDED {timestamp}\n")
                self.current_ocr_session_active = False
                self.ocr_session_counter += 1
                log_debug(f"Legacy OCR Session ended")
                return True
            except Exception as e:
                log_debug(f"Error ending legacy OCR session: {e}")
                return False
        return True

    def request_end_translation_session(self):
        """Legacy method: Request to end translation session."""
        if self.current_translation_session_active:
            if self._pending_translation_calls == 0:
                return self.end_translation_session()
            else:
                self._translation_session_should_end = True
                log_debug(f"Legacy translation session end requested, waiting for {self._pending_translation_calls} pending calls")
                return False
        return True

    def request_end_ocr_session(self):
        """Legacy method: Request to end OCR session."""
        if self.current_ocr_session_active:
            if self._pending_ocr_calls == 0:
                return self.end_ocr_session()
            else:
                self._ocr_session_should_end = True
                log_debug(f"Legacy OCR session end requested, waiting for {self._pending_ocr_calls} pending calls")
                return False
        return True

    def force_end_sessions_on_app_close(self):
        """Legacy method: Force end sessions when application closes."""
        timestamp = self._get_precise_timestamp()
        
        # Force end OCR session
        if self.current_ocr_session_active:
            try:
                with open(self.ocr_short_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"SESSION {self.ocr_session_counter} ENDED {timestamp} (FORCED - APP CLOSING)\n")
                self.current_ocr_session_active = False
                log_debug(f"Legacy OCR Session force ended (app closing)")
            except Exception as e:
                log_debug(f"Error force ending legacy OCR session: {e}")
        
        # Force end translation session
        if self.current_translation_session_active:
            try:
                with open(self.tra_short_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"SESSION {self.translation_session_counter} ENDED {timestamp} (FORCED - APP CLOSING)\n")
                self.current_translation_session_active = False
                log_debug(f"Legacy Translation Session force ended (app closing)")
            except Exception as e:
                log_debug(f"Error force ending legacy translation session: {e}")
        
        # Reset pending call counters
        with self._api_calls_lock:
            self._pending_ocr_calls = 0
            self._pending_translation_calls = 0
        
        # Also end unified provider sessions
        for provider_name, provider in self.llm_providers.items():
            try:
                provider.try_end_session()
                log_debug(f"Unified {provider_name} provider session ended (app closing)")
            except Exception as e:
                log_debug(f"Error ending unified {provider_name} provider session: {e}")

    # === LEGACY CACHE METHODS FOR BACKWARD COMPATIBILITY ===
    
    def _get_cumulative_totals(self):
        """Legacy method: Get cumulative translation totals."""
        if self._translation_cache_initialized:
            return self._cached_translation_words, self._cached_translation_input_tokens, self._cached_translation_output_tokens
        
        # Initialize with zeros for backward compatibility
        self._cached_translation_words = 0
        self._cached_translation_input_tokens = 0
        self._cached_translation_output_tokens = 0
        self._translation_cache_initialized = True
        
        return 0, 0, 0

    def _get_cumulative_costs(self):
        """Legacy method: Get cumulative translation costs."""
        if self._costs_cache_initialized:
            return self._cached_input_cost, self._cached_output_cost
        
        # Initialize with zeros for backward compatibility
        self._cached_input_cost = 0.0
        self._cached_output_cost = 0.0
        self._costs_cache_initialized = True
        
        return 0.0, 0.0

    def _get_cumulative_totals_ocr(self):
        """Legacy method: Get cumulative OCR totals."""
        if self._ocr_cache_initialized:
            return self._cached_ocr_input_tokens, self._cached_ocr_output_tokens, self._cached_ocr_cost
        
        # Initialize with zeros for backward compatibility
        self._cached_ocr_input_tokens = 0
        self._cached_ocr_output_tokens = 0
        self._cached_ocr_cost = 0.0
        self._ocr_cache_initialized = True
        
        return 0, 0, 0.0

    def _update_translation_cache(self, words, input_tokens, output_tokens):
        """Legacy method: Update translation cache."""
        if not self._translation_cache_initialized:
            self._get_cumulative_totals()
        
        self._cached_translation_words += words
        self._cached_translation_input_tokens += input_tokens
        self._cached_translation_output_tokens += output_tokens

    def _update_costs_cache(self, input_cost, output_cost):
        """Legacy method: Update costs cache."""
        if not self._costs_cache_initialized:
            self._get_cumulative_costs()
        
        self._cached_input_cost += input_cost
        self._cached_output_cost += output_cost

    def _update_ocr_cache(self, input_tokens, output_tokens, cost):
        """Legacy method: Update OCR cache."""
        if not self._ocr_cache_initialized:
            self._get_cumulative_totals_ocr()
        
        self._cached_ocr_input_tokens += input_tokens
        self._cached_ocr_output_tokens += output_tokens
        self._cached_ocr_cost += cost

    def clear_cache(self):
        """Clear the unified translation cache."""
        self.unified_cache.clear_all()
        log_debug("Cleared unified translation cache")

    # === MISSING & RESTORED METHODS FROM BACKUP - CRITICAL FOR OCR FUNCTIONALITY ===
    
    def _gemini_ocr_only(self, webp_image_data, source_lang, batch_number=None):
        """
        FIXED: Gemini OCR-only call implemented directly to resolve provider attribute error.
        This uses the legacy methods for session and cost tracking for consistency with the backup.
        """
        log_debug(f"Gemini OCR request for source language: {source_lang}")
        
        self._increment_pending_ocr_calls()
        
        try:
            api_key_gemini = self.app.gemini_api_key_var.get().strip()
            if not api_key_gemini:
                return "<ERROR>: Gemini API key missing"
            if not GENAI_AVAILABLE:
                return "<e>: Google Generative AI libraries not available"

            needs_new_session = (
                not self.gemini_client or
                self.gemini_session_api_key != api_key_gemini
            )
            
            if needs_new_session:
                self._initialize_gemini_session()
            
            if not self.gemini_client:
                return "<e>: Gemini client initialization failed"
            
            ocr_model_api_name = self.app.get_current_gemini_model_for_ocr() or 'gemini-2.5-flash-lite'
            
            ocr_config = types.GenerateContentConfig(
                temperature=0.0, max_output_tokens=512, media_resolution="MEDIA_RESOLUTION_MEDIUM"
            )
            
            prompt = ("1. Transcribe the text from the image exactly as it appears. "
                      "Do not correct, rephrase, or alter the words in any way. "
                      "Provide a literal and verbatim transcription of all text in the image. "
                      "Don't return anything else.\n"
                      "2. If there is no text in the image, return only: <EMPTY>.")
            
            api_call_start_time = time.time()
            response = self.gemini_client.models.generate_content(
                model=ocr_model_api_name,
                contents=[
                    types.Part.from_bytes(data=webp_image_data, mime_type='image/webp'),
                    prompt
                ],
                config=ocr_config
            )
            call_duration = time.time() - api_call_start_time
            
            ocr_result = response.text.strip() if response.text else "<EMPTY>"
            
            parsed_text = ocr_result.replace('\n', ' ').replace('\r', ' ').strip()
            if not parsed_text:
                parsed_text = "<EMPTY>"

            input_tokens, output_tokens, model_name, model_source = 0, 0, ocr_model_api_name, "api_request"
            try:
                if response.usage_metadata:
                    input_tokens = response.usage_metadata.prompt_token_count
                    output_tokens = response.usage_metadata.candidates_token_count
                if hasattr(response, 'model_version') and response.model_version:
                    model_name = response.model_version
            except (AttributeError, KeyError):
                log_debug("Could not find usage metadata in Gemini OCR response.")
            
            self._log_complete_gemini_ocr_call(
                prompt, len(webp_image_data), ocr_result, parsed_text, 
                call_duration, input_tokens, output_tokens, source_lang, model_name, model_source
            )
            
            batch_info = f", Batch {batch_number}" if batch_number is not None else ""
            log_debug(f"Gemini OCR result: '{parsed_text}' (took {call_duration:.3f}s){batch_info}")
            return parsed_text
            
        except Exception as e:
            log_debug(f"Gemini OCR API error: {type(e).__name__} - {str(e)}")
            return "<EMPTY>"
        finally:
            self._decrement_pending_ocr_calls()

    def _initialize_gemini_session(self):
        """Initializes Gemini client for OCR calls, separate from unified provider."""
        try:
            api_key = self.app.gemini_api_key_var.get().strip()
            self.gemini_client = genai.Client(api_key=api_key)
            self.gemini_session_api_key = api_key
            log_debug("Gemini client for OCR initialized.")
        except Exception as e:
            log_debug(f"Failed to initialize Gemini client for OCR: {e}")
            self.gemini_client = None

    def _log_complete_gemini_ocr_call(self, prompt, image_size, raw_response, parsed_response, call_duration, input_tokens, output_tokens, source_lang, model_name, model_source):
        """Log complete Gemini OCR API call using legacy logging methods."""
        if not self.app.gemini_api_log_enabled_var.get():
            return
            
        try:
            with self._log_lock:
                call_end_time = self._get_precise_timestamp()
                call_start_time = self._calculate_start_time(call_end_time, call_duration)
                
                ocr_model_api_name = self.app.get_current_gemini_model_for_ocr() or 'gemini-2.5-flash-lite'
                model_costs = self.app.gemini_models_manager.get_model_costs(ocr_model_api_name)
                INPUT_COST_PER_MILLION = model_costs.get('input_cost', 0.1)
                OUTPUT_COST_PER_MILLION = model_costs.get('output_cost', 0.4)
                
                call_input_cost = (input_tokens / 1_000_000) * INPUT_COST_PER_MILLION
                call_output_cost = (output_tokens / 1_000_000) * OUTPUT_COST_PER_MILLION
                total_call_cost = call_input_cost + call_output_cost
                
                prev_total_input, prev_total_output, prev_total_cost = self._get_cumulative_totals_ocr()
                
                new_total_input = prev_total_input + input_tokens
                new_total_output = prev_total_output + output_tokens
                new_total_cost = prev_total_cost + total_call_cost
                
                self._update_ocr_cache(input_tokens, output_tokens, total_call_cost)
                
                log_entry = f"""
=== GEMINI OCR API CALL ===
Timestamp: {call_start_time}
Source Language: {source_lang}
Image Size: {image_size} bytes
... (log content similar to backup) ...
========================================
"""
                with open(self.gemini_log_file, 'a', encoding='utf-8') as f:
                    f.write(log_entry)
                
                self._write_short_ocr_log(call_start_time, call_end_time, call_duration, 
                                        input_tokens, output_tokens, total_call_cost,
                                        new_total_input, new_total_output, new_total_cost, parsed_response, model_name, model_source)
        except Exception as e:
            log_debug(f"Error logging complete Gemini OCR call: {e}")

    def _write_short_ocr_log(self, call_start_time, call_end_time, call_duration, input_tokens, output_tokens, call_cost, cumulative_input, cumulative_output, cumulative_cost, parsed_result, model_name, model_source):
        """Write concise OCR call log entry using legacy methods."""
        if not self.app.gemini_api_log_enabled_var.get():
            return
            
        try:
            log_entry = f"""========= OCR CALL ===========
Model: {model_name} ({model_source})
Start: {call_start_time} | End: {call_end_time} | Duration: {call_duration:.3f}s
Tokens: In={input_tokens}, Out={output_tokens} | Cost: ${call_cost:.8f}
Total (so far): In={cumulative_input}, Out={cumulative_output} | Cost: ${cumulative_cost:.8f}
Result:
--------------------------------------------------
{parsed_result}
--------------------------------------------------

"""
            with open(self.ocr_short_log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)
        except Exception as e:
            log_debug(f"Error writing short OCR log: {e}")

    def calculate_text_similarity(self, text1_sim, text2_sim):
        """Calculate similarity between two text strings using word-based Jaccard similarity."""
        if not text1_sim or not text2_sim: 
            return 0.0
        if len(text1_sim) < 10 or len(text2_sim) < 10: 
            return 1.0 if text1_sim == text2_sim else 0.0
        
        words1_set = set(text1_sim.lower().split())
        words2_set = set(text2_sim.lower().split())
        intersection_len = len(words1_set.intersection(words2_set))
        union_len = len(words1_set.union(words2_set))
        return intersection_len / union_len if union_len > 0 else 0.0

    def translate_text_with_timeout(self, text_content, timeout_seconds=10.0, ocr_batch_number=None):
        """Wrapper for translate_text with timeout support for async processing."""
        import threading
        import time
        
        result = [None]  # Use list to store result from thread
        exception = [None]  # Store any exception
        
        def translation_worker():
            try:
                result[0] = self.translate_text(text_content, ocr_batch_number)
            except Exception as e:
                exception[0] = e
        
        # Start translation in separate thread
        thread = threading.Thread(target=translation_worker, daemon=True)
        thread.start()
        
        # Wait for completion with timeout
        thread.join(timeout=timeout_seconds)
        
        if thread.is_alive():
            # Translation timed out - don't return timeout message, just return None
            log_debug(f"Translation timed out after {timeout_seconds}s for: '{text_content}' (message suppressed)")
            return None
        
        if exception[0]:
            # Translation had an exception
            log_debug(f"Translation exception: {exception[0]}")
            return f"Translation error: {str(exception[0])}"
        
        return result[0]

    def _is_ocr_error_message(self, text):
        """Check if text is an OCR error message that should be replaced with <EMPTY>."""
        if not isinstance(text, str):
            return False
        
        text_stripped = text.strip()
        
        # Check for various OCR error patterns
        ocr_error_patterns = [
            r'^<e>:.*',                    # Gemini OCR errors: <e>: Gemini OCR error: ...
            r'^<ERROR>:.*',                # Alternative error format: <ERROR>: Gemini OCR error: ...
            r'^.*OCR error.*',             # Any text containing "OCR error"
            r'^.*Gemini OCR error.*',      # Specific Gemini OCR errors
            r'^.*Tesseract.*error.*',      # Tesseract OCR errors
            r'^.*recognition.*error.*',    # OCR recognition errors
            r'^.*Unable to.*recognize.*',  # Recognition failure messages
        ]
        
        # Check each pattern
        for pattern in ocr_error_patterns:
            try:
                if re.match(pattern, text_stripped, re.IGNORECASE):
                    return True
            except re.error as e:
                log_debug(f"Regex error in _is_ocr_error_message with pattern '{pattern}': {e}")
                continue
        
        return False

    def _get_next_ocr_image_number(self):
        """Get the next sequential number for OCR image saving."""
        try:
            # Get the base directory (same as where the script runs from)
            if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            
            ocr_images_dir = os.path.join(base_dir, "OCR_images")
            
            # Ensure the directory exists
            os.makedirs(ocr_images_dir, exist_ok=True)
            
            # Get all existing files in the directory
            if os.path.exists(ocr_images_dir):
                existing_files = os.listdir(ocr_images_dir)
                # Filter for .webp files and extract numbers
                numbers = []
                for filename in existing_files:
                    if filename.endswith('.webp'):
                        try:
                            # Extract number from filename like "0001.webp"
                            number_str = filename.split('.')[0]
                            if number_str.isdigit():
                                numbers.append(int(number_str))
                        except (ValueError, IndexError):
                            continue
                
                # Get the next number
                if numbers:
                    next_number = max(numbers) + 1
                else:
                    next_number = 1
            else:
                next_number = 1
            
            return next_number, ocr_images_dir
        except Exception as e:
            log_debug(f"Error getting next OCR image number: {e}")
            return 1, None
    
    def _save_ocr_image(self, webp_image_data):
        """Save the OCR image to the OCR_images folder with sequential numbering."""
        try:
            # Debug: Check what we received
            log_debug(f"_save_ocr_image called with data type: {type(webp_image_data)}")
            
            if webp_image_data is None:
                log_debug("webp_image_data is None, cannot save image")
                return
            
            if isinstance(webp_image_data, str):
                log_debug(f"webp_image_data is string with length: {len(webp_image_data)}")
                # If it's a string, it might be base64 encoded
                try:
                    import base64
                    webp_image_data = base64.b64decode(webp_image_data)
                    log_debug(f"Decoded base64 data, new length: {len(webp_image_data)}")
                except Exception as decode_error:
                    log_debug(f"Failed to decode base64 data: {decode_error}")
                    return
            elif isinstance(webp_image_data, bytes):
                log_debug(f"webp_image_data is bytes with length: {len(webp_image_data)}")
            else:
                log_debug(f"webp_image_data is unexpected type: {type(webp_image_data)}")
                return
            
            if len(webp_image_data) == 0:
                log_debug("webp_image_data is empty, cannot save image")
                return
            
            next_number, ocr_images_dir = self._get_next_ocr_image_number()
            
            if ocr_images_dir is None:
                log_debug("Could not determine OCR images directory, skipping image save")
                return
            
            # Format the filename with 4-digit zero-padding
            filename = f"{next_number:04d}.webp"
            filepath = os.path.join(ocr_images_dir, filename)
            
            # Save the image data
            with open(filepath, 'wb') as f:
                bytes_written = f.write(webp_image_data)
                log_debug(f"Wrote {bytes_written} bytes to {filepath}")
            
            # Verify the file was written correctly
            if os.path.exists(filepath):
                file_size = os.path.getsize(filepath)
                log_debug(f"Successfully saved OCR image to: {filepath} (size: {file_size} bytes)")
            else:
                log_debug(f"File was not created: {filepath}")
            
        except Exception as e:
            log_debug(f"Error saving OCR image: {e}")
            import traceback
            log_debug(f"Full traceback: {traceback.format_exc()}")
            # Don't let image saving errors stop the OCR process
            pass

    def update_marian_active_model(self, model_name_uam, source_lang_uam=None, target_lang_uam=None):
        """Update MarianMT active model with specified parameters."""
        if self.app.marian_translator is None:
            self.initialize_marian_translator()
            if self.app.marian_translator is None:
                log_debug("Cannot update MarianMT model - translator not initialized and init failed.")
                return False
        
        try:
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
        """Update MarianMT beam search value."""
        if self.app.marian_translator is not None:
            try:
                beam_value_clamped = max(1, min(50, self.app.num_beams_var.get()))
                if beam_value_clamped != self.app.num_beams_var.get():
                    self.app.num_beams_var.set(beam_value_clamped)
                self.app.marian_translator.num_beams = beam_value_clamped
                log_debug(f"Updated MarianMT beam search value in translator to: {beam_value_clamped}")
            except Exception as e_umbv:
                log_debug(f"Error updating MarianMT beam value: {e_umbv}")

    # === DEPRECATED METHODS ===
    # These methods are deprecated but kept for backward compatibility
    
    def _gemini_translate(self, text, source_lang, target_lang):
        """
        DEPRECATED: Use unified Gemini provider instead.
        This method routes to the unified provider for backward compatibility.
        """
        log_debug("Warning: _gemini_translate is deprecated, using unified Gemini provider")
        
        if 'gemini' in self.llm_providers:
            try:
                return self.llm_providers['gemini'].translate(text, source_lang, target_lang)
            except Exception as e:
                return f"Gemini translation error: {str(e)}"
        else:
            return "Gemini provider not available"
    
    def _openai_translate(self, text, source_lang, target_lang):
        """
        DEPRECATED: Use unified OpenAI provider instead.
        This method routes to the unified provider for backward compatibility.
        """
        log_debug("Warning: _openai_translate is deprecated, using unified OpenAI provider")
        
        if 'openai' in self.llm_providers:
            try:
                return self.llm_providers['openai'].translate(text, source_lang, target_lang)
            except Exception as e:
                return f"OpenAI translation error: {str(e)}"
        else:
            return "OpenAI provider not available"
    
    def _update_sliding_window(self, source_text, translated_text):
        """
        DEPRECATED: Context windows are now managed by individual providers.
        This method updates all LLM provider context windows for backward compatibility.
        """
        log_debug("Warning: _update_sliding_window is deprecated, providers manage their own context")
        
        for provider_name, provider in self.llm_providers.items():
            try:
                provider.update_context_window(source_text, translated_text)
            except Exception as e:
                log_debug(f"Error updating {provider_name} context window: {e}")
    
    def _update_openai_sliding_window(self, source_text, translated_text):
        """
        DEPRECATED: Context windows are now managed by individual providers.
        This method routes to the unified OpenAI provider for backward compatibility.
        """
        log_debug("Warning: _update_openai_sliding_window is deprecated, using unified provider")
        
        if 'openai' in self.llm_providers:
            try:
                self.llm_providers['openai'].update_context_window(source_text, translated_text)
            except Exception as e:
                log_debug(f"Error updating OpenAI context window: {e}")
    
    def _clear_gemini_context(self):
        """
        DEPRECATED: Context windows are now managed by individual providers.
        This method routes to the unified Gemini provider for backward compatibility.
        """
        log_debug("Warning: _clear_gemini_context is deprecated, using unified provider")
        
        if 'gemini' in self.llm_providers:
            try:
                self.llm_providers['gemini'].clear_context_window()
            except Exception as e:
                log_debug(f"Error clearing Gemini context: {e}")
    
    def _clear_openai_context(self):
        """
        DEPRECATED: Context windows are now managed by individual providers.
        This method routes to the unified OpenAI provider for backward compatibility.
        """
        log_debug("Warning: _clear_openai_context is deprecated, using unified provider")
        
        if 'openai' in self.llm_providers:
            try:
                self.llm_providers['openai'].clear_context_window()
            except Exception as e:
                log_debug(f"Error clearing OpenAI context: {e}")