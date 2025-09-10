# handlers/translation_handler.py
import re
import os
import gc
import sys
import time
import html
import traceback
import threading
from datetime import datetime, timedelta

from logger import log_debug
from marian_mt_translator import MarianMTTranslator
from unified_translation_cache import UnifiedTranslationCache

# Import the new LLM provider classes
from .llm_provider_base import NetworkCircuitBreaker # Used by legacy OCR
from .gemini_provider import GeminiProvider
from .openai_provider import OpenAIProvider

# Import other dependencies
try:
    import requests
    REQUESTS_AVAILABLE = True
    log_debug("Pre-loaded requests library")
except ImportError:
    REQUESTS_AVAILABLE = False
    log_debug("Requests library not available")

# Import legacy Gemini dependencies for OCR
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    try:
        import google.generativeai as genai
        GENAI_AVAILABLE = True
    except ImportError:
        GENAI_AVAILABLE = False


class TranslationHandler:
    def __init__(self, app):
        self.app = app
        self.unified_cache = UnifiedTranslationCache(max_size=1000)
        
        # Initialize LLM providers using the new architecture
        self.providers = {
            'gemini': GeminiProvider(app),
            'openai': OpenAIProvider(app)
        }
        
        self._log_lock = threading.Lock()
        self._api_calls_lock = threading.Lock()
        
        # --- LEGACY OCR SESSION & LOGIC (Kept for now) ---
        self.ocr_session_counter = 1
        self.current_ocr_session_active = False
        self._pending_ocr_calls = 0
        self._ocr_session_should_end = False
        
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            
        self.gemini_log_file = os.path.join(base_dir, "Gemini_API_call_logs.txt")
        self.ocr_short_log_file = os.path.join(base_dir, "GEMINI_API_OCR_short_log.txt")
        self._initialize_legacy_ocr_session_counter()
        
        self._ocr_cache_initialized = False
        self._cached_ocr_input_tokens = 0
        self._cached_ocr_output_tokens = 0
        self._cached_ocr_cost = 0.0

        self.gemini_client = None
        self.gemini_session_api_key = None
        self.client_created_time = 0
        self.api_call_count = 0
        
        self.ocr_circuit_breaker = NetworkCircuitBreaker()
        
        log_debug("Translation handler initialized with unified cache and LLM providers")

    def _get_active_llm_provider(self):
        selected_model = self.app.translation_model_var.get()
        if selected_model == 'gemini_api':
            return self.providers.get('gemini')
        elif self.app.is_openai_model(selected_model):
            return self.providers.get('openai')
        return None

    # === LLM SESSION MANAGEMENT ===
    def start_translation_session(self):
        provider = self._get_active_llm_provider()
        if provider:
            provider.start_translation_session()

    def request_end_translation_session(self):
        provider = self._get_active_llm_provider()
        if provider:
            return provider.request_end_translation_session()
        return True

    def force_end_sessions_on_app_close(self):
        for provider in self.providers.values():
            try:
                provider.end_translation_session()
            except Exception as e:
                log_debug(f"Error force ending {provider.provider_name} session: {e}")
        self.end_ocr_session(force=True)

    # === UNIFIED TRANSLATE METHOD ===
    def translate_text_with_timeout(self, text_content, timeout_seconds=10.0, ocr_batch_number=None):
        result = [None]
        exception = [None]
        
        def translation_worker():
            try:
                result[0] = self.translate_text(text_content, ocr_batch_number)
            except Exception as e:
                exception[0] = e
        
        thread = threading.Thread(target=translation_worker, daemon=True)
        thread.start()
        thread.join(timeout=timeout_seconds)
        
        if thread.is_alive():
            log_debug(f"Translation timed out for {timeout_seconds}s for: '{text_content}' (message suppressed)")
            return None
        
        if exception[0]:
            log_debug(f"Translation exception: {exception[0]}")
            return f"Translation error: {str(exception[0])}"
        
        return result[0]

    def translate_text(self, text_content_main, ocr_batch_number=None):
        cleaned_text_main = text_content_main.strip() if text_content_main else ""
        if not cleaned_text_main or self.is_placeholder_text(cleaned_text_main):
            return None

        translation_start_monotonic = time.monotonic()
        selected_model = self.app.translation_model_var.get()
        log_debug(f"Translate request for \"{cleaned_text_main}\" using {selected_model}")
        
        source_lang, target_lang, extra_params = None, None, {}
        
        # Setup provider-specific parameters
        if selected_model == 'marianmt':
            source_lang, target_lang = self.app.marian_source_lang, self.app.marian_target_lang
            extra_params = {"beam_size": self.app.num_beams_var.get()}
        elif selected_model == 'google_api':
            source_lang, target_lang = self.app.google_source_lang, self.app.google_target_lang
        elif selected_model == 'deepl_api':
            if not self.app.DEEPL_API_AVAILABLE: return "DeepL API libraries not available."
            if not self.app.deepl_api_key_var.get().strip(): return "DeepL API key missing."
            if self.app.deepl_api_client is None:
                try:
                    import deepl
                    self.app.deepl_api_client = deepl.Translator(self.app.deepl_api_key_var.get().strip())
                except Exception as e:
                    return f"DeepL Client init error: {e}"
            source_lang, target_lang = self.app.deepl_source_lang, self.app.deepl_target_lang
            extra_params = {"model_type": self.app.deepl_model_type_var.get()}
        elif selected_model == 'gemini_api':
            # *** FIX: Get language codes correctly from the app instance ***
            source_lang, target_lang = self.app.gemini_source_lang, self.app.gemini_target_lang
            provider = self.providers['gemini']
            extra_params = {"context_window": provider._get_context_window_size()}
        elif self.app.is_openai_model(selected_model):
            # *** FIX: Get language codes correctly from the app instance ***
            source_lang, target_lang = self.app.openai_source_lang, self.app.openai_target_lang
            provider = self.providers['openai']
            extra_params = {"context_window": provider._get_context_window_size()}
        else:
            return f"Error: Unknown translation model '{selected_model}'"

        # 1. Check Unified Cache
        cached_result = self.unified_cache.get(cleaned_text_main, source_lang, target_lang, selected_model, **extra_params)
        if cached_result:
            log_debug(f"Translation \"{cleaned_text_main}\" -> \"{cached_result}\" from unified cache")
            provider = self._get_active_llm_provider()
            if provider and not self._is_error_message(cached_result):
                provider._update_sliding_window(cleaned_text_main, cached_result)
            return self._format_dialog_text(cached_result)

        # 2. Check File Cache (can be added here if needed)

        # 3. All Caches Miss - Perform API Call
        log_debug(f"All caches MISS for \"{cleaned_text_main}\". Calling API.")
        translated_api_text = None
        
        if selected_model == 'marianmt':
            translated_api_text = self._marian_translate(cleaned_text_main, source_lang, target_lang, extra_params['beam_size'])
        elif selected_model == 'google_api':
            translated_api_text = self._google_translate(cleaned_text_main, source_lang, target_lang)
        elif selected_model == 'deepl_api':
            translated_api_text = self._deepl_translate(cleaned_text_main, source_lang, target_lang)
        elif selected_model == 'gemini_api':
            provider = self.providers['gemini']
            translated_api_text = provider.translate(cleaned_text_main, source_lang, target_lang, ocr_batch_number)
        elif self.app.is_openai_model(selected_model):
            provider = self.providers['openai']
            translated_api_text = provider.translate(cleaned_text_main, source_lang, target_lang, ocr_batch_number)
        
        # 4. Store successful translation
        if translated_api_text and not self._is_error_message(translated_api_text):
            self.unified_cache.store(cleaned_text_main, source_lang, target_lang, selected_model, translated_api_text, **extra_params)
        
        log_debug(f"Translation \"{cleaned_text_main}\" -> \"{str(translated_api_text)}\" took {time.monotonic() - translation_start_monotonic:.3f}s")
        return self._format_dialog_text(translated_api_text)

    # === NON-LLM PROVIDER METHODS (UNCHANGED) ===
    def _google_translate(self, text_to_translate_gt, source_lang_gt, target_lang_gt):
        log_debug(f"Google Translate API call for: {text_to_translate_gt}")
        api_key_google = self.app.google_api_key_var.get().strip()
        if not api_key_google: return "Google Translate API key missing"
        if not REQUESTS_AVAILABLE: return "Requests library not available for Google Translate"
        try:
            url = "https://translation.googleapis.com/language/translate/v2"
            params = {'key': api_key_google, 'q': text_to_translate_gt, 'target': target_lang_gt, 'format': 'text'}
            if source_lang_gt and source_lang_gt.lower() != 'auto': params['source'] = source_lang_gt
            response = requests.post(url, data=params, timeout=10)
            response.raise_for_status()
            result = response.json()
            if result and 'data' in result and 'translations' in result['data']:
                return html.unescape(result['data']['translations'][0]['translatedText'])
            return f"Google Translate API returned unexpected result: {result}"
        except requests.exceptions.RequestException as e_req:
            return f"Google Translate API request error: {str(e_req)}"
        except Exception as e_cgt:
            return f"Google Translate API error: {type(e_cgt).__name__} - {str(e_cgt)}"

    def _deepl_translate(self, text_to_translate_dl, source_lang_dl, target_lang_dl):
        model_type = self.app.deepl_model_type_var.get()
        log_debug(f"DeepL API call for: {text_to_translate_dl} using model_type={model_type}")
        if not self.app.deepl_api_client: return "DeepL API client not initialized"
        try:
            deepl_source_param = source_lang_dl if source_lang_dl and source_lang_dl.lower() != 'auto' else None
            try:
                result_dl = self.app.deepl_api_client.translate_text(
                    text_to_translate_dl, target_lang=target_lang_dl, source_lang=deepl_source_param, model_type=model_type
                )
                if result_dl and hasattr(result_dl, 'text') and result_dl.text:
                    return result_dl.text
                return "DeepL API returned empty or invalid result"
            except Exception as quality_error:
                if (model_type == "quality_optimized" and 
                    ("language pair" in str(quality_error).lower() or "not supported" in str(quality_error).lower() or "unsupported" in str(quality_error).lower())):
                    log_debug(f"DeepL quality_optimized failed, falling back to latency_optimized: {quality_error}")
                    result_dl_fallback = self.app.deepl_api_client.translate_text(
                        text_to_translate_dl, target_lang=target_lang_dl, source_lang=deepl_source_param, model_type="latency_optimized"
                    )
                    if result_dl_fallback and hasattr(result_dl_fallback, 'text') and result_dl_fallback.text:
                        return result_dl_fallback.text
                    return "DeepL API fallback returned empty or invalid result"
                else:
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
            url = "https://api-free.deepl.com/v2/usage"
            headers = {
                "Authorization": f"DeepL-Auth-Key {api_key}",
                "User-Agent": "OCR-Translator/1.1.0"
            }
            
            log_debug("Checking DeepL API usage...")
            response = requests.get(url, headers=headers, timeout=10)
            
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
        log_debug(f"MarianMT translation call for: {text_to_translate_mm} (beam={beam_value_mm})")
        if self.app.marian_translator is None: return "MarianMT translator not initialized"
        text_to_translate_cleaned = re.sub(r'\s+', ' ', text_to_translate_mm).strip()
        if not text_to_translate_cleaned: return ""
        try:
            self.app.marian_translator.num_beams = beam_value_mm
            result_mm = self.app.marian_translator.translate(text_to_translate_cleaned, source_lang_mm, target_lang_mm)
            return result_mm
        except Exception as e_cmm:
            return f"MarianMT translation error: {type(e_cmm).__name__} - {str(e_cmm)}"

    # === LEGACY OCR METHODS (RESTORED FROM BACKUP) ===
    def _initialize_legacy_ocr_session_counter(self):
        try:
            highest_ocr_session = 0
            if os.path.exists(self.ocr_short_log_file):
                with open(self.ocr_short_log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith("SESSION ") and (" STARTED " in line or " ENDED " in line):
                            try:
                                session_num = int(line.split()[1])
                                highest_ocr_session = max(highest_ocr_session, session_num)
                            except (IndexError, ValueError):
                                continue
            self.ocr_session_counter = highest_ocr_session + 1
            log_debug(f"Initialized legacy OCR session counter: {self.ocr_session_counter}")
        except Exception as e:
            log_debug(f"Error initializing OCR session counter: {e}, using default")
            self.ocr_session_counter = 1

    def _increment_pending_ocr_calls(self):
        with self._api_calls_lock:
            self._pending_ocr_calls += 1

    def _decrement_pending_ocr_calls(self):
        with self._api_calls_lock:
            self._pending_ocr_calls = max(0, self._pending_ocr_calls - 1)
            if self._pending_ocr_calls == 0 and self._ocr_session_should_end:
                self.end_ocr_session()

    def start_ocr_session(self):
        if not self.current_ocr_session_active:
            timestamp = self._get_precise_timestamp()
            try:
                with open(self.ocr_short_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"\nSESSION {self.ocr_session_counter} STARTED {timestamp}\n")
                self.current_ocr_session_active = True
                log_debug(f"OCR Session {self.ocr_session_counter} started")
            except Exception as e:
                log_debug(f"Error starting OCR session: {e}")

    def end_ocr_session(self, force=False):
        if self.current_ocr_session_active:
            if self._pending_ocr_calls > 0 and not force:
                log_debug(f"OCR session end delayed: {self._pending_ocr_calls} pending calls")
                self._ocr_session_should_end = True
                return False
            timestamp = self._get_precise_timestamp()
            try:
                end_reason = "(FORCED - APP CLOSING)" if force else ""
                with open(self.ocr_short_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"SESSION {self.ocr_session_counter} ENDED {timestamp} {end_reason}\n".strip() + "\n")
                self.current_ocr_session_active = False
                self._ocr_session_should_end = False
                self.ocr_session_counter += 1
                log_debug(f"OCR Session {self.ocr_session_counter - 1} ended")
                return True
            except Exception as e:
                log_debug(f"Error ending OCR session: {e}")
                return False
        return True

    def request_end_ocr_session(self):
        if self.current_ocr_session_active:
            if self._pending_ocr_calls == 0:
                return self.end_ocr_session()
            else:
                self._ocr_session_should_end = True
                log_debug(f"OCR session end requested, waiting for {self._pending_ocr_calls} pending calls")
                return False
        return True

    def _gemini_ocr_only(self, webp_image_data, source_lang, batch_number=None):
        log_debug(f"Gemini OCR request for source language: {source_lang}")
        if self.ocr_circuit_breaker.should_force_refresh():
            log_debug("Circuit breaker forcing legacy OCR client refresh due to network issues")
            self.gemini_client = None
            self.ocr_circuit_breaker = NetworkCircuitBreaker()
        
        self._increment_pending_ocr_calls()
        try:
            api_key_gemini = self.app.gemini_api_key_var.get().strip()
            if not api_key_gemini: return "<ERROR>: Gemini API key missing"
            if not GENAI_AVAILABLE: return "<e>: Google Generative AI libraries not available"

            if self.gemini_client is None or self.gemini_session_api_key != api_key_gemini:
                log_debug("Creating new Gemini client for legacy OCR")
                self.gemini_client = genai.Client(api_key=api_key_gemini)
                self.gemini_session_api_key = api_key_gemini
            
            if self.gemini_client is None: return "<e>: Gemini client initialization failed"
            
            ocr_model_api_name = self.app.get_current_gemini_model_for_ocr() or 'gemini-2.5-flash-lite'
            
            ocr_config = types.GenerateContentConfig(
                temperature=0.0, max_output_tokens=512, media_resolution="MEDIA_RESOLUTION_MEDIUM",
                safety_settings=[types.SafetySetting(category=c, threshold='BLOCK_NONE') for c in ['HARM_CATEGORY_HARASSMENT', 'HARM_CATEGORY_HATE_SPEECH', 'HARM_CATEGORY_SEXUALLY_EXPLICIT', 'HARM_CATEGORY_DANGEROUS_CONTENT']]
            )
            
            prompt = """1. Transcribe the text from the image exactly as it appears. Do not correct, rephrase, or alter the words in any way. Provide a literal and verbatim transcription of all text in the image. Don't return anything else.\n2. If there is no text in the image, return only: <EMPTY>."""
            
            api_call_start_time = time.time()
            response = self.gemini_client.models.generate_content(
                model=ocr_model_api_name,
                contents=[types.Part.from_bytes(data=webp_image_data, mime_type='image/webp'), prompt],
                config=ocr_config
            )
            call_duration = time.time() - api_call_start_time
            
            self.ocr_circuit_breaker.record_call(call_duration, True)
            
            ocr_result = response.text.strip() if response.text else "<EMPTY>"
            parsed_text = ocr_result.replace('```text\n', '').replace('```', '').replace('\n', ' ').strip()
            if not parsed_text or "<EMPTY>" in parsed_text:
                parsed_text = "<EMPTY>"
            
            input_tokens, output_tokens, model_name, model_source = 0, 0, ocr_model_api_name, "api_request"
            try:
                if response.usage_metadata:
                    input_tokens = response.usage_metadata.prompt_token_count
                    output_tokens = response.usage_metadata.candidates_token_count
            except (AttributeError, KeyError):
                log_debug("Could not find usage_metadata in Gemini OCR response.")
            
            self._log_complete_gemini_ocr_call(prompt, len(webp_image_data), ocr_result, parsed_text, call_duration, input_tokens, output_tokens, source_lang, model_name, model_source)
            
            log_debug(f"Gemini OCR result: '{parsed_text}' (took {call_duration:.3f}s)")
            return parsed_text
            
        except Exception as e:
            self.ocr_circuit_breaker.record_call(0, False)
            log_debug(f"Gemini OCR API error: {type(e).__name__} - {str(e)}")
            return "<EMPTY>"
        finally:
            self._decrement_pending_ocr_calls()

    # *** FIX: RESTORED FULL, UNABRIDGED OCR LOGGING METHODS FROM BACKUP ***
    def _log_complete_gemini_ocr_call(self, prompt, image_size, raw_response, parsed_response, call_duration, input_tokens, output_tokens, source_lang, model_name, model_source):
        if not self.app.gemini_api_log_enabled_var.get(): return
        try:
            with self._log_lock:
                call_end_time = self._get_precise_timestamp()
                call_start_time = self._calculate_start_time(call_end_time, call_duration)
                
                model_costs = self.app.gemini_models_manager.get_model_costs(model_name)
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
                
                input_cost_str = f"${INPUT_COST_PER_MILLION:.3f}" if (INPUT_COST_PER_MILLION * 1000) % 10 != 0 else f"${INPUT_COST_PER_MILLION:.2f}"
                output_cost_str = f"${OUTPUT_COST_PER_MILLION:.3f}" if (OUTPUT_COST_PER_MILLION * 1000) % 10 != 0 else f"${OUTPUT_COST_PER_MILLION:.2f}"
                
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
Model: {model_name} ({model_source})
Cost: input {input_cost_str}, output {output_cost_str} (per 1M)
Timestamp: {call_end_time}
Call Duration: {call_duration:.3f} seconds

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
                with open(self.gemini_log_file, 'a', encoding='utf-8') as f: f.write(log_entry)
                self._write_short_ocr_log(call_start_time, call_end_time, call_duration, input_tokens, output_tokens, total_call_cost, new_total_input, new_total_output, new_total_cost, parsed_response, model_name, model_source)
        except Exception as e:
            log_debug(f"Error logging complete Gemini OCR call: {e}")

    def _write_short_ocr_log(self, call_start_time, call_end_time, call_duration, input_tokens, output_tokens, call_cost, cumulative_input, cumulative_output, cumulative_cost, parsed_result, model_name, model_source):
        if not self.app.gemini_api_log_enabled_var.get(): return
        try:
            cost_line = ""
            try:
                model_costs = self.app.gemini_models_manager.get_model_costs(model_name)
                input_cost, output_cost = model_costs['input_cost'], model_costs['output_cost']
                input_str = f"${input_cost:.3f}" if (input_cost * 1000) % 10 != 0 else f"${input_cost:.2f}"
                output_str = f"${output_cost:.3f}" if (output_cost * 1000) % 10 != 0 else f"${output_cost:.2f}"
                cost_line = f"Cost: input {input_str}, output {output_str} (per 1M)\n"
            except Exception: pass
            
            log_entry = f"""========= OCR CALL ===========
Model: {model_name} ({model_source})
{cost_line}Start: {call_start_time}
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

    def _get_cumulative_totals_ocr(self):
        if self._ocr_cache_initialized:
            return self._cached_ocr_input_tokens, self._cached_ocr_output_tokens, self._cached_ocr_cost
        
        total_input, total_output, total_cost = 0, 0, 0.0
        if not os.path.exists(self.gemini_log_file):
            self._ocr_cache_initialized = True
            return 0, 0, 0.0
        
        input_token_regex = re.compile(r"^\s*-\s*Total Input Tokens \(OCR, so far\):\s*(\d+)")
        output_token_regex = re.compile(r"^\s*-\s*Total Output Tokens \(OCR, so far\):\s*(\d+)")
        cost_regex = re.compile(r"^\s*-\s*Total OCR Cost \(so far\):\s*\$([0-9.]+)")
        
        try:
            with open(self.gemini_log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if m := input_token_regex.match(line): total_input = int(m.group(1))
                    if m := output_token_regex.match(line): total_output = int(m.group(1))
                    if m := cost_regex.match(line): total_cost = float(m.group(1))
            
            self._cached_ocr_input_tokens, self._cached_ocr_output_tokens, self._cached_ocr_cost = total_input, total_output, total_cost
            self._ocr_cache_initialized = True
            return total_input, total_output, total_cost
        except (IOError, ValueError) as e:
            log_debug(f"Error reading OCR cumulative totals: {e}")
            self._ocr_cache_initialized = True
            return 0, 0, 0.0

    def _update_ocr_cache(self, input_tokens, output_tokens, cost):
        if not self._ocr_cache_initialized: self._get_cumulative_totals_ocr()
        self._cached_ocr_input_tokens += input_tokens
        self._cached_ocr_output_tokens += output_tokens
        self._cached_ocr_cost += cost

    # === UTILITY METHODS (UNCHANGED) ===
    def _get_precise_timestamp(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def _calculate_start_time(self, end_time_str, duration_seconds):
        try:
            end_time = datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S.%f")
            start_time = end_time - timedelta(seconds=duration_seconds)
            return start_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        except Exception:
            return end_time_str
            
    def _format_dialog_text(self, text):
        if not text or not isinstance(text, str): return text
        if not (text.startswith("-") or text.startswith("–") or text.startswith("—")): return text
        formatted_text = re.sub(r'([.?!])\s+([-–—])', r'\1\n\2', text)
        return formatted_text
    
    def _is_error_message(self, text):
        if not isinstance(text, str): return True
        error_indicators = ["error:", "api error", "not initialized", "missing", "failed", "not available", "not supported", "invalid result", "empty result"]
        return any(indicator in text.lower() for indicator in error_indicators)
    
    def is_placeholder_text(self, text_content):
        if not text_content: return True
        text_lower = text_content.lower().strip()
        placeholders = ["source text will appear here", "translation will appear here", "translation...", "ocr source", "source text", "loading...", "translating...", "", "translation", "...", "translation error:"]
        return text_lower in placeholders or text_lower.startswith("translation error:")

    def initialize_marian_translator(self):
        if self.app.marian_translator is not None: return
        if not hasattr(self.app, 'MARIANMT_AVAILABLE') or not self.app.MARIANMT_AVAILABLE: return
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            cache_dir_name = "marian_models_cache"
            if getattr(sys, 'frozen', False):
                 executable_dir = os.path.dirname(sys.executable)
                 cache_dir = os.path.join(executable_dir, "_internal", cache_dir_name)
            else:
                 cache_dir = os.path.join(base_dir, cache_dir_name)
            os.makedirs(cache_dir, exist_ok=True)
            current_beam_value = self.app.num_beams_var.get()
            self.app.marian_translator = MarianMTTranslator(cache_dir=cache_dir, num_beams=current_beam_value)
            log_debug(f"MarianMT translator initialized (cache: {cache_dir}, beams: {current_beam_value})")
        except Exception as e:
            log_debug(f"Error initializing MarianMT translator: {e}\n{traceback.format_exc()}")