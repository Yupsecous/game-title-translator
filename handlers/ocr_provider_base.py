# handlers/ocr_provider_base.py

import re
import os
import time
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from logger import log_debug
from .llm_provider_base import NetworkCircuitBreaker  # Reuse existing circuit breaker


class AbstractOCRProvider(ABC):
    """Abstract base class for API-based OCR providers."""
    
    def __init__(self, app, provider_name):
        self.app = app
        self.provider_name = provider_name
        
        # Initialize common components
        self._initialize_common_components()
    
    def _initialize_common_components(self):
        """Initialize all common functionality shared across OCR providers."""
        # Thread safety
        self._log_lock = threading.Lock()
        self._api_calls_lock = threading.Lock()
        
        # Circuit breaker for network issues
        self.circuit_breaker = NetworkCircuitBreaker()
        
        # Session management
        self.ocr_session_counter = 1
        self.current_ocr_session_active = False
        self._pending_ocr_calls = 0
        self._ocr_session_should_end = False
        
        # Client management
        self.client = None
        self.session_api_key = None
        self.client_created_time = 0
        self.api_call_count = 0
        
        # Logging paths
        self._initialize_logging_paths()
        
        # Initialize log files
        self._initialize_log_files()
        
        # Initialize session counters by reading existing logs
        self._initialize_session_counters()
        
        # Cache for cumulative totals (performance optimization)
        self._ocr_cache_initialized = False
        self._cached_ocr_input_tokens = 0
        self._cached_ocr_output_tokens = 0
        self._cached_ocr_cost = 0.0
    
    def _initialize_logging_paths(self):
        """Initialize provider-specific logging file paths."""
        import sys
        
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Provider-specific log files (OCR-specific naming)
        self.main_log_file = os.path.join(base_dir, f"{self.provider_name.title()}_API_call_logs.txt")
        self.short_log_file = os.path.join(base_dir, f"{self.provider_name.upper()}_API_OCR_short_log.txt")
    
    def _initialize_log_files(self):
        """Initialize log files with headers if they're new."""
        try:
            # Ensure the directory exists
            log_dir = os.path.dirname(self.main_log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)

            timestamp = self._get_precise_timestamp()

            # Initialize main log file
            if not os.path.exists(self.main_log_file):
                # Calculate proper centering for provider name in header
                border_width = 55  # Total width of the border
                api_call_text = f"{self.provider_name.upper()} OCR API CALL LOG"
                padding_needed = border_width - len(api_call_text) - 2  # -2 for the # symbols on each side
                left_padding = padding_needed // 2
                right_padding = padding_needed - left_padding
                centered_api_line = f"#{' ' * left_padding}{api_call_text}{' ' * right_padding}#"
                
                header = f"""
#######################################################
{centered_api_line}
#      Game-Changing Translator - OCR Analysis       #
#######################################################

Logging Started: {timestamp}
Purpose: Track input/output token usage for {self.provider_name.title()} OCR API calls, along with exact costs.
Format: Each entry shows complete message content sent to and received from {self.provider_name.title()},
        plus exact token counts and costs for the individual call and the session.

"""
                with open(self.main_log_file, 'w', encoding='utf-8') as f:
                    f.write(header)
                log_debug(f"{self.provider_name.title()} OCR API logging initialized: {self.main_log_file}")
            else:
                # Append a session start separator to existing log
                session_start_msg = f"\n\n--- NEW LOGGING SESSION STARTED: {timestamp} ---\n"
                with open(self.main_log_file, 'a', encoding='utf-8') as f:
                    f.write(session_start_msg)
                log_debug(f"{self.provider_name.title()} OCR API logging continues in existing file: {self.main_log_file}")

            # Initialize short OCR log file
            if not os.path.exists(self.short_log_file):
                # Calculate proper centering for provider name in header
                border_width = 55  # Total width of the border
                ocr_text = f"{self.provider_name.upper()} OCR - SHORT LOG"
                padding_needed = border_width - len(ocr_text) - 2  # -2 for the # symbols on each side
                left_padding = padding_needed // 2
                right_padding = padding_needed - left_padding
                centered_ocr_line = f"#{' ' * left_padding}{ocr_text}{' ' * right_padding}#"
                
                ocr_header = f"""
#######################################################
{centered_ocr_line}
#######################################################

Session Started: {timestamp}
Purpose: Concise {self.provider_name} OCR call results and statistics

"""
                with open(self.short_log_file, 'w', encoding='utf-8') as f:
                    f.write(ocr_header)
                log_debug(f"{self.provider_name.title()} OCR short log initialized: {self.short_log_file}")
            else:
                # Append session separator
                with open(self.short_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"\n--- SESSION: {timestamp} ---\n")

        except Exception as e:
            log_debug(f"Error initializing {self.provider_name} OCR API logs: {e}")
    
    def _initialize_session_counters(self):
        """Initialize session counters by reading existing logs to find the highest session number."""
        try:
            # Read OCR log to find highest session number
            highest_ocr_session = 0
            if os.path.exists(self.short_log_file):
                with open(self.short_log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith("SESSION ") and " STARTED " in line:
                            try:
                                # Extract session number from "SESSION X STARTED"
                                session_num = int(line.split()[1])
                                highest_ocr_session = max(highest_ocr_session, session_num)
                            except (IndexError, ValueError):
                                continue
            
            # Set counter to highest found + 1 (for next session)
            self.ocr_session_counter = highest_ocr_session + 1
            
            log_debug(f"Initialized {self.provider_name} OCR session counter: {self.ocr_session_counter}")
            
        except Exception as e:
            log_debug(f"Error initializing {self.provider_name} OCR session counters: {e}, using defaults")
            # Fall back to 1 if there's any error
            self.ocr_session_counter = 1
    
    # === SESSION MANAGEMENT (ADAPTED FROM LLM PROVIDERS) ===
    
    def start_ocr_session(self):
        """Start a new OCR session with numbered identifier."""
        if not self.current_ocr_session_active:
            timestamp = self._get_precise_timestamp()
            try:
                with open(self.short_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"\nSESSION {self.ocr_session_counter} STARTED {timestamp}\n")
                self.current_ocr_session_active = True
                log_debug(f"{self.provider_name.title()} OCR Session {self.ocr_session_counter} started")
            except Exception as e:
                log_debug(f"Error starting {self.provider_name} OCR session: {e}")

    def request_end_ocr_session(self):
        """Request to end OCR session - will end when no pending calls remain."""
        if self.current_ocr_session_active:
            if self._pending_ocr_calls == 0:
                # Can end immediately
                return self.end_ocr_session()
            else:
                # Mark for ending when calls complete (session will end automatically)
                self._ocr_session_should_end = True
                log_debug(f"{self.provider_name.title()} OCR session end requested, waiting for {self._pending_ocr_calls} pending calls")
                return False
        return True
    
    def end_ocr_session(self, force=False):
        """End the current OCR session only if no pending calls."""
        if self.current_ocr_session_active:
            # Wait for any pending calls to complete before ending session
            if self._pending_ocr_calls > 0 and not force:
                log_debug(f"{self.provider_name.title()} OCR session end delayed: {self._pending_ocr_calls} pending calls")
                return False  # Session not ended yet
            
            timestamp = self._get_precise_timestamp()
            try:
                end_reason = "(FORCED - APP CLOSING)" if force else ""
                with open(self.short_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"SESSION {self.ocr_session_counter} ENDED {timestamp} {end_reason}\n".strip() + "\n")
                self.current_ocr_session_active = False
                self._ocr_session_should_end = False
                self.ocr_session_counter += 1
                log_debug(f"{self.provider_name.title()} OCR Session {self.ocr_session_counter - 1} ended")
                return True  # Session ended successfully
            except Exception as e:
                log_debug(f"Error ending {self.provider_name} OCR session: {e}")
                return False
        return True  # Already inactive
    
    def _increment_pending_ocr_calls(self):
        """Increment the count of pending OCR calls."""
        with self._api_calls_lock:
            self._pending_ocr_calls += 1

    def _decrement_pending_ocr_calls(self):
        """Decrement the count of pending OCR calls."""
        with self._api_calls_lock:
            self._pending_ocr_calls = max(0, self._pending_ocr_calls - 1)
            if self._pending_ocr_calls == 0 and self._ocr_session_should_end:
                self.end_ocr_session()
    
    # === CLIENT MANAGEMENT (IDENTICAL TO LLM PROVIDERS) ===
    
    def _should_refresh_client(self):
        """Check if client should be refreshed to prevent stale connections."""
        if not hasattr(self, 'client_created_time'):
            self.client_created_time = time.time()
            return False
        
        current_time = time.time()
        
        # Refresh client every 30 minutes to prevent stale connections
        if current_time - self.client_created_time > 1800:  # 30 minutes
            log_debug(f"Refreshing {self.provider_name} OCR client due to age (30 minutes)")
            return True
        
        # Refresh after every 100 API calls to prevent connection accumulation
        if not hasattr(self, 'api_call_count'):
            self.api_call_count = 0
        
        if self.api_call_count > 100:
            log_debug(f"Refreshing {self.provider_name} OCR client after 100 API calls")
            return True
        
        return False

    def _force_client_refresh(self):
        """Force refresh of client and reset counters."""
        self.client = None
        self.client_created_time = time.time()
        self.api_call_count = 0
        log_debug(f"{self.provider_name.title()} OCR client forcefully refreshed")
    
    def _should_reset_session(self, api_key):
        """Check if session needs to be reset due to API key change."""
        if not hasattr(self, 'client'):
            return True
        return self.session_api_key != api_key
    
    # === LOGGING SYSTEM (ADAPTED FOR OCR) ===
    
    def _log_complete_ocr_call(self, prompt, image_size, raw_response, parsed_response, 
                             call_duration, input_tokens, output_tokens, source_lang, 
                             model_name, model_source):
        """Log complete OCR API call with atomic writing."""
        # Check if API logging is enabled
        if not self._is_logging_enabled():
            return
            
        try:
            with self._log_lock:  # Ensure atomic logging to prevent interleaved logs
                # Calculate correct start and end times based on call duration
                call_end_time = self._get_precise_timestamp()
                call_start_time = self._calculate_start_time(call_end_time, call_duration)
                
                # --- Get cumulative totals BEFORE this call ---
                prev_total_input, prev_total_output, prev_total_cost = self._get_cumulative_totals_ocr()

                # --- Get model-specific costs and calculate for current call ---
                input_cost_per_million, output_cost_per_million = self._get_model_costs(model_name)
                
                call_input_cost = (input_tokens / 1_000_000) * input_cost_per_million
                call_output_cost = (output_tokens / 1_000_000) * output_cost_per_million
                total_call_cost = call_input_cost + call_output_cost
                
                # --- Calculate new cumulative totals using simple addition ---
                new_total_input = prev_total_input + input_tokens
                new_total_output = prev_total_output + output_tokens
                new_total_cost = prev_total_cost + total_call_cost
                
                # Update OCR cache with new values for performance
                self._update_ocr_cache(input_tokens, output_tokens, total_call_cost)
                
                # Format cost display with smart decimal precision
                input_cost_str = f"${input_cost_per_million:.3f}" if (input_cost_per_million * 1000) % 10 != 0 else f"${input_cost_per_million:.2f}"
                output_cost_str = f"${output_cost_per_million:.3f}" if (output_cost_per_million * 1000) % 10 != 0 else f"${output_cost_per_million:.2f}"
                
                # --- Format the complete log entry ---
                log_entry = f"""
=== {self.provider_name.upper()} OCR API CALL ===
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
                
                # --- Write to main log file ---
                with open(self.main_log_file, 'a', encoding='utf-8') as f:
                    f.write(log_entry)
                
                # --- Write to short OCR log ---
                self._write_short_ocr_log(call_start_time, call_end_time, call_duration, 
                                        input_tokens, output_tokens, total_call_cost,
                                        new_total_input, new_total_output, new_total_cost, 
                                        parsed_response, model_name, model_source)
                
                log_debug(f"Complete {self.provider_name} OCR call logged: In={input_tokens}, Out={output_tokens}, Duration={call_duration:.3f}s")
                    
        except Exception as e:
            log_debug(f"Error logging complete {self.provider_name} OCR call: {e}")
    
    def _write_short_ocr_log(self, call_start_time, call_end_time, call_duration, 
                           input_tokens, output_tokens, call_cost, cumulative_input, 
                           cumulative_output, cumulative_cost, parsed_result, 
                           model_name, model_source):
        """Write concise OCR call log entry."""
        if not self._is_logging_enabled():
            return
            
        try:
            # Get model costs from configuration for display
            cost_line = ""
            try:
                input_cost, output_cost = self._get_model_costs(model_name)
                
                # Format with 3 decimals if third decimal is non-zero, otherwise 2 decimals
                input_str = f"${input_cost:.3f}" if (input_cost * 1000) % 10 != 0 else f"${input_cost:.2f}"
                output_str = f"${output_cost:.3f}" if (output_cost * 1000) % 10 != 0 else f"${output_cost:.2f}"
                
                cost_line = f"Cost: input {input_str}, output {output_str} (per 1M)\n"
            except Exception:
                pass
            
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
            with open(self.short_log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)
        except Exception as e:
            log_debug(f"Error writing short {self.provider_name} OCR log: {e}")
    
    # === CACHE MANAGEMENT (ADAPTED FOR OCR) ===
    
    def _get_cumulative_totals_ocr(self):
        """Get cumulative OCR totals using efficient memory cache."""
        # Use cache if initialized
        if self._ocr_cache_initialized:
            return self._cached_ocr_input_tokens, self._cached_ocr_output_tokens, self._cached_ocr_cost
        
        # Initialize cache by reading log file once
        total_input = 0
        total_output = 0
        total_cost = 0.0
        
        if not os.path.exists(self.main_log_file):
            # Initialize cache with zeros
            self._cached_ocr_input_tokens = 0
            self._cached_ocr_output_tokens = 0
            self._cached_ocr_cost = 0.0
            self._ocr_cache_initialized = True
            log_debug(f"{self.provider_name} OCR cache initialized with zeros (no log file)")
            return 0, 0, 0.0
        
        # Define regex to find the exact counts
        input_token_regex = re.compile(r"^\s*-\s*Total Input Tokens \(OCR, so far\):\s*(\d+)")
        output_token_regex = re.compile(r"^\s*-\s*Total Output Tokens \(OCR, so far\):\s*(\d+)")
        cost_regex = re.compile(r"^\s*-\s*Total OCR Cost \(so far\):\s*\$([0-9.]+)")
        
        try:
            with open(self.main_log_file, 'r', encoding='utf-8') as f:
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
            
            # Initialize cache with values from file
            self._cached_ocr_input_tokens = total_input
            self._cached_ocr_output_tokens = total_output
            self._cached_ocr_cost = total_cost
            self._ocr_cache_initialized = True
            
            log_debug(f"{self.provider_name} OCR cache initialized: {total_input} input, {total_output} output, ${total_cost:.8f}")
                        
        except (IOError, ValueError) as e:
            log_debug(f"Error reading {self.provider_name} OCR cumulative totals: {e}")
            # Initialize cache with zeros on error
            self._cached_ocr_input_tokens = 0
            self._cached_ocr_output_tokens = 0
            self._cached_ocr_cost = 0.0
            self._ocr_cache_initialized = True
            return 0, 0, 0.0
            
        return total_input, total_output, total_cost

    def _update_ocr_cache(self, input_tokens, output_tokens, cost):
        """Update OCR cache with new values for performance."""
        if not self._ocr_cache_initialized:
            # If cache not initialized, initialize it first
            self._get_cumulative_totals_ocr()
        
        # Increment cached values
        self._cached_ocr_input_tokens += input_tokens
        self._cached_ocr_output_tokens += output_tokens
        self._cached_ocr_cost += cost
    
    # === UTILITY METHODS ===
    
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
    
    # === MAIN OCR INTERFACE ===
    
    def recognize(self, image_data, source_lang, batch_number=None):
        """Main OCR method - handles all common logic."""
        log_debug(f"{self.provider_name.title()} OCR request for: {source_lang}")
        
        # Check circuit breaker and force refresh if needed
        if self.circuit_breaker.should_force_refresh():
            log_debug(f"{self.provider_name.title()} circuit breaker forcing client refresh due to network issues")
            self._force_client_refresh()
            self.circuit_breaker = NetworkCircuitBreaker()  # Reset circuit breaker
        
        # Track pending call
        self._increment_pending_ocr_calls()
        
        try:
            # Check API key
            api_key = self._get_api_key()
            if not api_key:
                return f"<e>: {self.provider_name.title()} API key missing"
            
            # Check if provider libraries are available
            if not self._check_provider_availability():
                return f"<e>: {self.provider_name.title()} libraries not available"
            
            # Check if we need to create a new client
            needs_new_session = (
                not hasattr(self, 'client') or 
                self.client is None or
                self._should_reset_session(api_key)  # API key changed
            )
            
            if needs_new_session:
                if hasattr(self, 'session_api_key') and self.session_api_key != api_key:
                    log_debug(f"Creating new {self.provider_name} OCR client (API key changed)")
                else:
                    log_debug(f"Creating new {self.provider_name} OCR client (no existing client)")
                self._initialize_client(api_key)
            
            if self.client is None:
                return f"<e>: {self.provider_name.title()} client initialization failed"
            
            log_debug(f"Making {self.provider_name.title()} OCR API call for: {source_lang}")
            
            api_call_start_time = time.time()
            
            # Make the provider-specific API call
            response = self._make_api_call(image_data, source_lang)
            
            call_duration = time.time() - api_call_start_time
            log_debug(f"{self.provider_name.title()} OCR API call took {call_duration:.3f}s")
            
            # Record successful call with circuit breaker
            needs_refresh = self.circuit_breaker.record_call(call_duration, True)
            if needs_refresh:
                # Schedule client refresh for next call
                self.client = None
            
            # Increment API call counter for periodic refresh
            if hasattr(self, 'api_call_count'):
                self.api_call_count += 1

            # Parse the response (provider-specific)
            parsed_text, input_tokens, output_tokens, model_name, model_source = self._parse_response(response)
            
            # Log complete API call atomically
            prompt = self._get_ocr_prompt(source_lang)
            image_size = len(image_data) if image_data else 0
            raw_response = getattr(response, 'text', str(response)) if hasattr(response, 'text') else str(response)
            
            self._log_complete_ocr_call(prompt, image_size, raw_response, parsed_text, 
                                      call_duration, input_tokens, output_tokens, 
                                      source_lang, model_name, model_source)
            
            batch_info = f", Batch {batch_number}" if batch_number is not None else ""
            log_debug(f"{self.provider_name.title()} OCR result: '{parsed_text}' (took {call_duration:.3f}s){batch_info}")
            return parsed_text
            
        except Exception as e:
            # Record failed call with circuit breaker
            self.circuit_breaker.record_call(0, False)
            error_str = str(e)
            log_debug(f"{self.provider_name.title()} OCR API error: {type(e).__name__} - {error_str}")
            return "<EMPTY>"
        finally:
            # Always decrement pending call counter
            self._decrement_pending_ocr_calls()
    
    def _get_ocr_prompt(self, source_lang):
        """Get the OCR prompt for logging purposes."""
        return """1. Transcribe the text from the image exactly as it appears. Do not correct, rephrase, or alter the words in any way. Provide a literal and verbatim transcription of all text in the image. Don't return anything else.
2. If there is no text in the image, return only: <EMPTY>."""
    
    # === ABSTRACT METHODS (MUST BE IMPLEMENTED BY SUBCLASSES) ===
    
    @abstractmethod
    def _get_api_key(self):
        """Get API key for this provider."""
        pass
    
    @abstractmethod
    def _check_provider_availability(self):
        """Check if provider libraries are available."""
        pass
    
    @abstractmethod
    def _initialize_client(self, api_key):
        """Initialize provider-specific client."""
        pass
    
    @abstractmethod
    def _make_api_call(self, image_data, source_lang):
        """Make provider-specific API call."""
        pass
    
    @abstractmethod
    def _parse_response(self, response):
        """Parse provider-specific response and return (result, input_tokens, output_tokens, model_name, model_source)."""
        pass
    
    @abstractmethod
    def _get_model_costs(self, model_name):
        """Get model-specific costs (input_cost_per_million, output_cost_per_million)."""
        pass
    
    @abstractmethod
    def _is_logging_enabled(self):
        """Check if logging is enabled for this provider."""
        pass
