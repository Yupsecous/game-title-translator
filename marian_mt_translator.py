import threading
import time
import gc
import re
import os
import traceback
import shutil
import subprocess
import hashlib
import zipfile
import urllib.request
from pathlib import Path

from logger import log_debug

# --- Configuration ---
ENABLE_PYTORCH_THREAD_LIMITING = False  # Set to False to disable PyTorch thread limiting

# --- For MarianMT Translation with GPU Support ---
try:
    log_debug("MarianMT: Attempting to import transformers...")
    from transformers import MarianMTModel, MarianTokenizer
    log_debug("MarianMT: transformers import successful")
    
    log_debug("MarianMT: Attempting to import torch...")
    import torch
    log_debug("MarianMT: torch import successful")
    
    # Detailed GPU and CUDA Library Detection
    # Check if PyTorch was compiled with CUDA support (works for both compiled and Python modes)
    CUDA_LIBRARIES_AVAILABLE = (hasattr(torch, 'version') and 
                               hasattr(torch.version, 'cuda') and 
                               torch.version.cuda is not None)
    
    if CUDA_LIBRARIES_AVAILABLE:
        GPU_HARDWARE_AVAILABLE = torch.cuda.is_available()
        if GPU_HARDWARE_AVAILABLE:
            # Scenario 4: GPU-ready app on PC with GPU - USE GPU
            GPU_AVAILABLE = True
            GPU_DEVICE = torch.device("cuda:0")
            try:
                GPU_NAME = torch.cuda.get_device_name(0)
                GPU_MEMORY = torch.cuda.get_device_properties(0).total_memory / 1024**3
                cuda_version = torch.version.cuda if torch.version.cuda else "Unknown"
                log_debug(f"GPU: found, GPU libraries: found (CUDA {cuda_version}), MarianMT running on GPU.")
                log_debug(f"GPU detected: {GPU_NAME} ({GPU_MEMORY:.1f} GB VRAM)")
            except:
                # Fallback if GPU detection fails
                GPU_NAME = "Unknown GPU"
                GPU_MEMORY = 0
                cuda_version = torch.version.cuda if torch.version.cuda else "Unknown"
                log_debug(f"GPU: found, GPU libraries: found (CUDA {cuda_version}), MarianMT running on GPU.")
                log_debug("GPU detected but details unavailable")
        else:
            # Scenario 3: GPU-ready app on CPU-only PC - USE CPU
            GPU_AVAILABLE = False
            GPU_DEVICE = torch.device("cpu")
            GPU_NAME = None
            GPU_MEMORY = 0
            cuda_version = torch.version.cuda if torch.version.cuda else "Unknown"
            log_debug(f"GPU: not found, GPU libraries: found (CUDA {cuda_version}), MarianMT running on CPU.")
    else:
        # Scenarios 1 & 2: CPU-only app (no CUDA libraries) - USE CPU
        GPU_AVAILABLE = False
        GPU_DEVICE = torch.device("cpu")
        GPU_NAME = None
        GPU_MEMORY = 0
        
        # Try to detect if GPU hardware exists even without CUDA libraries
        gpu_hardware_detected = False
        gpu_name_detected = "Unknown"
        try:
            # Try alternative GPU detection methods for logging purposes only
            import subprocess
            result = subprocess.run(['nvidia-smi', '--query-gpu=name', '--format=csv,noheader,nounits'], 
                                  capture_output=True, text=True, timeout=3)
            if result.returncode == 0 and result.stdout.strip():
                gpu_hardware_detected = True
                gpu_name_detected = result.stdout.strip().split('\n')[0]
        except:
            pass
        
        if gpu_hardware_detected:
            # Scenario 2: CPU-only app on PC with GPU
            log_debug(f"GPU: found ({gpu_name_detected}), GPU libraries: not found, MarianMT running on CPU.")
        else:
            # Scenario 1: CPU-only app on CPU-only PC
            log_debug("GPU: not found, GPU libraries: not found, MarianMT running on CPU.")
    
    MARIANMT_AVAILABLE = True
    log_debug("MarianMT: All imports successful, MARIANMT_AVAILABLE = True")
    
except ImportError as import_error:
    MARIANMT_AVAILABLE = False
    torch = None
    GPU_AVAILABLE = False
    GPU_DEVICE = None
    GPU_NAME = None
    GPU_MEMORY = 0
    log_debug(f"MarianMT: Import failed with ImportError: {import_error}")
    log_debug("GPU: unknown, GPU libraries: not found, MarianMT not available (transformers/torch not installed).")
except Exception as general_error:
    MARIANMT_AVAILABLE = False
    torch = None
    GPU_AVAILABLE = False
    GPU_DEVICE = None
    GPU_NAME = None
    GPU_MEMORY = 0
    log_debug(f"MarianMT: Import failed with unexpected error: {general_error}")
    log_debug("GPU: unknown, GPU libraries: not found, MarianMT not available (unexpected import error).")

class MarianMTTranslator:
    """GPU-accelerated MarianMT translator with automatic CPU fallback."""

    torch = torch # Class attribute to make torch accessible if imported

    def __init__(self, cache_dir=None, num_beams=2):
        """
        Initialize the translator with GPU/CPU device detection.

        Args:
            cache_dir: Directory to store downloaded models. If None, uses default Hugging Face cache.
            num_beams: Beam search value for translation quality (1-8)
        """
        # Verify imports are available
        if not MARIANMT_AVAILABLE:
            raise ImportError("MarianMT modules not available. Make sure transformers is installed.")

        # GPU/CPU Device Configuration - PERMANENT DECISION
        self.device = GPU_DEVICE if GPU_AVAILABLE else torch.device("cpu")
        self.gpu_enabled = GPU_AVAILABLE
        self.gpu_name = GPU_NAME
        self.gpu_memory = GPU_MEMORY
        
        # Store permanent device configuration (never changes after initialization)
        self.permanent_device = self.device
        self.permanent_gpu_enabled = self.gpu_enabled
        
        # Smart fallback system - allows temporary CPU fallback for GPU OOM
        self.current_device = self.permanent_device  # Current active device (can temporarily change)
        self.temporary_cpu_fallback = False  # Flag to track if we're in temporary CPU mode
        
        # Flag to track when cache has been cleared and model needs reloading
        self.cache_cleared_flag = False
        
        # Log device configuration with explicit scenario information
        if self.gpu_enabled:
            cuda_version = torch.version.cuda if (torch and hasattr(torch, 'version') and torch.version.cuda) else "Unknown"
            log_debug(f"MarianMT initialized with GPU acceleration (PERMANENT)")
            log_debug(f"GPU: {self.gpu_name} ({self.gpu_memory:.1f} GB VRAM)")
            log_debug(f"Scenario 4: GPU-ready application on PC with GPU CUDA support (CUDA {cuda_version})")
        else:
            log_debug("MarianMT initialized with CPU processing (PERMANENT)")
            # Determine which of the first 3 scenarios we're in using improved detection
            if (torch and hasattr(torch, 'version') and 
                hasattr(torch.version, 'cuda') and 
                torch.version.cuda is not None):
                cuda_version = torch.version.cuda
                log_debug(f"Scenario 3: GPU-ready application on CPU-only PC (CUDA {cuda_version} available but no GPU)")
            else:
                # Check if GPU hardware exists for more specific logging
                gpu_hardware_detected = False
                gpu_name = "Unknown"
                try:
                    import subprocess
                    result = subprocess.run(['nvidia-smi', '--query-gpu=name', '--format=csv,noheader,nounits'], 
                                          capture_output=True, text=True, timeout=3)
                    if result.returncode == 0 and result.stdout.strip():
                        gpu_hardware_detected = True
                        gpu_name = result.stdout.strip().split('\n')[0]
                        log_debug(f"Scenario 2: CPU-only application on PC with GPU CUDA support (GPU: {gpu_name})")
                    else:
                        log_debug("Scenario 1: CPU-only application on CPU-only PC")
                except:
                    log_debug("Scenario 1: CPU-only application on CPU-only PC")

        # Add a thread lock for model operations
        self.model_lock = threading.RLock()

        self.active_model_key = None
        self.active_tokenizer = None
        self.active_model = None
        self.active_pivot = None
        self.cache_dir = cache_dir
        self.num_beams = num_beams  # Store beam search value (1-8)

        # Log CPU thread configuration
        if torch: # Check if torch was imported successfully
            cpu_count = os.cpu_count() or 2
            
            if ENABLE_PYTORCH_THREAD_LIMITING and cpu_count > 2:
                # Limit PyTorch to half of available CPU cores for better system performance
                max_torch_threads = max(1, cpu_count // 2)
                torch.set_num_threads(max_torch_threads)
                log_debug(f"MarianMT limited PyTorch to {max_torch_threads} threads (out of {cpu_count} CPU cores)")
            else:
                if not ENABLE_PYTORCH_THREAD_LIMITING:
                    log_debug(f"MarianMT PyTorch thread limiting DISABLED - using default {torch.get_num_threads()} threads")
                else:
                    log_debug(f"MarianMT initialized with {torch.get_num_threads()} CPU threads (no limiting on {cpu_count} cores)")
        else:
            log_debug("MarianMT initialized, but PyTorch not available for thread count.")

        # Define supported language pairs and their model names
        self.supported_langs = set()  # Will be populated dynamically
        self.direct_pairs = {
            # Note: No ('en', 'pl') entry here as it uses special handling
            ('pl', 'en'): 'Helsinki-NLP/opus-mt-pl-en',
            ('en', 'de'): 'Helsinki-NLP/opus-mt-en-de',
            ('de', 'en'): 'Helsinki-NLP/opus-mt-de-en',
            ('en', 'fr'): 'Helsinki-NLP/opus-mt-en-fr',
            ('fr', 'en'): 'Helsinki-NLP/opus-mt-fr-en',
            ('fr', 'de'): 'Helsinki-NLP/opus-mt-fr-de',
            ('de', 'fr'): 'Helsinki-NLP/opus-mt-de-fr',
            ('pl', 'de'): 'Helsinki-NLP/opus-mt-pl-de',
            ('de', 'pl'): 'Helsinki-NLP/opus-mt-de-pl',
            ('pl', 'fr'): 'Helsinki-NLP/opus-mt-pl-fr',
            ('fr', 'pl'): 'Helsinki-NLP/opus-mt-fr-pl'
        }

        # Populate supported languages set
        for source, target in self.direct_pairs.keys():
            self.supported_langs.add(source)
            self.supported_langs.add(target)
        
        # Add special support for English to Polish (handled separately)
        self.supported_langs.add('en')
        self.supported_langs.add('pl')

        # Define model name to language pair mapping (for explicitly adding models)
        # This helps when we need to dynamically select specific models
        self.model_to_langs = {}
        for (source, target), model in self.direct_pairs.items():
            self.model_to_langs[model] = (source, target)

    def notify_cache_cleared(self):
        """
        Notify the translator that the translation cache has been cleared.
        This will force the model to be reloaded on next translation to ensure proper state.
        """
        with self.model_lock:
            self.cache_cleared_flag = True
            device_type = "GPU" if self.permanent_gpu_enabled else "CPU"
            log_debug(f"MarianMT notified of cache clearing - will force model reload on {device_type}")

    def _translate_batch_sentences(self, sentences, source_lang, target_lang):
        """
        Translate multiple sentences in a single batch operation.
        
        Args:
            sentences: List of sentences to translate
            source_lang: Source language code
            target_lang: Target language code
            
        Returns:
            List of translated sentences
        """
        try:
            batch_start_time = time.monotonic()
            
            # Filter out empty sentences but keep track of indices
            non_empty_sentences = []
            sentence_indices = []
            for i, sentence in enumerate(sentences):
                clean_sentence = sentence.strip()
                if clean_sentence:
                    non_empty_sentences.append(clean_sentence)
                    sentence_indices.append(i)
            
            if not non_empty_sentences:
                return [""] * len(sentences)
            
            log_debug(f"Batch translating {len(non_empty_sentences)} non-empty sentences from {len(sentences)} total")
            
            # Use the enhanced _translate_text_cached method with batch input
            model_key = (source_lang, target_lang)
            translated_batch = self._translate_text_cached(non_empty_sentences, model_key, self.num_beams)
            
            # Handle case where translation failed
            if isinstance(translated_batch, str):
                # Single string error message - apply to all sentences
                log_debug(f"Batch translation failed with error: {translated_batch}")
                return [translated_batch] * len(sentences)
            
            # Reconstruct full results list including empty sentences
            results = [""] * len(sentences)
            for i, translated in enumerate(translated_batch):
                original_index = sentence_indices[i]
                results[original_index] = translated
            
            batch_time = time.monotonic() - batch_start_time
            current_device_name = "GPU" if (self.current_device.type == 'cuda') else "CPU"
            fallback_info = " (temporary fallback)" if self.temporary_cpu_fallback else ""
            log_debug(f"Batch translation complete on {current_device_name}{fallback_info}: {len(non_empty_sentences)} sentences in {batch_time:.3f} seconds")
            
            return results
            
        except Exception as e:
            error_msg = f"Error in batch translation: {str(e)}"
            log_debug(error_msg)
            log_debug(traceback.format_exc())
            # Return original sentences on error
            return sentences

    def _unload_current_model(self):
        """Unload the current model to free memory (GPU and CPU) while preserving device configuration."""
        # This method is called from within _try_load_direct_model which already
        # holds the lock, so we don't need to acquire it again here
        device_type = "GPU" if self.permanent_gpu_enabled else "CPU"
        fallback_status = " (temporary CPU fallback)" if self.temporary_cpu_fallback else ""
        log_debug(f"Unloading current MarianMT model and tokenizer from {device_type}{fallback_status}.")
        
        self.active_model_key = None
        self.active_tokenizer = None
        self.active_model = None
        self.active_pivot = None
        
        # Reset to permanent device configuration and clear fallback status
        self.current_device = self.permanent_device
        self.temporary_cpu_fallback = False
        
        # Force garbage collection to release memory
        gc.collect()
        
        # Clear GPU cache if available and we're using GPU permanently
        if torch and torch.cuda.is_available() and self.permanent_gpu_enabled:
            torch.cuda.empty_cache()
            log_debug("GPU cache cleared after model unload.")
        else:
            log_debug("CPU memory released after model unload.")

    def _try_load_direct_model(self, source_lang, target_lang):
        """Try to load a direct translation model for the language pair with thread safety."""
        model_key = (source_lang, target_lang)

        device_type = "GPU" if self.permanent_gpu_enabled else "CPU"
        log_debug(f"Attempting to load translation model for language pair: '{source_lang}' to '{target_lang}' on {device_type}")

        # Use a lock to ensure thread safety
        with self.model_lock:
            # Check if cache was cleared - if so, force reload even if model seems loaded
            if self.cache_cleared_flag:
                log_debug(f"Cache was cleared - forcing model reload on {device_type}")
                self._unload_current_model()
                self.cache_cleared_flag = False  # Reset the flag
                
            # Check if this model pair is already loaded and cache wasn't cleared
            elif self.active_model_key == model_key and self.active_model is not None:
                log_debug(f"Model for '{source_lang}' to '{target_lang}' already loaded and active on {device_type}.")
                return True

            # Unload existing model to save memory if a different model is active or needs to be loaded
            if self.active_model_key != model_key or self.active_model is None: # More precise condition for unload
                log_debug(f"Unloading previous model (if any) before loading {source_lang}->{target_lang} on {device_type}.")
                self._unload_current_model() # Unconditional unload logic moved into _unload_current_model

            # Special handling for English to Polish model
            if source_lang == 'en' and target_lang == 'pl':
                special_model_path = self._ensure_special_en_pl_model()
                if special_model_path:
                    model_name = special_model_path
                    log_debug(f"Using special English to Polish model from: {model_name}")
                else:
                    log_debug("Special English to Polish model not available, no fallback exists")
                    return False
            # Regular model loading logic for all other language pairs
            elif model_key in self.direct_pairs:
                model_name = self.direct_pairs[model_key]
                log_debug(f"Found predefined model '{model_name}' for language pair '{source_lang}' to '{target_lang}'")
                # Verify it's a Helsinki-NLP model
                if not model_name.startswith('Helsinki-NLP/opus-mt'):
                    log_debug(f"Model '{model_name}' is not a Helsinki-NLP/opus-mt model, skipping")
                    return False
            else:
                # Try to dynamically construct a Helsinki-NLP model name
                model_name = f"Helsinki-NLP/opus-mt-{source_lang}-{target_lang}"
                log_debug(f"No predefined model, trying to dynamically load: '{model_name}'")

            try:
                log_debug(f"Attempting to download and load model: {model_name} on {device_type}")
                start_time = time.time()

                # Load tokenizer (always on CPU)
                self.active_tokenizer = MarianTokenizer.from_pretrained(model_name, cache_dir=self.cache_dir)
                
                # Load model with device-specific configuration
                self.active_model = MarianMTModel.from_pretrained(
                    model_name,
                    cache_dir=self.cache_dir,
                    low_cpu_mem_usage=True,  # More memory-efficient loading
                    torch_dtype=torch.float16 if self.permanent_gpu_enabled else torch.float32,  # Use FP16 on GPU
                )

                # Move model to appropriate device with smart fallback
                try:
                    # Always try permanent device first (GPU if configured)
                    if self.temporary_cpu_fallback and self.permanent_gpu_enabled:
                        # We were in CPU fallback mode, try to restore GPU
                        log_debug("Attempting to restore GPU after temporary CPU fallback")
                        self.current_device = self.permanent_device
                        self.temporary_cpu_fallback = False
                    
                    self.active_model = self.active_model.to(self.current_device)
                    load_time = time.time() - start_time
                    
                    device_name = "GPU" if (self.current_device.type == 'cuda') else "CPU"
                    log_debug(f"Model {model_name} loaded to {device_name} in {load_time:.2f} seconds")
                    
                    if self.current_device.type == 'cuda':
                        # Log GPU memory usage
                        if torch.cuda.is_available():
                            memory_allocated = torch.cuda.memory_allocated(0) / 1024**3
                            log_debug(f"GPU memory allocated: {memory_allocated:.2f} GB")
                        
                        # Reset fallback flag since GPU loading succeeded
                        if self.temporary_cpu_fallback:
                            self.temporary_cpu_fallback = False
                            log_debug("Successfully restored GPU operation after temporary fallback")
                        
                except (RuntimeError, torch.cuda.OutOfMemoryError) as e:
                    # Smart fallback: only fall back to CPU if we were configured for GPU
                    if self.permanent_gpu_enabled and not self.temporary_cpu_fallback:
                        log_debug(f"GPU loading failed ({e}), implementing temporary CPU fallback")
                        log_debug("This is a temporary fallback - will attempt GPU again on next model load")
                        
                        # Set temporary CPU fallback mode
                        self.current_device = torch.device("cpu")
                        self.temporary_cpu_fallback = True
                        
                        try:
                            # Try loading on CPU
                            self.active_model = self.active_model.to(self.current_device)
                            load_time = time.time() - start_time
                            log_debug(f"Model {model_name} loaded to CPU (temporary fallback) in {load_time:.2f} seconds")
                        except Exception as cpu_error:
                            log_debug(f"CPU fallback also failed: {cpu_error}")
                            return False
                    else:
                        # We're either permanently CPU-configured or already in fallback mode
                        if self.permanent_gpu_enabled:
                            log_debug(f"CPU fallback also failed: {e}")
                        else:
                            log_debug(f"CPU loading failed (permanently configured for CPU): {e}")
                        return False

                self.active_model_key = model_key
                # Add to supported languages if successful
                self.supported_langs.add(source_lang)
                self.supported_langs.add(target_lang)
                # Add to direct pairs if it wasn't there before
                if model_key not in self.direct_pairs:
                    self.direct_pairs[model_key] = model_name
                    log_debug(f"Added new model to direct_pairs: {model_key} -> {model_name}")

                return True
            except Exception as e:
                log_debug(f"Could not load model {model_name}: {e}")
                # Will continue to pivot translation
                return False

    # MODIFIED: Removed @lru_cache decorator - caching now handled by unified cache
    def _translate_text_cached(self, text, model_key, beam_value): # Added beam_value parameter
        """Perform the actual translation with caching and thread safety. Supports both single text and batch input."""
        # Use a lock for thread-safe model access
        with self.model_lock:
            # This method assumes the correct model is already loaded
            if self.active_model_key != model_key or self.active_tokenizer is None or self.active_model is None:
                log_debug(f"Model key mismatch or model not loaded. Active: {self.active_model_key}, Requested: {model_key}")
                return f"Error: Model {model_key} not loaded correctly"

        # Determine if this is batch input (list) or single input (string)
        is_batch_input = isinstance(text, list)
        
        if is_batch_input:
            return self._translate_batch_input(text, beam_value)
        else:
            return self._translate_single_input(text, beam_value)

    def _translate_single_input(self, text, beam_value):
        """Handle single text input translation."""
        try:
            # IMPROVED: Handle potential token limits by checking text length
            total_chars = len(text)

            # For very short text, just translate directly with high quality settings
            if total_chars < 2:
                inputs = self.active_tokenizer([text], return_tensors="pt", padding=True)
                # Move inputs to current device (GPU or CPU, includes fallback handling)
                inputs = {k: v.to(self.current_device) for k, v in inputs.items()}
                
                if torch: # Check torch exists
                    with torch.no_grad():
                        try:
                            if self.current_device.type == 'cuda':
                                # GPU generation with mixed precision for speed
                                with torch.cuda.amp.autocast():
                                    translated = self.active_model.generate(
                                        **inputs,
                                        max_length=512,
                                        num_beams=beam_value,
                                        length_penalty=1.0,
                                        no_repeat_ngram_size=2
                                    )
                            else:
                                # CPU generation
                                translated = self.active_model.generate(
                                    **inputs,
                                    max_length=512,
                                    num_beams=beam_value,
                                    length_penalty=1.0,
                                    no_repeat_ngram_size=2
                                )
                        except torch.cuda.OutOfMemoryError:
                            # Smart fallback for GPU OOM during translation
                            if self.permanent_gpu_enabled and self.current_device.type == 'cuda':
                                log_debug("GPU out of memory during translation, falling back to CPU temporarily")
                                
                                # Move everything to CPU for this translation
                                inputs_cpu = {k: v.cpu() for k, v in inputs.items()}
                                model_cpu = self.active_model.cpu()
                                self.current_device = torch.device("cpu")
                                self.temporary_cpu_fallback = True
                                
                                # Perform translation on CPU
                                translated = model_cpu.generate(
                                    **inputs_cpu,
                                    max_length=512,
                                    num_beams=beam_value,
                                    length_penalty=1.0,
                                    no_repeat_ngram_size=2
                                )
                                
                                # Keep model on CPU for subsequent translations until next model load
                                self.active_model = model_cpu
                                log_debug("Translation completed on CPU fallback. GPU will be retried on next model load.")
                            else:
                                # Either not GPU-configured or already in CPU mode
                                log_debug("Out of memory error in CPU mode or non-GPU configuration")
                                return "Error: Out of memory during translation."
                    
                    result = self.active_tokenizer.batch_decode(translated, skip_special_tokens=True)[0]
                    return result
                else: # Fallback if torch is not available (should not happen if MARIANMT_AVAILABLE is True)
                    return "Error: PyTorch not available for translation."

            # For longer text, ensure we don't exceed tokenizer limits
            # First normalize spacing and punctuation
            text = re.sub(r'\s+', ' ', text).strip()

            # IMPROVED: Get token count before translation to check limits
            # This helps diagnose potential truncation issues
            token_info = self.active_tokenizer.encode(text, add_special_tokens=True)
            token_count = len(token_info)
            log_debug(f"Text has {token_count} tokens for {total_chars} characters")

            # IMPROVED: Handle very long text with potential token limit issues
            if token_count > 450:  # Most models have ~512 token limits
                log_debug(f"Warning: Text exceeds recommended token limit ({token_count} tokens)")

                if token_count > 900:  # Critical limit, force chunking
                    log_debug("Critical token limit exceeded, forcing text truncation")
                    # Get a safely-sized substring
                    tokens_to_use = token_info[:400]  # Use first ~400 tokens
                    # Convert tokens back to text to preserve complete sentences
                    truncated_text = self.active_tokenizer.decode(tokens_to_use, skip_special_tokens=True)
                    log_debug(f"Truncated text from {total_chars} to {len(truncated_text)} chars")
                    text = truncated_text

            # Create a clean input for translation with the possibly truncated text
            inputs = self.active_tokenizer([text], return_tensors="pt", padding=True)
            # Move inputs to current device (GPU or CPU, includes fallback handling)
            inputs = {k: v.to(self.current_device) for k, v in inputs.items()}

            # Use no_grad for better memory usage during inference
            if torch: # Check torch exists
                with torch.no_grad():
                    log_debug(f"Using beam search value: {beam_value}")

                    try:
                        if self.current_device.type == 'cuda':
                            # GPU generation with mixed precision for speed and memory efficiency
                            with torch.cuda.amp.autocast():
                                translated = self.active_model.generate(
                                    **inputs,
                                    max_length=512,  # Increased max_length for longer content
                                    num_beams=beam_value,
                                    length_penalty=1.0, # Higher penalty = longer outputs
                                    no_repeat_ngram_size=2,  # Prevent repetition
                                    min_length=0,
                                    early_stopping=(beam_value > 1),
                                    repetition_penalty=1.1  # Further discourage repetition/truncation
                                )
                        else:
                            # CPU generation
                            translated = self.active_model.generate(
                                **inputs,
                                max_length=512,  # Increased max_length for longer content
                                num_beams=beam_value,
                                length_penalty=1.0, # Higher penalty = longer outputs
                                no_repeat_ngram_size=2,  # Prevent repetition
                                min_length=0,
                                early_stopping=(beam_value > 1),
                                repetition_penalty=1.1  # Further discourage repetition/truncation
                            )
                    
                    except torch.cuda.OutOfMemoryError:
                        # Smart fallback for GPU OOM during longer text translation
                        if self.permanent_gpu_enabled and self.current_device.type == 'cuda':
                            log_debug("GPU out of memory during longer text translation, falling back to CPU temporarily")
                            
                            # Move everything to CPU for this translation
                            inputs_cpu = {k: v.cpu() for k, v in inputs.items()}
                            model_cpu = self.active_model.cpu()
                            self.current_device = torch.device("cpu")
                            self.temporary_cpu_fallback = True
                            
                            # Perform translation on CPU
                            translated = model_cpu.generate(
                                **inputs_cpu,
                                max_length=512,
                                num_beams=beam_value,
                                length_penalty=1.0,
                                no_repeat_ngram_size=2,
                                min_length=0,
                                early_stopping=(beam_value > 1),
                                repetition_penalty=1.1
                            )
                            
                            # Keep model on CPU for subsequent translations until next model load
                            self.active_model = model_cpu
                            log_debug("Longer text translation completed on CPU fallback. GPU will be retried on next model load.")
                        else:
                            # Either not GPU-configured or already in CPU mode
                            log_debug("Out of memory error during longer text translation in CPU mode or non-GPU configuration")
                            return "Error: Out of memory during translation."

                # Decode the result
                result = self.active_tokenizer.batch_decode(translated, skip_special_tokens=True)[0]

                # Enhanced logging and validation
                input_sentences = len(re.findall(r'[.!?]\s+|\n+', text)) + 1
                output_sentences = len(re.findall(r'[.!?]\s+|\n+', result)) + 1
                log_ratio = len(result) / max(1, len(text))
                
                # Log device used for performance tracking
                current_device_name = "GPU" if (self.current_device.type == 'cuda') else "CPU"
                fallback_info = " (temporary fallback)" if self.temporary_cpu_fallback else ""
                log_debug(f"Translation completed on {current_device_name}{fallback_info}: {len(text)} → {len(result)} chars")

                # IMPROVED: Check for potentially incomplete translations
                if (len(result) < len(text) * 0.7 and len(text) > 50) or \
                   (output_sentences < input_sentences and input_sentences > 1) or \
                   (len(result) < 10 and len(text) > 20):
                    log_debug(f"Warning: Translation may be incomplete. Input: {len(text)} chars ({input_sentences} sentences), Output: {len(result)} chars ({output_sentences} sentences), Ratio: {log_ratio:.2f}")
                    log_debug(f"Input text: '{text}'")
                    log_debug(f"Result: '{result}'")

                return result
            else: # Fallback if torch is not available
                return "Error: PyTorch not available for translation."

        except Exception as e:
            # import traceback # Already imported at the top of the file
            error_details = traceback.format_exc()
            log_debug(f"Translation error: {e}\n{error_details}")
            return f"Translation error: {str(e)}"

    def _translate_batch_input(self, text_list, beam_value):
        """Handle batch text input translation."""
        try:
            if not text_list:
                return []

            # Log batch processing start
            batch_size = len(text_list)
            log_debug(f"Processing batch of {batch_size} sentences for translation")

            # Prepare inputs for batch processing
            inputs = self.active_tokenizer(text_list, return_tensors="pt", padding=True, truncation=True, max_length=450)
            # Move inputs to current device (GPU or CPU, includes fallback handling)
            inputs = {k: v.to(self.current_device) for k, v in inputs.items()}

            # Use no_grad for better memory usage during inference
            if torch: # Check torch exists
                with torch.no_grad():
                    log_debug(f"Using beam search value: {beam_value} for batch translation")

                    try:
                        if self.current_device.type == 'cuda':
                            # GPU generation with mixed precision for speed and memory efficiency
                            with torch.cuda.amp.autocast():
                                translated = self.active_model.generate(
                                    **inputs,
                                    max_length=512,  # Increased max_length for longer content
                                    num_beams=beam_value,
                                    length_penalty=1.0, # Higher penalty = longer outputs
                                    no_repeat_ngram_size=2,  # Prevent repetition
                                    min_length=0,
                                    early_stopping=(beam_value > 1),
                                    repetition_penalty=1.1  # Further discourage repetition/truncation
                                )
                        else:
                            # CPU generation
                            translated = self.active_model.generate(
                                **inputs,
                                max_length=512,  # Increased max_length for longer content
                                num_beams=beam_value,
                                length_penalty=1.0, # Higher penalty = longer outputs
                                no_repeat_ngram_size=2,  # Prevent repetition
                                min_length=0,
                                early_stopping=(beam_value > 1),
                                repetition_penalty=1.1  # Further discourage repetition/truncation
                            )
                    
                    except torch.cuda.OutOfMemoryError:
                        # Smart fallback for GPU OOM during batch translation
                        if self.permanent_gpu_enabled and self.current_device.type == 'cuda':
                            log_debug("GPU out of memory during batch translation, falling back to CPU temporarily")
                            
                            # Move everything to CPU for this translation
                            inputs_cpu = {k: v.cpu() for k, v in inputs.items()}
                            model_cpu = self.active_model.cpu()
                            self.current_device = torch.device("cpu")
                            self.temporary_cpu_fallback = True
                            
                            # Perform translation on CPU
                            translated = model_cpu.generate(
                                **inputs_cpu,
                                max_length=512,
                                num_beams=beam_value,
                                length_penalty=1.0,
                                no_repeat_ngram_size=2,
                                min_length=0,
                                early_stopping=(beam_value > 1),
                                repetition_penalty=1.1
                            )
                            
                            # Keep model on CPU for subsequent translations until next model load
                            self.active_model = model_cpu
                            log_debug("Batch translation completed on CPU fallback. GPU will be retried on next model load.")
                        else:
                            # Either not GPU-configured or already in CPU mode
                            log_debug("Out of memory error during batch translation in CPU mode or non-GPU configuration")
                            return ["Error: Out of memory during translation."] * batch_size

                # Decode all results at once
                results = self.active_tokenizer.batch_decode(translated, skip_special_tokens=True)

                # Log device used for performance tracking
                current_device_name = "GPU" if (self.current_device.type == 'cuda') else "CPU"
                fallback_info = " (temporary fallback)" if self.temporary_cpu_fallback else ""
                log_debug(f"Batch translation completed on {current_device_name}{fallback_info}: {batch_size} sentences processed")

                return results
            else: # Fallback if torch is not available
                return ["Error: PyTorch not available for translation."] * batch_size

        except Exception as e:
            # import traceback # Already imported at the top of the file
            error_details = traceback.format_exc()
            log_debug(f"Batch translation error: {e}\n{error_details}")
            return [f"Translation error: {str(e)}"] * len(text_list)

    def translate(self, text, source_lang, target_lang):
        """
        Translate text from source language to target language using batch processing.

        Args:
            text: Text to translate
            source_lang: Source language code
            target_lang: Target language code

        Returns:
            Translated text or error message
        """
        translation_start_time = time.monotonic()  # Start timing the entire process

        # Basic validation
        source_lang = source_lang.lower()
        target_lang = target_lang.lower()

        if source_lang == target_lang:
            return text  # No translation needed

        # Try to load direct model or dynamically attempt the pair
        model_key = (source_lang, target_lang)
        direct_model_loaded = self._try_load_direct_model(source_lang, target_lang)

        if not direct_model_loaded:
            # If we couldn't load the model, provide a specific error message
            # Get language names from codes for a more user-friendly message
            # Use a simple capitalize for names, specific handling for common ones if needed
            source_lang_name = source_lang.capitalize()
            target_lang_name = target_lang.capitalize()

            common_lang_map = {
                'en': 'English', 'pl': 'Polish', 'de': 'German', 'fr': 'French', 
                'es': 'Spanish', 'it': 'Italian'
            }
            source_lang_name = common_lang_map.get(source_lang, source_lang_name)
            target_lang_name = common_lang_map.get(target_lang, target_lang_name)

            error_msg = f"The {source_lang_name} to {target_lang_name} translation is not supported by MarianMT models. Consider switching to Google Translate."
            log_debug(error_msg)
            return error_msg

        # Ensure we're working with a clean string
        if not text or not isinstance(text, str):
            return "" if text is None else str(text)

        # Clean up and normalize the text
        text = re.sub(r'\s+', ' ', text).strip()
        if not text:
            return ""

        # Log the text being translated for debugging
        current_device_name = "GPU" if (self.current_device.type == 'cuda') else "CPU"
        fallback_info = " (temporary fallback)" if self.temporary_cpu_fallback else ""
        log_debug(f"MarianMT translating on {current_device_name}{fallback_info}: \"{text}\" from {source_lang} to {target_lang}")

        # Split text into sentences
        sentences = self._split_into_sentences(text)

        # Handle single-sentence case directly
        if len(sentences) <= 1 or len(text) < 30:
            log_debug(f"Using direct translation for single sentence or short text: \"{text}\"")
            result = self._translate_batch(text, source_lang, target_lang)

            # Log completion time
            translation_time = time.monotonic() - translation_start_time
            current_device_name = "GPU" if (self.current_device.type == 'cuda') else "CPU"
            fallback_info = " (temporary fallback)" if self.temporary_cpu_fallback else ""
            log_debug(f"MarianMT translation complete in {translation_time:.3f} seconds on {current_device_name}{fallback_info}")
            log_debug(f"The completed translation is displayed: \"{result}\"")

            return result

        # Log that we're using batch translation
        current_device_name = "GPU" if (self.current_device.type == 'cuda') else "CPU"
        fallback_info = " (temporary fallback)" if self.temporary_cpu_fallback else ""
        log_debug(f"Translating {len(sentences)} sentences in batch mode on {current_device_name}{fallback_info}")

        try:
            # Use batch translation for multiple sentences
            translated_sentences = self._translate_batch_sentences(sentences, source_lang, target_lang)

            # Join translated sentences with appropriate spacing
            result = " ".join(translated_sentences)

            # Calculate and log total time
            translation_time = time.monotonic() - translation_start_time
            current_device_name = "GPU" if (self.current_device.type == 'cuda') else "CPU"
            fallback_info = " (temporary fallback)" if self.temporary_cpu_fallback else ""
            log_debug(f"Batch translation complete on {current_device_name}{fallback_info}: {len(translated_sentences)} sentences processed in {translation_time:.3f} seconds")
            log_debug(f"The completed subtitle is displayed: \"{result}\"")

            return result

        except Exception as e:
            error_msg = f"Error in batch translation: {str(e)}"
            log_debug(error_msg)
            log_debug(traceback.format_exc())

            # Fall back to sequential translation on error
            log_debug("Falling back to sequential translation")
            return self._sequential_fallback_translate(text, sentences, source_lang, target_lang)

    def _sequential_fallback_translate(self, full_text, sentences, source_lang, target_lang):
        """Fallback method to translate sequentially if batch translation fails."""
        sequential_start_time = time.monotonic()  # Start timing the sequential process

        try:
            # If sentences list is empty or invalid, translate the full text directly
            if not sentences:
                log_debug(f"No sentences to translate, using full text: \"{full_text}\"")
                result = self._translate_batch(full_text, source_lang, target_lang)
                log_debug(f"Full text translated in fallback mode: \"{result}\"")
                return result

            # Process sentences sequentially using the single input method
            log_debug(f"Sequential translation of {len(sentences)} sentences:")
            translated_parts = []
            for i, sentence in enumerate(sentences):
                if sentence.strip():
                    log_debug(f"Sequentially translating sentence {i+1}: \"{sentence}\"")

                    # Track individual sentence translation time
                    sentence_start_time = time.monotonic()
                    translated = self._translate_batch(sentence, source_lang, target_lang)
                    sentence_translation_time = time.monotonic() - sentence_start_time

                    if translated and not self._is_error_message(translated):
                        log_debug(f"Sentence {i+1}: \"{sentence}\" has been translated by MarianMT in {sentence_translation_time:.2f}s")
                        log_debug(f"Translation result: \"{translated}\"")
                        translated_parts.append(translated)
                    else:
                        log_debug(f"Sentence {i+1} translation failed, using original: \"{sentence}\"")
                        translated_parts.append(sentence)
                else:
                    # Add empty sentence as-is
                    translated_parts.append(sentence)

            # Join results
            if translated_parts:
                result = " ".join(translated_parts)
                translation_time = time.monotonic() - sequential_start_time
                log_debug(f"Sequential translation complete: {len(translated_parts)} sentences processed in {translation_time:.3f} seconds")
                log_debug(f"The completed subtitle is displayed: \"{result}\"")
                return result
            else:
                # Last resort - translate full text
                log_debug(f"No translated parts, using full text as last resort: \"{full_text}\"")
                result = self._translate_batch(full_text, source_lang, target_lang)
                translation_time = time.monotonic() - sequential_start_time
                log_debug(f"Full text translated in {translation_time:.3f} seconds: \"{result}\"")
                return result

        except Exception as e:
            log_debug(f"Sequential fallback translation failed: {e}")
            # Return original text in case of complete failure
            return full_text

    def _is_error_message(self, text):
        """Check if a translation result is an error message."""
        if not isinstance(text, str):
            return True
        error_indicators = [
            "error:", "translation error", "not initialized", "missing", "failed",
            "not available", "not supported", "invalid result", "empty result"
        ]
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in error_indicators)

    def _translate_batch(self, text, source_lang, target_lang):
        """Translate a single batch of text using appropriate model. (Pivot translation removed)."""
        try:
            log_debug(f"Attempting to translate batch: \"{text}\" from {source_lang} to {target_lang}")

            # --- Direct Translation Attempt Only ---
            model_key = (source_lang, target_lang)

            # Check if we need to force load the model (if it changed)
            force_load_needed = (self.active_model_key != model_key or self.active_model is None) # Also check if model is None
            if force_load_needed:
                log_debug(f"Model key change or model not loaded: {self.active_model_key} -> {model_key}, Model loaded: {self.active_model is not None}")

            # Try to load the direct model for the requested pair
            direct_model_loaded = False
            # Attempt load if needed or if the correct model isn't already active
            if force_load_needed : # Simplified condition
                direct_model_loaded = self._try_load_direct_model(source_lang, target_lang)
            elif self.active_model_key == model_key and self.active_model is not None : # Model is correct and loaded
                direct_model_loaded = True
                log_debug(f"Using already loaded model for {source_lang}->{target_lang}")
            else: # Model key matches but model is None (e.g. previous load failed)
                direct_model_loaded = self._try_load_direct_model(source_lang, target_lang)

            # --- Perform Translation if Direct Model Loaded ---
            if direct_model_loaded:
                log_debug(f"Using direct translation model for {source_lang}->{target_lang}")
                # Pass self.num_beams as the third argument to the cached function
                translated = self._translate_text_cached(text, model_key, self.num_beams)
                log_debug(f"Direct translation result: \"{translated}\"")
                return translated

            # --- Handle Failure: Direct Model Not Available (No Pivot Fallback) ---
            else:
                log_debug(f"Direct model for {source_lang}->{target_lang} failed to load or is not available.")

                # Generate user-friendly language names for the error message
                source_lang_name = source_lang.capitalize()
                target_lang_name = target_lang.capitalize()
                # Add common language names for better messages
                common_langs = {'en': 'English', 'pl': 'Polish', 'de': 'German', 'fr': 'French', 'es': 'Spanish', 'it': 'Italian'}
                source_lang_name = common_langs.get(source_lang, source_lang_name)
                target_lang_name = common_langs.get(target_lang, target_lang_name)

                # Construct the specific error message indicating lack of support
                error_msg = f"The {source_lang_name} to {target_lang_name} translation is not supported by MarianMT models. Consider switching to Google Translate."
                log_debug(error_msg) # Log the error
                return error_msg # Return the error message to the caller

        # --- General Exception Handling ---
        except Exception as e:
            # Log any unexpected errors during the process
            log_debug(f"MarianMT translation error in _translate_batch: {type(e).__name__} - {str(e)}")
            log_debug(traceback.format_exc())
            # Return a generic error message
            return f"Translation error: {type(e).__name__} - {str(e)}"

    def _split_into_sentences(self, text):
        """Split text into sentences for parallel translation processing."""
        if not text:
            return []

        # Normalize whitespace first
        text = re.sub(r'\s+', ' ', text).strip()

        # Log the full text before splitting
        log_debug(f"Splitting text into sentences: \"{text}\"")

        # Define character ranges for different languages
        # latin_chars = r'A-ZÀ-ÖØ-ÞÇÉÈÊÂÄÀÔÛÙÏÎŘa-z0-9–—-'
        # latin_caps = r'A-ZÀ-ÖØ-ÞÇÉÈÊÂÄÀÔÛÙÏÎŘ–—-'
        latin_chars = r'A-ZÀ-ÖØ-ÞĀĂĄĆĈĊČĎĐĒĔĖĘĚĜĞĠĢĤĦĨĪĬĮİĲĴĶĹĻĽĿŁŃŅŇŊŌŎŐŒŔŖŘŚŜŞŠŢŤŦŨŪŬŮŰŲŴŶŸŹŻŽa-z0-9–—\-¿¡'
        latin_caps = r'A-ZÀ-ÖØ-ÞĀĂĄĆĈĊČĎĐĒĔĖĘĚĜĞĠĢĤĦĨĪĬĮİĲĴĶĹĻĽĿŁŃŅŇŊŌŎŐŒŔŖŘŚŜŞŠŢŤŦŨŪŬŮŰŲŴŶŸŹŻŽ–—\-¿¡'
        hiragana_katakana = r'\u3040-\u30FF'  # Hiragana and Katakana ranges
        cjk_chars = r'\u4E00-\u9FAF'          # Common CJK characters

        # Create patterns for sentence splitting
        patterns = []

        # Basic Western punctuation with Latin character support
        patterns.append(r'(?<=\.)(?=\s*[' + latin_chars + r'])')              # Period + space + Latin chars
        patterns.append(r'(?<=!)(?=\s*[' + latin_chars + r'])')               # Exclamation + space + Latin chars
        patterns.append(r'(?<=\?)(?=\s*[' + latin_chars + r'])')              # Question + space + Latin chars
        patterns.append(r'(?<=\.\.\.)(?=\s*[' + latin_caps + r'])')           # Ellipsis + space + Latin capitals
        patterns.append(r'(?<=\.\.\.)(?=\s*[' + latin_chars + r'])')          # Ellipsis + space + any Latin char (lowercase included)
        patterns.append(r'(?<=…)(?=\s*[' + latin_caps + r'])')                # Unicode ellipsis + space + Latin capitals
        patterns.append(r'(?<=…)(?=\s*[' + latin_chars + r'])')               # Unicode ellipsis + space + any Latin char (lowercase included)
        
        # Basic Japanese/CJK punctuation (keep separate from Latin patterns)
        patterns.append(r'(?<=。)(?=[' + hiragana_katakana + cjk_chars + r'])')  # Japanese period + CJK char
        patterns.append(r'(?<=！)(?=[' + hiragana_katakana + cjk_chars + r'])')  # Japanese exclamation + CJK char
        patterns.append(r'(?<=？)(?=[' + hiragana_katakana + cjk_chars + r'])')  # Japanese question + CJK char
        patterns.append(r'(?<=……)(?=[' + hiragana_katakana + cjk_chars + r'])')  # Japanese ellipsis + CJK char
        
        # Combined punctuation
        # Western style with Latin char support
        patterns.append(r'(?<=!\?)(?=\s*[' + latin_chars + r'])')             # !? + Latin chars
        patterns.append(r'(?<=\?!)(?=\s*[' + latin_chars + r'])')             # ?! + Latin chars
        
        # Japanese style (separate from Latin)
        patterns.append(r'(?<=！？)(?=[' + hiragana_katakana + cjk_chars + r'])')  # Japanese !? + CJK char
        patterns.append(r'(?<=？！)(?=[' + hiragana_katakana + cjk_chars + r'])')  # Japanese ?! + CJK char
        
        # Common Japanese sentence endings (keep separate from Latin)
        jp_endings = ['だ', 'ね', 'よ', 'ぞ', 'わ', 'さ', 'な', 'か', 'ます', 'です', 'たい', 'ない']
        jp_punctuation = ['。', '！', '？']
        
        for ending in jp_endings:
            for punct in jp_punctuation:
                # Pattern: ending + punctuation + CJK character
                patterns.append(r'(?<=' + ending + punct + r')(?=[' + hiragana_katakana + cjk_chars + r'])')
        
        # Newlines as sentence separators
        patterns.append(r'(?<=\.)(?=\s*\n)')         # Period + newline
        patterns.append(r'(?<=!)(?=\s*\n)')          # Exclamation + newline
        patterns.append(r'(?<=\?)(?=\s*\n)')         # Question + newline
        patterns.append(r'(?<=。)(?=\s*\n)')          # Japanese period + newline
        patterns.append(r'(?<=！)(?=\s*\n)')          # Japanese exclamation + newline
        patterns.append(r'(?<=？)(?=\s*\n)')          # Japanese question + newline
        
        # Join all patterns
        sentence_terminators = '|'.join(patterns)
        
        # Split using the pattern
        try:
            sentences = re.split(sentence_terminators, text)
            log_debug(f"Successfully split text using {len(patterns)} patterns")
        except Exception as e:
            log_debug(f"Error in sentence splitting: {str(e)}")
            # Fallback to simple splitting on basic punctuation if regex fails
            sentences = re.split(r'(?<=\.)\s+|(?<=!)\s+|(?<=\?)\s+|(?<=。)|(?<=！)|(?<=？)', text)
            log_debug(f"Used fallback sentence splitting")

        # Process and filter the resulting sentences
        processed_sentences = []
        for s in sentences:
            if s is None: continue # re.split can produce None values
            s_stripped = s.strip()
            if not s_stripped:
                continue
            processed_sentences.append(s_stripped)

        # Handle special cases
        if not processed_sentences:
            log_debug(f"No sentences found after splitting, using full text: \"{text}\"")
            return [text]  # Return original if splitting failed

        # Don't split very short text
        if len(text) < 30:
            log_debug(f"Text too short for splitting (<30 chars): \"{text}\"")
            return [text]

        # Log each sentence found
        log_debug(f"Splitting into {len(processed_sentences)} sentences:")
        for i, sentence in enumerate(processed_sentences):
            log_debug(f"Sentence {i+1}: \"{sentence}\"")

        return processed_sentences

    def get_device_info(self):
        """Get current device information for debugging."""
        info = {
            'permanent_device': str(self.permanent_device),
            'current_device': str(self.current_device),
            'permanent_gpu_enabled': self.permanent_gpu_enabled,
            'temporary_cpu_fallback': self.temporary_cpu_fallback,
            'gpu_available': torch.cuda.is_available() if torch else False,
            'gpu_name': self.gpu_name,
            'gpu_memory_total': self.gpu_memory,
            'current_model': self.active_model_key,
            'cache_cleared_flag': self.cache_cleared_flag
        }
        
        if torch and torch.cuda.is_available() and self.current_device.type == 'cuda':
            try:
                info['gpu_memory_allocated'] = torch.cuda.memory_allocated(0) / 1024**3
                info['gpu_memory_cached'] = torch.cuda.memory_reserved(0) / 1024**3
            except:
                info['gpu_memory_allocated'] = 0
                info['gpu_memory_cached'] = 0
        
        return info

    def _ensure_special_en_pl_model(self):
        """
        Ensure the special English-to-Polish model is available.
        Downloads, converts, and sets up the model if needed.
        Returns the path to the model or None if failed.
        """
        try:
            # Define paths
            cache_base = Path(self.cache_dir) if self.cache_dir else Path("marian_models_cache")
            special_model_dir = cache_base / "models--Tatoeba--opus-en-pl-official"
            
            # Check if model already exists
            if self._is_special_model_ready(special_model_dir):
                snapshot_path = self._get_model_snapshot_path(special_model_dir)
                if snapshot_path:
                    log_debug(f"Special EN-PL model already available at: {snapshot_path}")
                    return str(snapshot_path)
            
            log_debug("Special EN-PL model not found, starting download and conversion process")
            
            # Create necessary directories
            download_dir = cache_base / "download"
            converted_dir = cache_base / "converted"
            
            # Clean up any existing temp directories
            if download_dir.exists():
                shutil.rmtree(download_dir)
            if converted_dir.exists():
                shutil.rmtree(converted_dir)
            
            download_dir.mkdir(parents=True, exist_ok=True)
            converted_dir.mkdir(parents=True, exist_ok=True)
            
            # Step 1: Download the model
            if not self._download_tatoeba_model(download_dir):
                log_debug("Failed to download Tatoeba model")
                return None
            
            # Step 2: Convert the model
            if not self._convert_tatoeba_model(download_dir, converted_dir):
                log_debug("Failed to convert Tatoeba model")
                return None
            
            # Step 3: Set up HuggingFace-compatible cache structure
            snapshot_path = self._setup_hf_cache_structure(converted_dir, special_model_dir)
            if not snapshot_path:
                log_debug("Failed to set up HuggingFace cache structure")
                return None
            
            # Step 4: Clean up temporary directories
            if download_dir.exists():
                shutil.rmtree(download_dir)
            if converted_dir.exists():
                shutil.rmtree(converted_dir)
            
            log_debug(f"Special EN-PL model successfully set up at: {snapshot_path}")
            return str(snapshot_path)
            
        except Exception as e:
            log_debug(f"Error setting up special EN-PL model: {e}")
            log_debug(traceback.format_exc())
            return None

    def _is_special_model_ready(self, model_dir):
        """Check if the special model is already set up and ready to use."""
        try:
            if not model_dir.exists():
                return False
            
            snapshot_path = self._get_model_snapshot_path(model_dir)
            if not snapshot_path:
                return False
            
            # Check if required files exist
            required_files = ['config.json', 'model.safetensors', 'tokenizer_config.json', 'vocab.json']
            for file_name in required_files:
                if not (snapshot_path / file_name).exists():
                    return False
            
            return True
        except Exception as e:
            log_debug(f"Error checking special model readiness: {e}")
            return False

    def _get_model_snapshot_path(self, model_dir):
        """Get the snapshot path for the model."""
        try:
            snapshots_dir = model_dir / "snapshots"
            if not snapshots_dir.exists():
                return None
            
            # Find the first (and should be only) snapshot directory
            snapshot_dirs = [d for d in snapshots_dir.iterdir() if d.is_dir()]
            if not snapshot_dirs:
                return None
            
            return snapshot_dirs[0]
        except Exception as e:
            log_debug(f"Error getting snapshot path: {e}")
            return None

    def _download_tatoeba_model(self, download_dir):
        """Download the Tatoeba model from the specified URL."""
        try:
            url = "https://object.pouta.csc.fi/Tatoeba-MT-models/eng-pol/opus+bt-2021-04-14.zip"
            zip_path = download_dir / "opus+bt-2021-04-14.zip"
            
            log_debug(f"Downloading Tatoeba model from: {url}")
            
            # Download with progress (simple version)
            urllib.request.urlretrieve(url, zip_path)
            
            if not zip_path.exists():
                log_debug("Downloaded file not found")
                return False
            
            log_debug(f"Download complete, extracting to: {download_dir}")
            
            # Extract the zip file
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(download_dir)
            
            # Remove the zip file
            zip_path.unlink()
            
            log_debug("Extraction complete")
            return True
            
        except Exception as e:
            log_debug(f"Error downloading Tatoeba model: {e}")
            return False

    def _convert_tatoeba_model(self, download_dir, converted_dir):
        """Convert the downloaded Tatoeba model using the convert_marian.py script."""
        try:
            # The model files are extracted directly to download_dir, not in a subdirectory
            source_model_dir = download_dir
            log_debug(f"Using source model directory: {source_model_dir}")
            
            # Debug: List all files in the source directory
            log_debug("Contents of source model directory:")
            for item in source_model_dir.rglob("*"):
                if item.is_file():
                    log_debug(f"  File: {item.relative_to(source_model_dir)} (size: {item.stat().st_size} bytes)")
                elif item.is_dir():
                    log_debug(f"  Directory: {item.relative_to(source_model_dir)}/")
            
            # Check for required files
            npz_files = list(source_model_dir.glob("*.npz"))
            yml_files = list(source_model_dir.glob("*.yml"))
            decoder_yml = source_model_dir / "decoder.yml"
            
            log_debug(f"Found .npz files: {[f.name for f in npz_files]}")
            log_debug(f"Found .yml files: {[f.name for f in yml_files]}")
            log_debug(f"decoder.yml exists: {decoder_yml.exists()}")
            
            if not npz_files:
                log_debug("No .npz model files found in source directory")
                return False
            
            if not decoder_yml.exists():
                log_debug("decoder.yml file not found in source directory")
                return False
            
            # Path to the conversion script
            script_dir = Path(__file__).parent
            convert_script = script_dir / "convert_marian.py"
            
            if not convert_script.exists():
                log_debug(f"Conversion script not found at: {convert_script}")
                return False
            
            log_debug(f"Running conversion script: {convert_script}")
            
            # Run the conversion script
            cmd = [
                "python", 
                str(convert_script),
                "--src", str(source_model_dir),
                "--dest", str(converted_dir)
            ]
            
            log_debug(f"Conversion command: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            log_debug(f"Conversion script return code: {result.returncode}")
            if result.stdout:
                log_debug(f"Conversion stdout: {result.stdout}")
            if result.stderr:
                log_debug(f"Conversion stderr: {result.stderr}")
            
            if result.returncode != 0:
                log_debug(f"Conversion script failed with return code: {result.returncode}")
                return False
            
            # Verify converted files exist
            converted_files = list(converted_dir.glob("*"))
            log_debug(f"Files in converted directory: {[f.name for f in converted_files]}")
            
            if not converted_files:
                log_debug("No files found in converted directory after conversion")
                return False
            
            log_debug("Model conversion completed successfully")
            return True
            
        except Exception as e:
            log_debug(f"Error converting Tatoeba model: {e}")
            log_debug(traceback.format_exc())
            return False

    def _setup_hf_cache_structure(self, converted_dir, target_model_dir):
        """Set up HuggingFace-compatible cache structure."""
        try:
            # Create the target directory structure
            target_model_dir.mkdir(parents=True, exist_ok=True)
            refs_dir = target_model_dir / "refs"
            snapshots_dir = target_model_dir / "snapshots"
            refs_dir.mkdir(exist_ok=True)
            snapshots_dir.mkdir(exist_ok=True)
            
            # Generate a hash for the snapshot directory
            snapshot_hash = hashlib.sha1(b"tatoeba-opus-en-pl-official").hexdigest()
            snapshot_dir = snapshots_dir / snapshot_hash
            snapshot_dir.mkdir(exist_ok=True)
            
            # Copy all files from converted directory to snapshot directory
            for item in converted_dir.iterdir():
                if item.is_file():
                    shutil.copy2(item, snapshot_dir / item.name)
            
            # Create the refs/main file pointing to our snapshot
            main_ref = refs_dir / "main"
            main_ref.write_text(snapshot_hash)
            
            log_debug(f"HuggingFace cache structure created at: {target_model_dir}")
            log_debug(f"Snapshot directory: {snapshot_dir}")
            
            return snapshot_dir
            
        except Exception as e:
            log_debug(f"Error setting up HuggingFace cache structure: {e}")
            return None

    def get_scenario_description(self):
        """Get a human-readable description of the current scenario."""
        if self.permanent_gpu_enabled:
            cuda_version = torch.version.cuda if (torch and hasattr(torch, 'version') and torch.version.cuda) else "Unknown"
            return f"Scenario 4: GPU-ready application on PC with GPU CUDA support (CUDA {cuda_version}) → MarianMT using GPU"
        else:
            # Use improved detection logic for CPU scenarios
            if (torch and hasattr(torch, 'version') and 
                hasattr(torch.version, 'cuda') and 
                torch.version.cuda is not None):
                cuda_version = torch.version.cuda
                return f"Scenario 3: GPU-ready application on CPU-only PC (CUDA {cuda_version} available) → MarianMT using CPU"
            else:
                # Try to detect GPU hardware for distinction between scenarios 1 and 2
                try:
                    import subprocess
                    result = subprocess.run(['nvidia-smi', '--query-gpu=name', '--format=csv,noheader,nounits'], 
                                          capture_output=True, text=True, timeout=3)
                    if result.returncode == 0 and result.stdout.strip():
                        gpu_name = result.stdout.strip().split('\n')[0]
                        return f"Scenario 2: CPU-only application on PC with GPU CUDA support (GPU: {gpu_name}) → MarianMT using CPU"
                    else:
                        return "Scenario 1: CPU-only application on CPU-only PC → MarianMT using CPU"
                except:
                    return "Scenario 1: CPU-only application on CPU-only PC → MarianMT using CPU"
