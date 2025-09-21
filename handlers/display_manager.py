import tkinter as tk
from tkinter import font
import time
import cv2
import numpy as np
from PIL import Image, ImageTk
from logger import log_debug

# RTL Text Processing Architecture:
# 1. PRIMARY: PySide overlay with Qt's native RTL support (optimal for all RTL languages)
# 2. FALLBACK: tkinter with rtl_text_processor.py using python-bidi (legacy compatibility)
# Both systems share RTL language detection for consistency

# Import RTL text processor for tkinter fallback and shared utilities
try:
    from rtl_text_processor import RTLTextProcessor
    RTL_PROCESSOR_AVAILABLE = True
    log_debug("RTL text processor imported successfully")
except ImportError as e:
    RTL_PROCESSOR_AVAILABLE = False
    log_debug(f"RTL text processor not available: {e}")

class DisplayManager:
    """Handles display and UI updates for overlays and debug information"""
    
    def __init__(self, app):
        """Initialize with a reference to the main application
        
        Args:
            app: The main GameChangingTranslator application instance
        """
        self.app = app
        self.last_widget_width = 0
        self.current_logical_text = ""
        self.current_language_code = None
    
    def update_translation_text(self, text_to_display):
        """Updates the translation text overlay with new content
        
        Args:
            text_to_display: Text content to display in the overlay
        """
        # Check if the target overlay and text widget references are valid
        if not self.app.target_overlay or not hasattr(self.app.target_overlay, 'winfo_exists') or not self.app.target_overlay.winfo_exists() or \
           not self.app.translation_text or not hasattr(self.app.translation_text, 'winfo_exists') or not self.app.translation_text.winfo_exists():
            # log_debug("Update translation skipped: Target overlay or text widget invalid/destroyed.") # Can be verbose
            return
            
        # Schedule the actual update via the main thread's event loop
        self.app.root.after(0, self._update_translation_text_on_main_thread, text_to_display)

    def manually_wrap_and_process_rtl(self, widget, logical_text, language_code, retry_count=0):
        """
        Enhanced manual text wrapping with better accuracy and edge case handling.
        
        This prevents tkinter's automatic wrapping from interfering with RTL text display.
        """
        try:
            # 1. Ensure widget is properly rendered and get accurate measurements
            widget.update_idletasks()  # Force widget to complete any pending layout updates
            
            widget_width = widget.winfo_width()
            widget_height = widget.winfo_height()
            
            # Dynamic padding calculation based on widget configuration
            try:
                # Get actual padding values from widget
                padx = widget.cget('padx') or 0
                pady = widget.cget('pady') or 0
                relief = widget.cget('relief')
                bd = widget.cget('bd') or 0
                
                # Calculate total horizontal padding
                horizontal_padding = (padx * 2) + (bd * 2)
                if relief != 'flat':
                    horizontal_padding += 4  # Additional space for relief styles
                    
                log_debug(f"DisplayManager: Calculated padding: {horizontal_padding} (padx={padx}, bd={bd}, relief={relief})")
            except:
                # Fallback to conservative estimate
                horizontal_padding = 12
                log_debug(f"DisplayManager: Using fallback padding: {horizontal_padding}")
            
            # Check if widget is ready for processing
            if widget_width <= horizontal_padding or widget_height <= 10:
                if retry_count < 3:
                    log_debug(f"DisplayManager: Widget not ready (w={widget_width}, h={widget_height}), retrying in 50ms (attempt {retry_count + 1})")
                    # Retry after a short delay to allow widget to finish rendering
                    widget.after(50, lambda: self.manually_wrap_and_process_rtl(widget, logical_text, language_code, retry_count + 1))
                    return
                else:
                    log_debug(f"DisplayManager: Widget still not ready after 3 retries, using fallback processing")
                    # Fall back to standard processing if widget never becomes ready
                    self._apply_fallback_rtl_processing(widget, logical_text, language_code)
                    return

            effective_width = widget_width - horizontal_padding
            log_debug(f"DisplayManager: Effective width for wrapping: {effective_width} (widget={widget_width}, padding={horizontal_padding})")

            # 2. Get accurate font information
            try:
                # Try to get the actual font from the widget
                widget_font_spec = widget.cget("font")
                if isinstance(widget_font_spec, tuple):
                    # Font specified as tuple (family, size, style)
                    widget_font = font.Font(family=widget_font_spec[0], size=widget_font_spec[1])
                elif isinstance(widget_font_spec, str):
                    # Font specified as string
                    widget_font = font.Font(font=widget_font_spec)
                else:
                    # Named font or default
                    widget_font = font.Font(font=widget_font_spec)
                    
                # Test font measurement to ensure it's working
                test_width = widget_font.measure("Test")
                if test_width <= 0:
                    raise Exception("Font measurement returned invalid width")
                    
                log_debug(f"DisplayManager: Using widget font: {widget_font['family']} {widget_font['size']}")
            except Exception as e:
                log_debug(f"DisplayManager: Font detection failed ({e}), using fallback")
                # More accurate fallback based on typical Text widget defaults
                widget_font = font.Font(family="Arial", size=12)

            # 3. Split logical text into words and manually wrap
            words = logical_text.split()
            if not words:
                return

            wrapped_lines = []
            current_line = ""
            
            for word in words:
                # Test if adding this word would exceed the width
                test_line = current_line + " " + word if current_line else word
                test_width = widget_font.measure(test_line)
                
                if test_width <= effective_width:
                    current_line = test_line
                else:
                    # Line would be too long, start a new line
                    if current_line:  # Only add non-empty lines
                        wrapped_lines.append(current_line)
                    
                    # Check if single word exceeds width (very long word)
                    word_width = widget_font.measure(word)
                    if word_width > effective_width:
                        # Word is too long for any line, but include it anyway
                        # This prevents infinite loops with very long words
                        wrapped_lines.append(word)
                        current_line = ""
                    else:
                        current_line = word
            
            # Add the final line
            if current_line:
                wrapped_lines.append(current_line)

            log_debug(f"DisplayManager: Wrapped {len(words)} words into {len(wrapped_lines)} lines")

            # 4. Apply BiDi processing to each wrapped line
            processed_lines = []
            for line in wrapped_lines:
                processed_line = RTLTextProcessor.process_bidi_text(line, language_code)
                processed_lines.append(processed_line)

            # 5. Update widget with processed text
            final_text = "\n".join(processed_lines)
            
            widget.config(state=tk.NORMAL)
            widget.delete("1.0", tk.END)
            widget.insert("1.0", final_text)
            
            # Configure for RTL display
            RTLTextProcessor.configure_tkinter_widget_for_rtl(widget, is_rtl=True)
            widget.config(state=tk.DISABLED)
            
            log_debug(f"DisplayManager: Successfully applied manual RTL wrapping")

        except Exception as e:
            log_debug(f"DisplayManager: Error in manual RTL wrapping: {e}")
            # Fall back to basic processing
            self._apply_fallback_rtl_processing(widget, logical_text, language_code)

    def _apply_fallback_rtl_processing(self, widget, logical_text, language_code):
        """Fallback RTL processing when manual wrapping fails."""
        try:
            processed_text = RTLTextProcessor.process_bidi_text(logical_text, language_code)
            
            widget.config(state=tk.NORMAL)
            widget.delete("1.0", tk.END)
            widget.insert("1.0", processed_text)
            RTLTextProcessor.configure_tkinter_widget_for_rtl(widget, is_rtl=True)
            widget.config(state=tk.DISABLED)
            
            log_debug(f"DisplayManager: Applied fallback RTL processing")
        except Exception as e:
            log_debug(f"DisplayManager: Fallback RTL processing failed: {e}")

    def on_translation_widget_resize(self, event):
        """Enhanced callback to re-process RTL text when the widget is resized."""
        if (event.widget == self.app.translation_text and 
            event.widget.winfo_width() != self.last_widget_width and
            self.current_logical_text and 
            self.current_language_code):
            
            # Small delay to ensure resize is complete before re-processing
            event.widget.after(10, self._delayed_resize_handler)

    def _delayed_resize_handler(self):
        """Delayed resize handler to ensure widget is stable before processing."""
        new_width = self.app.translation_text.winfo_width()
        if new_width != self.last_widget_width:
            self.last_widget_width = new_width
            log_debug(f"DisplayManager: Widget resized to width {new_width}, re-processing RTL text")
            
            # Re-run the manual wrapping with improved accuracy
            if RTL_PROCESSOR_AVAILABLE and RTLTextProcessor._is_rtl_language(self.current_language_code):
                self.manually_wrap_and_process_rtl(
                    self.app.translation_text, 
                    self.current_logical_text, 
                    self.current_language_code,
                    retry_count=0  # Reset retry count for resize events
                )

    def _update_translation_text_on_main_thread(self, text_content_main_thread):
        """Updates the translation text widget on the main thread with proper BiDi support
        
        Args:
            text_content_main_thread: Text content to display
        """
        if not self.app.target_overlay or not self.app.target_overlay.winfo_exists() or \
           not self.app.translation_text:
            return

        try:
            if self.app.is_running:
                if not self.app.target_overlay.winfo_viewable():
                    self.app.target_overlay.show() 
                else:
                    if hasattr(self.app.target_overlay, 'attributes'):
                        self.app.target_overlay.attributes("-topmost", True)
                    else:
                        self.app.target_overlay.raise_()

            new_text_to_display = text_content_main_thread.strip() if text_content_main_thread else ""
            log_debug(f"DisplayManager: Processing text for display: '{new_text_to_display}'")

            # Convert <br> tags to newlines for display
            new_text_to_display = new_text_to_display.replace('<br>', '\n')

            # --- FIX: Directly use the target language code from the correct variable ---
            target_lang_code = self.app.target_lang_var.get()
            log_debug(f"DisplayManager: Target language code is '{target_lang_code}'")

            # Store current text and language for resize handling
            self.current_logical_text = new_text_to_display
            self.current_language_code = target_lang_code
            
            if hasattr(self.app.translation_text, 'set_rtl_text'):
                # PySide text widget
                log_debug(f"DisplayManager: Using PySide RTL text display for language: {target_lang_code}")
                text_color = self.app.target_text_colour_var.get()
                font_size = self.app.target_font_size_var.get()
                font_type = self.app.target_font_type_var.get()
                bg_color = self.app.target_colour_var.get()
                
                self.app.translation_text.set_rtl_text(
                    new_text_to_display, 
                    target_lang_code, 
                    bg_color, 
                    text_color, 
                    font_size
                )
                self.app.translation_text.configure(font=(font_type, font_size))
            else:
                # Fallback to tkinter handling
                log_debug(f"DisplayManager: Using tkinter text widget with RTL processor (fallback)")
                is_rtl = RTL_PROCESSOR_AVAILABLE and RTLTextProcessor._is_rtl_language(target_lang_code)
                
                if is_rtl and new_text_to_display:
                    log_debug(f"DisplayManager: Using manual wrapping for RTL text - Language: {target_lang_code}")
                    if not hasattr(self.app.translation_text, '_rtl_processed_once'):
                        self.app.translation_text._rtl_processed_once = True
                        log_debug(f"DisplayManager: First-time RTL processing with delay for language: {target_lang_code}")
                        self.app.root.after(100, lambda: self.manually_wrap_and_process_rtl(
                            self.app.translation_text, new_text_to_display, target_lang_code, retry_count=0))
                    else:
                        log_debug(f"DisplayManager: Subsequent RTL processing for language: {target_lang_code}")
                        self.manually_wrap_and_process_rtl(self.app.translation_text, new_text_to_display, target_lang_code)
                else:
                    log_debug(f"DisplayManager: Using standard processing for LTR text")
                    self.app.translation_text.config(state=tk.NORMAL) 
                    self.app.translation_text.delete(1.0, tk.END)     
                    self.app.translation_text.insert(tk.END, new_text_to_display)
                    
                    if RTL_PROCESSOR_AVAILABLE:
                        RTLTextProcessor.configure_tkinter_widget_for_rtl(self.app.translation_text, False)
                    else:
                        self.app.translation_text.tag_configure("ltr", justify='left')
                        self.app.translation_text.tag_add("ltr", "1.0", "end")
                    
                    self.app.translation_text.config(state=tk.DISABLED)
                
                if hasattr(self.app.translation_text, 'see'):
                    self.app.translation_text.see("1.0")
                
        except tk.TclError as e_uttomt: 
            log_debug(f"Error updating translation text widget (TclError, likely destroyed): {e_uttomt}")
        except Exception as e_uttomt_gen:
            log_debug(f"Unexpected error updating translation text: {type(e_uttomt_gen).__name__} - {e_uttomt_gen}")
            if (self.app.translation_text and 
                hasattr(self.app.translation_text, 'config') and 
                hasattr(self.app.translation_text, 'winfo_exists') and 
                self.app.translation_text.winfo_exists()): 
                try: 
                    self.app.translation_text.config(state=tk.DISABLED)
                except tk.TclError: 
                    pass

    def update_debug_display(self, original_img_pil_udd, processed_img_cv_udd, ocr_text_content_udd):
        """Updates the debug display with current images and OCR text
        
        Args:
            original_img_pil_udd: Original screenshot as PIL Image
            processed_img_cv_udd: Processed image as OpenCV numpy array
            ocr_text_content_udd: OCR extracted text content
        """
        # Check if debugging is enabled and the widgets still exist
        if not self.app.ocr_debugging_var.get(): 
            return
        
        # Check for existence of all required UI elements for the debug tab
        required_debug_widgets = ['original_image_label', 'processed_image_label', 'ocr_results_text']
        for widget_name in required_debug_widgets:
            widget_ref = getattr(self.app, widget_name, None)
            if not widget_ref or not hasattr(widget_ref, 'winfo_exists') or not widget_ref.winfo_exists():
                # log_debug(f"Debug display update skipped: Widget '{widget_name}' missing or destroyed.") # Can be verbose
                return
                
        try:
            display_width_udd = 250 # Max width for display images in the tab

            # Original Image (PIL format is passed in)
            if original_img_pil_udd:
                try:
                    img_copy_udd = original_img_pil_udd.copy() 
                    h_udd, w_udd = img_copy_udd.height, img_copy_udd.width
                    aspect_ratio_udd = h_udd / w_udd if w_udd > 0 else 1
                    display_height_udd = max(20, int(display_width_udd * aspect_ratio_udd))
                    
                    resample_filter_udd = Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS
                    img_resized_udd = img_copy_udd.resize((display_width_udd, display_height_udd), resample_filter_udd)
                    
                    original_tk_udd = ImageTk.PhotoImage(img_resized_udd)
                    self.app.original_image_label.configure(image=original_tk_udd, text="") 
                    self.app.original_image_label.image = original_tk_udd # Keep reference
                except Exception as img_err_udd: # Use distinct variable name
                     log_debug(f"Error processing original image for debug display: {img_err_udd}")
                     self.app.original_image_label.configure(image=None, text="Error Original")

            # Processed Image (OpenCV NumPy array is passed in)
            if isinstance(processed_img_cv_udd, np.ndarray):
                try:
                    pil_processed_udd = None
                    if len(processed_img_cv_udd.shape) == 2: # Grayscale
                        pil_processed_udd = Image.fromarray(processed_img_cv_udd)
                    elif len(processed_img_cv_udd.shape) == 3: # Color (BGR from OpenCV)
                        pil_processed_udd = Image.fromarray(cv2.cvtColor(processed_img_cv_udd, cv2.COLOR_BGR2RGB))
                    
                    if pil_processed_udd:
                        h_proc_udd, w_proc_udd = pil_processed_udd.height, pil_processed_udd.width
                        aspect_ratio_proc_udd = h_proc_udd / w_proc_udd if w_proc_udd > 0 else 1
                        display_height_proc_udd = max(20, int(display_width_udd * aspect_ratio_proc_udd))
                        
                        resample_filter_nearest_udd = Image.Resampling.NEAREST if hasattr(Image, 'Resampling') else Image.NEAREST
                        processed_resized_udd = pil_processed_udd.resize((display_width_udd, display_height_proc_udd), resample_filter_nearest_udd)
                        
                        processed_tk_udd = ImageTk.PhotoImage(processed_resized_udd)
                        self.app.processed_image_label.configure(image=processed_tk_udd, text="")
                        self.app.processed_image_label.image = processed_tk_udd 
                    else: # Should not happen if input is valid np.ndarray from cv2
                        self.app.processed_image_label.configure(image=None, text="Invalid Processed Format")
                except Exception as img_err_proc_udd: # Use distinct variable name
                    log_debug(f"Error processing processed image for debug display: {img_err_proc_udd}")
                    self.app.processed_image_label.configure(image=None, text="Error Processed")

            # Update OCR Results Text
            self.app.ocr_results_text.config(state=tk.NORMAL)
            self.app.ocr_results_text.delete(1.0, tk.END)
            # Add metadata
            debug_info_text = (f"Timestamp: {time.strftime('%H:%M:%S')}\n"
                               f"Preprocessing: {self.app.preprocessing_mode_var.get()}\n"
                               f"OCR Lang (Tess): {self.app.get_tesseract_lang_code()}\n"
                               f"Target Lang (API): {self.app.target_lang_var.get()}\n" # This is the API target lang setting
                               f"Stability: {self.app.text_stability_counter}/{self.app.stable_threshold}\n"
                               f"Confidence Threshold: {self.app.confidence_threshold}%\n"
                               f"Remove Trailing Garbage: {'Enabled' if self.app.remove_trailing_garbage_var.get() else 'Disabled'}\n"
                               f"{'-'*20}\n"
                               f"{ocr_text_content_udd}\n") # Use renamed arg
            self.app.ocr_results_text.insert(tk.END, debug_info_text)
            self.app.ocr_results_text.config(state=tk.DISABLED)
            self.app.ocr_results_text.see("1.0") # Scroll to the top

        except tk.TclError as e_udd_tcl:
             log_debug(f"Error updating debug display (TclError - widget likely destroyed): {e_udd_tcl}")
        except Exception as e_udd_gen:
            log_debug(f"Unexpected error updating debug display: {type(e_udd_gen).__name__} - {str(e_udd_gen)}")
            if self.app.ocr_results_text and self.app.ocr_results_text.winfo_exists(): # Ensure disabled on other errors
                 try: 
                     self.app.ocr_results_text.config(state=tk.DISABLED)
                 except tk.TclError: 
                     pass
