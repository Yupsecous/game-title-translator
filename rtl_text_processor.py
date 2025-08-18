#!/usr/bin/env python3
"""Enhanced RTL Text Processor with Python BiDi Integration - Handles proper RTL text display in tkinter."""

import re
import tkinter as tk

# Simple fallback logger if a dedicated logger module is not available.
# This makes the script self-contained and runnable without extra setup.
def log_debug(message):
    """Prints a debug message. Can be replaced with a more robust logger."""
    # To enable logging for debugging, uncomment the following line:
    # print(f"DEBUG: {message}")
    pass

# Import BiDi libraries for proper RTL text processing
try:
    from bidi.algorithm import get_display
    import arabic_reshaper
    BIDI_AVAILABLE = True
    log_debug("Python BiDi and Arabic Reshaper libraries imported successfully")
except ImportError as e:
    BIDI_AVAILABLE = False
    log_debug(f"BiDi libraries not available: {e}. RTL processing will use a fallback method.")

class RTLTextProcessor:
    """Enhanced RTL text processing with proper Python BiDi integration for tkinter display."""

    # Set of RTL language codes that need BiDi processing
    RTL_LANGUAGES = {'ar', 'he', 'fa', 'ur', 'ps', 'ku', 'sd', 'yi'}

    @staticmethod
    def process_bidi_text(text, language_code=None):
        """
        Process text using the Unicode Bidirectional Algorithm for proper RTL display in tkinter.

        CRITICAL FIX: Process each line separately to avoid incorrect line reordering.
        The BiDi algorithm should only reorder characters *within* each line, not reorder the lines themselves.
        This is the key to fixing the issue where widget text-wrapping reverses the line order.

        Args:
            text (str): Input text in logical order (may be multi-line).
            language_code (str): Language code (e.g., 'fa', 'ar', 'he').

        Returns:
            str: Text processed for correct visual display in LTR contexts like tkinter.
        """
        if not text or not text.strip():
            return text

        if not BIDI_AVAILABLE:
            log_debug("BiDi libraries not available, using fallback processing.")
            return RTLTextProcessor._fallback_rtl_processing(text, language_code)

        try:
            # Only process if the language is identified as RTL
            if not RTLTextProcessor._is_rtl_language(language_code):
                log_debug(f"Language '{language_code}' is not RTL, returning original text.")
                return text

            log_debug(f"Processing BiDi text for {language_code}: '{text[:70]}...'")

            # --- CRITICAL FIX IMPLEMENTATION ---
            # 1. Split the text into lines based on the newline character. This is essential
            #    because the BiDi algorithm, when applied to a whole paragraph, can
            #    reorder the lines themselves, leading to incorrect visual output.
            lines = text.split('\n')
            processed_lines = []

            # 2. Process each line individually. This preserves the vertical order of lines.
            for line in lines:
                if not line.strip():
                    # Preserve empty lines as they are
                    processed_lines.append(line)
                    continue

                log_debug(f"Processing line: '{line}'")

                # Step 2a: Reshape Arabic/Persian text to connect letters properly.
                # This must be done before the BiDi algorithm is applied.
                reshaped_line = arabic_reshaper.reshape(line)
                log_debug(f"After reshaping: '{reshaped_line}'")

                # Step 2b: Apply the BiDi algorithm to this *single line*.
                # This reorders characters within the line for correct LTR display.
                bidi_line = get_display(reshaped_line)
                log_debug(f"After BiDi processing: '{bidi_line}'")

                processed_lines.append(bidi_line)

            # 3. Reassemble the processed lines in their original order, joined by newlines.
            result = '\n'.join(processed_lines)
            log_debug(f"Final BiDi result: '{result[:70]}...'")

            return result

        except Exception as e:
            log_debug(f"Error in BiDi text processing: {e}. Falling back to basic processing.")
            return RTLTextProcessor._fallback_rtl_processing(text, language_code)

    @staticmethod
    def _is_rtl_language(language_code):
        """Enhanced check if the given language code or name represents an RTL language."""
        if not language_code:
            return False
        
        # Convert to lowercase for consistent checking
        lang_lower = language_code.lower()
        
        # Extract the primary language code (e.g., 'fa' from 'fa-IR')
        primary_code = lang_lower.split('-')[0]
        
        # Check against RTL language codes
        if primary_code in RTLTextProcessor.RTL_LANGUAGES:
            return True
            
        # Also check against common RTL language display names
        rtl_display_names = {
            'hebrew', 'arabic', 'persian', 'farsi', 'urdu', 
            'pashto', 'kurdish', 'sindhi', 'yiddish'
        }
        
        return lang_lower in rtl_display_names

    @staticmethod
    def _fallback_rtl_processing(text, language_code):
        """
        Fallback RTL processing when BiDi libraries are not available.
        Uses a simplified approach for basic RTL display.
        """
        if not RTLTextProcessor._is_rtl_language(language_code):
            return text
        log_debug(f"Using fallback RTL processing for {language_code}.")
        return RTLTextProcessor._basic_punctuation_fix(text)

    @staticmethod
    def _basic_punctuation_fix(text):
        """Basic punctuation repositioning for RTL text when BiDi is not available."""
        if not text or not text.strip():
            return text
        text = text.strip()
        # Move punctuation from the beginning to the end
        leading_punct = []
        while text and text[0] in '.!?؟،':
            leading_punct.append(text[0])
            text = text[1:].strip()
        if not text:
            return ''.join(leading_punct)
        if leading_punct and not text.endswith(('.', '!', '?', '؟')):
            text += leading_punct[0]
        return text

    @staticmethod
    def prepare_for_tkinter_display(text, language_code=None):
        """
        Prepares text for display in tkinter widgets with proper RTL handling.
        This is the main public method to be called before setting text in a widget.

        Args:
            text (str): Text to prepare for display.
            language_code (str): Language code for RTL detection.

        Returns:
            tuple: (processed_text, is_rtl) where is_rtl indicates if RTL formatting should be applied.
        """
        if not text or not text.strip():
            return text, False

        is_rtl = RTLTextProcessor._is_rtl_language(language_code)

        if is_rtl:
            log_debug(f"Preparing RTL text for tkinter display: '{text[:70]}...'")
            processed_text = RTLTextProcessor.process_bidi_text(text, language_code)
            log_debug(f"RTL text processed for display: '{processed_text[:70]}...'")
            return processed_text, True
        else:
            return text, False

    @staticmethod
    def configure_tkinter_widget_for_rtl(widget, is_rtl=True):
        """
        Configures a tkinter Text or Label widget for proper RTL display.
        This ensures the text is right-aligned.

        Args:
            widget: The tkinter widget to configure (e.g., tk.Text, tk.Label).
            is_rtl (bool): Whether to configure for RTL or LTR display.
        """
        try:
            if is_rtl:
                # For Text widgets, use tags for flexible, per-line alignment.
                if isinstance(widget, tk.Text):
                    widget.tag_configure("rtl", justify='right')
                    widget.tag_add("rtl", "1.0", "end")
                # For simpler widgets like Label, configure justification directly.
                else:
                    widget.configure(justify='right')
                log_debug(f"Widget '{widget.winfo_class()}' configured for RTL (right-aligned).")
            else:
                if isinstance(widget, tk.Text):
                    widget.tag_configure("ltr", justify='left')
                    widget.tag_add("ltr", "1.0", "end")
                else:
                    widget.configure(justify='left')
                log_debug(f"Widget '{widget.winfo_class()}' configured for LTR (left-aligned).")
        except Exception as e:
            log_debug(f"Error configuring widget for RTL/LTR: {e}")

    # Legacy methods provided for backward compatibility
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
        Heuristically detects if RTL text likely has positioning issues (e.g., punctuation at the start).

        Args:
            text (str): Text to analyze.

        Returns:
            bool: True if text positioning looks incorrect for RTL.
        """
        if not text or len(text) < 2:
            return False
        text = text.strip()
        # Check for common indicators of incorrect RTL rendering
        indicators = [
            text.startswith('.') and not text.endswith('.'),
            text.startswith('!') and not text.endswith('!'),
            text.startswith('?') and not text.endswith('?'),
            text.startswith(')') and not text.endswith('('),
        ]
        return any(indicators)

    @staticmethod
    def get_bidi_info():
        """Returns a dictionary with information about BiDi processing capabilities."""
        return {
            'bidi_available': BIDI_AVAILABLE,
            'supported_languages': sorted(list(RTLTextProcessor.RTL_LANGUAGES)),
            'processing_method': 'python-bidi' if BIDI_AVAILABLE else 'fallback'
        }