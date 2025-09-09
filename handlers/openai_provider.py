# handlers/openai_provider.py

import time

from logger import log_debug
from .llm_provider_base import AbstractLLMProvider

try:
    import openai
    OPENAI_AVAILABLE = True
    log_debug("Pre-loaded OpenAI library")
except ImportError:
    OPENAI_AVAILABLE = False
    log_debug("OpenAI library not available")


class OpenAIProvider(AbstractLLMProvider):
    """OpenAI-specific implementation of LLM translation provider."""
    
    def __init__(self, app):
        super().__init__(app, "openai")
        
        log_debug("OpenAI provider initialized")
    
    # === ABSTRACT METHOD IMPLEMENTATIONS ===
    
    def _get_api_key(self):
        """Get OpenAI API key."""
        return self.app.openai_api_key_var.get().strip()
    
    def _check_provider_availability(self):
        """Check if OpenAI libraries are available."""
        return OPENAI_AVAILABLE
    
    def _get_context_window_size(self):
        """Get OpenAI context window size setting."""
        return self.app.openai_context_window_var.get()
    
    def _initialize_client(self, api_key, source_lang, target_lang):
        """Initialize OpenAI client session."""
        try:
            self.client = openai.OpenAI(api_key=api_key)
            self.session_api_key = api_key
            self.client_created_time = time.time()
            self.api_call_count = 0
            
            # Clear context window on session initialization
            self._clear_context()
            
            log_debug(f"OpenAI client initialized for {source_lang}->{target_lang}")
            
        except Exception as e:
            log_debug(f"Error initializing OpenAI session: {e}")
            self.client = None
    
    def _get_model_config(self):
        """Get OpenAI model configuration for API calls."""
        # Get the appropriate model for translation
        translation_model_api_name = self.app.get_current_openai_model_for_translation()
        if not translation_model_api_name:
            # Fallback to config if no specific model selected
            translation_model_api_name = self.app.config['Settings'].get('openai_model_name', 'gpt-4o-mini')
        
        return {
            'api_name': translation_model_api_name,
            'temperature': 0.0,
            'max_tokens': 2000
        }
    
    def _make_api_call(self, message_content, model_config):
        """Make OpenAI-specific API call handling both Chat Completions and Responses API."""
        if not hasattr(self, 'client') or self.client is None:
            raise Exception("OpenAI client not initialized")
        
        model_name = model_config['api_name']
        
        # Build messages for API call - convert unified format to OpenAI messages
        messages = self._build_openai_messages(message_content)
        
        # Check if this is a GPT 5 model and handle accordingly
        if model_name.startswith('gpt-5'):
            # GPT 5 models use the Responses API
            if model_name == 'gpt-5-nano':
                # GPT 5 Nano: Use minimal reasoning and low verbosity
                log_debug("Using GPT 5 Nano with minimal reasoning and low verbosity")
                response = self.client.responses.create(
                    model=model_name,
                    input=self._format_input_for_responses_api(messages),
                    reasoning={'effort': 'minimal'},
                    text={'verbosity': 'low'}
                )
            else:
                # Other GPT 5 models: Use default reasoning
                log_debug(f"Using GPT 5 model {model_name} with default settings")
                response = self.client.responses.create(
                    model=model_name,
                    input=self._format_input_for_responses_api(messages)
                )
        elif model_name in ['gpt-4.1-mini', 'gpt-4.1-nano']:
            # GPT 4.1 Mini and Nano: Use temperature=0 for non-thinking mode
            log_debug(f"Using {model_name} with temperature=0 (non-thinking mode)")
            response = self.client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=model_config['temperature'],
                max_tokens=model_config['max_tokens']
            )
        else:
            # Other models: Use default Chat Completions API with temperature=0
            response = self.client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=model_config['temperature'],
                max_tokens=model_config['max_tokens']
            )
        
        return response
    
    def _build_openai_messages(self, unified_content):
        """Convert unified message content to OpenAI messages format."""
        # Split the unified content into instruction and context
        lines = unified_content.split('\n')
        instruction_line = lines[0] if lines else ""
        context_content = '\n'.join(lines[1:]) if len(lines) > 1 else ""
        
        # Extract the system instruction
        if instruction_line.startswith('<') and instruction_line.endswith('>'):
            system_content = instruction_line[1:-1]  # Remove < >
        else:
            system_content = instruction_line
        
        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": context_content}
        ]
    
    def _format_input_for_responses_api(self, messages):
        """Format OpenAI messages for the Responses API input parameter."""
        if not messages:
            return ""
        
        # For GPT 5 models using Responses API, we need to combine system and user messages
        # into a single input string
        formatted_parts = []
        
        for message in messages:
            role = message.get('role', '')
            content = message.get('content', '')
            
            if role == 'system':
                # System messages become instructions
                formatted_parts.append(content)
            elif role == 'user':
                # User messages become the main content
                formatted_parts.append(content)
        
        return '\n\n'.join(formatted_parts)
    
    def _parse_response(self, response):
        """Parse OpenAI response and extract relevant information."""
        model_config = self._get_model_config()
        model_name = model_config['api_name']
        
        # Extract exact token counts from API response metadata
        input_tokens, output_tokens = 0, 0
        model_source = "api_request"
        
        try:
            # Handle different response structures for different APIs
            if model_name.startswith('gpt-5'):
                # GPT 5 models use Responses API - check for usage in different locations
                if hasattr(response, 'usage') and response.usage:
                    input_tokens = getattr(response.usage, 'prompt_tokens', 0) or getattr(response.usage, 'input_tokens', 0)
                    output_tokens = getattr(response.usage, 'completion_tokens', 0) or getattr(response.usage, 'output_tokens', 0)
                elif hasattr(response, 'input_tokens') and hasattr(response, 'output_tokens'):
                    input_tokens = response.input_tokens
                    output_tokens = response.output_tokens
                log_debug(f"OpenAI GPT-5 usage metadata: In={input_tokens}, Out={output_tokens}")
            else:
                # GPT 4.1 and other models use Chat Completions API
                if hasattr(response, 'usage') and response.usage:
                    input_tokens = response.usage.prompt_tokens
                    output_tokens = response.usage.completion_tokens
                log_debug(f"OpenAI Chat Completions usage metadata: In={input_tokens}, Out={output_tokens}")
            
            log_debug(f"OpenAI model used: {model_name} (source: {model_source})")
        except (AttributeError, KeyError) as e:
            log_debug(f"Could not find usage metadata in OpenAI response: {e}. Using requested model name as fallback.")
            # For GPT-5 models, estimate tokens if not available
            if model_name.startswith('gpt-5'):
                # This will be calculated after we get the translation_result
                pass

        # Handle different response structures for different APIs
        if model_name.startswith('gpt-5'):
            # GPT 5 models use Responses API
            translation_result = response.output_text.strip() if hasattr(response, 'output_text') else response.text.strip()
        else:
            # GPT 4.1 and other models use Chat Completions API
            translation_result = response.choices[0].message.content.strip()
        
        # For GPT-5 models, estimate tokens if not available
        if model_name.startswith('gpt-5') and (input_tokens == 0 or output_tokens == 0):
            input_tokens = max(input_tokens, int(len(str(response).split()) * 1.3))  # Rough estimate
            output_tokens = max(output_tokens, int(len(translation_result.split()) * 1.3))  # Rough estimate
            log_debug(f"OpenAI GPT-5 estimated tokens: In={input_tokens}, Out={output_tokens}")
        
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
        translation_result = self._clean_language_prefixes(translation_result)
        
        return translation_result, input_tokens, output_tokens, model_name, model_source
    
    def _clean_language_prefixes(self, text):
        """Remove language prefixes from OpenAI response."""
        # Get target language display name
        if hasattr(self, 'current_target_lang'):
            target_lang_name = self._get_language_display_name(self.current_target_lang)
            target_lang_upper = target_lang_name.upper()
            target_lang_code = self.current_target_lang
            
            # Check for uppercase language name with colon and space
            if text.startswith(f"{target_lang_upper}: "):
                return text[len(f"{target_lang_upper}: "):].strip()
            # Check for uppercase language name with colon only
            elif text.startswith(f"{target_lang_upper}:"):
                return text[len(f"{target_lang_upper}:"):].strip()
            # Also check for the old format (lowercase language code) just in case
            elif text.startswith(f"{target_lang_code}: "):
                return text[len(f"{target_lang_code}: "):].strip()
            elif text.startswith(f"{target_lang_code}:"):
                return text[len(f"{target_lang_code}:"):].strip()
        
        return text
    
    def _get_model_costs(self, model_name):
        """Get OpenAI model-specific costs."""
        try:
            if hasattr(self.app, 'openai_models_manager') and self.app.openai_models_manager:
                model_costs = self.app.openai_models_manager.get_model_costs(model_name)
                return model_costs['input_cost'], model_costs['output_cost']
        except Exception as e:
            log_debug(f"Error getting OpenAI model costs for {model_name}: {e}")
        
        # Fallback costs (GPT-4o-mini pricing)
        return 0.15, 0.6
    
    def _is_logging_enabled(self):
        """Check if OpenAI logging is enabled."""
        return self.app.openai_api_log_enabled_var.get()
    
    def _should_suppress_error(self, error_str):
        """Check if OpenAI error should be suppressed from display."""
        # Suppress rate limit errors from being displayed in translation window
        return "rate limit" in error_str.lower()
