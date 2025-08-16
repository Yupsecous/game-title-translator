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
        Fix punctuation positioning for RTL languages.
        
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
                # Fix common RTL punctuation issues
                processed_text = RTLTextProcessor._fix_sentence_punctuation(text)
                processed_text = RTLTextProcessor._fix_parentheses_brackets(processed_text)
                processed_text = RTLTextProcessor._apply_rtl_comma(processed_text, language_code)
                
                log_debug(f"RTL punctuation fixed for {language_code}: '{text}' -> '{processed_text}'")
                return processed_text
            else:
                return text
                
        except Exception as e:
            log_debug(f"Error fixing RTL punctuation: {e}")
            return text  # Return original text if processing fails
    
    @staticmethod
    def _fix_sentence_punctuation(text):
        """Fix sentence-ending punctuation positioning for RTL."""
        # This handles the main issue: periods at the beginning instead of end
        
        # Pattern: Look for punctuation at the start followed by RTL text
        # In RTL, sentence punctuation should be at the visual END (left side)
        
        # For now, let's use a simple approach: ensure punctuation is at the actual end
        text = text.strip()
        
        # Check if text starts with punctuation (incorrect for RTL)
        if text and text[0] in '.!?':
            # Move the punctuation to the end
            punct = text[0]
            rest_text = text[1:].strip()
            
            # Check if there's already punctuation at the end
            if rest_text and rest_text[-1] not in '.!?':
                return rest_text + punct
            else:
                return rest_text  # Already has end punctuation
        
        return text
    
    @staticmethod
    def _fix_parentheses_brackets(text):
        """Fix parentheses and brackets for RTL text direction."""
        # In RTL, parentheses and brackets should be mirrored
        # However, this depends on the context and might be complex
        # For now, we'll keep this simple and only fix if obviously wrong
        
        # Simple fix: if text starts with closing bracket/paren, it might need swapping
        text = text.strip()
        
        bracket_map = {')': '(', ']': '[', '}': '{', '(': ')', '[': ']', '{': '}'}
        
        # Only apply if the text looks like it has incorrectly positioned brackets
        if len(text) > 2:
            if text[0] in ')]}' and text[-1] in '([{':
                # Likely incorrect bracket positioning
                start_char = bracket_map.get(text[0], text[0])
                end_char = bracket_map.get(text[-1], text[-1])
                middle_text = text[1:-1]
                return start_char + middle_text + end_char
        
        return text
    
    @staticmethod
    def _apply_rtl_comma(text, language_code):
        """Apply language-specific comma characters."""
        if language_code.lower().startswith(('fa', 'ar')):
            # Replace regular comma with Persian/Arabic comma
            text = text.replace(',', '،')
        
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

def test_rtl_punctuation_fix():
    """Test the RTL punctuation fix functionality."""
    test_cases = [
        # (input, language, expected_improvement)
        (".حداقل بیست نفر اونجا هستن", "fa", "should move period to end"),
        ("!سلام", "fa", "should move exclamation to end"),
        ("مرحبا، کیف حالک؟", "ar", "should use Arabic comma"),
        ("Hello, world!", "en", "should not change"),
        (")معکوس قوس(", "fa", "should fix parentheses"),
    ]
    
    processor = RTLTextProcessor()
    
    print("RTL Punctuation Fix Test Results:")
    print("-" * 50)
    
    for i, (input_text, lang, description) in enumerate(test_cases, 1):
        result = processor.fix_rtl_punctuation(input_text, lang)
        changed = "CHANGED" if result != input_text else "UNCHANGED"
        
        print(f"Test {i}: {description}")
        print(f"  Input:  '{input_text}'")
        print(f"  Output: '{result}' [{changed}]")
        print(f"  Lang:   {lang}")
        print()

if __name__ == "__main__":
    test_rtl_punctuation_fix()
