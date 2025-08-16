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
            # Only reverse for RTL languages
            if language_code and language_code.lower().startswith(('fa', 'ar', 'he')):
                # Simple character-level reversal for RTL display
                # This fixes the tkinter BiDi display issue
                reversed_text = RTLTextProcessor._reverse_text_for_display(text)
                log_debug(f"RTL text prepared for display ({language_code}): reversed for proper tkinter rendering")
                return reversed_text
            else:
                return text
                
        except Exception as e:
            log_debug(f"Error preparing RTL text for display: {e}")
            return text  # Return original text if processing fails
    
    @staticmethod
    def _reverse_text_for_display(text):
        """
        Reverse RTL text for proper display in tkinter. This compensates for tkinter's lack of proper BiDi support.
        
        FIXED: This implementation correctly handles multi-line text (from Gemini's <br>),
        and adds a Right-to-Left Mark (RLM) at the end to prevent the final punctuation
        from wrapping around to the start of the text block in the display.
        """
        if not text:
            return ""

        # Handle multi-line text from Gemini API which may use <br>
        lines = re.split(r'\s*<br>\s*', text)
        processed_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Split the line by punctuation, keeping delimiters. This correctly handles
            # sentences with and without trailing punctuation.
            parts = re.split(r'([.!?؟،؛])', line)
            parts = [p for p in parts if p]  # Remove any empty strings

            # Group text parts with their following punctuation to form sentence chunks
            sentence_chunks = []
            i = 0
            while i < len(parts):
                text_part = parts[i]
                punct_part = ""
                # Check if the next part is a punctuation mark
                if i + 1 < len(parts) and parts[i+1] in ".!?؟،؛":
                    punct_part = parts[i+1]
                    i += 1  # Consume the punctuation part as well
                
                # Reverse the order of words within the text part
                reversed_words = ' '.join(text_part.strip().split()[::-1])
                
                # Re-attach the punctuation to the end of the reversed word string.
                # Visually, this places it at the left of the text chunk in an RTL context.
                sentence_chunks.append(reversed_words + punct_part)
                i += 1
            
            # Reverse the order of the sentence chunks themselves for RTL display
            processed_lines.append(' '.join(sentence_chunks[::-1]))

        # Reverse the order of the processed lines for multi-line RTL display
        final_text = '\n'.join(processed_lines[::-1])
        
        # CRITICAL FIX: Append the Unicode Right-to-Left Mark (RLM).
        # This is an invisible character that provides a "strong" RTL context,
        # preventing the very last punctuation mark of the entire text block
        # from being incorrectly moved to the beginning (far right) by the renderer.
        return final_text + '\u200F'

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