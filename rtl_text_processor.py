#!/usr/bin/env python3
"""RTL Punctuation Fix Module - Handles proper punctuation positioning for RTL languages."""

import re
from logger import log_debug

class RTLTextProcessor:
    """Handles RTL text processing including proper punctuation positioning."""
    
    # Common punctuation marks that need repositioning in RTL text
    PUNCTUATION_MARKS = {
        '.': '.',
        ',': '،',  # Persian/Arabic comma
        '!': '!',
        '?': '؟',  # Persian/Arabic question mark
        ':': '：',
        ';': '؛',  # Persian/Arabic semicolon
        '"': '"',  # Can use different quote styles
        "'": "'",
        '(': ')',  # Parentheses swap in RTL
        ')': '(',
        '[': ']',  # Brackets swap in RTL
        ']': '[',
        '{': '}',  # Braces swap in RTL
        '}': '{'
    }
    
    @staticmethod
    def fix_rtl_punctuation(text, language_code=None):
        """
        Fix punctuation positioning for RTL languages by reversing punctuation order.
        
        Args:
            text (str): Input text that may have incorrect punctuation positioning
            language_code (str): Language code (e.g., 'fa', 'ar', 'he')
            
        Returns:
            str: Text with corrected RTL punctuation positioning
        """
        if not text or not text.strip():
            return text
            
        try:
            # Apply language-specific fixes
            if language_code and language_code.lower().startswith(('fa', 'ar', 'he')):
                # Simple approach: reverse punctuation order for RTL text
                processed_text = RTLTextProcessor._reverse_punctuation_for_rtl(text)
                
                log_debug(f"RTL punctuation fixed for {language_code}: '{text}' -> '{processed_text}'")
                return processed_text
            else:
                return text
                
        except Exception as e:
            log_debug(f"Error fixing RTL punctuation: {e}")
            return text  # Return original text if processing fails
    
    @staticmethod
    def _reverse_punctuation_for_rtl(text):
        """
        Simple punctuation reversal for RTL text.
        Remove punctuation from wrong positions and place at correct RTL positions.
        """
        import re
        
        text = text.strip()
        if not text:
            return text
        
        # Step 1: Remove punctuation from the beginning (wrong for RTL)
        collected_punctuation = []
        while text and text[0] in '.!?؟،':
            collected_punctuation.append(text[0])
            text = text[1:].strip()
        
        if not text:
            return ''.join(collected_punctuation)  # Only punctuation, return as-is
        
        # Step 2: Split into sentences and process
        # Split by sentence endings but keep the delimiters
        sentence_parts = re.split(r'([.!?؟]+)', text)
        
        # Step 3: Process sentences
        processed_sentences = []
        i = 0
        while i < len(sentence_parts):
            sentence_text = sentence_parts[i].strip()
            
            # Get the punctuation if it exists
            punctuation = ''
            if i + 1 < len(sentence_parts) and re.match(r'[.!?؟]+', sentence_parts[i + 1]):
                punctuation = sentence_parts[i + 1]
                i += 1  # Skip the punctuation part
            
            # Add the sentence with proper punctuation
            if sentence_text:
                if punctuation:
                    processed_sentences.append(sentence_text + punctuation)
                else:
                    processed_sentences.append(sentence_text)
            
            i += 1
        
        # Step 4: Join sentences and ensure final punctuation
        result = ' '.join(processed_sentences)
        
        # Step 5: If we collected punctuation from the start, add it at the end
        if collected_punctuation:
            # Use the most appropriate punctuation mark
            final_punct = collected_punctuation[0]  # Use first collected punctuation
            if not result.endswith(('.', '!', '?', '؟')):
                result += final_punct
        
        # Step 6: Ensure text ends with punctuation if it looks like complete sentences
        elif not result.endswith(('.', '!', '?', '؟')) and len(result.split()) > 2:
            result += '.'
        
        return result.strip()
    
    @staticmethod
    def prepare_rtl_for_display(text, language_code=None):
        """
        Prepare RTL text for proper display in tkinter Text widget.
        Tkinter doesn't handle bidirectional text properly, so we need to reverse RTL text.
        
        Args:
            text (str): Text that has been processed for RTL punctuation
            language_code (str): Language code (e.g., 'fa', 'ar', 'he')
            
        Returns:
            str: Text prepared for display (reversed if RTL)
        """
        if not text or not text.strip():
            return text
            
        try:
            # DEBUG: Log entry to this method
            log_debug(f"RTL prepare_rtl_for_display called with: text='{text}', lang='{language_code}'")
            
            # Only reverse for RTL languages
            if language_code and language_code.lower().startswith(('fa', 'ar', 'he')):
                log_debug(f"RTL language detected: {language_code} - applying RTL processing")
                
                # Simple character-level reversal for RTL display
                # This fixes the tkinter BiDi display issue
                reversed_text = RTLTextProcessor._reverse_text_for_display(text)
                log_debug(f"RTL text reversed: '{text}' -> '{reversed_text}'")
                
                # Apply final punctuation fix before display
                final_text = RTLTextProcessor._fix_final_punctuation_position(reversed_text)
                
                log_debug(f"RTL text prepared for display ({language_code}): reversed for proper tkinter rendering")
                if final_text != reversed_text:
                    log_debug(f"PUNCTUATION FIX APPLIED: '{reversed_text}' -> '{final_text}'")
                else:
                    log_debug(f"No punctuation fix needed - conditions not met")
                
                log_debug(f"RTL final result: '{final_text}'")
                return final_text
            else:
                log_debug(f"Non-RTL language or no language code: {language_code} - no RTL processing")
                return text
                
        except Exception as e:
            log_debug(f"Error preparing RTL text for display: {e}")
            return text  # Return original text if processing fails
    
    @staticmethod
    def _reverse_text_for_display(text):
        """
        Prepare RTL text for proper display in tkinter. 
        
        SIMPLIFIED: For RTL languages, we don't need to reverse words within sentences.
        Modern tkinter with proper right-alignment handles RTL text correctly.
        We only need to apply the punctuation fix.
        """
        if not text:
            return ""

        # For RTL text, just add the Right-to-Left Mark (RLM) to ensure proper directionality
        # The tkinter Text widget with right alignment will handle the rest
        return text + '\u200F'

    @staticmethod
    def _fix_final_punctuation_position(text):
        """
        Fix final punctuation positioning for RTL display.
        
        UPDATED: Now works with original RTL text (not reversed text) since we're using
        proper tkinter right-alignment instead of text reversal.
        
        Args:
            text (str): RTL text with RLM marker
            
        Returns:
            str: Text with corrected final punctuation positioning if needed
        """
        log_debug(f"_fix_final_punctuation_position called with: '{text}'")
        
        if not text or len(text) < 2:
            log_debug(f"Skipping punctuation fix - text too short or empty")
            return text
            
        # For RTL text with proper right-alignment, the punctuation fix may not be needed
        # Let's check if there are any specific issues that need fixing
        
        # Remove RLM character for analysis
        working_text = text.replace('\u200F', '') if '\u200F' in text else text
        
        if not working_text:
            return text
            
        log_debug(f"Working with text (RLM removed): '{working_text}'")
        
        # With proper RTL display and right-alignment, punctuation should be positioned correctly
        # Return the original text with RLM
        log_debug(f"Using original RTL text with proper alignment - no punctuation repositioning needed")
        return text

    @staticmethod
    def is_rtl_text_likely_incorrect(text):
        """
        Detect if RTL text likely has punctuation positioning issues.
        
        Args:
            text (str): Text to analyze
            
        Returns:
            bool: True if punctuation positioning looks incorrect for RTL
        """
        if not text or len(text) < 2:
            return False
            
        text = text.strip()
        
        # Check for common indicators of incorrect RTL punctuation
        indicators = [
            text.startswith('.'),  # Period at beginning (should be at end for RTL)
            text.startswith('!'),  # Exclamation at beginning
            text.startswith('?'),  # Question mark at beginning
            text.startswith(')') and not text.endswith('('),  # Incorrect parentheses
        ]
        
        return any(indicators)