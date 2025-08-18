#!/usr/bin/env python3
"""Enhanced RTL Text Processor with Python BiDi Integration - Handles proper RTL text display in tkinter."""

import re
from logger import log_debug

# Import BiDi libraries for proper RTL text processing
try:
    from bidi.algorithm import get_display
    import arabic_reshaper
    BIDI_AVAILABLE = True
    log_debug("Python BiDi and Arabic Reshaper libraries imported successfully")
except ImportError as e:
    BIDI_AVAILABLE = False
    log_debug(f"BiDi libraries not available: {e}")

class RTLTextProcessor:
    """Enhanced RTL text processing with proper Python BiDi integration for tkinter display."""
    
    # RTL language codes that need BiDi processing
    RTL_LANGUAGES = {'ar', 'he', 'fa', 'ur', 'ps', 'ku', 'sd', 'yi'}
    
    @staticmethod
    def process_bidi_text(text, language_code=None):
        """
        Process text using the Unicode Bidirectional Algorithm for proper RTL display in tkinter.
        
        CRITICAL FIX: Process each line separately to avoid incorrect line reordering.
        The BiDi algorithm should only reorder characters within lines, not reorder lines themselves.
        
        Args:
            text (str): Input text in logical order (may be multi-line)
            language_code (str): Language code (e.g., 'fa', 'ar', 'he')
            
        Returns:
            str: Text processed for correct visual display in LTR contexts like tkinter
        """
        if not text or not text.strip():
            return text
            
        if not BIDI_AVAILABLE:
            log_debug("BiDi libraries not available, using fallback processing")
            return RTLTextProcessor._fallback_rtl_processing(text, language_code)
            
        try:
            # Only process if language is RTL
            if not RTLTextProcessor._is_rtl_language(language_code):
                log_debug(f"Language {language_code} is not RTL, returning original text")
                return text
                
            log_debug(f"Processing BiDi text for {language_code}: '{text}'")
            
            # CRITICAL FIX: Process each line separately to preserve line order
            lines = text.split('\n')
            processed_lines = []
            
            for line in lines:
                if not line.strip():
                    # Preserve empty lines
                    processed_lines.append(line)
                    continue
                    
                log_debug(f"Processing line: '{line}'")
                
                # Step 1: Reshape Arabic/Persian text (connects letters properly)
                reshaped_line = arabic_reshaper.reshape(line)
                log_debug(f"After reshaping: '{reshaped_line}'")
                
                # Step 2: Apply the BiDi algorithm to this line only
                bidi_line = get_display(reshaped_line)
                log_debug(f"After BiDi processing: '{bidi_line}'")
                
                processed_lines.append(bidi_line)
            
            # Reassemble lines in their original order
            result = '\n'.join(processed_lines)
            log_debug(f"Final BiDi result: '{result}'")
            
            return result
            
        except Exception as e:
            log_debug(f"Error in BiDi text processing: {e}")
            return RTLTextProcessor._fallback_rtl_processing(text, language_code)
    
    @staticmethod
    def _is_rtl_language(language_code):
        """Check if the given language code represents an RTL language."""
        if not language_code:
            return False
        
        # Extract the primary language code (e.g., 'fa' from 'fa-IR')
        primary_code = language_code.lower().split('-')[0]
        return primary_code in RTLTextProcessor.RTL_LANGUAGES
    
    @staticmethod
    def _fallback_rtl_processing(text, language_code):
        """
        Fallback RTL processing when BiDi libraries are not available.
        Uses simplified approach for basic RTL display.
        """
        if not RTLTextProcessor._is_rtl_language(language_code):
            return text
            
        log_debug(f"Using fallback RTL processing for {language_code}")
        
        # Simple punctuation fix for RTL languages
        return RTLTextProcessor._basic_punctuation_fix(text)
    
    @staticmethod
    def _basic_punctuation_fix(text):
        """Basic punctuation repositioning for RTL text when BiDi is not available."""
        if not text or not text.strip():
            return text
            
        text = text.strip()
        
        # Remove punctuation from wrong positions (beginning)
        leading_punct = []
        while text and text[0] in '.!?؟،':
            leading_punct.append(text[0])
            text = text[1:].strip()
        
        if not text:
            return ''.join(leading_punct)
        
        # Add punctuation at the end if we had leading punctuation
        if leading_punct and not text.endswith(('.', '!', '?', '؟')):
            text += leading_punct[0]
        
        return text
    
    @staticmethod
    def prepare_for_tkinter_display(text, language_code=None):
        """
        Prepare text for display in tkinter widgets with proper RTL handling.
        
        This method should be called just before setting text in tkinter widgets
        to ensure proper display regardless of text direction.
        
        Args:
            text (str): Text to prepare for display
            language_code (str): Language code for RTL detection
            
        Returns:
            tuple: (processed_text, is_rtl) where is_rtl indicates if RTL formatting should be applied
        """
        if not text or not text.strip():
            return text, False
            
        is_rtl = RTLTextProcessor._is_rtl_language(language_code)
        
        if is_rtl:
            log_debug(f"Preparing RTL text for tkinter display: '{text}'")
            processed_text = RTLTextProcessor.process_bidi_text(text, language_code)
            log_debug(f"RTL text processed for display: '{processed_text}'")
            return processed_text, True
        else:
            return text, False
    
    @staticmethod
    def configure_tkinter_widget_for_rtl(widget, is_rtl=True):
        """
        Configure a tkinter Text widget for proper RTL display.
        
        Args:
            widget: tkinter Text widget to configure
            is_rtl (bool): Whether to configure for RTL display
        """
        try:
            if is_rtl:
                # Configure RTL display properties
                widget.configure(justify='right')
                
                # Set RTL tag for all text
                widget.tag_configure("rtl", justify='right')
                widget.tag_add("rtl", "1.0", "end")
                
                # Mark widget as RTL configured
                widget.is_rtl = True
                log_debug("Widget configured for RTL display")
            else:
                # Configure LTR display properties
                widget.configure(justify='left')
                
                # Set LTR tag for all text
                widget.tag_configure("ltr", justify='left')
                widget.tag_add("ltr", "1.0", "end")
                
                # Mark widget as LTR configured
                widget.is_rtl = False
                log_debug("Widget configured for LTR display")
                
        except Exception as e:
            log_debug(f"Error configuring widget for RTL/LTR: {e}")
    
    # Legacy methods for backward compatibility
    @staticmethod
    def fix_rtl_punctuation(text, language_code=None):
        """Legacy method - redirects to process_bidi_text for consistency."""
        return RTLTextProcessor.process_bidi_text(text, language_code)
    
    @staticmethod
    def prepare_rtl_for_display(text, language_code=None):
        """Legacy method - redirects to prepare_for_tkinter_display."""
        processed_text, _ = RTLTextProcessor.prepare_for_tkinter_display(text, language_code)
        return processed_text
    
    @staticmethod
    def is_rtl_text_likely_incorrect(text):
        """
        Detect if RTL text likely has positioning issues.
        
        Args:
            text (str): Text to analyze
            
        Returns:
            bool: True if text positioning looks incorrect for RTL
        """
        if not text or len(text) < 2:
            return False
            
        text = text.strip()
        
        # Check for indicators of incorrect RTL text positioning
        indicators = [
            text.startswith('.') and not text.endswith('.'),  # Period at beginning only
            text.startswith('!') and not text.endswith('!'),  # Exclamation at beginning only
            text.startswith('?') and not text.endswith('?'),  # Question mark at beginning only
            text.startswith(')') and not text.endswith('('),  # Incorrect parentheses
        ]
        
        return any(indicators)
    
    @staticmethod
    def get_bidi_info():
        """Get information about BiDi processing capabilities."""
        return {
            'bidi_available': BIDI_AVAILABLE,
            'supported_languages': list(RTLTextProcessor.RTL_LANGUAGES),
            'processing_method': 'python-bidi' if BIDI_AVAILABLE else 'fallback'
        }
