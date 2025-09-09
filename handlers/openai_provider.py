# handlers/openai_provider.py
"""
OpenAI provider implementation for unified LLM architecture.
Inherits all common functionality from AbstractLLMProvider and implements only OpenAI-specific API calls.
"""

import time
from logger import log_debug
from handlers.llm_provider_base import AbstractLLMProvider

# Pre-load OpenAI libraries at module level for performance
try:
    import openai
    OPENAI_AVAILABLE = True
    log_debug("Pre-loaded OpenAI library")
except ImportError:
    OPENAI_AVAILABLE = False
    log_debug("OpenAI library not available")


class OpenAIProvider(AbstractLLMProvider):
    """
    OpenAI provider implementation using unified LLM architecture.
    
    Inherits all common functionality:
    - Comprehensive API logging with identical format
    - Advanced cost tracking with real-time calculation  
    - Smart context windows with sliding window algorithm
    - Robust session management with circuit breaker protection
    - Thread-safe operations with atomic logging
    
    Implements only OpenAI-specific:
    - API call mechanism using openai.OpenAI client
    - Support for both Chat Completions API (GPT-4.1) and Responses API (GPT-5)
    - Response parsing for different OpenAI response formats
    - Model configuration for OpenAI models
    """
    
    def __init__(self, app):
        """Initialize OpenAI provider with unified architecture."""
        super().__init__(app, "openai")
        
        # OpenAI-specific client variables
        self.openai_client = None
        
        log_debug("OpenAI provider initialized with unified architecture")
    
    # === OPENAI-SPECIFIC API CALL IMPLEMENTATION ===
    
    def _make_api_call(self, message_content, model_config):
        """OpenAI-specific API call handling both Chat Completions and Responses API."""
        
        if not hasattr(self, 'openai_client') or self.openai_client is None:
            raise Exception("OpenAI client not initialized")
        
        api_name = model_config['api_name']
        
        # Check if this is a GPT-5 model and handle accordingly
        if api_name.startswith('gpt-5'):
            # GPT-5 models use the Responses API - send unified message content as input
            if api_name == 'gpt-5-nano':
                # GPT-5 Nano: Use minimal reasoning and low verbosity
                log_debug("Using GPT-5 Nano with minimal reasoning and low verbosity")
                response = self.openai_client.responses.create(
                    model=api_name,
                    input=message_content,  # Same unified format as Gemini
                    reasoning={'effort': 'minimal'},
                    text={'verbosity': 'low'}
                )
            else:
                # Other GPT-5 models: Use default reasoning
                log_debug(f"Using GPT-5 model {api_name} with default settings")
                response = self.openai_client.responses.create(
                    model=api_name,
                    input=message_content  # Same unified format as Gemini
                )
        
        elif api_name in ['gpt-4.1-mini', 'gpt-4.1-nano']:
            # GPT-4.1 models: Use temperature=0 for non-thinking mode
            log_debug(f"Using {api_name} with temperature=0 (non-thinking mode)")
            response = self.openai_client.chat.completions.create(
                model=api_name,
                messages=[
                    {"role": "user", "content": message_content}  # Same unified format as Gemini
                ],
                temperature=0.0,
                max_tokens=2000
            )
        
        else:
            # Other models: Use default Chat Completions API
            response = self.openai_client.chat.completions.create(
                model=api_name,
                messages=[
                    {"role": "user", "content": message_content}  # Same unified format as Gemini
                ],
                temperature=model_config.get('temperature', 0.0),
                max_tokens=2000
            )
        
        return response
    
    def _initialize_client(self, api_key):
        """OpenAI-specific client initialization."""
        
        try:
            # Initialize OpenAI client with API key
            self.openai_client = openai.OpenAI(api_key=api_key)
            
            # Set session variables
            self.session_api_key = api_key
            self.client_created_time = time.time()
            self.api_call_count = 0
            
            # Assign to unified client variable
            self.client = self.openai_client
            
            log_debug("OpenAI client initialized successfully")
            
        except Exception as e:
            log_debug(f"Error initializing OpenAI client: {e}")
            self.openai_client = None
            self.client = None
            raise
    
    def _parse_response(self, response):
        """OpenAI-specific response parsing for different API types."""
        
        # Extract exact token counts from API response metadata
        input_tokens, output_tokens = 0, 0
        translation_result = ""
        
        # Get model name from current configuration
        model_name = self.app.get_current_openai_model_for_translation() or "gpt-4o-mini"
        model_source = "api_request"
        
        try:
            # Handle different response structures for different APIs
            if model_name.startswith('gpt-5'):
                # GPT-5 models use Responses API
                if hasattr(response, 'usage') and response.usage:
                    input_tokens = getattr(response.usage, 'prompt_tokens', 0) or getattr(response.usage, 'input_tokens', 0)
                    output_tokens = getattr(response.usage, 'completion_tokens', 0) or getattr(response.usage, 'output_tokens', 0)
                elif hasattr(response, 'input_tokens') and hasattr(response, 'output_tokens'):
                    input_tokens = response.input_tokens
                    output_tokens = response.output_tokens
                
                # Extract response text from GPT-5 response
                if hasattr(response, 'output_text'):
                    translation_result = response.output_text
                elif hasattr(response, 'text'):
                    translation_result = response.text
                else:
                    translation_result = str(response)
                
                log_debug(f"OpenAI GPT-5 usage metadata: In={input_tokens}, Out={output_tokens}")
            
            else:
                # GPT-4.1 and other models use Chat Completions API
                if hasattr(response, 'usage') and response.usage:
                    input_tokens = response.usage.prompt_tokens
                    output_tokens = response.usage.completion_tokens
                
                # Extract response text from Chat Completions response
                if hasattr(response, 'choices') and response.choices:
                    translation_result = response.choices[0].message.content
                
                log_debug(f"OpenAI Chat Completions usage metadata: In={input_tokens}, Out={output_tokens}")
            
            log_debug(f"OpenAI model used: {model_name} (source: {model_source})")
        
        except (AttributeError, KeyError) as e:
            log_debug(f"Could not find usage metadata in OpenAI response: {e}. Using estimated values.")
            
            # For GPT-5 models, estimate tokens if not available
            if model_name.startswith('gpt-5'):
                # Rough estimation for GPT-5 models
                input_tokens = len(str(response).split()) * 1.3  # Rough estimate
                output_tokens = len(translation_result.split()) * 1.3 if translation_result else 10
            else:
                # Rough estimation for Chat Completions models
                input_tokens = 50  # Conservative estimate
                output_tokens = 20  # Conservative estimate
        
        # Clean up the translation result
        translation_result = translation_result.strip() if translation_result else ""
        
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
        target_lang_name = self._get_language_display_name(self.current_target_lang, 'openai')
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
        """OpenAI-specific model configuration."""
        
        api_name = self.app.get_current_openai_model_for_translation() or 'gpt-4o-mini'
        
        config = {
            'api_name': api_name,
            'temperature': 0.0,  # Default for most models
            'max_tokens': 2000
        }
        
        # Add model-specific parameters
        try:
            if self.app.openai_models_manager:
                model_info = self.app.openai_models_manager.get_model_by_api_name(api_name)
                if model_info and 'special_config' in model_info:
                    special_config = model_info['special_config']
                    
                    # Parse special config for model-specific parameters
                    if 'reasoning=minimal' in special_config:
                        config['reasoning'] = 'minimal'
                    if 'verbosity=low' in special_config:
                        config['verbosity'] = 'low'
                    if 'non_thinking=true' in special_config:
                        config['temperature'] = 0.0
        except:
            pass
        
        return config
    
    # === OPENAI-SPECIFIC ABSTRACT METHOD IMPLEMENTATIONS ===
    
    def _get_api_key(self):
        """Get OpenAI API key from app configuration."""
        return self.app.openai_api_key_var.get().strip()
    
    def _check_library_availability(self):
        """Check if OpenAI libraries are available."""
        return OPENAI_AVAILABLE
    
    def _get_context_window_size(self):
        """Get OpenAI context window size setting."""
        return self.app.openai_context_window_var.get()
    
    def _get_model_costs(self):
        """Get OpenAI model costs from model manager."""
        try:
            translation_model_api_name = self.app.get_current_openai_model_for_translation()
            if translation_model_api_name and self.app.openai_models_manager:
                return self.app.openai_models_manager.get_model_costs(translation_model_api_name)
        except:
            pass
        
        # Fallback to default GPT-4o-mini costs
        return {
            'input_cost': 0.15,
            'output_cost': 0.6
        }
    
    def _is_logging_enabled(self):
        """Check if OpenAI API logging is enabled."""
        # Use the same logging setting as other providers, or create OpenAI-specific setting
        return getattr(self.app, 'openai_api_log_enabled_var', self.app.gemini_api_log_enabled_var).get()
    
    def _initialize_session(self, source_lang, target_lang):
        """Initialize OpenAI session with client setup."""
        
        api_key = self._get_api_key()
        if not api_key:
            raise Exception("OpenAI API key missing")
        
        # Initialize the OpenAI client
        self._initialize_client(api_key)
        
        # Clear context if language pair changed
        if (hasattr(self, 'current_source_lang') and hasattr(self, 'current_target_lang') and
            (self.current_source_lang != source_lang or self.current_target_lang != target_lang)):
            self._clear_context()
        
        log_debug(f"OpenAI session initialized for {source_lang} -> {target_lang}")
    
    def _should_suppress_error(self, error_str):
        """Check if OpenAI error should be suppressed from display."""
        
        # Suppress rate limit errors from being displayed in translation window
        if "rate limit" in error_str.lower():
            return True
        
        # Suppress certain network errors
        if "connection error" in error_str.lower():
            return True
        
        return False
    
    # === OPENAI-SPECIFIC UTILITY METHODS ===
    
    def update_context_window(self, source_text, translated_text):
        """Update context window and call parent method for consistency."""
        self._update_sliding_window(source_text, translated_text)
    
    def clear_context_window(self):
        """Clear context window using parent method for consistency.""" 
        self._clear_context()
    
    def force_client_refresh(self):
        """Force refresh OpenAI client using parent method for consistency."""
        self._force_client_refresh()
        self.openai_client = None
