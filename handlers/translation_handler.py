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

    def _gemini_translate(self, text_to_translate_gm, source_lang_gm, target_lang_gm):
        """Gemini API call with session management and fuzzy duplicate detection."""
        log_debug(f"Gemini API call for: {text_to_translate_gm}")
        
        api_key_gemini = self.app.gemini_api_key_var.get().strip()
        if not api_key_gemini:
            return "Gemini API key missing"
        
        # Check file cache if enabled
        if self.app.gemini_file_cache_var.get():
            cache_key_gm = f"gemini:{source_lang_gm}:{target_lang_gm}:{text_to_translate_gm}"
            file_cached_gm = self.app.cache_manager.check_file_cache('gemini', cache_key_gm)
            if file_cached_gm:
                log_debug(f"Found in Gemini file cache: {text_to_translate_gm}")
                return file_cached_gm
        
        try:
            import google.generativeai as genai
            
            # Check if we need to create a new session (minimal conditions)
            needs_new_session = (
                not hasattr(self, 'gemini_chat_session') or 
                self.gemini_chat_session is None or
                self.should_reset_session(api_key_gemini)  # API key changed
            )
            
            if needs_new_session:
                if hasattr(self, 'gemini_session_api_key') and self.gemini_session_api_key != api_key_gemini:
                    log_debug("Creating new Gemini session (API key changed)")
                else:
                    log_debug("Creating new Gemini session (no existing session)")
                self._initialize_gemini_session(source_lang_gm, target_lang_gm)
            else:
                # Check if language pair changed - clear context to prevent wrong SKIP responses
                if (hasattr(self, 'gemini_current_source_lang') and hasattr(self, 'gemini_current_target_lang') and
                    (self.gemini_current_source_lang != source_lang_gm or self.gemini_current_target_lang != target_lang_gm)):
                    log_debug(f"Language pair changed from {self.gemini_current_source_lang}->{self.gemini_current_target_lang} to {source_lang_gm}->{target_lang_gm}, clearing context to prevent incorrect SKIP responses")
                    self._clear_gemini_context()
            
            # Track current language pair for context clearing
            self.gemini_current_source_lang = source_lang_gm
            self.gemini_current_target_lang = target_lang_gm
            
            if self.gemini_chat_session is None:
                return "Gemini session initialization failed"
            
            # Build final message with language codes and context
            language_code_header = f"<{source_lang_gm}-{target_lang_gm}>"
            
            # Prepare context from sliding window
            context_window = self._build_context_window()
            
            if context_window and self.app.gemini_fuzzy_detection_var.get():
                # Context exists, use full format with context + new text to translate
                message_content = f"{language_code_header}\n{context_window}\n{text_to_translate_gm}:=:"
            elif self.app.gemini_fuzzy_detection_var.get() and hasattr(self, 'gemini_last_translation') and self.gemini_last_translation:
                # No sliding window context but we have last translation, show it for comparison
                message_content = f"{language_code_header}\n{self.gemini_last_source}:=:{self.gemini_last_translation}\n{text_to_translate_gm}:=:"
            else:
                # No context available or fuzzy detection disabled - simple translation
                message_content = f"{language_code_header}\n{text_to_translate_gm}"
            
            log_debug(f"Sending to Gemini with language codes {source_lang_gm}->{target_lang_gm}: [{text_to_translate_gm}]")
            
            api_call_start_time = time.time()
            response = self.gemini_chat_session.send_message(message_content)
            log_debug(f"Gemini API call took {time.time() - api_call_start_time:.3f}s")
            
            translation_result = response.text.strip()
            log_debug(f"Gemini response: {translation_result}")
            
            # Handle SKIP responses
            if translation_result == "<SKIP>":
                # Get last valid translation from memory
                last_translation = self._get_last_valid_translation()
                if last_translation:
                    log_debug(f"SKIP detected, reusing last translation: {last_translation}")
                    # Store the SKIP->actual translation mapping in cache
                    if self.app.gemini_file_cache_var.get():
                        self.app.cache_manager.save_to_file_cache('gemini', cache_key_gm, last_translation)
                    return last_translation
                else:
                    log_debug("SKIP received but no previous translation available")
                    return "Translation not available"
            
            # Store successful translation in file cache
            if self.app.gemini_file_cache_var.get():
                self.app.cache_manager.save_to_file_cache('gemini', cache_key_gm, translation_result)
            
            # Update sliding window memory (no language filtering needed)
            self._update_sliding_window(text_to_translate_gm, translation_result)
            
            return translation_result
            
        except Exception as e_gm:
            log_debug(f"Gemini API error: {type(e_gm).__name__} - {str(e_gm)}")
            return f"Gemini API error: {str(e_gm)}"

    def _initialize_gemini_session(self, source_lang, target_lang):
        """Initialize new Gemini chat session with system instructions."""
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=self.app.gemini_api_key_var.get().strip())
            
            # Get language names for system instructions
            source_name = self._get_language_display_name(source_lang, 'gemini')
            target_name = self._get_language_display_name(target_lang, 'gemini')
            
            # Build system instructions
            system_instructions = self._build_system_instructions(source_name, target_name)
            
            # Optimal generation configuration for translation
            generation_config = {
                "temperature": 0.8,              # Natural, creative translations for dialogue
                "max_output_tokens": 1024,       # Sufficient for subtitle translations
                "candidate_count": 1,            # Single response needed
                "top_p": 0.95,                   # Slightly constrain token selection
                "top_k": 40,                     # Limit candidate tokens
                "response_mime_type": "text/plain"
            }
            
            # Gaming-appropriate safety settings
            from google.generativeai.types import HarmCategory, HarmBlockThreshold
            safety_settings = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            }
            
            # Create model with optimized settings (cost-efficient, low latency)
            model = genai.GenerativeModel(
                model_name="gemini-2.5-flash-lite-preview-06-17",  # Most cost-efficient, real-time optimized
                generation_config=generation_config,
                safety_settings=safety_settings,
                system_instruction=system_instructions
            )
            
            # Start chat session
            self.gemini_chat_session = model.start_chat(history=[])
            
            # Initialize sliding window memory and session tracking
            self.gemini_context_window = []
            self.gemini_session_api_key = self.app.gemini_api_key_var.get().strip()
            self.gemini_last_translation = None
            self.gemini_last_source = None
            
            # Initialize language tracking for context clearing
            self.gemini_current_source_lang = source_lang
            self.gemini_current_target_lang = target_lang
            
            log_debug(f"Gemini session initialized with language code support")
            
        except Exception as e:
            log_debug(f"Failed to initialize Gemini session: {e}")
            self.gemini_chat_session = None

    def _reset_gemini_session(self):
        """Reset Gemini session and context completely."""
        try:
            # Clear all session-related attributes
            session_attrs = [
                'gemini_chat_session',
                'gemini_context_window', 
                'gemini_last_translation',
                'gemini_last_source',
                'gemini_session_api_key',
                'gemini_current_source_lang',
                'gemini_current_target_lang'
            ]
            
            for attr in session_attrs:
                if hasattr(self, attr):
                    setattr(self, attr, None)
                    log_debug(f"Reset Gemini attribute: {attr}")
            
            # Initialize empty context window
            self.gemini_context_window = []
            
            log_debug("Gemini session reset completed - all state cleared")
        except Exception as e:
            log_debug(f"Error resetting Gemini session: {e}")
        # Always ensure session is None to force reinitialization
        self.gemini_chat_session = None

    def force_gemini_session_reset(self, reason="Manual reset"):
        """Force a complete session reset when actually necessary (API key changes, etc.)."""
        log_debug(f"Forcing Gemini session reset - Reason: {reason}")
        self._reset_gemini_session()
        
    def _clear_gemini_context(self):
        """Clear Gemini context window and last translation to prevent incorrect SKIP responses after language changes."""
        try:
            self.gemini_context_window = []
            self.gemini_last_translation = None
            self.gemini_last_source = None
            log_debug("Gemini context cleared - no previous translations available for comparison")
        except Exception as e:
            log_debug(f"Error clearing Gemini context: {e}")
        
    def should_reset_session(self, api_key):
        """Check if session needs to be reset due to API key change."""
        if not hasattr(self, 'gemini_session_api_key'):
            return True
        return self.gemini_session_api_key != api_key
    
    def handle_fuzzy_detection_change(self):
        """Handle fuzzy detection setting change - requires session reset due to system instruction change."""
        if hasattr(self, 'gemini_chat_session') and self.gemini_chat_session is not None:
            log_debug("Fuzzy detection setting changed - resetting Gemini session (system instructions changed)")
            self.force_gemini_session_reset("Fuzzy detection setting changed")

    def _build_system_instructions(self, source_name, target_name):
        """Build system instructions for Gemini with language codes and fuzzy detection."""
        base_instructions = f"""You are a professional translator. You will receive translation requests with language codes in this format:

FORMAT 1 - Simple translation (no context):
<source_code-target_code>
Text to translate

FORMAT 2 - Translation with context:
<source_code-target_code>
Previous text:=:Previous translation
Another text:=:Another translation
Current text:=:

Language Codes:
ar=Arabic, bg=Bulgarian, zh-CN=Chinese (Simplified), zh-TW=Chinese (Traditional), hr=Croatian, cs=Czech, da=Danish, nl=Dutch, en=English, et=Estonian, fi=Finnish, fr=French, de=German, el=Greek, he=Hebrew, hi=Hindi, hu=Hungarian, is=Icelandic, id=Indonesian, it=Italian, ja=Japanese, ko=Korean, lv=Latvian, lt=Lithuanian, no=Norwegian, pl=Polish, pt-BR=Portuguese (Brazil), pt-PT=Portuguese (Portugal), ro=Romanian, ru=Russian, sr=Serbian, sk=Slovak, sl=Slovenian, es=Spanish, sw=Swahili, sv=Swedish, th=Thai, tr=Turkish, uk=Ukrainian, vi=Vietnamese

When you see Format 1 (simple text after language code), always provide a translation.
When you see Format 2 (context with :=: pairs), the context lines help with translation. The last line ending in :=: needs translation.

CRITICAL: For timestamps, numbers, codes, or unclear input, return EXACTLY what you received:
- Input "1:21:49 v" → Output "1:21:49 v" (EXACTLY as received)
- Input "22:15" → Output "22:15" (EXACTLY as received)
- Input "G" → Output "G" (EXACTLY as received)
- Input "123" → Output "123" (EXACTLY as received)

Only translate clear, meaningful text. NEVER invent or guess translations for unclear input."""

        if self.app.gemini_fuzzy_detection_var.get():
            return base_instructions + """

DUPLICATE DETECTION: ONLY when using Format 2 (with :=: context pairs), if the current text to translate is essentially the same as the immediately previous subtitle (accounting for minor OCR errors, typos, punctuation differences, or spacing issues), respond with exactly: "<SKIP>"

IMPORTANT: Only use "<SKIP>" when:
1. The message uses Format 2 (you see :=: pairs showing previous translations)
2. The current text is essentially identical to the immediately previous subtitle
3. You are confident the meaning is the same

If the message uses Format 1 (simple text after language code), ALWAYS provide a translation, never "<SKIP>".

Examples that should trigger "<SKIP>" response (only in Format 2):
- Previous: "Watch out!" → Current: "Watch out! " (spacing)
- Previous: "She is beautiful" → Current: "She is beutiful" (typo)  
- Previous: "Hello there" → Current: "Hello there." (punctuation)
- Previous: "Amazing view" → Current: "Amazing vlew" (OCR error)"""
        else:
            return base_instructions

    def _build_context_window(self):
        """Build context window from previous translations."""
        if not hasattr(self, 'gemini_context_window'):
            self.gemini_context_window = []
        
        context_size = self.app.gemini_context_window_var.get()
        if context_size == 0 or not self.gemini_context_window:
            return ""
        
        # Get last N context pairs
        context_pairs = self.gemini_context_window[-context_size:]
        context_lines = []
        
        for source_text, target_text in context_pairs:
            context_lines.append(f"{source_text}:=:{target_text}")
        
        return "\n".join(context_lines)

    def _update_sliding_window(self, source_text, target_text):
        """Update sliding window with new translation pair."""
        if not hasattr(self, 'gemini_context_window'):
            self.gemini_context_window = []
        
        # Add new pair
        self.gemini_context_window.append((source_text, target_text))
        
        # Keep only last 5 pairs (more than the max context window setting)
        self.gemini_context_window = self.gemini_context_window[-5:]
        
        # Update last translation for SKIP functionality
        self.gemini_last_translation = target_text
        self.gemini_last_source = source_text

    def _get_last_valid_translation(self):
        """Get the last valid translation for SKIP responses."""
        if hasattr(self, 'gemini_last_translation') and self.gemini_last_translation:
            return self.gemini_last_translation
        return None

    def _get_language_display_name(self, lang_code, provider):
        """Get display name for language code using the language manager."""
        try:
            # Use the language manager's existing functionality
            display_name = self.app.language_manager.get_localized_language_name(lang_code, provider, 'english')
            
            # If not found, try fallback logic
            if display_name == lang_code:
                # Special case for 'auto'
                if lang_code.lower() == 'auto':
                    return 'Auto'
                # Fallback to title case
                return lang_code.title()
            
            return display_name
        except Exception as e:
            log_debug(f"Error getting language display name for {lang_code}/{provider}: {e}")
            # Special case for 'auto'
            if lang_code.lower() == 'auto':
                return 'Auto'
            return lang_code.title()

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
        
        elif selected_translation_model == 'gemini_api':
            if not self.app.GEMINI_API_AVAILABLE:
                return "Gemini API libraries not available."
            
            api_key_gemini = self.app.gemini_api_key_var.get().strip()
            if not api_key_gemini:
                return "Gemini API key missing."
            
            source_lang = self.app.gemini_source_lang
            target_lang = self.app.gemini_target_lang
            context_window = self.app.gemini_context_window_var.get()
            fuzzy_detection = self.app.gemini_fuzzy_detection_var.get()
            extra_params = {
                "context_window": context_window,
                "fuzzy_detection": fuzzy_detection
            }
            log_debug(f"Gemini translation request with context_window={context_window}, fuzzy_detection={fuzzy_detection}, {source_lang}->{target_lang}")
        
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
        elif selected_translation_model == 'gemini_api':
            translated_api_text = self._gemini_translate(cleaned_text_main, source_lang, target_lang)
            # Save to file cache if successful and file caching enabled
            if (not self._is_error_message(translated_api_text) 
                and self.app.gemini_file_cache_var.get()):
                cache_key_gemini = f"gemini:{source_lang}:{target_lang}:{cleaned_text_main}"
                self.app.cache_manager.save_to_file_cache('gemini', cache_key_gemini, translated_api_text)
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
        
        # Only filter out obvious UI placeholders and empty content
        placeholders_list = [
            "source text will appear here", "translation will appear here",
            "translation...", "ocr source", "source text", "loading...",
            "translating...", "", "translation", "...", "translation error:"
        ]
        if text_lower_content in placeholders_list or text_lower_content.startswith("translation error:"):
            return True
        
        # Only filter truly obvious UI artifacts - be very conservative
        ui_patterns_list = [
            r'^[_\-=<>/\s\.\\|\[\]\{\}]+$',  # Special characters only (no letters/numbers)
            r'^ocr\s+source', r'^source\s+text', 
            r'^translat(ion|ing)', r'appear\s+here$', 
            r'[×✖️]',  # Close/delete symbols only
        ]
        
        for pattern_re in ui_patterns_list:
            try:
                if (pattern_re.startswith('^') and re.match(pattern_re, text_content, re.IGNORECASE)) or \
                   (not pattern_re.startswith('^') and re.search(pattern_re, text_content, re.IGNORECASE)):
                    log_debug(f"Filtered out UI pattern '{pattern_re}': '{text_content}'")
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
