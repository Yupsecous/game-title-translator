# handlers/gemini_provider.py
"""
Gemini provider implementation for unified LLM architecture.
Inherits all common functionality from AbstractLLMProvider and implements only Gemini-specific API calls.
"""

import time
from logger import log_debug
from handlers.llm_provider_base import AbstractLLMProvider

# Pre-load Gemini libraries at module level for performance
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


class GeminiProvider(AbstractLLMProvider):
    """
    Gemini provider implementation using unified LLM architecture.
    
    Inherits all common functionality:
    - Comprehensive API logging with identical format
    - Advanced cost tracking with real-time calculation  
    - Smart context windows with sliding window algorithm
    - Robust session management with circuit breaker protection
    - Thread-safe operations with atomic logging
    
    Implements only Gemini-specific:
    - API call mechanism using genai.Client
    - Response parsing for Gemini response format
    - Model configuration for Gemini models
    """
    
    def __init__(self, app):
        """Initialize Gemini provider with unified architecture."""
        super().__init__(app, "gemini")
        
        # Gemini-specific client variables
        self.gemini_client = None
        self.gemini_generation_config = None
        
        log_debug("Gemini provider initialized with unified architecture")
    
    # === GEMINI-SPECIFIC API CALL IMPLEMENTATION ===
    
    def _make_api_call(self, message_content, model_config):
        """Gemini-specific API call using genai.Client."""
        
        if not hasattr(self, 'gemini_client') or self.gemini_client is None:
            raise Exception("Gemini client not initialized")
        
        # Get the appropriate model for translation
        translation_model_api_name = self.app.get_current_gemini_model_for_translation()
        if not translation_model_api_name:
            # Fallback to config if no specific model selected
            translation_model_api_name = self.app.config['Settings'].get('gemini_model_name', 'gemini-2.5-flash-lite')
        
        # Make the API call
        response = self.gemini_client.models.generate_content(
            model=translation_model_api_name,
            contents=message_content,
            config=self.gemini_generation_config
        )
        
        return response
    
    def _initialize_client(self, api_key):
        """Gemini-specific client initialization."""
        
        try:
            # Initialize Gemini client with API key
            self.gemini_client = genai.Client(api_key=api_key)
            
            # Create generation config with Gemini-specific parameters
            self.gemini_generation_config = types.GenerateContentConfig(
                temperature=float(self.app.config['Settings'].get('gemini_model_temp', '0.0')),
                max_output_tokens=1024,
            )
            
            # Add thinking_config for models that support it
            try:
                translation_model_api_name = self.app.get_current_gemini_model_for_translation()
                if translation_model_api_name and self.app.gemini_models_manager:
                    model_config = self.app.gemini_models_manager.get_model_by_api_name(translation_model_api_name)
                    if model_config and 'thinking_budget' in model_config.get('special_config', ''):
                        self.gemini_generation_config.thinking_config = types.ThinkingConfig(
                            thinking_budget=0  # Conservative budget for translation
                        )
            except Exception as e:
                log_debug(f"Could not configure thinking_config: {e}")
            
            # Set session variables
            self.session_api_key = api_key
            self.client_created_time = time.time()
            self.api_call_count = 0
            
            # Assign to unified client variable
            self.client = self.gemini_client
            
            log_debug("Gemini client initialized successfully")
            
        except Exception as e:
            log_debug(f"Error initializing Gemini client: {e}")
            self.gemini_client = None
            self.client = None
            raise
    
    def _parse_response(self, response):
        """Gemini-specific response parsing."""
        
        # Extract exact token counts from API response metadata
        input_tokens, output_tokens = 0, 0
        model_name = "unknown"
        model_source = "fallback"
        
        try:
            if response.usage_metadata:
                input_tokens = response.usage_metadata.prompt_token_count
                output_tokens = response.usage_metadata.candidates_token_count
                log_debug(f"Gemini usage metadata found: In={input_tokens}, Out={output_tokens}")
            
            # Try to extract model name from response metadata
            if hasattr(response, 'model_version') and response.model_version:
                model_name = response.model_version
                model_source = "api_response"
            elif hasattr(response, '_response') and hasattr(response._response, 'model_version'):
                model_name = response._response.model_version
                model_source = "api_response"
            else:
                # Fallback to requested model name
                model_name = self.app.get_current_gemini_model_for_translation() or "gemini-2.5-flash-lite"
                model_source = "fallback"
            
            log_debug(f"Gemini model used: {model_name} (source: {model_source})")
        
        except (AttributeError, KeyError):
            log_debug("Could not find usage_metadata or model info in Gemini response. Using fallback values.")
            # Use fallback model name
            model_name = self.app.get_current_gemini_model_for_translation() or "gemini-2.5-flash-lite"
            model_source = "fallback"
        
        # Extract translation text
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
        
        # Strip language prefixes from the result using unified method
        translation_result = self._strip_language_prefixes(translation_result)
        
        return translation_result, input_tokens, output_tokens, model_name, model_source
    
    def _strip_language_prefixes(self, text):
        """Strip language prefixes from translation result."""
        
        if not self.current_target_lang:
            return text
        
        # Get target language display name
        target_lang_name = self._get_language_display_name(self.current_target_lang, 'gemini')
        target_lang_upper = target_lang_name.upper()
        
        # Check for uppercase language name with colon and space
        if text.startswith(f"{target_lang_upper}: "):
            text = text[len(f"{target_lang_upper}: "):].strip()
        # Check for uppercase language name with colon only
        elif text.startswith(f"{target_lang_upper}:"):
            text = text[len(f"{target_lang_upper}:"):].strip()
        # Also check for the old format (lowercase language code) just in case
        elif text.startswith(f"{self.current_target_lang}: "):
            text = text[len(f"{self.current_target_lang}: "):].strip()
        elif text.startswith(f"{self.current_target_lang}:"):
            text = text[len(f"{self.current_target_lang}:"):].strip()
        
        return text
    
    def _get_model_config(self):
        """Gemini-specific model configuration."""
        
        config = {
            'api_name': self.app.get_current_gemini_model_for_translation() or 'gemini-2.5-flash-lite',
            'temperature': float(self.app.config['Settings'].get('gemini_model_temp', '0.0')),
            'max_output_tokens': 1024
        }
        
        # Add model-specific parameters
        try:
            if self.app.gemini_models_manager:
                model_info = self.app.gemini_models_manager.get_model_by_api_name(config['api_name'])
                if model_info and 'special_config' in model_info:
                    config['special_config'] = model_info['special_config']
        except:
            pass
        
        return config
    
    # === GEMINI-SPECIFIC ABSTRACT METHOD IMPLEMENTATIONS ===
    
    def _get_api_key(self):
        """Get Gemini API key from app configuration."""
        return self.app.gemini_api_key_var.get().strip()
    
    def _check_library_availability(self):
        """Check if Gemini libraries are available."""
        return GENAI_AVAILABLE
    
    def _get_context_window_size(self):
        """Get Gemini context window size setting."""
        return self.app.gemini_context_window_var.get()
    
    def _get_model_costs(self):
        """Get Gemini model costs from model manager."""
        try:
            translation_model_api_name = self.app.get_current_gemini_model_for_translation()
            if translation_model_api_name and self.app.gemini_models_manager:
                return self.app.gemini_models_manager.get_model_costs(translation_model_api_name)
        except:
            pass
        
        # Fallback to default Gemini 2.5 Flash-Lite costs
        return {
            'input_cost': 0.1,
            'output_cost': 0.4
        }
    
    def _is_logging_enabled(self):
        """Check if Gemini API logging is enabled."""
        return self.app.gemini_api_log_enabled_var.get()
    
    def _initialize_session(self, source_lang, target_lang):
        """Initialize Gemini session with client setup."""
        
        api_key = self._get_api_key()
        if not api_key:
            raise Exception("Gemini API key missing")
        
        # Initialize the Gemini client
        self._initialize_client(api_key)
        
        # Clear context if language pair changed
        if (hasattr(self, 'current_source_lang') and hasattr(self, 'current_target_lang') and
            (self.current_source_lang != source_lang or self.current_target_lang != target_lang)):
            self._clear_context()
        
        log_debug(f"Gemini session initialized for {source_lang} -> {target_lang}")
    
    def _should_suppress_error(self, error_str):
        """Check if Gemini error should be suppressed from display."""
        
        # Suppress 503 errors from being displayed in translation window
        if "503 UNAVAILABLE" in error_str:
            return True
        
        return False
    
    # === GEMINI-SPECIFIC UTILITY METHODS ===
    
    def update_context_window(self, source_text, translated_text):
        """Update context window and call parent method for consistency."""
        self._update_sliding_window(source_text, translated_text)
    
    def clear_context_window(self):
        """Clear context window using parent method for consistency.""" 
        self._clear_context()
    
    def force_client_refresh(self):
        """Force refresh Gemini client using parent method for consistency."""
        self._force_client_refresh()
        self.gemini_client = None
