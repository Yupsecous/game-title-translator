# handlers/translation_handler.py
import re
import os
import gc
import sys
import time
import html
import hashlib # Not used here directly, but good for consistency
import traceback
from datetime import datetime
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
        
        # Initialize Gemini API call log file path
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.gemini_log_file = os.path.join(base_dir, "Gemini_API_call_logs.txt")
        
        # Initialize Gemini API call log file
        self._initialize_gemini_log()
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

    def _initialize_gemini_log(self):
        """Initialize the Gemini API call log file with a header if it's new."""
        try:
            # Ensure the directory exists
            log_dir = os.path.dirname(self.gemini_log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)

            if not os.path.exists(self.gemini_log_file):
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                header = f"""
###############################################
#         GEMINI API CALL LOG                 #
#         OCR Translator - Token Analysis     #
###############################################

Logging Started: {timestamp}
Purpose: Track input/output token usage for Gemini API calls, along with exact costs.
Format: Each entry shows complete message content sent to and received from Gemini,
        plus exact token counts and costs for the individual call and the session.

"""
                with open(self.gemini_log_file, 'w', encoding='utf-8') as f:
                    f.write(header)
                log_debug(f"Gemini API logging initialized: {self.gemini_log_file}")
            else:
                # Append a session start separator to existing log
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                session_start_msg = f"\n\n--- NEW LOGGING SESSION STARTED: {timestamp} ---\n"
                with open(self.gemini_log_file, 'a', encoding='utf-8') as f:
                    f.write(session_start_msg)
                log_debug(f"Gemini API logging continues in existing file: {self.gemini_log_file}")

        except Exception as e:
            log_debug(f"Error initializing Gemini API log: {e}")

    def _log_gemini_api_call(self, message_content, source_lang, target_lang, text_to_translate):
        """Log complete Gemini API call content to file for token usage analysis."""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Calculate detailed token estimates
            words_in_message = len(message_content.split())
            chars_in_message = len(message_content)
            lines_in_message = len(message_content.split('\n'))
            
            log_entry = f"""
=== GEMINI API CALL LOG ===
Timestamp: {timestamp}
Language Pair: {source_lang} -> {target_lang}
Original Text: {text_to_translate}

CALL DETAILS:
- Message Length: {chars_in_message} characters
- Word Count: {words_in_message} words
- Line Count: {lines_in_message} lines

COMPLETE MESSAGE CONTENT SENT TO GEMINI:
---BEGIN MESSAGE---
{message_content}
---END MESSAGE---

"""
            
            with open(self.gemini_log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)
                
            log_debug(f"Gemini API call logged: {chars_in_message} chars, ~{int(words_in_message * 1.3)} tokens")
            
        except Exception as e:
            log_debug(f"Error logging Gemini API call: {e}")

    def _get_cumulative_totals(self):
        """Reads the log file and calculates cumulative translated words and token totals."""
        total_translated_words = 0
        total_input = 0
        total_output = 0
        if not os.path.exists(self.gemini_log_file):
            return 0, 0, 0
        
        # Define regex to find the exact counts (accounting for "- " prefix)
        translated_words_regex = re.compile(r"^\s*-\s*Translated Words:\s*(\d+)")
        input_token_regex = re.compile(r"^\s*-\s*Exact Input Tokens:\s*(\d+)")
        output_token_regex = re.compile(r"^\s*-\s*Exact Output Tokens:\s*(\d+)")
        
        try:
            with open(self.gemini_log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    translated_words_match = translated_words_regex.match(line)
                    if translated_words_match:
                        total_translated_words += int(translated_words_match.group(1))
                        continue
                    
                    input_match = input_token_regex.match(line)
                    if input_match:
                        total_input += int(input_match.group(1))
                        continue # Move to next line
                    
                    output_match = output_token_regex.match(line)
                    if output_match:
                        total_output += int(output_match.group(1))
        except (IOError, ValueError) as e:
            log_debug(f"Error reading or parsing cumulative totals from log file: {e}")
            # Return 0, 0, 0 as a fallback
            return 0, 0, 0
            
        return total_translated_words, total_input, total_output

    def _log_gemini_response(self, response_text, call_duration, input_tokens, output_tokens, original_text):
        """Log Gemini API response, exact tokens, costs, and cumulative totals."""
        try:
            # --- 1. Calculate current call translated word count from original text ---
            current_translated_words = len(original_text.split())
            
            # --- 2. Get cumulative totals BEFORE this call ---
            prev_total_translated_words, prev_total_input, prev_total_output = self._get_cumulative_totals()

            # --- 3. Define costs and calculate for current call ---
            INPUT_COST_PER_MILLION = 0.10  # USD for gemini-2.5-flash-lite
            OUTPUT_COST_PER_MILLION = 0.40 # USD for gemini-2.5-flash-lite
            
            call_input_cost = (input_tokens / 1_000_000) * INPUT_COST_PER_MILLION
            call_output_cost = (output_tokens / 1_000_000) * OUTPUT_COST_PER_MILLION
            
            # --- 4. Calculate new cumulative totals AND costs ---
            new_total_translated_words = prev_total_translated_words + current_translated_words
            new_total_input = prev_total_input + input_tokens
            new_total_output = prev_total_output + output_tokens
            
            total_input_cost = (new_total_input / 1_000_000) * INPUT_COST_PER_MILLION
            total_output_cost = (new_total_output / 1_000_000) * OUTPUT_COST_PER_MILLION
            
            # --- 5. Format the log entry ---
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            response_entry = f"""
RESPONSE RECEIVED:
Timestamp: {timestamp}
Call Duration: {call_duration:.3f} seconds

---BEGIN RESPONSE---
{response_text}
---END RESPONSE---

TOKEN & COST ANALYSIS (CURRENT CALL):
- Translated Words: {current_translated_words}
- Exact Input Tokens: {input_tokens}
- Exact Output Tokens: {output_tokens}
- Input Cost: ${call_input_cost:.8f}
- Output Cost: ${call_output_cost:.8f}
- Total Cost for this Call: ${(call_input_cost + call_output_cost):.8f}

CUMULATIVE TOTALS (INCLUDING THIS CALL, FROM LOG START):
- Total Translated Words (so far): {new_total_translated_words}
- Total Input Tokens (so far): {new_total_input}
- Total Output Tokens (so far): {new_total_output}
- Total Input Cost (so far): ${total_input_cost:.8f}
- Total Output Cost (so far): ${total_output_cost:.8f}
- Cumulative Log Cost: ${(total_input_cost + total_output_cost):.8f}

========================================

"""
            
            # --- 6. Write to file ---
            with open(self.gemini_log_file, 'a', encoding='utf-8') as f:
                f.write(response_entry)
                
            log_debug(f"Gemini response logged: In={input_tokens}, Out={output_tokens}, Duration={call_duration:.3f}s")
                
        except Exception as e:
            log_debug(f"Error logging Gemini API response: {e}\n{traceback.format_exc()}")

    def _gemini_translate(self, text_to_translate_gm, source_lang_gm, target_lang_gm):
        """Gemini API call with simplified message format (no system instructions)."""
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
            
            # Check if we need to create a new model (minimal conditions)
            needs_new_session = (
                not hasattr(self, 'gemini_model') or 
                self.gemini_model is None or
                self.should_reset_session(api_key_gemini)  # API key changed
            )
            
            if needs_new_session:
                if hasattr(self, 'gemini_session_api_key') and self.gemini_session_api_key != api_key_gemini:
                    log_debug("Creating new Gemini model (API key changed)")
                else:
                    log_debug("Creating new Gemini model (no existing model)")
                self._initialize_gemini_session(source_lang_gm, target_lang_gm)
            else:
                # Check if language pair changed - clear context
                if (hasattr(self, 'gemini_current_source_lang') and hasattr(self, 'gemini_current_target_lang') and
                    (self.gemini_current_source_lang != source_lang_gm or self.gemini_current_target_lang != target_lang_gm)):
                    log_debug(f"Language pair changed from {self.gemini_current_source_lang}->{self.gemini_current_target_lang} to {source_lang_gm}->{target_lang_gm}, clearing context")
                    self._clear_gemini_context()
            
            # Track current language pair for context clearing
            self.gemini_current_source_lang = source_lang_gm
            self.gemini_current_target_lang = target_lang_gm
            
            if self.gemini_model is None:
                return "Gemini model initialization failed"
            
            # Get display names for source and target languages
            source_lang_name = self._get_language_display_name(source_lang_gm, 'gemini')
            target_lang_name = self._get_language_display_name(target_lang_gm, 'gemini')
            
            # Always start with the instruction line with explicit language names
            instruction_line = f"<Translate idiomatically the last {source_lang_name} item only to {target_lang_name}. Ensure perfect grammar, style and accuracy. Return translation only.>"
            
            # Build context window with new text integrated in grouped format
            context_with_new_text = self._build_context_window(text_to_translate_gm, source_lang_gm)
            
            if context_with_new_text:
                # Use grouped format with integrated new text
                message_content = f"{instruction_line}\n\n{context_with_new_text}\n{target_lang_name.upper()}:"
            else:
                # No context, use simple format 
                message_content = f"{instruction_line}\n\n{source_lang_name.upper()}: {text_to_translate_gm}\n\n{target_lang_name.upper()}:"
            
            log_debug(f"Sending to Gemini {source_lang_gm}->{target_lang_gm}: [{text_to_translate_gm}]")
            
            # Log complete API call content for token usage analysis
            self._log_gemini_api_call(message_content, source_lang_gm, target_lang_gm, text_to_translate_gm)
            
            api_call_start_time = time.time()
            if not hasattr(self, 'gemini_model') or self.gemini_model is None:
                return "Gemini model not initialized"
            
            response = self.gemini_model.generate_content(message_content)
            call_duration = time.time() - api_call_start_time
            log_debug(f"Gemini API call took {call_duration:.3f}s")

            # Extract exact token counts from API response metadata
            input_tokens, output_tokens = 0, 0
            try:
                if response.usage_metadata:
                    input_tokens = response.usage_metadata.prompt_token_count
                    output_tokens = response.usage_metadata.candidates_token_count
                    log_debug(f"Gemini usage metadata found: In={input_tokens}, Out={output_tokens}")
            except (AttributeError, KeyError):
                log_debug("Could not find usage_metadata in Gemini response. Tokens will be logged as 0.")

            translation_result = response.text.strip()
            # New: Add a line to strip the language code if it still appears
            target_lang_upper = target_lang_name.upper()
            if translation_result.startswith(f"{target_lang_upper}: "):
                translation_result = translation_result[len(f"{target_lang_upper}: "):].strip()
            if translation_result.startswith(f"{target_lang_upper}:"):
                translation_result = translation_result[len(f"{target_lang_upper}:"):].strip()
            # Also check for the old format just in case
            if translation_result.startswith(f"{target_lang_gm}: "):
                translation_result = translation_result[len(f"{target_lang_gm}: "):].strip()
            if translation_result.startswith(f"{target_lang_gm}:"):
                translation_result = translation_result[len(f"{target_lang_gm}:"):].strip()                
            log_debug(f"Gemini response: {translation_result}")
            
            # Log the response, tokens, and costs to the API call log file
            self._log_gemini_response(translation_result, call_duration, input_tokens, output_tokens, text_to_translate_gm)
            
            # Store successful translation in file cache
            if self.app.gemini_file_cache_var.get():
                self.app.cache_manager.save_to_file_cache('gemini', cache_key_gm, translation_result)
            
            # Update sliding window memory
            self._update_sliding_window(text_to_translate_gm, translation_result)
            
            return translation_result
            
        except Exception as e_gm:
            log_debug(f"Gemini API error: {type(e_gm).__name__} - {str(e_gm)}")
            return f"Gemini API error: {str(e_gm)}"

    def _initialize_gemini_session(self, source_lang, target_lang):
        """Initialize new Gemini chat session without system instructions."""
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=self.app.gemini_api_key_var.get().strip())
            
            # Optimal generation configuration for translation
            generation_config = {
                "temperature": 0.0,              # Natural, creative translations for dialogue
                "max_output_tokens": 1024,       # Sufficient for subtitle translations
                "candidate_count": 1,            # Single response needed
                "top_p": 0.95,                   # Slightly constrain token selection
                "top_k": 40,                     # Limit candidate tokens
                "response_mime_type": "text/plain"
            }
            
            # Gaming-appropriate safety settings
            from google.generativeai.types import HarmCategory, HarmBlockThreshold
            safety_settings = {
                # HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                # HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                # HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                # HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
            
            # Create model with optimized settings (no system instructions)
            model = genai.GenerativeModel(
                model_name="gemini-2.5-flash-lite-preview-06-17",  # Most cost-efficient, real-time optimized
                generation_config=generation_config,
                safety_settings=safety_settings
                # No system_instruction parameter - removed to reduce costs
            )
            
            # Store model directly for stateless calls (no chat session)
            self.gemini_model = model
            
            # Initialize sliding window memory and session tracking
            self.gemini_context_window = []
            self.gemini_session_api_key = self.app.gemini_api_key_var.get().strip()
            
            # Initialize language tracking for context clearing
            self.gemini_current_source_lang = source_lang
            self.gemini_current_target_lang = target_lang
            
            log_debug(f"Gemini model initialized for stateless calls (no chat session)")
            
        except Exception as e:
            log_debug(f"Failed to initialize Gemini model: {e}")
            self.gemini_model = None

    def _reset_gemini_session(self):
        """Reset Gemini model and context completely."""
        try:
            # Clear all session-related attributes
            session_attrs = [
                'gemini_model',
                'gemini_context_window', 
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
            
            log_debug("Gemini model reset completed - all state cleared")
        except Exception as e:
            log_debug(f"Error resetting Gemini model: {e}")
        # Always ensure model is None to force reinitialization
        self.gemini_model = None

    def force_gemini_session_reset(self, reason="Manual reset"):
        """Force a complete session reset when actually necessary (API key changes, etc.)."""
        log_debug(f"Forcing Gemini session reset - Reason: {reason}")
        self._reset_gemini_session()
        
    def _clear_gemini_context(self):
        """Clear Gemini context window after language changes."""
        try:
            self.gemini_context_window = []
            log_debug("Gemini context cleared")
        except Exception as e:
            log_debug(f"Error clearing Gemini context: {e}")
        
    def should_reset_session(self, api_key):
        """Check if session needs to be reset due to API key change."""
        if not hasattr(self, 'gemini_session_api_key'):
            return True
        return self.gemini_session_api_key != api_key
    
    def _build_context_window(self, new_source_text=None, source_lang_code=None):
        """Build context window from previous translations with grouped format."""
        if not hasattr(self, 'gemini_context_window'):
            self.gemini_context_window = []
        
        context_size = self.app.gemini_context_window_var.get()
        if context_size == 0 and not new_source_text:
            return ""
        
        source_lines = []
        target_lines = []
        
        # Add context pairs if available
        if context_size > 0 and self.gemini_context_window:
            # Get last N context pairs
            context_pairs = self.gemini_context_window[-context_size:]
            
            # Collect all source lines first, then all target lines
            for source_text, target_text, source_lang, target_lang in context_pairs:
                # Get display names and convert to uppercase
                source_display = self._get_language_display_name(source_lang, 'gemini').upper()
                target_display = self._get_language_display_name(target_lang, 'gemini').upper()
                source_lines.append(f"{source_display}: {source_text}")
                target_lines.append(f"{target_display}: {target_text}")
        
        # Add new source text if provided
        if new_source_text and source_lang_code:
            source_display = self._get_language_display_name(source_lang_code, 'gemini').upper()
            source_lines.append(f"{source_display}: {new_source_text}")
        
        # Combine: all sources first, blank line, then all targets
        if source_lines and target_lines:
            all_lines = source_lines + [""] + target_lines
        elif source_lines:
            all_lines = source_lines
        elif target_lines:
            all_lines = target_lines
        else:
            all_lines = []
        return "\n".join(all_lines) if all_lines else ""

    def _update_sliding_window(self, source_text, target_text):
        """Update sliding window with new translation pair including language codes."""
        if not hasattr(self, 'gemini_context_window'):
            self.gemini_context_window = []
        
        # Get current language codes
        source_lang = getattr(self, 'gemini_current_source_lang', 'en')
        target_lang = getattr(self, 'gemini_current_target_lang', 'pl')
        
        # Add new pair with language codes
        self.gemini_context_window.append((source_text, target_text, source_lang, target_lang))
        
        # Keep only last 5 pairs (more than the max context window setting)
        self.gemini_context_window = self.gemini_context_window[-5:]



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
            extra_params = {
                "context_window": context_window
            }
            log_debug(f"Gemini translation request with context_window={context_window}, {source_lang}->{target_lang}")
        
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
