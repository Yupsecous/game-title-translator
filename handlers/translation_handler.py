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
        
        # === LEGACY PROVIDER SUPPORT ===
        # Keep existing variables for backward compatibility with non-LLM providers
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
        
        # Initialize legacy log file paths
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Legacy Gemini log files (kept for backward compatibility)
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
        if not text:
            return False
        
        text_lower = text.lower()
        error_indicators = [
            'error:', 'api error', 'translation error', 'not available',
            'missing', 'failed', 'initialization failed', 'timeout'
        ]
        
        return any(indicator in text_lower for indicator in error_indicators)
    
    def _format_dialog_text(self, text):
        """Format dialog text with proper punctuation."""
        if not text:
            return text
        
        text = text.strip()
        
        # Basic dialog formatting
        # Add period if text doesn't end with punctuation
        if text and not text[-1] in '.!?…':
            text += '.'
        
        return text
    
    def is_placeholder_text(self, text):
        """Check if text is a placeholder that should not be translated."""
        if not text:
            return True
        
        text = text.strip().lower()
        
        # Common placeholder patterns
        placeholders = [
            'loading', 'please wait', '...', '…', 'n/a', 'tbd', 'todo',
            'placeholder', 'sample text', 'test', 'debug'
        ]
        
        return text in placeholders or len(text) < 2
    
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
