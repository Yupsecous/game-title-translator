# handlers/llm_provider_base.py
"""
Abstract base class for unified LLM provider architecture.
Contains all common functionality shared across Gemini, OpenAI, and future providers.
"""

import os
import sys
import time
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from logger import log_debug


class NetworkCircuitBreaker:
    """Circuit breaker to detect and handle network degradation."""
    
    def __init__(self):
        self.failure_count = 0
        self.slow_call_count = 0
        self.last_reset = time.time()
        self.is_open = False
        self.total_calls = 0
    
    def record_call(self, duration, success):
        """Record API call result and determine if circuit should open."""
        self.total_calls += 1
        
        # Reset counters every 5 minutes
        current_time = time.time()
        if current_time - self.last_reset > 300:  # 5 minutes
            log_debug(f"Circuit breaker stats reset. Previous period: {self.failure_count} failures, {self.slow_call_count} slow calls, {self.total_calls} total")
            self.failure_count = 0
            self.slow_call_count = 0
            self.total_calls = 0
            self.is_open = False
            self.last_reset = current_time
        
        if not success:
            self.failure_count += 1
            log_debug(f"Circuit breaker: API failure recorded ({self.failure_count}/5)")
        elif duration > 3.0:  # Slow call threshold
            self.slow_call_count += 1
            log_debug(f"Circuit breaker: Slow call recorded ({duration:.2f}s, {self.slow_call_count}/10)")
        
        # Open circuit if too many failures or slow calls
        if self.failure_count >= 5:
            self.is_open = True
            log_debug("Circuit breaker OPEN due to failure threshold - forcing client refresh")
            return True
        elif self.slow_call_count >= 10:
            self.is_open = True
            log_debug("Circuit breaker OPEN due to slow call threshold - forcing client refresh")
            return True
        
        return False
    
    def should_force_refresh(self):
        """Check if circuit is open and client should be refreshed."""
        return self.is_open


class AbstractLLMProvider(ABC):
    """
    Abstract base class for unified LLM provider architecture.
    
    All LLM providers (Gemini, OpenAI, DeepSeek) inherit from this class and share
    identical functionality for:
    - Comprehensive API logging with identical format
    - Advanced cost tracking with real-time calculation
    - Smart context windows with sliding window algorithm
    - Robust session management with circuit breaker protection
    - Thread-safe operations with atomic logging
    
    Only provider-specific API calls are implemented in concrete classes.
    """
    
    def __init__(self, app, provider_name):
        """
        Initialize the LLM provider with common functionality.
        
        Args:
            app: Main application instance
            provider_name: Provider identifier (e.g., 'gemini', 'openai', 'deepseek')
        """
        self.app = app
        self.provider_name = provider_name.lower()
        
        # Initialize all common components
        self._initialize_common_components()
    
    def _initialize_common_components(self):
        """Initialize all common functionality shared across providers."""
        
        # === LOGGING SYSTEM INITIALIZATION ===
        self._initialize_logging_system()
        
        # === SESSION MANAGEMENT INITIALIZATION ===
        self._initialize_session_management()
        
        # === CIRCUIT BREAKER INITIALIZATION ===
        self.circuit_breaker = NetworkCircuitBreaker()
        
        # === CONTEXT WINDOW INITIALIZATION ===
        self.context_window = []
        self.current_source_lang = None
        self.current_target_lang = None
        
        # === CLIENT MANAGEMENT INITIALIZATION ===
        self.client = None
        self.session_api_key = None
        self.client_created_time = 0
        self.api_call_count = 0
        
        # === CACHE INITIALIZATION ===
        self._cache_initialized = False
        self._cached_words = 0
        self._cached_input_tokens = 0
        self._cached_output_tokens = 0
        self._cached_input_cost = 0.0
        self._cached_output_cost = 0.0
        
        log_debug(f"{self.provider_name.capitalize()} provider initialized with unified architecture")
    
    def _initialize_logging_system(self):
        """Initialize comprehensive logging system with identical format across providers."""
        
        # Thread lock for atomic logging
        self._log_lock = threading.Lock()
        
        # Determine base directory for log files
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Initialize log file paths with provider-specific names
        provider_cap = self.provider_name.capitalize()
        self.detailed_log_file = os.path.join(base_dir, f"{provider_cap}_API_call_logs.txt")
        self.short_log_file = os.path.join(base_dir, f"{provider_cap}_API_TRA_short_log.txt")
        
        # Initialize log files
        self._initialize_detailed_log()
        self._initialize_short_log()
        
        log_debug(f"{provider_cap} logging system initialized")
    
    def _initialize_detailed_log(self):
        """Initialize detailed API call log file."""
        try:
            # Ensure directory exists
            log_dir = os.path.dirname(self.detailed_log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            
            timestamp = self._get_precise_timestamp()
            provider_upper = self.provider_name.upper()
            
            # Initialize main log file
            if not os.path.exists(self.detailed_log_file):
                header = f"""
#######################################################
# {provider_upper} API CALL LOG - Game-Changing Translator #
#      Comprehensive Request/Response Analysis       #
#######################################################

Logging Started: {timestamp}
Purpose: Complete {provider_upper} API call documentation with request content,
response data, token analysis, cost tracking, and performance metrics
plus exact token counts and costs for the individual call and the session.

"""
                with open(self.detailed_log_file, 'w', encoding='utf-8') as f:
                    f.write(header)
                log_debug(f"{provider_upper} detailed log initialized: {self.detailed_log_file}")
            else:
                # Append a session start separator to existing log
                session_start_msg = f"\n\n--- NEW LOGGING SESSION STARTED: {timestamp} ---\n"
                with open(self.detailed_log_file, 'a', encoding='utf-8') as f:
                    f.write(session_start_msg)
                log_debug(f"{provider_upper} detailed log session separator added")
        
        except Exception as e:
            log_debug(f"Error initializing {self.provider_name} detailed log: {e}")
    
    def _initialize_short_log(self):
        """Initialize concise API call log file for statistics."""
        try:
            timestamp = self._get_precise_timestamp()
            provider_upper = self.provider_name.upper()
            
            # Initialize short translation log file
            if not os.path.exists(self.short_log_file):
                tra_header = f"""
#######################################################
# {provider_upper} TRANSLATION API SHORT LOG             #
#      Game-Changing Translator - Quick Analysis     #
#######################################################

Session Started: {timestamp}
Purpose: Concise {provider_upper} translation call results and statistics

"""
                with open(self.short_log_file, 'w', encoding='utf-8') as f:
                    f.write(tra_header)
                log_debug(f"{provider_upper} translation short log initialized: {self.short_log_file}")
            else:
                # Append session separator
                with open(self.short_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"\n--- SESSION: {timestamp} ---\n")
        
        except Exception as e:
            log_debug(f"Error initializing {self.provider_name} short log: {e}")
    
    def _initialize_session_management(self):
        """Initialize session management system with pending call tracking."""
        
        # Session counter - will be set by reading existing logs
        self.session_counter = 1
        self.current_session_active = False
        
        # Track pending API calls to ensure session ends only after all calls complete
        self._pending_calls = 0
        self._api_calls_lock = threading.Lock()
        
        # Initialize session counter by reading existing logs
        self._initialize_session_counter()
    
    def _initialize_session_counter(self):
        """Initialize session counter by reading existing logs to find the highest session number."""
        try:
            highest_session = 0
            if os.path.exists(self.short_log_file):
                with open(self.short_log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith("SESSION ") and " STARTED " in line:
                            try:
                                # Extract session number from "SESSION X STARTED"
                                session_num = int(line.split()[1])
                                highest_session = max(highest_session, session_num)
                            except (IndexError, ValueError):
                                continue
            
            # Set counter to highest found + 1 (for next session)
            self.session_counter = highest_session + 1
            
            log_debug(f"{self.provider_name.capitalize()} session counter initialized: {self.session_counter}")
        
        except Exception as e:
            log_debug(f"Error initializing {self.provider_name} session counter: {e}, using default")
            self.session_counter = 1    
    # === SESSION MANAGEMENT METHODS ===
    
    def _increment_pending_calls(self):
        """Increment the count of pending API calls."""
        with self._api_calls_lock:
            self._pending_calls += 1
    
    def _decrement_pending_calls(self):
        """Decrement the count of pending API calls and try to end session if ready."""
        with self._api_calls_lock:
            self._pending_calls = max(0, self._pending_calls - 1)
            # Try to end session if it was requested and no pending calls remain
            if self._pending_calls == 0 and hasattr(self, '_session_should_end') and self._session_should_end:
                self._try_end_session_when_ready()
    
    def _has_pending_calls(self):
        """Check if there are any pending API calls."""
        with self._api_calls_lock:
            return self._pending_calls > 0
    
    def start_session(self):
        """Start a new translation session with numbered identifier."""
        if not self.current_session_active:
            timestamp = self._get_precise_timestamp()
            try:
                with open(self.short_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"\nSESSION {self.session_counter} STARTED {timestamp}\n")
                self.current_session_active = True
                log_debug(f"{self.provider_name.capitalize()} Session {self.session_counter} started")
            except Exception as e:
                log_debug(f"Error starting {self.provider_name} session: {e}")
    
    def try_end_session(self):
        """Attempt to end current session, but wait for pending calls to complete."""
        if not self.current_session_active:
            return
        
        if self._has_pending_calls():
            log_debug(f"{self.provider_name.capitalize()} session end requested but {self._pending_calls} calls pending")
            self._session_should_end = True  # Mark for later ending
        else:
            self._actually_end_session()
    
    def _actually_end_session(self):
        """Actually end the current session (called when no pending calls remain)."""
        if self.current_session_active:
            timestamp = self._get_precise_timestamp()
            try:
                with open(self.short_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"SESSION {self.session_counter} ENDED {timestamp}\n\n")
                self.current_session_active = False
                self.session_counter += 1
                self._session_should_end = False
                log_debug(f"{self.provider_name.capitalize()} Session ended")
            except Exception as e:
                log_debug(f"Error ending {self.provider_name} session: {e}")
    
    # === CONTEXT WINDOW MANAGEMENT ===
    
    def _build_context_string(self, text, context_size, source_lang, target_lang):
        """
        Build identical context format for all providers (using Gemini's format).
        This ensures all providers receive exactly the same message content.
        """
        
        # Get language display names
        source_lang_name = self._get_language_display_name(source_lang, self.provider_name)
        target_lang_name = self._get_language_display_name(target_lang, self.provider_name)
        
        # Build instruction line based on actual context window content
        if context_size == 0:
            instruction_line = f"<Translate idiomatically from {source_lang_name} to {target_lang_name}. Return translation only.>"
        else:
            # Check actual number of stored context pairs
            actual_context_count = len(self.context_window)
            
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
            elif context_size >= 5:
                target_position = min(actual_context_count + 1, 6)  # Max "sixth subtitle"
                ordinal = self._get_ordinal_number(target_position)
                instruction_line = f"<Translate idiomatically the {ordinal} subtitle from {source_lang_name} to {target_lang_name}. Return translation only.>"
        
        # Build context window with new text integrated in grouped format
        if context_size == 0:
            # No context, use simple format 
            message_content = f"{instruction_line}\n\n{source_lang_name.upper()}: {text}\n\n{target_lang_name.upper()}:"
        else:
            # Build context window for multi-line format
            context_with_new_text = self._build_context_window_content(text, source_lang)
            message_content = f"{instruction_line}\n\n{context_with_new_text}\n{target_lang_name.upper()}:"
        
        return message_content
    
    def _build_context_window_content(self, text, source_lang):
        """Build the context window content part of the message."""
        
        # Get language display names
        source_lang_name = self._get_language_display_name(source_lang, self.provider_name)
        target_lang_name = self._get_language_display_name(self.current_target_lang, self.provider_name)
        
        # Build context sections
        context_lines = []
        
        # Add previous context entries
        for source_text, target_text in self.context_window:
            context_lines.append(f"{source_lang_name.upper()}: {source_text}")
        
        # Add current text to translate
        context_lines.append(f"{source_lang_name.upper()}: {text}")
        
        # Add previous translations
        for i, (_, target_text) in enumerate(self.context_window):
            context_lines.append(f"{target_lang_name.upper()}: {target_text}")
        
        return '\n'.join(context_lines)
    
    def _update_sliding_window(self, source_text, translated_text):
        """Update the sliding context window with new translation pair."""
        
        # Add new pair to context
        self.context_window.append((source_text, translated_text))
        
        # Get context window size from provider-specific configuration
        context_size = self._get_context_window_size()
        
        # Trim context window to maintain size limit
        if len(self.context_window) > context_size and context_size > 0:
            self.context_window = self.context_window[-context_size:]
        
        log_debug(f"{self.provider_name.capitalize()} context window updated (size: {len(self.context_window)}/{context_size})")
    
    def _clear_context(self):
        """Clear the context window."""
        self.context_window.clear()
        log_debug(f"{self.provider_name.capitalize()} context window cleared")
    
    # === COST TRACKING AND CALCULATIONS ===
    
    def _calculate_costs_and_tokens(self, input_tokens, output_tokens):
        """Calculate costs using model-specific pricing with cumulative tracking."""
        
        # Get model-specific costs
        model_costs = self._get_model_costs()
        input_cost_per_million = model_costs['input_cost']
        output_cost_per_million = model_costs['output_cost']
        
        # Calculate current call costs
        call_input_cost = (input_tokens / 1_000_000) * input_cost_per_million
        call_output_cost = (output_tokens / 1_000_000) * output_cost_per_million
        total_call_cost = call_input_cost + call_output_cost
        
        return call_input_cost, call_output_cost, total_call_cost
    
    def _get_cumulative_totals(self):
        """Get cumulative totals from previous log entries with memory caching."""
        
        # Return cached values if available
        if self._cache_initialized:
            return self._cached_words, self._cached_input_tokens, self._cached_output_tokens
        
        # Parse log file to get cumulative totals
        total_words = 0
        total_input_tokens = 0
        total_output_tokens = 0
        
        try:
            if os.path.exists(self.detailed_log_file):
                with open(self.detailed_log_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                    # Find all "Translated Words:" entries
                    import re
                    word_matches = re.findall(r'- Translated Words: (\d+)', content)
                    input_matches = re.findall(r'- Exact Input Tokens: (\d+)', content)
                    output_matches = re.findall(r'- Exact Output Tokens: (\d+)', content)
                    
                    for word_count in word_matches:
                        total_words += int(word_count)
                    
                    for input_count in input_matches:
                        total_input_tokens += int(input_count)
                    
                    for output_count in output_matches:
                        total_output_tokens += int(output_count)
        
        except Exception as e:
            log_debug(f"Error reading {self.provider_name} cumulative totals: {e}")
        
        # Cache the results
        self._cached_words = total_words
        self._cached_input_tokens = total_input_tokens
        self._cached_output_tokens = total_output_tokens
        self._cache_initialized = True
        
        return total_words, total_input_tokens, total_output_tokens
    
    def _update_cache(self, words, input_tokens, output_tokens):
        """Update the cumulative totals cache with new values."""
        if self._cache_initialized:
            self._cached_words += words
            self._cached_input_tokens += input_tokens
            self._cached_output_tokens += output_tokens
    
    def _get_cumulative_costs(self):
        """Get cumulative costs from previous log entries with memory caching."""
        
        # Return cached values if available
        if hasattr(self, '_costs_cache_initialized') and self._costs_cache_initialized:
            return self._cached_input_cost, self._cached_output_cost
        
        # Parse log file to get cumulative costs
        total_input_cost = 0.0
        total_output_cost = 0.0
        
        try:
            if os.path.exists(self.detailed_log_file):
                with open(self.detailed_log_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                    # Find all cost entries
                    import re
                    input_cost_matches = re.findall(r'- Input Cost: \$([0-9.]+)', content)
                    output_cost_matches = re.findall(r'- Output Cost: \$([0-9.]+)', content)
                    
                    for cost in input_cost_matches:
                        total_input_cost += float(cost)
                    
                    for cost in output_cost_matches:
                        total_output_cost += float(cost)
        
        except Exception as e:
            log_debug(f"Error reading {self.provider_name} cumulative costs: {e}")
        
        # Cache the results
        self._cached_input_cost = total_input_cost
        self._cached_output_cost = total_output_cost
        self._costs_cache_initialized = True
        
        return total_input_cost, total_output_cost
    
    def _update_costs_cache(self, input_cost, output_cost):
        """Update the cumulative costs cache with new values."""
        if hasattr(self, '_costs_cache_initialized') and self._costs_cache_initialized:
            self._cached_input_cost += input_cost
            self._cached_output_cost += output_cost    
    # === COMPREHENSIVE API LOGGING ===
    
    def _log_complete_translation_call(self, message_content, response_text, call_duration, 
                                     input_tokens, output_tokens, original_text, 
                                     source_lang, target_lang, model_name, model_source):
        """Log complete translation API call with atomic writing (identical format across providers)."""
        
        # Check if API logging is enabled
        if not self._is_logging_enabled():
            return
        
        try:
            with self._log_lock:  # Ensure atomic logging
                
                # Calculate correct start and end times
                call_end_time = self._get_precise_timestamp()
                call_start_time = self._calculate_start_time(call_end_time, call_duration)
                
                # Calculate current call translated word count
                current_translated_words = len(original_text.split())
                
                # Get cumulative totals BEFORE this call
                prev_total_words, prev_total_input, prev_total_output = self._get_cumulative_totals()
                
                # Calculate costs for current call
                call_input_cost, call_output_cost, total_call_cost = self._calculate_costs_and_tokens(input_tokens, output_tokens)
                
                # Calculate new cumulative totals
                new_total_words = prev_total_words + current_translated_words
                new_total_input = prev_total_input + input_tokens
                new_total_output = prev_total_output + output_tokens
                
                # Update cache
                self._update_cache(current_translated_words, input_tokens, output_tokens)
                
                # Get cumulative costs
                prev_total_input_cost, prev_total_output_cost = self._get_cumulative_costs()
                total_input_cost = prev_total_input_cost + call_input_cost
                total_output_cost = prev_total_output_cost + call_output_cost
                
                # Update costs cache
                self._update_costs_cache(call_input_cost, call_output_cost)
                
                # Calculate message stats
                words_in_message = len(message_content.split())
                chars_in_message = len(message_content)
                lines_in_message = len(message_content.split('\n'))
                
                # Get language display names
                source_lang_name = self._get_language_display_name(source_lang, self.provider_name).upper()
                target_lang_name = self._get_language_display_name(target_lang, self.provider_name).upper()
                
                # Format provider name for consistent display
                provider_upper = self.provider_name.upper()
                
                # === DETAILED LOG ENTRY (IDENTICAL FORMAT) ===
                log_entry = f"""
=== {provider_upper} TRANSLATION API CALL ===
Timestamp: {call_start_time}
Language Pair: {source_lang} -> {target_lang}
Original Text: {original_text}

CALL DETAILS:
- Message Length: {chars_in_message} characters
- Word Count: {words_in_message} words
- Line Count: {lines_in_message} lines

COMPLETE MESSAGE CONTENT SENT TO {provider_upper}:
---BEGIN MESSAGE---
{message_content}
---END MESSAGE---

RESPONSE RECEIVED:
Model: {model_name} ({model_source})
Cost: input ${self._get_model_costs()['input_cost']:.3f}, output ${self._get_model_costs()['output_cost']:.3f} (per 1M)
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
- Total Translated Words (so far): {new_total_words}
- Total Input Tokens (so far): {new_total_input}
- Total Output Tokens (so far): {new_total_output}
- Total Input Cost (so far): ${total_input_cost:.8f}
- Total Output Cost (so far): ${total_output_cost:.8f}
- Cumulative Log Cost: ${total_input_cost + total_output_cost:.8f}

========================================

"""
                
                # Write to detailed log
                with open(self.detailed_log_file, 'a', encoding='utf-8') as f:
                    f.write(log_entry)
                
                # Write to short log
                self._write_short_translation_log(
                    call_start_time, call_end_time, call_duration, 
                    input_tokens, output_tokens, total_call_cost,
                    new_total_input, new_total_output, total_input_cost + total_output_cost,
                    original_text, response_text, source_lang, target_lang, 
                    model_name, model_source
                )
        
        except Exception as e:
            log_debug(f"Error in {self.provider_name} API logging: {e}")
    
    def _write_short_translation_log(self, call_start_time, call_end_time, call_duration, 
                                   input_tokens, output_tokens, call_cost, 
                                   cumulative_input, cumulative_output, cumulative_cost,
                                   original_text, translated_text, source_lang, target_lang, 
                                   model_name, model_source):
        """Write concise translation call log entry."""
        if not self._is_logging_enabled():
            return
        
        try:
            # Get language display names
            source_lang_name = self._get_language_display_name(source_lang, self.provider_name).upper()
            target_lang_name = self._get_language_display_name(target_lang, self.provider_name).upper()
            
            # Get model costs for display
            model_costs = self._get_model_costs()
            input_cost = model_costs['input_cost']
            output_cost = model_costs['output_cost']
            
            # Format costs with smart precision
            input_str = f"${input_cost:.3f}" if (input_cost * 1000) % 10 != 0 else f"${input_cost:.2f}"
            output_str = f"${output_cost:.3f}" if (output_cost * 1000) % 10 != 0 else f"${output_cost:.2f}"
            cost_line = f"Cost: input {input_str}, output {output_str} (per 1M)\n"
            
            log_entry = f"""===== TRANSLATION CALL =======
Model: {model_name} ({model_source})
{cost_line}Start: {call_start_time}
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
            with open(self.short_log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)
        
        except Exception as e:
            log_debug(f"Error writing {self.provider_name} short translation log: {e}")
    
    # === CLIENT MANAGEMENT ===
    
    def _should_refresh_client(self):
        """Check if client should be refreshed to prevent stale connections."""
        if not hasattr(self, 'client_created_time') or self.client_created_time == 0:
            self.client_created_time = time.time()
            return False
        
        current_time = time.time()
        
        # Refresh client every 30 minutes to prevent stale connections
        if current_time - self.client_created_time > 1800:  # 30 minutes
            log_debug(f"Refreshing {self.provider_name} client due to age (30 minutes)")
            return True
        
        # Refresh after every 100 API calls to prevent connection accumulation
        if not hasattr(self, 'api_call_count'):
            self.api_call_count = 0
        
        if self.api_call_count > 100:
            log_debug(f"Refreshing {self.provider_name} client after 100 API calls")
            return True
        
        return False
    
    def _force_client_refresh(self):
        """Force refresh of client and reset counters."""
        self.client = None
        self.client_created_time = time.time()
        self.api_call_count = 0
        log_debug(f"{self.provider_name.capitalize()} client refresh forced")
    
    def should_reset_session(self, api_key):
        """Check if session should be reset due to API key change."""
        if not hasattr(self, 'session_api_key') or self.session_api_key != api_key:
            self.session_api_key = api_key
            return True
        return False
    
    # === CIRCUIT BREAKER METHODS ===
    
    def _circuit_breaker_protection(self):
        """Apply circuit breaker protection before API calls."""
        
        # Initialize circuit breaker if needed
        if not hasattr(self, 'circuit_breaker'):
            self.circuit_breaker = NetworkCircuitBreaker()
        
        # Check circuit breaker and force refresh if needed
        if self.circuit_breaker.should_force_refresh():
            log_debug(f"{self.provider_name.capitalize()} circuit breaker forcing client refresh due to network issues")
            self._force_client_refresh()
            self.circuit_breaker = NetworkCircuitBreaker()  # Reset circuit breaker
    
    def _record_api_call_result(self, call_duration, success):
        """Record API call result with circuit breaker."""
        needs_refresh = self.circuit_breaker.record_call(call_duration, success)
        if needs_refresh:
            # Schedule client refresh for next call
            self.client = None
        
        # Increment API call counter for periodic refresh
        if hasattr(self, 'api_call_count'):
            self.api_call_count += 1
    
    # === UTILITY METHODS ===
    
    def _get_precise_timestamp(self):
        """Get precise timestamp for logging."""
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    
    def _calculate_start_time(self, end_time_str, duration_seconds):
        """Calculate start time from end time and duration."""
        try:
            end_time = datetime.strptime(end_time_str, '%Y-%m-%d %H:%M:%S.%f')
            start_time = end_time - timedelta(seconds=duration_seconds)
            return start_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        except:
            # Fallback to simpler calculation
            return end_time_str
    
    def _get_ordinal_number(self, num):
        """Convert number to ordinal (1st, 2nd, 3rd, etc.)."""
        if 10 <= num % 100 <= 20:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(num % 10, 'th')
        return f"{num}{suffix}"
    
    def _get_language_display_name(self, lang_code, provider):
        """Get display name for language code."""
        # This should be implemented to use the app's language manager
        try:
            return self.app.language_manager.get_display_name(lang_code, provider)
        except:
            return lang_code.capitalize()    
    # === UNIFIED TRANSLATE METHOD ===
    
    def translate(self, text, source_lang, target_lang, ocr_batch_number=None):
        """
        Main unified translation method that all providers use.
        Handles all common functionality and delegates only API calls to concrete implementations.
        """
        
        log_debug(f"{self.provider_name.capitalize()} translate request for: {text}")
        
        # Apply circuit breaker protection
        self._circuit_breaker_protection()
        
        # Track pending call
        self._increment_pending_calls()
        
        try:
            # Get API key and validate
            api_key = self._get_api_key()
            if not api_key:
                return f"{self.provider_name.capitalize()} API key missing"
            
            # Check if libraries are available
            if not self._check_library_availability():
                return f"{self.provider_name.capitalize()} libraries not available"
            
            # Check if we need to create a new client
            needs_new_session = (
                not hasattr(self, 'client') or 
                self.client is None or
                self.should_reset_session(api_key)  # API key changed
            )
            
            if needs_new_session:
                if hasattr(self, 'session_api_key') and self.session_api_key != api_key:
                    log_debug(f"Creating new {self.provider_name} client (API key changed)")
                else:
                    log_debug(f"Creating new {self.provider_name} client (no existing client)")
                self._initialize_session(source_lang, target_lang)
            else:
                # Check if language pair changed - clear context
                if (hasattr(self, 'current_source_lang') and hasattr(self, 'current_target_lang') and
                    (self.current_source_lang != source_lang or self.current_target_lang != target_lang)):
                    log_debug(f"{self.provider_name.capitalize()} language pair changed from {self.current_source_lang}->{self.current_target_lang} to {source_lang}->{target_lang}, clearing context")
                    self._clear_context()
            
            # Track current language pair for context clearing
            self.current_source_lang = source_lang
            self.current_target_lang = target_lang
            
            if self.client is None:
                return f"{self.provider_name.capitalize()} client initialization failed"
            
            # Get context window size
            context_size = self._get_context_window_size()
            
            # Build unified message content (identical across all providers)
            message_content = self._build_context_string(text, context_size, source_lang, target_lang)
            
            log_debug(f"Sending to {self.provider_name.capitalize()} {source_lang}->{target_lang}: [{text}]")
            log_debug(f"Making {self.provider_name.capitalize()} API call for: {text}")
            
            # Make the actual API call (provider-specific implementation)
            api_call_start_time = time.time()
            response = self._make_api_call(message_content, self._get_model_config())
            call_duration = time.time() - api_call_start_time
            
            log_debug(f"{self.provider_name.capitalize()} API call took {call_duration:.3f}s")
            
            # Record successful call result
            self._record_api_call_result(call_duration, True)
            
            # Parse response (provider-specific implementation)
            translation_result, input_tokens, output_tokens, model_name, model_source = self._parse_response(response)
            
            log_debug(f"{self.provider_name.capitalize()} response: {translation_result}")
            
            # Log complete API call atomically
            self._log_complete_translation_call(
                message_content, translation_result, call_duration,
                input_tokens, output_tokens, text, source_lang, target_lang,
                model_name, model_source
            )
            
            return translation_result
        
        except Exception as e:
            # Record failed call
            self._record_api_call_result(0, False)
            error_str = str(e)
            log_debug(f"{self.provider_name.capitalize()} API error: {type(e).__name__} - {error_str}")
            
            # Suppress certain errors from being displayed
            if self._should_suppress_error(error_str):
                log_debug(f"{self.provider_name.capitalize()} error suppressed from translation display")
                return None
            else:
                return f"{self.provider_name.capitalize()} API error: {error_str}"
        
        finally:
            # Decrement pending calls
            self._decrement_pending_calls()
    
    # === ABSTRACT METHODS (PROVIDER-SPECIFIC IMPLEMENTATION REQUIRED) ===
    
    @abstractmethod
    def _make_api_call(self, message_content, model_config):
        """
        Provider-specific API call implementation.
        
        Args:
            message_content: The unified message content (identical across providers)
            model_config: Provider-specific model configuration
        
        Returns:
            Provider-specific response object
        """
        pass
    
    @abstractmethod
    def _initialize_client(self, api_key):
        """
        Provider-specific client initialization.
        
        Args:
            api_key: API key for authentication
        
        Returns:
            Initialized client object
        """
        pass
    
    @abstractmethod
    def _parse_response(self, response):
        """
        Provider-specific response parsing.
        
        Args:
            response: Provider-specific response object
        
        Returns:
            Tuple of (translated_text, input_tokens, output_tokens, model_name, model_source)
        """
        pass
    
    @abstractmethod
    def _get_model_config(self):
        """
        Provider-specific model configuration.
        
        Returns:
            Dictionary with model configuration parameters
        """
        pass
    
    @abstractmethod
    def _get_api_key(self):
        """
        Get provider-specific API key.
        
        Returns:
            API key string
        """
        pass
    
    @abstractmethod
    def _check_library_availability(self):
        """
        Check if provider-specific libraries are available.
        
        Returns:
            Boolean indicating library availability
        """
        pass
    
    @abstractmethod
    def _get_context_window_size(self):
        """
        Get provider-specific context window size setting.
        
        Returns:
            Integer context window size
        """
        pass
    
    @abstractmethod
    def _get_model_costs(self):
        """
        Get provider-specific model costs.
        
        Returns:
            Dictionary with 'input_cost' and 'output_cost' keys
        """
        pass
    
    @abstractmethod
    def _is_logging_enabled(self):
        """
        Check if API logging is enabled for this provider.
        
        Returns:
            Boolean indicating if logging is enabled
        """
        pass
    
    @abstractmethod
    def _initialize_session(self, source_lang, target_lang):
        """
        Initialize provider-specific session.
        
        Args:
            source_lang: Source language code
            target_lang: Target language code
        """
        pass
    
    @abstractmethod
    def _should_suppress_error(self, error_str):
        """
        Check if error should be suppressed from display.
        
        Args:
            error_str: Error message string
        
        Returns:
            Boolean indicating if error should be suppressed
        """
        pass