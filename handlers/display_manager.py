import tkinter as tk
import time
import cv2
import numpy as np
from PIL import Image, ImageTk
from logger import log_debug

class DisplayManager:
    """Handles display and UI updates for overlays and debug information"""
    
    def __init__(self, app):
        """Initialize with a reference to the main application
        
        Args:
            app: The main GameChangingTranslator application instance
        """
        self.app = app
    
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

    def _update_translation_text_on_main_thread(self, text_content_main_thread):
        """Updates the translation text widget on the main thread
        
        Args:
            text_content_main_thread: Text content to display
        """
        if not self.app.target_overlay or not self.app.target_overlay.winfo_exists() or \
           not self.app.translation_text or not self.app.translation_text.winfo_exists():
            return

        try:
            # Only show the target overlay if the application is running
            if self.app.is_running:
                if not self.app.target_overlay.winfo_viewable():
                    self.app.target_overlay.show() 
                else: # Ensure it's topmost if already visible
                    self.app.target_overlay.attributes("-topmost", True)

            current_displayed_text = self.app.translation_text.get("1.0", tk.END).strip()
            new_text_to_display = text_content_main_thread.strip() if text_content_main_thread else ""

            if current_displayed_text != new_text_to_display:
                self.app.translation_text.config(state=tk.NORMAL) 
                self.app.translation_text.delete(1.0, tk.END)     
                self.app.translation_text.insert(tk.END, new_text_to_display) 
                self.app.translation_text.config(state=tk.DISABLED) 
                self.app.translation_text.see("1.0") # Scroll to top
        except tk.TclError as e_uttomt: 
            log_debug(f"Error updating translation text widget (TclError, likely destroyed): {e_uttomt}")
        except Exception as e_uttomt_gen:
            log_debug(f"Unexpected error updating translation text: {type(e_uttomt_gen).__name__} - {e_uttomt_gen}")
            if self.app.translation_text and self.app.translation_text.winfo_exists(): # Ensure disabled on other errors
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
