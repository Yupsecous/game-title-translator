import os
import time
from logger import log_debug

class CacheManager:
    """Handles file caching operations for translation services"""
    
    def __init__(self, app):
        """Initialize with a reference to the main application
        
        Args:
            app: The main OCRTranslator application instance
        """
        self.app = app
    
    def load_file_caches(self):
        """Loads cached translations from disk files into memory"""
        # Google Translate cache
        try:
            if os.path.exists(self.app.google_cache_file):
                with open(self.app.google_cache_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#') or ':==:' not in line: 
                            continue
                        
                        # Split at the first occurrence of ':==:'
                        parts = line.split(':==:', 1)
                        if len(parts) == 2:
                            full_cache_key = parts[0]
                            translated_text = parts[1]
                            
                            # Handle the new format with timestamp
                            # GoogleTranslate(FR-PL,2025-05-13 22:43:12):text_to_translate
                            if full_cache_key.startswith('GoogleTranslate(') or full_cache_key.startswith('DeepL('):
                                # Extract the original text from after the timestamp closing parenthesis
                                if ')' in full_cache_key:
                                    text_part = full_cache_key.split(')', 1)[1]
                                    if text_part.startswith(':'):
                                        text_part = text_part[1:]  # Remove leading colon
                                    
                                    # Construct internal cache key
                                    # Format: google:source_lang:target_lang:text_to_translate
                                    if full_cache_key.startswith('GoogleTranslate('):
                                        service = 'google'
                                    else:  # DeepL
                                        service = 'deepl'
                                    
                                    # Extract language pair from within parentheses
                                    lang_part = full_cache_key.split('(', 1)[1].split(',', 1)[0]
                                    if '-' in lang_part:
                                        source_lang, target_lang = lang_part.split('-', 1)
                                        source_lang = source_lang.lower()
                                        target_lang = target_lang.lower()
                                        
                                        # Create internal cache key format
                                        internal_cache_key = f"{service}:{source_lang}:{target_lang}:{text_part}"
                                        self.app.google_file_cache[internal_cache_key] = translated_text
                                    else:
                                        # Handle malformed language pair
                                        self.app.google_file_cache[full_cache_key] = translated_text
                                else:
                                    # Handle malformed entries
                                    self.app.google_file_cache[full_cache_key] = translated_text
                            else:
                                # Handle old format entries directly
                                self.app.google_file_cache[full_cache_key] = translated_text
                
                log_debug(f"Loaded {len(self.app.google_file_cache)} entries from Google Translate file cache.")
        except Exception as e_lfcg: 
            log_debug(f"Error loading Google Translate file cache: {e_lfcg}")
            
        # DeepL cache
        try:
            if os.path.exists(self.app.deepl_cache_file):
                with open(self.app.deepl_cache_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#') or ':==:' not in line: 
                            continue
                        
                        # Split at the first occurrence of ':==:'
                        parts = line.split(':==:', 1)
                        if len(parts) == 2:
                            full_cache_key = parts[0]
                            translated_text = parts[1]
                            
                            # Handle the new format with timestamp
                            # DeepL(FR-PL,2025-05-13 22:43:12):text_to_translate
                            if full_cache_key.startswith('GoogleTranslate(') or full_cache_key.startswith('DeepL('):
                                # Extract the original text from after the timestamp closing parenthesis
                                if ')' in full_cache_key:
                                    text_part = full_cache_key.split(')', 1)[1]
                                    if text_part.startswith(':'):
                                        text_part = text_part[1:]  # Remove leading colon
                                    
                                    # Construct internal cache key
                                    # Format: deepl:source_lang:target_lang:text_to_translate
                                    if full_cache_key.startswith('GoogleTranslate('):
                                        service = 'google'
                                    else:  # DeepL
                                        service = 'deepl'
                                    
                                    # Extract language pair from within parentheses
                                    lang_part = full_cache_key.split('(', 1)[1].split(',', 1)[0]
                                    if '-' in lang_part:
                                        source_lang, target_lang = lang_part.split('-', 1)
                                        source_lang = source_lang.lower()
                                        target_lang = target_lang.lower()
                                        
                                        # Create internal cache key format
                                        internal_cache_key = f"{service}:{source_lang}:{target_lang}:{text_part}"
                                        self.app.deepl_file_cache[internal_cache_key] = translated_text
                                    else:
                                        # Handle malformed language pair
                                        self.app.deepl_file_cache[full_cache_key] = translated_text
                                else:
                                    # Handle malformed entries
                                    self.app.deepl_file_cache[full_cache_key] = translated_text
                            else:
                                # Handle old format entries directly
                                self.app.deepl_file_cache[full_cache_key] = translated_text
                
                log_debug(f"Loaded {len(self.app.deepl_file_cache)} entries from DeepL file cache.")
        except Exception as e_lfcd: 
            log_debug(f"Error loading DeepL file cache: {e_lfcd}")
    
    def save_to_file_cache(self, cache_type, cache_key, translated_text):
        """Saves a translation to the appropriate file cache with timestamp
        
        Args:
            cache_type: 'google' or 'deepl'
            cache_key: Unique key for the translation
            translated_text: Translated content to save
            
        Returns:
            bool: True if successfully saved, False otherwise
        """
        cache_file_path, memory_cache, enabled_tk_var = None, None, None

        if cache_type == 'google':
            cache_file_path = self.app.google_cache_file
            memory_cache = self.app.google_file_cache
            enabled_tk_var = self.app.google_file_cache_var
            service_name = "GoogleTranslate"
        elif cache_type == 'deepl':
            cache_file_path = self.app.deepl_cache_file
            memory_cache = self.app.deepl_file_cache
            enabled_tk_var = self.app.deepl_file_cache_var
            service_name = "DeepL"
        elif cache_type == 'gemini':
            cache_file_path = self.app.gemini_cache_file
            memory_cache = self.app.gemini_file_cache
            enabled_tk_var = self.app.gemini_file_cache_var
            service_name = "Gemini"
        
        if not cache_file_path or not enabled_tk_var.get():
            return False
            
        try:
            # Update in-memory cache first
            memory_cache[cache_key] = translated_text
            
            # Extract language pair from the cache key
            # Format: 'google:en:pl:text' or 'deepl:EN:PL:text'
            parts = cache_key.split(':', 3)
            if len(parts) >= 3:
                source_lang = parts[1].upper()
                target_lang = parts[2].upper()
                lang_pair = f"{source_lang}-{target_lang}"
                original_text = parts[3] if len(parts) >= 4 else cache_key
            else:
                lang_pair = "UNK-UNK"  # Unknown language pair
                original_text = cache_key
            
            # Get current timestamp
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            
            # Always check if this entry actually exists in the file
            # Don't rely on memory cache - user might have manually deleted from file
            already_in_file = False
            
            if os.path.exists(cache_file_path):
                with open(cache_file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if not line.strip() or line.startswith('#'):
                            continue
                            
                        # Look for lines with this exact original text and translation
                        if ':==:' in line:
                            line_parts = line.split(':==:', 1)
                            if len(line_parts) == 2:
                                line_key_part = line_parts[0]
                                line_translation = line_parts[1].strip()
                                
                                # Check if this is the same text and translation
                                if f"{service_name}({lang_pair}," in line_key_part and f"):{original_text}" in line_key_part:
                                    if line_translation == translated_text:
                                        already_in_file = True
                                        break
            
            # Only append to the file if not already there
            if not already_in_file:
                # Create new cache key format with timestamp
                formatted_cache_key = f"{service_name}({lang_pair},{timestamp}):{original_text}"
                
                # Append to file with formatted cache key
                with open(cache_file_path, 'a', encoding='utf-8') as f:
                    f.write(f"{formatted_cache_key}:==:{translated_text}\n")
                
                log_debug(f"Added new translation to {cache_type} file cache: {original_text}")
            else:
                log_debug(f"Translation already exists in {cache_type} file cache: {original_text}")
            
            return True
        except Exception as e_stfc:
            log_debug(f"Error saving to {cache_type} file cache: {e_stfc}")
        
        return False

    def check_file_cache(self, cache_type, cache_key):
        """Checks if a translation exists in the file cache
        
        Args:
            cache_type: 'google' or 'deepl'
            cache_key: Unique key for the translation
            
        Returns:
            str or None: The cached translation text or None if not found/disabled
        """
        memory_cache, enabled_tk_var = None, None
        if cache_type == 'google':
            memory_cache = self.app.google_file_cache
            enabled_tk_var = self.app.google_file_cache_var
        elif cache_type == 'deepl':
            memory_cache = self.app.deepl_file_cache
            enabled_tk_var = self.app.deepl_file_cache_var
        elif cache_type == 'gemini':
            memory_cache = self.app.gemini_file_cache
            enabled_tk_var = self.app.gemini_file_cache_var
        
        if memory_cache is not None and enabled_tk_var.get(): # Check if caching for this type is enabled
            return memory_cache.get(cache_key) # Return from in-memory cache
        return None
    
    def clear_file_caches(self):
        """Clears both in-memory and on-disk file caches"""
        try:
            # Clear Google Translate file cache
            self.app.google_file_cache.clear() # Clear in-memory
            if os.path.exists(self.app.google_cache_file):
                with open(self.app.google_cache_file, 'w', encoding='utf-8') as f: # Truncate file
                    f.write("# Google Translate Cache File\n")
                    f.write("# Format: GoogleTranslate(SOURCE-TARGET,TIMESTAMP):text:==:translation\n")
                    f.write("# Example: GoogleTranslate(EN-PL,2025-05-13 22:43:12):Hello world:==:Witaj świecie\n")
            
            # Clear DeepL file cache
            self.app.deepl_file_cache.clear() # Clear in-memory
            if os.path.exists(self.app.deepl_cache_file):
                with open(self.app.deepl_cache_file, 'w', encoding='utf-8') as f: # Truncate file
                    f.write("# DeepL Cache File\n")
                    f.write("# Format: DeepL(SOURCE-TARGET,TIMESTAMP):text:==:translation\n")
                    f.write("# Example: DeepL(EN-PL,2025-05-13 22:43:12):Hello world:==:Witaj świecie\n")
            
            # Clear Gemini file cache
            self.app.gemini_file_cache.clear() # Clear in-memory
            if os.path.exists(self.app.gemini_cache_file):
                with open(self.app.gemini_cache_file, 'w', encoding='utf-8') as f: # Truncate file
                    f.write("# Gemini Cache File\n")
                    f.write("# Format: Gemini(SOURCE-TARGET,TIMESTAMP):text:==:translation\n")
                    f.write("# Example: Gemini(EN-PL,2025-05-13 22:43:12):Hello world:==:Witaj świecie\n")
            
            log_debug("Cleared all translation file caches (in-memory and on disk).")
        except Exception as e_cfc: # Use distinct variable name
            log_debug(f"Error clearing file caches: {e_cfc}")
