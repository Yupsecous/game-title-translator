# handlers/translation_handler.py
import re
import os
import gc
import sys
import time
import html
import hashlib # Not used here directly, but good for consistency
import traceback
import threading
from datetime import datetime, timedelta
# Removed lru_cache import - replaced with unified cache

from logger import log_debug
# from translation_utils import get_lang_code_for_translation_api # Replaced by direct use of API codes
from marian_mt_translator import MarianMTTranslator # Already imported
from unified_translation_cache import UnifiedTranslationCache

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
    def __init__(self, app):
        self.app = app
        # Initialize unified translation cache (replaces all individual LRU caches)
        self.unified_cache = UnifiedTranslationCache(max_size=1000)
        
        # Add thread lock for atomic logging to prevent interleaved logs
        self._log_lock = threading.Lock()
        
        # Initialize session counters - will be set by reading existing logs
        self.ocr_session_counter = 1
        self.translation_session_counter = 1
        self.current_ocr_session_active = False
        self.current_translation_session_active = False
        
        # Track pending API calls to ensure session ends only after all calls complete
        self._pending_ocr_calls = 0
        self._pending_translation_calls = 0
        self._api_calls_lock = threading.Lock()
        
        # Initialize Gemini API call log file path
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.gemini_log_file = os.path.join(base_dir, "Gemini_API_call_logs.txt")
        
        # Initialize short log file paths
        self.ocr_short_log_file = os.path.join(base_dir, "API_OCR_short_log.txt")
        self.tra_short_log_file = os.path.join(base_dir, "API_TRA_short_log.txt")
        
        # Initialize Gemini API call log file
        self._initialize_gemini_log()
        
        # Initialize session counters by reading existing logs
        self._initialize_session_counters()
        
        log_debug("Translation handler initialized with unified cache")
    
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
        """Initialize the Gemini API call log file and short log files with headers if they're new."""
        try:
            # Ensure the directory exists
            log_dir = os.path.dirname(self.gemini_log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)

            timestamp = self._get_precise_timestamp()

            # Initialize main log file
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
                log_debug(f"Gemini API logging initialized: {self.gemini_log_file}")
            else:
                # Append a session start separator to existing log
                session_start_msg = f"\n\n--- NEW LOGGING SESSION STARTED: {timestamp} ---\n"
                with open(self.gemini_log_file, 'a', encoding='utf-8') as f:
                    f.write(session_start_msg)
                log_debug(f"Gemini API logging continues in existing file: {self.gemini_log_file}")

            # Initialize short OCR log file
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
                log_debug(f"Gemini OCR short log initialized: {self.ocr_short_log_file}")
            else:
                # Append session separator
                with open(self.ocr_short_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"\n--- SESSION: {timestamp} ---\n")

            # Initialize short translation log file
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
                log_debug(f"Gemini translation short log initialized: {self.tra_short_log_file}")
            else:
                # Append session separator
                with open(self.tra_short_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"\n--- SESSION: {timestamp} ---\n")

        except Exception as e:
            log_debug(f"Error initializing Gemini API logs: {e}")

    def _initialize_session_counters(self):
        """Initialize session counters by reading existing logs to find the highest session number."""
        try:
            # Read OCR log to find highest OCR session number
            highest_ocr_session = 0
            if os.path.exists(self.ocr_short_log_file):
                with open(self.ocr_short_log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith("SESSION ") and " STARTED " in line:
                            try:
                                # Extract session number from "SESSION X STARTED"
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
                                # Extract session number from "SESSION X STARTED"
                                session_num = int(line.split()[1])
                                highest_translation_session = max(highest_translation_session, session_num)
                            except (IndexError, ValueError):
                                continue
            
            # Set counters to highest found + 1 (for next session)
            self.ocr_session_counter = highest_ocr_session + 1
            self.translation_session_counter = highest_translation_session + 1
            
            log_debug(f"Initialized session counters: OCR={self.ocr_session_counter}, Translation={self.translation_session_counter}")
            
        except Exception as e:
            log_debug(f"Error initializing session counters: {e}, using defaults")
            # Fall back to 1 if there's any error
            self.ocr_session_counter = 1
            self.translation_session_counter = 1

    def _increment_pending_ocr_calls(self):
        """Increment the count of pending OCR calls."""
        with self._api_calls_lock:
            self._pending_ocr_calls += 1

    def _decrement_pending_ocr_calls(self):
        """Decrement the count of pending OCR calls and try to end session if ready."""
        with self._api_calls_lock:
            self._pending_ocr_calls = max(0, self._pending_ocr_calls - 1)
            # Try to end session if it was requested and no pending calls remain
            if self._pending_ocr_calls == 0 and hasattr(self, '_ocr_session_should_end') and self._ocr_session_should_end:
                # Schedule session end outside the lock to avoid potential deadlock
                self.try_end_sessions_when_ready()

    def _increment_pending_translation_calls(self):
        """Increment the count of pending translation calls."""
        with self._api_calls_lock:
            self._pending_translation_calls += 1

    def _decrement_pending_translation_calls(self):
        """Decrement the count of pending translation calls and try to end session if ready."""
        with self._api_calls_lock:
            self._pending_translation_calls = max(0, self._pending_translation_calls - 1)
            # Try to end session if it was requested and no pending calls remain
            if self._pending_translation_calls == 0 and hasattr(self, '_translation_session_should_end') and self._translation_session_should_end:
                # Schedule session end outside the lock to avoid potential deadlock
                self.try_end_sessions_when_ready()

    def _has_pending_calls(self):
        """Check if there are any pending API calls."""
        with self._api_calls_lock:
            return self._pending_ocr_calls > 0 or self._pending_translation_calls > 0

    def start_ocr_session(self):
        """Start a new OCR session with numbered identifier."""
        if not self.current_ocr_session_active:
            timestamp = self._get_precise_timestamp()
            try:
                with open(self.ocr_short_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"\nSESSION {self.ocr_session_counter} STARTED {timestamp}\n")
                self.current_ocr_session_active = True
                log_debug(f"OCR Session {self.ocr_session_counter} started")
            except Exception as e:
                log_debug(f"Error starting OCR session: {e}")

    def end_ocr_session(self):
        """End the current OCR session only if no pending OCR calls."""
        if self.current_ocr_session_active:
            # Wait for any pending OCR calls to complete before ending session
            if self._pending_ocr_calls > 0:
                log_debug(f"OCR session end delayed: {self._pending_ocr_calls} pending calls")
                return False  # Session not ended yet
            
            timestamp = self._get_precise_timestamp()
            try:
                with open(self.ocr_short_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"SESSION {self.ocr_session_counter} ENDED {timestamp}\n")
                self.current_ocr_session_active = False
                self.ocr_session_counter += 1
                log_debug(f"OCR Session {self.ocr_session_counter - 1} ended")
                return True  # Session ended successfully
            except Exception as e:
                log_debug(f"Error ending OCR session: {e}")
                return False
        return True  # Already inactive

    def start_translation_session(self):
        """Start a new translation session with numbered identifier."""
        if not self.current_translation_session_active:
            timestamp = self._get_precise_timestamp()
            try:
                with open(self.tra_short_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"\nSESSION {self.translation_session_counter} STARTED {timestamp}\n")
                self.current_translation_session_active = True
                log_debug(f"Translation Session {self.translation_session_counter} started")
            except Exception as e:
                log_debug(f"Error starting translation session: {e}")

    def end_translation_session(self):
        """End the current translation session only if no pending translation calls."""
        if self.current_translation_session_active:
            # Wait for any pending translation calls to complete before ending session
            if self._pending_translation_calls > 0:
                log_debug(f"Translation session end delayed: {self._pending_translation_calls} pending calls")
                return False  # Session not ended yet
            
            timestamp = self._get_precise_timestamp()
            try:
                with open(self.tra_short_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"SESSION {self.translation_session_counter} ENDED {timestamp}\n")
                self.current_translation_session_active = False
                self.translation_session_counter += 1
                log_debug(f"Translation Session {self.translation_session_counter - 1} ended")
                return True  # Session ended successfully
            except Exception as e:
                log_debug(f"Error ending translation session: {e}")
                return False
        return True  # Already inactive

    def try_end_sessions_when_ready(self):
        """Try to end sessions if they're marked for ending and no pending calls remain."""
        sessions_ended = []
        
        # Try to end OCR session if it should be ended
        if hasattr(self, '_ocr_session_should_end') and self._ocr_session_should_end:
            if self.end_ocr_session():
                self._ocr_session_should_end = False
                sessions_ended.append("OCR")
        
        # Try to end translation session if it should be ended
        if hasattr(self, '_translation_session_should_end') and self._translation_session_should_end:
            if self.end_translation_session():
                self._translation_session_should_end = False
                sessions_ended.append("Translation")
        
        if sessions_ended:
            log_debug(f"Successfully ended pending sessions: {', '.join(sessions_ended)}")
        
        return len(sessions_ended) > 0

    def request_end_ocr_session(self):
        """Request to end OCR session - will end when no pending calls remain."""
        if self.current_ocr_session_active:
            if self._pending_ocr_calls == 0:
                # Can end immediately
                return self.end_ocr_session()
            else:
                # Mark for ending when calls complete
                self._ocr_session_should_end = True
                log_debug(f"OCR session end requested, waiting for {self._pending_ocr_calls} pending calls")
                return False
        return True

    def request_end_translation_session(self):
        """Request to end translation session - will end when no pending calls remain."""
        if self.current_translation_session_active:
            if self._pending_translation_calls == 0:
                # Can end immediately
                return self.end_translation_session()
            else:
                # Mark for ending when calls complete
                self._translation_session_should_end = True
                log_debug(f"Translation session end requested, waiting for {self._pending_translation_calls} pending calls")
                return False
        return True

    def force_end_sessions_on_app_close(self):
        """Force end both sessions when application is closing, even if there are pending calls."""
        timestamp = self._get_precise_timestamp()
        
        # Force end OCR session
        if self.current_ocr_session_active:
            try:
                with open(self.ocr_short_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"SESSION {self.ocr_session_counter} ENDED {timestamp} (FORCED - APP CLOSING)\n")
                self.current_ocr_session_active = False
                log_debug(f"OCR Session {self.ocr_session_counter} force ended (app closing)")
            except Exception as e:
                log_debug(f"Error force ending OCR session: {e}")
        
        # Force end translation session
        if self.current_translation_session_active:
            try:
                with open(self.tra_short_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"SESSION {self.translation_session_counter} ENDED {timestamp} (FORCED - APP CLOSING)\n")
                self.current_translation_session_active = False
                log_debug(f"Translation Session {self.translation_session_counter} force ended (app closing)")
            except Exception as e:
                log_debug(f"Error force ending translation session: {e}")
        
        # Reset pending call counters
        with self._api_calls_lock:
            self._pending_ocr_calls = 0
            self._pending_translation_calls = 0

    def _log_gemini_api_call(self, message_content, source_lang, target_lang, text_to_translate):
        """Deprecated - replaced by _log_complete_gemini_translation_call for atomic logging."""
        log_debug("Warning: _log_gemini_api_call is deprecated, use _log_complete_gemini_translation_call instead")
        pass

    def _get_cumulative_totals(self):
        """Reads the log file and calculates cumulative translated words and token totals."""
        total_translated_words = 0
        total_input = 0
        total_output = 0
        if not os.path.exists(self.gemini_log_file):
            log_debug(f"Gemini log file does not exist: {self.gemini_log_file}")
            return 0, 0, 0
        
        # Define regex to find the exact counts (accounting for "- " prefix and "(so far)" format)
        translated_words_regex = re.compile(r"^\s*-\s*Total Translated Words \(so far\):\s*(\d+)")
        input_token_regex = re.compile(r"^\s*-\s*Total Input Tokens \(so far\):\s*(\d+)")
        output_token_regex = re.compile(r"^\s*-\s*Total Output Tokens \(so far\):\s*(\d+)")
        
        try:
            with open(self.gemini_log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    translated_words_match = translated_words_regex.match(line)
                    if translated_words_match:
                        total_translated_words = int(translated_words_match.group(1))
                        continue
                    
                    input_match = input_token_regex.match(line)
                    if input_match:
                        total_input = int(input_match.group(1))
                        continue # Move to next line
                    
                    output_match = output_token_regex.match(line)
                    if output_match:
                        total_output = int(output_match.group(1))
                        
        except (IOError, ValueError) as e:
            log_debug(f"Error reading or parsing cumulative totals from log file: {e}")
            # Return 0, 0, 0 as a fallback
            return 0, 0, 0
            
        return total_translated_words, total_input, total_output

    def _get_precise_timestamp(self):
        """Get timestamp with millisecond precision."""
        now = datetime.now()
        return now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # Remove last 3 digits for milliseconds

    def _calculate_start_time(self, end_time_str, duration_seconds):
        """Calculate start time based on end time and duration."""
        try:
            # Parse the end time string
            end_time = datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S.%f")
            # Subtract the duration to get start time
            start_time = end_time - timedelta(seconds=duration_seconds)
            # Format back to string
            return start_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        except Exception as e:
            log_debug(f"Error calculating start time: {e}")
            # Fallback to end time if calculation fails
            return end_time_str

    def _get_cumulative_totals_ocr(self):
        """Get cumulative totals for OCR calls from the log file."""
        total_input = 0
        total_output = 0
        total_cost = 0.0
        
        if not os.path.exists(self.gemini_log_file):
            return 0, 0, 0.0
        
        # Regex to find OCR cumulative totals
        input_token_regex = re.compile(r"^\s*-\s*Total Input Tokens \(OCR, so far\):\s*(\d+)")
        output_token_regex = re.compile(r"^\s*-\s*Total Output Tokens \(OCR, so far\):\s*(\d+)")
        cost_regex = re.compile(r"^\s*-\s*Total OCR Cost \(so far\):\s*\$([0-9.]+)")
        
        try:
            with open(self.gemini_log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    input_match = input_token_regex.match(line)
                    if input_match:
                        total_input = int(input_match.group(1))
                        continue
                    
                    output_match = output_token_regex.match(line)
                    if output_match:
                        total_output = int(output_match.group(1))
                        continue
                        
                    cost_match = cost_regex.match(line)
                    if cost_match:
                        total_cost = float(cost_match.group(1))
                        
        except (IOError, ValueError) as e:
            log_debug(f"Error reading OCR cumulative totals: {e}")
            return 0, 0, 0.0
            
        return total_input, total_output, total_cost

    def _write_short_ocr_log(self, call_start_time, call_end_time, call_duration, input_tokens, output_tokens, call_cost, cumulative_input, cumulative_output, cumulative_cost, parsed_result):
        """Write concise OCR call log entry."""
        if not self.app.gemini_api_log_enabled_var.get():
            return
            
        try:
            log_entry = f"""========= OCR CALL ===========
Start: {call_start_time}
End: {call_end_time}
Duration: {call_duration:.3f}s
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

    def _write_short_translation_log(self, call_start_time, call_end_time, call_duration, input_tokens, output_tokens, call_cost, cumulative_input, cumulative_output, cumulative_cost, original_text, translated_text, source_lang, target_lang):
        """Write concise translation call log entry."""
        if not self.app.gemini_api_log_enabled_var.get():
            return
            
        try:
            # Get language display names
            source_lang_name = self._get_language_display_name(source_lang, 'gemini').upper()
            target_lang_name = self._get_language_display_name(target_lang, 'gemini').upper()
            
            log_entry = f"""===== TRANSLATION CALL =======
Start: {call_start_time}
End: {call_end_time}
Duration: {call_duration:.3f}s
Tokens: In={input_tokens}, Out={output_tokens} | Cost: ${call_cost:.8f}
Total (so far): In={cumulative_input}, Out={cumulative_output} | Cost: ${cumulative_cost:.8f}
Result:
--------------------------------------------------
{source_lang_name}: {original_text}
{target_lang_name}: {translated_text}
--------------------------------------------------

"""
            with open(self.tra_short_log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)
        except Exception as e:
            log_debug(f"Error writing short translation log: {e}")

    def _log_complete_gemini_translation_call(self, message_content, response_text, call_duration, input_tokens, output_tokens, original_text, source_lang, target_lang):
        """Log complete Gemini translation API call with atomic writing (request + response + stats)."""
        # Check if API logging is enabled
        if not self.app.gemini_api_log_enabled_var.get():
            return
            
        try:
            with self._log_lock:  # Ensure atomic logging to prevent interleaved logs
                # Calculate correct start and end times based on call duration
                call_end_time = self._get_precise_timestamp()
                call_start_time = self._calculate_start_time(call_end_time, call_duration)
                
                # --- 1. Calculate current call translated word count from original text ---
                current_translated_words = len(original_text.split())
                
                # --- 2. Get cumulative totals BEFORE this call ---
                prev_total_translated_words, prev_total_input, prev_total_output = self._get_cumulative_totals()

                # --- 3. Define costs and calculate for current call ---
                INPUT_COST_PER_MILLION = float(self.app.config['Settings'].get('input_token_cost', '0.1'))
                OUTPUT_COST_PER_MILLION = float(self.app.config['Settings'].get('output_token_cost', '0.4'))
                
                call_input_cost = (input_tokens / 1_000_000) * INPUT_COST_PER_MILLION
                call_output_cost = (output_tokens / 1_000_000) * OUTPUT_COST_PER_MILLION
                total_call_cost = call_input_cost + call_output_cost
                
                # --- 4. Calculate new cumulative totals AND costs ---
                new_total_translated_words = prev_total_translated_words + current_translated_words
                new_total_input = prev_total_input + input_tokens
                new_total_output = prev_total_output + output_tokens
                
                total_input_cost = (new_total_input / 1_000_000) * INPUT_COST_PER_MILLION
                total_output_cost = (new_total_output / 1_000_000) * OUTPUT_COST_PER_MILLION
                
                # --- 5. Calculate detailed message stats ---
                words_in_message = len(message_content.split())
                chars_in_message = len(message_content)
                lines_in_message = len(message_content.split('\n'))
                
                # --- 6. Format the complete log entry with fixed header ---
                log_entry = f"""
=== GEMINI TRANSLATION API CALL ===
Timestamp: {call_start_time}
Language Pair: {source_lang} -> {target_lang}
Original Text: {original_text}

CALL DETAILS:
- Message Length: {chars_in_message} characters
- Word Count: {words_in_message} words
- Line Count: {lines_in_message} lines

COMPLETE MESSAGE CONTENT SENT TO GEMINI:
---BEGIN MESSAGE---
{message_content}
---END MESSAGE---


RESPONSE RECEIVED:
Timestamp: {call_end_time}
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
- Total Cost for this Call: ${total_call_cost:.8f}

CUMULATIVE TOTALS (INCLUDING THIS CALL, FROM LOG START):
- Total Translated Words (so far): {new_total_translated_words}
- Total Input Tokens (so far): {new_total_input}
- Total Output Tokens (so far): {new_total_output}
- Total Input Cost (so far): ${total_input_cost:.8f}
- Total Output Cost (so far): ${total_output_cost:.8f}
- Cumulative Log Cost: ${(total_input_cost + total_output_cost):.8f}

========================================

"""
                
                # --- 7. Write to main log file ---
                with open(self.gemini_log_file, 'a', encoding='utf-8') as f:
                    f.write(log_entry)
                
                # --- 8. Write to short translation log ---
                self._write_short_translation_log(call_start_time, call_end_time, call_duration, 
                                                input_tokens, output_tokens, total_call_cost,
                                                new_total_input, new_total_output, 
                                                total_input_cost + total_output_cost, 
                                                original_text, response_text, source_lang, target_lang)
                
                log_debug(f"Complete Gemini translation call logged: In={input_tokens}, Out={output_tokens}, Duration={call_duration:.3f}s")
                    
        except Exception as e:
            log_debug(f"Error logging complete Gemini translation call: {e}\n{traceback.format_exc()}")

    def _log_gemini_response(self, response_text, call_duration, input_tokens, output_tokens, original_text):
        """Deprecated - replaced by _log_complete_gemini_translation_call for atomic logging."""
        log_debug("Warning: _log_gemini_response is deprecated, use _log_complete_gemini_translation_call instead")
        pass

    def _gemini_translate(self, text_to_translate_gm, source_lang_gm, target_lang_gm):
        """Gemini API call with simplified message format (no system instructions)."""
        log_debug(f"Gemini translate request for: {text_to_translate_gm}")
        
        # Track pending call
        self._increment_pending_translation_calls()
        
        try:
            api_key_gemini = self.app.gemini_api_key_var.get().strip()
            if not api_key_gemini:
                return "Gemini API key missing"
            
            if not GENAI_AVAILABLE:
                return "Google Generative AI libraries not available"
            
            # Check if we need to create a new client (minimal conditions)
            needs_new_session = (
                not hasattr(self, 'gemini_client') or 
                self.gemini_client is None or
                self.should_reset_session(api_key_gemini)  # API key changed
            )
            
            if needs_new_session:
                if hasattr(self, 'gemini_session_api_key') and self.gemini_session_api_key != api_key_gemini:
                    log_debug("Creating new Gemini client (API key changed)")
                else:
                    log_debug("Creating new Gemini client (no existing client)")
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
            
            if self.gemini_client is None:
                return "Gemini client initialization failed"
            
            # Get display names for source and target languages
            source_lang_name = self._get_language_display_name(source_lang_gm, 'gemini')
            target_lang_name = self._get_language_display_name(target_lang_gm, 'gemini')
            
            # Get context window size to determine instruction format
            context_size = self.app.gemini_context_window_var.get()
            
            # Build instruction line based on actual context window content
            if context_size == 0:
                instruction_line = f"<Translate idiomatically from {source_lang_name} to {target_lang_name}. Return translation only.>"
            else:
                # Check actual number of stored context pairs
                actual_context_count = len(self.gemini_context_window) if hasattr(self, 'gemini_context_window') else 0
                
                if actual_context_count == 0:
                    instruction_line = f"<Translate idiomatically from {source_lang_name} to {target_lang_name}. Return translation only.>"
                elif context_size == 1:
                    instruction_line = f"<Translate idiomatically the second subtitle from {source_lang_name} to {target_lang_name}. Return translation only.>"
                elif context_size == 2:
                    if actual_context_count == 1:
                        instruction_line = f"<Translate idiomatically the second subtitle from {source_lang_name} to {target_lang_name}. Return translation only.>"
                    else:
                        instruction_line = f"<Translate idiomatically the third subtitle from {source_lang_name} to {target_lang_name}. Return translation only.>"
                elif context_size == 3:
                    target_position = min(actual_context_count + 1, 4)  # Max "fourth subtitle"
                    ordinal = self._get_ordinal_number(target_position)
                    instruction_line = f"<Translate idiomatically the {ordinal} subtitle from {source_lang_name} to {target_lang_name}. Return translation only.>"
                elif context_size == 4:
                    target_position = min(actual_context_count + 1, 5)  # Max "fifth subtitle"
                    ordinal = self._get_ordinal_number(target_position)
                    instruction_line = f"<Translate idiomatically the {ordinal} subtitle from {source_lang_name} to {target_lang_name}. Return translation only.>"
                elif context_size == 5:
                    target_position = min(actual_context_count + 1, 6)  # Max "sixth subtitle"
                    ordinal = self._get_ordinal_number(target_position)
                    instruction_line = f"<Translate idiomatically the {ordinal} subtitle from {source_lang_name} to {target_lang_name}. Return translation only.>"
            
            # Build context window with new text integrated in grouped format
            context_size = self.app.gemini_context_window_var.get()
            
            if context_size == 0:
                # No context, use simple format 
                message_content = f"{instruction_line}\n\n{source_lang_name.upper()}: {text_to_translate_gm}\n\n{target_lang_name.upper()}:"
            else:
                # Build context window for multi-line format
                context_with_new_text = self._build_context_window(text_to_translate_gm, source_lang_gm)
                message_content = f"{instruction_line}\n\n{context_with_new_text}\n{target_lang_name.upper()}:"
            
            log_debug(f"Sending to Gemini {source_lang_gm}->{target_lang_gm}: [{text_to_translate_gm}]")
            
            log_debug(f"Making Gemini API call for: {text_to_translate_gm}")
            
            # Note: API call logging now happens atomically after the response
            
            api_call_start_time = time.time()
            if not hasattr(self, 'gemini_client') or self.gemini_client is None:
                return "Gemini client not initialized"
            
            # Get the appropriate model for translation
            translation_model_api_name = self.app.get_current_gemini_model_for_translation()
            if not translation_model_api_name:
                # Fallback to config if no specific model selected
                translation_model_api_name = self.app.config['Settings'].get('gemini_model_name', 'gemini-2.5-flash-lite')
            
            response = self.gemini_client.models.generate_content(
                model=translation_model_api_name,
                contents=message_content,
                config=self.gemini_generation_config
            )
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
            
            # Handle multiple lines - only keep the last line
            if '\n' in translation_result:
                lines = translation_result.split('\n')
                # Filter out empty lines and take the last non-empty line
                non_empty_lines = [line.strip() for line in lines if line.strip()]
                if non_empty_lines:
                    translation_result = non_empty_lines[-1]
                else:
                    translation_result = lines[-1].strip() if lines else ""
            
            # Strip language prefixes from the result
            target_lang_upper = target_lang_name.upper()
            
            # Check for uppercase language name with colon and space
            if translation_result.startswith(f"{target_lang_upper}: "):
                translation_result = translation_result[len(f"{target_lang_upper}: "):].strip()
            # Check for uppercase language name with colon only
            elif translation_result.startswith(f"{target_lang_upper}:"):
                translation_result = translation_result[len(f"{target_lang_upper}:"):].strip()
            # Also check for the old format (lowercase language code) just in case
            elif translation_result.startswith(f"{target_lang_gm}: "):
                translation_result = translation_result[len(f"{target_lang_gm}: "):].strip()
            elif translation_result.startswith(f"{target_lang_gm}:"):
                translation_result = translation_result[len(f"{target_lang_gm}:"):].strip()                
            log_debug(f"Gemini response: {translation_result}")
            
            # Log complete API call atomically (request + response + stats together)
            self._log_complete_gemini_translation_call(message_content, translation_result, call_duration, 
                                                     input_tokens, output_tokens, text_to_translate_gm, 
                                                     source_lang_gm, target_lang_gm)
            
            return translation_result
            
        except Exception as e_gm:
            log_debug(f"Gemini API error: {type(e_gm).__name__} - {str(e_gm)}")
            return f"Gemini API error: {str(e_gm)}"
        finally:
            # Always decrement pending call counter
            self._decrement_pending_translation_calls()

    def _initialize_gemini_session(self, source_lang, target_lang):
        """Initialize new Gemini client session without system instructions."""
        if not GENAI_AVAILABLE:
            log_debug("Google Gen AI libraries not available for Gemini session")
            self.gemini_client = None
            return
            
        try:
            # NEW: Client-based approach
            self.gemini_client = genai.Client(
                api_key=self.app.gemini_api_key_var.get().strip()
            )
            
            # Get configuration values
            model_temperature = float(self.app.config['Settings'].get('gemini_model_temp', '0.0'))
            
            # Store config for later use in API calls
            self.gemini_generation_config = types.GenerateContentConfig(
                temperature=model_temperature,
                max_output_tokens=1024,
                candidate_count=1,
                top_p=0.95,
                top_k=40,
                response_mime_type="text/plain",
                safety_settings=[
                    types.SafetySetting(
                        category='HARM_CATEGORY_HARASSMENT',
                        threshold='BLOCK_NONE'
                    ),
                    types.SafetySetting(
                        category='HARM_CATEGORY_HATE_SPEECH', 
                        threshold='BLOCK_NONE'
                    ),
                    types.SafetySetting(
                        category='HARM_CATEGORY_SEXUALLY_EXPLICIT',
                        threshold='BLOCK_NONE'
                    ),
                    types.SafetySetting(
                        category='HARM_CATEGORY_DANGEROUS_CONTENT',
                        threshold='BLOCK_NONE'
                    )
                ]
            )
            
            # Initialize sliding window memory and session tracking
            self.gemini_context_window = []
            self.gemini_session_api_key = self.app.gemini_api_key_var.get().strip()
            
            # Initialize language tracking for context clearing
            self.gemini_current_source_lang = source_lang
            self.gemini_current_target_lang = target_lang
            
            log_debug(f"Gemini client initialized for stateless calls (no chat session)")
            
        except Exception as e:
            log_debug(f"Failed to initialize Gemini client: {e}")
            self.gemini_client = None

    def _reset_gemini_session(self):
        """Reset Gemini client and context completely."""
        try:
            # Clear all session-related attributes
            session_attrs = [
                'gemini_client',  # NEW: Updated to use client instead of model
                'gemini_generation_config',  # NEW: Added config clearing
                'gemini_model_name',  # NEW: Added model name clearing
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
            
            log_debug("Gemini client reset completed - all state cleared")
        except Exception as e:
            log_debug(f"Error resetting Gemini client: {e}")
        # Always ensure client is None to force reinitialization
        self.gemini_client = None

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
        if not hasattr(self, 'gemini_client'):
            return True
        return self.gemini_session_api_key != api_key
    
    def _build_context_window(self, new_source_text=None, source_lang_code=None):
        """Build context window from previous translations with grouped format."""
        if not hasattr(self, 'gemini_context_window'):
            self.gemini_context_window = []
        
        context_size = self.app.gemini_context_window_var.get()
        if context_size == 0:
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
        
        # Combine: all sources first, blank line, then all targets (no new target)
        if source_lines and target_lines:
            all_lines = source_lines + [""] + target_lines
        elif source_lines:
            all_lines = source_lines
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
        
        # Check for duplicates according to specific rules:
        # Rule 2: If translation is identical to previous translation, cache but don't add to context
        # Rule 3: Only check last vs current (penultimate vs current)
        if self.gemini_context_window:
            last_source, last_target, _, _ = self.gemini_context_window[-1]
            
            # Rule 2: If translation is identical to previous, skip context update (but keep in cache)
            if target_text == last_target:
                log_debug(f"Skipping context window update - duplicate target text: '{target_text}'")
                return
            
            # Additional check: if source is also identical, skip (though this should be caught at OCR level)
            if source_text == last_source:
                log_debug(f"Skipping context window update - duplicate source text: '{source_text}'")
                return
        
        # Add new pair with language codes
        self.gemini_context_window.append((source_text, target_text, source_lang, target_lang))
        
        # Keep only last 5 pairs (more than the max context window setting)
        self.gemini_context_window = self.gemini_context_window[-5:]

    def _get_ordinal_number(self, number):
        """Convert number to ordinal string (1->first, 2->second, etc.)."""
        ordinals = {
            1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth",
            6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth"
        }
        return ordinals.get(number, f"{number}th")

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

    # ==================== GEMINI OCR METHODS (Phase 2) ====================
    
    def _gemini_ocr_only(self, webp_image_data, source_lang, batch_number=None):
        """Simple OCR-only call to Gemini API for extracting text from images."""
        log_debug(f"Gemini OCR request for source language: {source_lang}")
        
        # Track pending call
        self._increment_pending_ocr_calls()
        
        try:
            api_key_gemini = self.app.gemini_api_key_var.get().strip()
            if not api_key_gemini:
                return "<ERROR>: Gemini API key missing"
            if not GENAI_AVAILABLE:
                return "<e>: Google Generative AI libraries not available"
            
            # Configure Gemini API with new client approach
            client = genai.Client(api_key=api_key_gemini)
            
            # Get model configuration for OCR calls
            ocr_model_api_name = self.app.get_current_gemini_model_for_ocr()
            if not ocr_model_api_name:
                # Fallback to config if no specific model selected
                ocr_model_api_name = self.app.config['Settings'].get('gemini_model_name', 'gemini-2.5-flash-lite')
            
            # Optimal configuration for OCR tasks with MEDIA_RESOLUTION_MEDIUM (PRIMARY GOAL!)
            ocr_config = types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=512,
                candidate_count=1,
                top_p=1.0,
                top_k=40,
                response_mime_type="text/plain",
                media_resolution="MEDIA_RESOLUTION_MEDIUM",  # 🎯 PRIMARY GOAL ACHIEVED!
                safety_settings=[
                    types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE')
                ]
            )
            
            # Create model for OCR calls
            # Removed - using client-based approach now
            
            # Get language display name for prompt
            source_lang_name = self._get_language_display_name(source_lang, 'gemini')
            
            # Create OCR prompt with error correction - use exact prompt requested
            prompt = f"""1. Transcribe the text from the image exactly as it appears. Do not correct, rephrase, or alter the words in any way. Provide a literal and verbatim transcription of all text in the image without line breaks. Don't return anything else.
2. If there is no text in the image, return only: <EMPTY>."""
            
            log_debug(f"Making Gemini OCR API call for language: {source_lang_name}")
            
            # Save the image before sending to API
            # self._save_ocr_image(webp_image_data)
            
            # Make the API call and track timing
            api_call_start_time = time.time()
            response = client.models.generate_content(
                model=ocr_model_api_name,
                contents=[
                    types.Part.from_bytes(data=webp_image_data, mime_type='image/webp'),
                    prompt
                ],
                config=ocr_config
            )
            call_duration = time.time() - api_call_start_time
            
            # Extract the response text
            ocr_result = response.text.strip() if response.text else "<EMPTY>"
            
            # Parse the response according to the expected format
            if ocr_result == "<EMPTY>":
                parsed_text = "<EMPTY>"
            elif ocr_result.startswith(f"{source_lang_name.upper()}: "):
                # Extract text after "LANGUAGE: " prefix (with space)
                parsed_text = ocr_result[len(f"{source_lang_name.upper()}: "):].strip()
                if not parsed_text:
                    parsed_text = "<EMPTY>"
            elif ocr_result.startswith(f"{source_lang_name.upper()}:"):
                # Extract text after "LANGUAGE:" prefix (without space)
                parsed_text = ocr_result[len(f"{source_lang_name.upper()}:"):].strip()
                if not parsed_text:
                    parsed_text = "<EMPTY>"
            else:
                # With the new format, just use the response directly
                parsed_text = ocr_result
                if not parsed_text:
                    parsed_text = "<EMPTY>"
            
            # Replace line breaks with spaces in the extracted text
            if parsed_text != "<EMPTY>":
                parsed_text = parsed_text.replace('\n', ' ').replace('\r', ' ')
            
            # Extract exact token counts from API response metadata
            input_tokens, output_tokens = 0, 0
            try:
                if response.usage_metadata:
                    input_tokens = response.usage_metadata.prompt_token_count
                    output_tokens = response.usage_metadata.candidates_token_count
                    log_debug(f"Gemini OCR usage metadata: In={input_tokens}, Out={output_tokens}")
            except (AttributeError, KeyError):
                log_debug("Could not find usage_metadata in Gemini OCR response. Tokens will be logged as 0.")
            
            # Log complete OCR call with request, response, and stats
            self._log_complete_gemini_ocr_call(
                prompt, len(webp_image_data), ocr_result, parsed_text, 
                call_duration, input_tokens, output_tokens, source_lang
            )
            
            batch_info = f", Batch {batch_number}" if batch_number is not None else ""
            log_debug(f"Gemini OCR result: '{parsed_text}' (took {call_duration:.3f}s){batch_info}")
            return parsed_text
            
        except Exception as e:
            log_debug(f"Gemini OCR API error: {type(e).__name__} - {str(e)}")
            return "<EMPTY>"
        finally:
            # Always decrement pending call counter
            self._decrement_pending_ocr_calls()
    
    def _log_complete_gemini_ocr_call(self, prompt, image_size, raw_response, parsed_response, call_duration, input_tokens, output_tokens, source_lang):
        """Log complete Gemini OCR API call with atomic writing and cumulative totals."""
        # Check if API logging is enabled
        if not self.app.gemini_api_log_enabled_var.get():
            return
            
        try:
            with self._log_lock:  # Ensure atomic logging to prevent interleaved logs
                # Calculate correct start and end times based on call duration
                call_end_time = self._get_precise_timestamp()
                call_start_time = self._calculate_start_time(call_end_time, call_duration)
                
                # Calculate costs
                INPUT_COST_PER_MILLION = float(self.app.config['Settings'].get('input_token_cost', '0.1'))
                OUTPUT_COST_PER_MILLION = float(self.app.config['Settings'].get('output_token_cost', '0.4'))
                
                call_input_cost = (input_tokens / 1_000_000) * INPUT_COST_PER_MILLION
                call_output_cost = (output_tokens / 1_000_000) * OUTPUT_COST_PER_MILLION
                total_call_cost = call_input_cost + call_output_cost
                
                # Get cumulative totals for OCR
                prev_total_input, prev_total_output, prev_total_cost = self._get_cumulative_totals_ocr()
                
                # Calculate new cumulative totals
                new_total_input = prev_total_input + input_tokens
                new_total_output = prev_total_output + output_tokens
                new_total_cost = prev_total_cost + total_call_cost
                
                # Main log entry with fixed header
                log_entry = f"""
=== GEMINI OCR API CALL ===
Timestamp: {call_start_time}
Source Language: {source_lang}
Image Size: {image_size} bytes
Call Type: OCR Only

REQUEST PROMPT:
---BEGIN PROMPT---
{prompt}
---END PROMPT---

RESPONSE RECEIVED:
Timestamp: {call_end_time}

---BEGIN RESPONSE---
{raw_response}
---END RESPONSE---

PERFORMANCE & COST ANALYSIS:
- Input Tokens: {input_tokens}
- Output Tokens: {output_tokens}
- Input Cost: ${call_input_cost:.8f}
- Output Cost: ${call_output_cost:.8f}
- Total Cost for this Call: ${total_call_cost:.8f}

CUMULATIVE TOTALS (INCLUDING THIS CALL, FROM LOG START):
- Total Input Tokens (OCR, so far): {new_total_input}
- Total Output Tokens (OCR, so far): {new_total_output}
- Total OCR Cost (so far): ${new_total_cost:.8f}

========================================

"""
                
                # Write to main log file
                with open(self.gemini_log_file, 'a', encoding='utf-8') as f:
                    f.write(log_entry)
                
                # Write to short OCR log
                self._write_short_ocr_log(call_start_time, call_end_time, call_duration, 
                                        input_tokens, output_tokens, total_call_cost,
                                        new_total_input, new_total_output, new_total_cost, parsed_response)
                
                log_debug(f"Complete Gemini OCR call logged: {input_tokens}+{output_tokens} tokens, {call_duration:.3f}s")
                
        except Exception as e:
            log_debug(f"Error logging complete Gemini OCR call: {e}")

    # Remove old separate logging functions - replaced by complete logging above
    def _log_gemini_ocr_call(self, image_size, source_lang, sequence_number):
        """Deprecated - replaced by _log_complete_gemini_ocr_call."""
        pass
    
    def _log_gemini_ocr_response(self, response_text, sequence_number, call_duration):
        """Deprecated - replaced by _log_complete_gemini_ocr_call."""
        pass

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

    def translate_text(self, text_content_main, ocr_batch_number=None):
        cleaned_text_main = text_content_main.strip() if text_content_main else ""
        if not cleaned_text_main or len(cleaned_text_main) < 1: return None 
        if self.is_placeholder_text(cleaned_text_main): return None

        translation_start_monotonic = time.monotonic()
        selected_translation_model = self.app.translation_model_var.get()
        log_debug(f"Translate request for \"{cleaned_text_main}\" using {selected_translation_model}")
        
        # --- Start: Setup provider-specific parameters ---
        source_lang, target_lang, extra_params = None, None, {}
        beam_val = None
        
        if selected_translation_model == 'marianmt':
            if not self.app.MARIANMT_AVAILABLE: return "MarianMT libraries not available."
            if self.app.marian_translator is None:
                self.initialize_marian_translator()
                if self.app.marian_translator is None: return "MarianMT initialization failed."
            
            source_lang = self.app.marian_source_lang
            target_lang = self.app.marian_target_lang
            if not source_lang or not target_lang: return "MarianMT source/target language not determined. Select a model."
            
            beam_val = self.app.num_beams_var.get()
            extra_params = {"beam_size": beam_val}
        
        elif selected_translation_model == 'google_api':
            if not self.app.google_api_key_var.get().strip(): return "Google Translate API key missing."
            source_lang = self.app.google_source_lang
            target_lang = self.app.google_target_lang
        
        elif selected_translation_model == 'deepl_api':
            if not self.app.DEEPL_API_AVAILABLE: return "DeepL API libraries not available."
            if not self.app.deepl_api_key_var.get().strip(): return "DeepL API key missing."
            if self.app.deepl_api_client is None:
                try:
                    import deepl
                    self.app.deepl_api_client = deepl.Translator(self.app.deepl_api_key_var.get().strip())
                except Exception as e: return f"DeepL Client init error: {e}"
            source_lang = self.app.deepl_source_lang 
            target_lang = self.app.deepl_target_lang
            extra_params = {"model_type": self.app.deepl_model_type_var.get()}
        
        elif selected_translation_model == 'gemini_api':
            if not self.app.GEMINI_API_AVAILABLE: return "Gemini API libraries not available."
            if not self.app.gemini_api_key_var.get().strip(): return "Gemini API key missing."
            
            source_lang = self.app.gemini_source_lang
            target_lang = self.app.gemini_target_lang
            extra_params = {"context_window": self.app.gemini_context_window_var.get()}
        
        else:
            return f"Error: Unknown translation model '{selected_translation_model}'"
        # --- End: Setup ---

        # 1. Check Unified Cache (In-Memory LRU)
        cached_result = self.unified_cache.get(
            cleaned_text_main, source_lang, target_lang, 
            selected_translation_model, **extra_params
        )
        if cached_result:
            batch_info = f", Batch {ocr_batch_number}" if ocr_batch_number is not None else ""
            log_debug(f"Translation \"{cleaned_text_main}\" -> \"{cached_result}\" from unified cache{batch_info}")
            
            # ### FIX: Added cache synchronization logic here. ###
            # If we found it in memory, ensure it's also saved to disk for future sessions.
            if not self._is_error_message(cached_result):
                if selected_translation_model == 'gemini_api' and self.app.gemini_file_cache_var.get():
                    cache_key = f"gemini:{source_lang}:{target_lang}:{cleaned_text_main}"
                    if not self.app.cache_manager.check_file_cache('gemini', cache_key):
                        log_debug(f"Syncing LRU cache hit to Gemini file cache for: {cleaned_text_main}")
                        self.app.cache_manager.save_to_file_cache('gemini', cache_key, cached_result)
                elif selected_translation_model == 'google_api' and self.app.google_file_cache_var.get():
                    cache_key = f"google:{source_lang}:{target_lang}:{cleaned_text_main}"
                    if not self.app.cache_manager.check_file_cache('google', cache_key):
                        log_debug(f"Syncing LRU cache hit to Google file cache for: {cleaned_text_main}")
                        self.app.cache_manager.save_to_file_cache('google', cache_key, cached_result)
                elif selected_translation_model == 'deepl_api' and self.app.deepl_file_cache_var.get():
                    model_type = extra_params.get('model_type', 'latency_optimized')
                    cache_key = f"deepl:{source_lang}:{target_lang}:{model_type}:{cleaned_text_main}"
                    if not self.app.cache_manager.check_file_cache('deepl', cache_key):
                        log_debug(f"Syncing LRU cache hit to DeepL file cache for: {cleaned_text_main}")
                        self.app.cache_manager.save_to_file_cache('deepl', cache_key, cached_result)

            # Update Gemini context window if the translation was for Gemini
            if selected_translation_model == 'gemini_api' and not self._is_error_message(cached_result):
                self._update_sliding_window(cleaned_text_main, cached_result)
            
            return cached_result

        # 2. Check File Cache
        file_cache_hit = None
        if selected_translation_model == 'gemini_api' and self.app.gemini_file_cache_var.get():
            key = f"gemini:{source_lang}:{target_lang}:{cleaned_text_main}"
            file_cache_hit = self.app.cache_manager.check_file_cache('gemini', key)
        elif selected_translation_model == 'google_api' and self.app.google_file_cache_var.get():
            key = f"google:{source_lang}:{target_lang}:{cleaned_text_main}"
            file_cache_hit = self.app.cache_manager.check_file_cache('google', key)
        elif selected_translation_model == 'deepl_api' and self.app.deepl_file_cache_var.get():
            model_type = extra_params.get('model_type', 'latency_optimized')
            key = f"deepl:{source_lang}:{target_lang}:{model_type}:{cleaned_text_main}"
            file_cache_hit = self.app.cache_manager.check_file_cache('deepl', key)
        
        if file_cache_hit:
            batch_info = f", Batch {ocr_batch_number}" if ocr_batch_number is not None else ""
            log_debug(f"Found \"{cleaned_text_main}\" in {selected_translation_model} file cache{batch_info}.")
            self.unified_cache.store(
                cleaned_text_main, source_lang, target_lang,
                selected_translation_model, file_cache_hit, **extra_params
            )
            if selected_translation_model == 'gemini_api' and not self._is_error_message(file_cache_hit):
                self._update_sliding_window(cleaned_text_main, file_cache_hit)
            return file_cache_hit

        # 3. All Caches Miss - Perform API Call  
        batch_info = f", Batch {ocr_batch_number}" if ocr_batch_number is not None else ""
        log_debug(f"All caches MISS for \"{cleaned_text_main}\". Calling API{batch_info}.")
        translated_api_text = None
        if selected_translation_model == 'marianmt':
            translated_api_text = self._marian_translate(cleaned_text_main, source_lang, target_lang, beam_val)
        elif selected_translation_model == 'google_api':
            translated_api_text = self._google_translate(cleaned_text_main, source_lang, target_lang)
        elif selected_translation_model == 'gemini_api':
            translated_api_text = self._gemini_translate(cleaned_text_main, source_lang, target_lang)
        elif selected_translation_model == 'deepl_api':
            translated_api_text = self._deepl_translate(cleaned_text_main, source_lang, target_lang)
        
        # 4. Store successful API translation in both caches and update context
        if translated_api_text and not self._is_error_message(translated_api_text):
            # Store in file cache (if enabled for the specific provider)
            if selected_translation_model == 'gemini_api' and self.app.gemini_file_cache_var.get():
                cache_key_to_save = f"gemini:{source_lang}:{target_lang}:{cleaned_text_main}"
                self.app.cache_manager.save_to_file_cache('gemini', cache_key_to_save, translated_api_text)
            elif selected_translation_model == 'google_api' and self.app.google_file_cache_var.get():
                cache_key_to_save = f"google:{source_lang}:{target_lang}:{cleaned_text_main}"
                self.app.cache_manager.save_to_file_cache('google', cache_key_to_save, translated_api_text)
            elif selected_translation_model == 'deepl_api' and self.app.deepl_file_cache_var.get():
                model_type = extra_params.get('model_type', 'latency_optimized')
                cache_key_to_save = f"deepl:{source_lang}:{target_lang}:{model_type}:{cleaned_text_main}"
                self.app.cache_manager.save_to_file_cache('deepl', cache_key_to_save, translated_api_text)

            # Store in unified cache
            self.unified_cache.store(
                cleaned_text_main, source_lang, target_lang,
                selected_translation_model, translated_api_text, **extra_params
            )
            
            # Update Gemini context window if the translation was for Gemini
            if selected_translation_model == 'gemini_api':
                self._update_sliding_window(cleaned_text_main, translated_api_text)
        
        batch_info = f", Batch {ocr_batch_number}" if ocr_batch_number is not None else ""
        log_debug(f"Translation \"{cleaned_text_main}\" -> \"{str(translated_api_text)}\" took {time.monotonic() - translation_start_monotonic:.3f}s{batch_info}")
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
            r'^[_\-=<>/\s\.\\|\[\]\{\}]+$',
            r'^ocr\s+source', r'^source\s+text', 
            r'^translat(ion|ing)', r'appear\s+here$', 
            r'[×✖️]',
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

            if self.app.translation_model_var.get() == 'marianmt' and self.app.marian_model_var.get():
                log_debug("MarianMT is active model, attempting to preload selected Marian model.")
                self.app.ui_interaction_handler.on_marian_model_selection_changed(preload=True)
        except ImportError as e_imt_imp:
            log_debug(f"MarianMT initialization failed - missing dependencies: {e_imt_imp}")
        except Exception as e_imt:
            log_debug(f"Error initializing MarianMT translator: {e_imt}\n{traceback.format_exc()}")

    def update_marian_active_model(self, model_name_uam, source_lang_uam=None, target_lang_uam=None):
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
        if self.app.marian_translator is not None:
            try:
                beam_value_clamped = max(1, min(50, self.app.num_beams_var.get()))
                if beam_value_clamped != self.app.num_beams_var.get():
                    self.app.num_beams_var.set(beam_value_clamped)
                self.app.marian_translator.num_beams = beam_value_clamped
                log_debug(f"Updated MarianMT beam search value in translator to: {beam_value_clamped}")
            except Exception as e_umbv:
                log_debug(f"Error updating MarianMT beam value: {e_umbv}")