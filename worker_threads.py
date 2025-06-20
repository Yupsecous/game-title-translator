import tkinter as tk # For tk.Toplevel type check in capture_thread
from tkinter import messagebox # For Tesseract error in OCR thread
import time
import queue
import numpy as np
import cv2
import pytesseract
import pyautogui
import hashlib
import random
import re
import traceback 

from logger import log_debug
from ocr_utils import (
    preprocess_for_ocr, get_tesseract_model_params, 
    ocr_region_with_confidence, post_process_ocr_text_general, 
    remove_text_after_last_punctuation_mark
)
from translation_utils import post_process_translation_text
from PIL import Image # For hashing in capture_thread

def run_capture_thread(app):
    log_debug("WT: Capture thread started.")
    last_cap_time = 0.0
    last_cap_hash = None
    min_interval = 0.05  # 50ms minimum safety floor - user can control via Settings tab
    similar_frames = 0
    current_scan_interval_sec = min_interval # Initialize

    while app.is_running:
        now = time.monotonic()
        try:
            scan_interval_ms = app.scan_interval_var.get()
            base_scan_interval = max(min_interval, scan_interval_ms / 1000.0)
            q_fullness = app.ocr_queue.qsize() / (app.ocr_queue.maxsize or 1) # Avoid division by zero
            
            if q_fullness > 0.7: current_scan_interval_sec = base_scan_interval * (1 + q_fullness)
            elif q_fullness > 0.4: current_scan_interval_sec = base_scan_interval * 1.25
            else: current_scan_interval_sec = max(min_interval, current_scan_interval_sec * 0.95)
            
            if now - last_cap_time < current_scan_interval_sec:
                sleep_duration = current_scan_interval_sec - (now - last_cap_time)
                # Sleep in smaller chunks to check app.is_running more frequently
                slept_time = 0
                while slept_time < sleep_duration and app.is_running:
                    chunk = min(0.05, sleep_duration - slept_time)
                    time.sleep(chunk)
                    slept_time += chunk
                if not app.is_running: break
                continue
            
            overlay = app.source_overlay
            if not overlay or not isinstance(overlay, tk.Toplevel) or not overlay.winfo_exists():
                if app.is_running: time.sleep(max(current_scan_interval_sec, 0.5))
                continue
            
            try:
                area = overlay.get_geometry()
            except tk.TclError: # Window might be destroyed between check and get_geometry
                if app.is_running: time.sleep(max(current_scan_interval_sec, 0.5))
                continue
            if not area: # get_geometry can return None if window is destroyed
                if app.is_running: time.sleep(max(current_scan_interval_sec, 0.2))
                continue

            x1, y1, x2, y2 = map(int, area); width, height = x2-x1, y2-y1
            if width <=0 or height <=0: continue

            capture_moment = time.monotonic() # Time right before capture
            screenshot = pyautogui.screenshot(region=(x1,y1,width,height))
            last_cap_time = capture_moment # Update last_cap_time with moment before capture

            img_small = screenshot.resize((max(1, width//4), max(1, height//4)), Image.Resampling.NEAREST if hasattr(Image, "Resampling") else Image.NEAREST)
            img_hash = hashlib.md5(img_small.tobytes()).hexdigest()

            if img_hash == last_cap_hash:
                similar_frames +=1
                skip_probability = min(0.95, 0.5 + (similar_frames*0.05))
                if random.random() < skip_probability:
                    time.sleep(min(0.1, current_scan_interval_sec*0.5))
                    continue
            else:
                similar_frames = 0
            last_cap_hash = img_hash

            try:
                if app.ocr_queue.qsize() >= app.ocr_queue.maxsize * 0.8: 
                    try:
                        app.ocr_queue.get_nowait() # Make room
                        app.ocr_queue.put_nowait(screenshot)
                    except queue.Empty: # Race condition
                        if not app.ocr_queue.full(): app.ocr_queue.put_nowait(screenshot)
                elif not app.ocr_queue.full():
                    app.ocr_queue.put_nowait(screenshot)
                # else: log_debug("WT: Capture: OCR queue full, frame skipped.") # Can be verbose
            except Exception as q_err_wt_put:
                log_debug(f"WT: Capture: Error putting to OCR queue - {type(q_err_wt_put).__name__}: {q_err_wt_put}")

        except tk.TclError:
            log_debug("WT: Capture thread TclError (UI likely gone).")
            if not app.is_running: break
            time.sleep(0.1) 
        except Exception as loop_err_wt_capture:
            log_debug(f"WT: Capture thread error: {type(loop_err_wt_capture).__name__} - {loop_err_wt_capture}\n{traceback.format_exc()}")
            # Use current_scan_interval_sec if defined, otherwise a default
            sleep_after_error = current_scan_interval_sec if 'current_scan_interval_sec' in locals() else 0.5
            time.sleep(max(sleep_after_error, 0.5))
    log_debug("WT: Capture thread finished.")


def run_ocr_thread(app):
    log_debug("WT: OCR thread started.")
    tess_langs = app.get_tesseract_lang_code()
    last_lang_check = time.monotonic()
    last_ocr_proc_time = 0
    min_ocr_interval = 0.1
    similar_texts_count = 0
    prev_ocr_text = ""
    current_conf_thresh = app.confidence_threshold
    
    # Cache OCR parameters to avoid recalculating every cycle
    cached_prep_mode = None
    cached_tess_params = None

    while app.is_running:
        now = time.monotonic()
        try:
            if now - last_lang_check > 5.0:
                new_langs = app.get_tesseract_lang_code()
                if new_langs != tess_langs:
                    tess_langs = new_langs
                    log_debug(f"WT: OCR lang changed to {tess_langs}")
                
                # Check confidence threshold directly from app's Tkinter var
                new_conf = app.confidence_var.get() 
                if new_conf != current_conf_thresh: 
                    current_conf_thresh = new_conf
                    app.confidence_threshold = new_conf # Update app's runtime value immediately
                    log_debug(f"WT: Confidence threshold updated to {new_conf}")
                last_lang_check = now
            
            q_sz = app.ocr_queue.qsize()
            ocr_q_max = app.ocr_queue.maxsize or 1 # Avoid division by zero if maxsize is 0
            adaptive_ocr_interval = min_ocr_interval * (0.8 if q_sz <=1 else (1.0 + (q_sz / ocr_q_max)))

            if now - last_ocr_proc_time < adaptive_ocr_interval:
                sleep_duration = adaptive_ocr_interval - (now - last_ocr_proc_time)
                slept_time = 0
                while slept_time < sleep_duration and app.is_running:
                    chunk = min(0.05, sleep_duration - slept_time)
                    time.sleep(chunk)
                    slept_time += chunk
                if not app.is_running: break
                continue
            
            try:
                screenshot_pil = app.ocr_queue.get(timeout=0.5) # Reduced timeout
            except queue.Empty:
                time.sleep(0.05) # Small sleep to prevent busy-waiting
                continue

            ocr_proc_start_time = time.monotonic()
            last_ocr_proc_time = ocr_proc_start_time
            app.last_screenshot = screenshot_pil

            # Optimized image processing: Direct PIL to OpenCV conversion
            # Convert PIL to numpy array once
            img_np = np.array(screenshot_pil)
            img_shape = img_np.shape
            
            # Optimized conversion based on common cases (avoid repeated checks)
            if len(img_shape) == 3:
                if img_shape[2] == 3:  # RGB - most common case
                    img_cv_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
                elif img_shape[2] == 4:  # RGBA
                    img_cv_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGBA2BGR)
                else:
                    raise ValueError(f"WT: OCR: Unexpected 3D image channels: {img_shape[2]}")
            elif len(img_shape) == 2:  # Grayscale
                img_cv_bgr = cv2.cvtColor(img_np, cv2.COLOR_GRAY2BGR)
            else:
                raise ValueError(f"WT: OCR: Unexpected image dimensions: {len(img_shape)}D")

            prep_mode = app.preprocessing_mode_var.get()
            # Get adaptive thresholding parameters
            block_size = app.adaptive_block_size_var.get()
            c_value = app.adaptive_c_var.get()
            processed_cv_img = preprocess_for_ocr(img_cv_bgr, prep_mode, block_size, c_value) # From ocr_utils
            app.last_processed_image = processed_cv_img

            if app.ocr_debugging_var.get():
                app.root.after(0, app.update_debug_display, screenshot_pil, processed_cv_img, "Processing...")

            # Cache OCR parameters - only recalculate when preprocessing mode changes
            if cached_prep_mode != prep_mode:
                cached_prep_mode = prep_mode
                cached_tess_params = get_tesseract_model_params(prep_mode if prep_mode in ['gaming','document','subtitle'] else 'general')
                log_debug(f"WT: OCR parameters cached for mode: {prep_mode}")
            
            full_img_region = (0,0, processed_cv_img.shape[1], processed_cv_img.shape[0])
            # Use current_conf_thresh which is updated from app.confidence_var
            # Note: tess_langs is already set and updated every 5 seconds above - no need to call get_tesseract_lang_code() again
            ocr_raw_text = ocr_region_with_confidence(processed_cv_img, full_img_region, tess_langs, cached_tess_params, current_conf_thresh) # From ocr_utils
            
            ocr_cleaned_text = post_process_ocr_text_general(ocr_raw_text, tess_langs) # From ocr_utils
            if app.remove_trailing_garbage_var.get() and ocr_cleaned_text:
                pattern = r'[.!?]|\.{3}|…' 
                if not list(re.finditer(pattern, ocr_cleaned_text)):
                    app.text_stability_counter = 0
                    app.previous_text = ""
                    continue 
                ocr_cleaned_text = remove_text_after_last_punctuation_mark(ocr_cleaned_text) # From ocr_utils
            
            if app.ocr_debugging_var.get(): 
                app.root.after(0, app.update_debug_display, screenshot_pil, processed_cv_img, ocr_cleaned_text)

            if not ocr_cleaned_text or app.is_placeholder_text(ocr_cleaned_text):
                app.text_stability_counter = 0
                app.previous_text = ""
                continue

            similarity = app.calculate_text_similarity(ocr_cleaned_text, prev_ocr_text)
            if similarity > 0.9:
                similar_texts_count+=1
            else:
                similar_texts_count = 0
                prev_ocr_text = ocr_cleaned_text # Update only if text is dissimilar enough
            
            if similar_texts_count > 2 and (now - app.last_successful_translation_time) < 1.0:
                # log_debug("WT: OCR: Skipping very similar text to reduce processing") # Can be verbose
                continue

            if ocr_cleaned_text == app.previous_text:
                app.text_stability_counter +=1
            else:
                app.text_stability_counter = 0
                app.previous_text = ocr_cleaned_text
            
            if app.text_stability_counter >= app.stable_threshold:
                s_count = len(re.findall(r'[.!?]+', ocr_cleaned_text)) + 1
                txt_len = len(ocr_cleaned_text)
                adaptive_trans_interval = max(0.2, min(app.min_translation_interval, app.min_translation_interval * (0.5 + (0.1*s_count) + (txt_len/1000))))
                
                if (now - app.last_successful_translation_time >= adaptive_trans_interval):
                    if not app.translation_queue.full():
                        app.translation_queue.put_nowait(ocr_cleaned_text)
                        app.last_successful_translation_time = now
                        app.text_stability_counter = 0
                        # Alternative Conservative Fix: Update only if text changed, don't reset to empty if text is the same
                        if ocr_cleaned_text != app.previous_text:
                            app.previous_text = ocr_cleaned_text
                        similar_texts_count = 0 # Reset after sending for translation
                    # else: log_debug("WT: OCR: Translation queue full, skipping.") # Can be verbose
                # else: log_debug(f"WT: OCR: Throttling translation: last was {now - app.last_successful_translation_time:.2f}s ago") # Can be verbose
        
        except pytesseract.TesseractNotFoundError:
            log_debug(f"WT: OCR Error: Tesseract not found. Path: {pytesseract.pytesseract.tesseract_cmd}")
            # Schedule UI update and stop action on the main thread
            app.root.after(0, lambda: messagebox.showerror("Tesseract Error", f"Tesseract executable not found during OCR:\n{pytesseract.pytesseract.tesseract_cmd}\nPlease check path and restart.", parent=app.root))
            app.root.after(0, app.stop_translation_from_thread) # Request stop
            break 
        except tk.TclError:
            log_debug("WT: OCR thread TclError.")
            if not app.is_running: break
            time.sleep(0.1)
        except Exception as e_ocr_loop_wt:
            log_debug(f"WT: OCR thread error: {type(e_ocr_loop_wt).__name__} - {e_ocr_loop_wt}\n{traceback.format_exc()}")
            app.text_stability_counter=0
            app.previous_text=""
            time.sleep(0.2)
    log_debug("WT: OCR thread finished.")

def run_translation_thread(app):
    log_debug("WT: Translation thread started.")
    # Keep track of the last time a translation was sent to display (local to this thread)
    thread_local_last_translation_display_time = time.monotonic() 

    while app.is_running:
        now = time.monotonic()
        try:
            # Check if we need to clear the translation due to inactivity
            inactive_duration = now - thread_local_last_translation_display_time
            
            # Only clear translation if timeout is enabled and there's no ongoing text detection
            if app.clear_translation_timeout > 0 and inactive_duration > app.clear_translation_timeout:
                # Only clear if there's no text being detected in the source area
                # Check if there's any text in the previous_text (indicating source has content)
                if not app.previous_text or app.previous_text == "":
                    app.update_translation_text("") # Use app's method to update UI
                    log_debug(f"WT: Cleared translation after {inactive_duration:.1f}s of inactivity with no source text (timeout: {app.clear_translation_timeout}s)")
                else:
                    # If there's still text in the source area, don't clear the translation
                    log_debug(f"WT: Not clearing translation despite {inactive_duration:.1f}s inactivity because source area still has text")
                
                thread_local_last_translation_display_time = now # Reset timer after checking

            try:
                text_to_translate = app.translation_queue.get(timeout=1.0) # Reduced timeout
            except queue.Empty:
                time.sleep(0.05) 
                continue

            if not text_to_translate or app.is_placeholder_text(text_to_translate): # Use app's method
                continue
            
            translation_process_start_time = time.monotonic()
            translated_text = app.translate_text(text_to_translate) # Call app's main translation method
            translation_process_duration = time.monotonic() - translation_process_start_time

            error_prefixes = ("Err:", "MarianMT error:", "Google API error:", "DeepL API error:", 
                              "No translation for model:", "MarianMT not initialized.", 
                              "MarianMT language pair not determined.", "Google API key missing.",
                              "DeepL API key missing.", "Google Client init error:", 
                              "DeepL Client init error:", "Translation error:", # Generic error from MarianMT
                              "Google Translate API client not initialized", # Error from Google API cached func
                              "DeepL API client not initialized", # Error from DeepL API cached func
                              "MarianMT translator not initialized" # Error from MarianMT cached func
                              )


            if isinstance(translated_text, str) and not any(translated_text.startswith(p) for p in error_prefixes):
                final_processed_translation = post_process_translation_text(translated_text) # From translation_utils
                app.update_translation_text(final_processed_translation) # Use app's method
                log_debug(f"WT: Translation displayed (took {translation_process_duration:.3f}s): \"{final_processed_translation}\"")
                thread_local_last_translation_display_time = time.monotonic() # Update display time
                app.last_successful_translation_time = time.monotonic() # Update app's global tracker
            elif translated_text is not None: # It's likely an error message string
                log_debug(f"WT: Translation Failed/Skipped: {translated_text}. Original: \"{text_to_translate}\"")
                app.update_translation_text(f"Translation Error:\n{translated_text}") # Use app's method
                thread_local_last_translation_display_time = time.monotonic() # Update display time for errors too

        except tk.TclError:
            log_debug("WT: Translation thread TclError.")
            if not app.is_running: break
            time.sleep(0.1)
        except Exception as e_trans_loop_wt:
            log_debug(f"WT: Translation thread error: {type(e_trans_loop_wt).__name__} - {e_trans_loop_wt}\n{traceback.format_exc()}")
            # Display a generic error in the target window via main thread (app's method)
            app.root.after(0, app.update_translation_text, f"Translation Thread Error:\n{type(e_trans_loop_wt).__name__}")
            time.sleep(0.2)
    log_debug("WT: Translation thread finished.")
