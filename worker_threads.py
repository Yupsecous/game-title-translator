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
            
            # Simple logic for Gemini OCR - strict scan interval adherence
            ocr_model = app.get_ocr_model_setting()
            if ocr_model == 'gemini':
                # For Gemini OCR: Simple, strict interval - no adaptive logic
                if now - last_cap_time < base_scan_interval:
                    sleep_duration = base_scan_interval - (now - last_cap_time)
                    # Sleep in smaller chunks to check app.is_running more frequently
                    slept_time = 0
                    while slept_time < sleep_duration and app.is_running:
                        chunk = min(0.05, sleep_duration - slept_time)
                        time.sleep(chunk)
                        slept_time += chunk
                    if not app.is_running: break
                    continue
                
                # Set current scan interval to base for Gemini (no adaptation)
                current_scan_interval_sec = base_scan_interval
                
            else:
                # Adaptive logic for Tesseract OCR (existing behavior)
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

            # Simplified frame deduplication for Gemini OCR
            if ocr_model == 'gemini':
                # For Gemini: Simple hash check, no probability skipping
                img_small = screenshot.resize((max(1, width//4), max(1, height//4)), Image.Resampling.NEAREST if hasattr(Image, "Resampling") else Image.NEAREST)
                img_hash = hashlib.md5(img_small.tobytes()).hexdigest()
                
                if img_hash == last_cap_hash:
                    # Skip identical frames for Gemini
                    continue
                last_cap_hash = img_hash
                
            else:
                # Complex frame deduplication for Tesseract (existing behavior)
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
                # Simplified queue management for Gemini OCR
                if ocr_model == 'gemini':
                    # For Gemini: Simple queue - just add to queue if not full
                    if not app.ocr_queue.full():
                        app.ocr_queue.put_nowait(screenshot)
                    # else: skip frame if queue is full (no complex management)
                        
                else:
                    # Complex queue management for Tesseract (existing behavior)
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
            
            # Different processing logic for Gemini vs Tesseract
            ocr_model = app.get_ocr_model_setting()
            
            if ocr_model == 'gemini':
                # For Gemini: Simple interval matching scan interval (no adaptive logic)
                scan_interval_ms = app.scan_interval_var.get()
                required_ocr_interval = max(0.1, scan_interval_ms / 1000.0)
                
                if now - last_ocr_proc_time < required_ocr_interval:
                    sleep_duration = required_ocr_interval - (now - last_ocr_proc_time)
                    slept_time = 0
                    while slept_time < sleep_duration and app.is_running:
                        chunk = min(0.05, sleep_duration - slept_time)
                        time.sleep(chunk)
                        slept_time += chunk
                    if not app.is_running: break
                    continue
            else:
                # For Tesseract: Use adaptive processing (existing logic)
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

            # ==================== OCR MODEL ROUTING (Phase 2) ====================
            # Check OCR model setting and route accordingly
            ocr_model = app.get_ocr_model_setting()
            
            if ocr_model == 'gemini':
                # Use Gemini OCR - start async batch processing (no WebP conversion here)
                log_debug("WT: OCR routing to Gemini OCR")
                run_gemini_ocr_only(app, screenshot_pil)
                continue  # Skip Tesseract processing
            
            elif ocr_model == 'tesseract':
                # Convert to WebP for Gemini API only for Tesseract fallback scenarios
                app.raw_image_for_gemini = app.convert_to_webp_for_gemini(screenshot_pil)
                
                # Use Tesseract OCR (existing logic continues below)
                log_debug("WT: OCR routing to Tesseract OCR")
                # Continue with existing Tesseract processing
                pass
            
            else:
                # Unknown OCR model - fallback to Tesseract with warning
                app.raw_image_for_gemini = app.convert_to_webp_for_gemini(screenshot_pil)
                log_debug(f"WT: OCR: Unknown OCR model '{ocr_model}', falling back to Tesseract")
                # Continue with existing Tesseract processing
                pass
            
            # ==================== TESSERACT OCR PROCESSING ====================

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
                    # Use async translation instead of queue to eliminate bottlenecks
                    start_async_translation(app, ocr_cleaned_text, 0)  # Use 0 as OCR sequence for Tesseract
                    app.last_successful_translation_time = now
                    app.text_stability_counter = 0
                    # Alternative Conservative Fix: Update only if text changed, don't reset to empty if text is the same
                    if ocr_cleaned_text != app.previous_text:
                        app.previous_text = ocr_cleaned_text
                    similar_texts_count = 0 # Reset after sending for translation
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
    """Simplified translation thread - mainly handles Tesseract timeout logic.
    
    Async translations are now handled by start_async_translation() for both Gemini and Tesseract OCR.
    This thread primarily manages the clear translation timeout for Tesseract OCR.
    """
    log_debug("WT: Translation thread started (simplified for async processing).")
    # Keep track of the last time a translation was sent to display (local to this thread)
    thread_local_last_translation_display_time = time.monotonic() 

    while app.is_running:
        now = time.monotonic()
        try:
            # Check if we need to clear the translation due to inactivity
            # DISABLE this timeout logic when using Gemini OCR as it has its own timeout handling
            ocr_model = app.get_ocr_model_setting()
            
            if ocr_model != 'gemini':  # Only use translation thread timeout for Tesseract OCR
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

            # For async processing: Check if we need to update the local timer based on global successful translation time
            if app.last_successful_translation_time > thread_local_last_translation_display_time:
                thread_local_last_translation_display_time = app.last_successful_translation_time

            # Check for any remaining items in translation queue and process them (legacy support)
            try:
                text_to_translate = app.translation_queue.get(timeout=0.1)  # Very short timeout
                if text_to_translate and not app.is_placeholder_text(text_to_translate):
                    log_debug(f"WT: Processing legacy queue item: '{text_to_translate}'")
                    # Process using async translation instead of blocking
                    start_async_translation(app, text_to_translate, 0)  # Use 0 as OCR sequence for legacy items
            except queue.Empty:
                pass  # No items in queue, continue
            
            # Sleep to avoid busy waiting
            time.sleep(0.1)

        except tk.TclError:
            log_debug("WT: Translation thread TclError.")
            if not app.is_running: break
            time.sleep(0.1)
        except Exception as e_trans_loop_wt:
            log_debug(f"WT: Translation thread error: {type(e_trans_loop_wt).__name__} - {e_trans_loop_wt}\n{traceback.format_exc()}")
            time.sleep(0.2)
    log_debug("WT: Translation thread finished.")


# ==================== GEMINI OCR ASYNC PROCESSING (Phase 2) ====================

def run_gemini_ocr_only(app, screenshot_pil):
    """Start Gemini OCR processing for a screenshot with simplified flow."""
    try:
        # Check if Gemini OCR is selected
        if app.get_ocr_model_setting() != 'gemini':
            return
        
        # Initialize batch management if not exists
        if not hasattr(app, 'batch_sequence_counter'):
            app.batch_sequence_counter = 0
        if not hasattr(app, 'last_displayed_batch_sequence'):
            app.last_displayed_batch_sequence = 0
        
        # Convert image to WebP for Gemini API
        webp_image_data = app.convert_to_webp_for_gemini(screenshot_pil)
        if not webp_image_data:
            log_debug("Failed to convert image to WebP for Gemini OCR")
            return
        
        # Get current source language
        source_lang = getattr(app, 'gemini_source_lang', 'en')
        
        # Increment batch sequence counter
        app.batch_sequence_counter += 1
        sequence_number = app.batch_sequence_counter
        
        # Check concurrent calls limit
        if len(app.active_ocr_calls) >= app.max_concurrent_ocr_calls:
            log_debug(f"Max concurrent OCR calls ({app.max_concurrent_ocr_calls}) reached, skipping batch {sequence_number}")
            return
        
        # Start OCR processing immediately (no queue for Gemini)
        app.active_ocr_calls.add(sequence_number)
        
        import threading
        ocr_thread = threading.Thread(
            target=process_gemini_ocr_async,
            args=(app, webp_image_data, source_lang, sequence_number),
            name=f"GeminiOCR-{sequence_number}",
            daemon=True
        )
        ocr_thread.start()
        
        log_debug(f"Started Gemini OCR batch {sequence_number} (active calls: {len(app.active_ocr_calls)})")
        
    except Exception as e:
        log_debug(f"Error starting Gemini OCR batch: {type(e).__name__} - {e}")


def process_gemini_ocr_async(app, webp_image_data, source_lang, sequence_number):
    """Process Gemini OCR API call asynchronously with timeout handling."""
    start_time = time.monotonic()
    
    try:
        log_debug(f"Processing Gemini OCR batch {sequence_number}")
        
        # Make the Gemini OCR API call - logging is handled inside the function
        ocr_result = app.translation_handler._gemini_ocr_only(webp_image_data, source_lang)
        
        # Check timeout (3 seconds total including API call)
        elapsed_time = time.monotonic() - start_time
        if elapsed_time > 3.0:
            log_debug(f"Batch {sequence_number} exceeded 3-second timeout ({elapsed_time:.2f}s), discarding")
            return
        
        log_debug(f"Gemini OCR batch {sequence_number} completed: '{ocr_result}'")
        
        # Schedule processing of the OCR response on the main thread
        app.root.after(0, process_gemini_ocr_response, app, ocr_result, sequence_number, source_lang)
        
    except Exception as e:
        elapsed_time = time.monotonic() - start_time
        log_debug(f"Error in async Gemini OCR batch {sequence_number} after {elapsed_time:.2f}s: {type(e).__name__} - {e}")
        
        # Schedule error handling on main thread if not timed out
        if elapsed_time <= 3.0:
            error_msg = f"<e>: OCR batch {sequence_number} error: {str(e)}"
            app.root.after(0, process_gemini_ocr_response, app, error_msg, sequence_number, source_lang)
    
    finally:
        # Always remove from active calls
        try:
            app.active_ocr_calls.discard(sequence_number)
            log_debug(f"Gemini OCR batch {sequence_number} finished (active calls: {len(app.active_ocr_calls)})")
        except Exception as cleanup_error:
            log_debug(f"Error cleaning up OCR batch {sequence_number}: {cleanup_error}")


def process_gemini_ocr_response(app, ocr_result, sequence_number, source_lang):
    """Process Gemini OCR response with chronological order enforcement."""
    try:
        log_debug(f"Processing OCR response for batch {sequence_number}: '{ocr_result}'")
        
        # Initialize last displayed sequence if not exists
        if not hasattr(app, 'last_displayed_batch_sequence'):
            app.last_displayed_batch_sequence = 0
        
        # CHRONOLOGICAL ORDER ENFORCEMENT - Only reject OLD results, allow any NEW results
        # This prevents old batches from overriding newer translations
        if sequence_number <= app.last_displayed_batch_sequence:
            log_debug(f"OCR batch {sequence_number}: Sequence too old (last displayed: {app.last_displayed_batch_sequence}), discarding")
            return
        
        # This is a newer sequence - proceed with processing
        log_debug(f"OCR batch {sequence_number}: Processing newer sequence (last displayed: {app.last_displayed_batch_sequence})")
        
        # Handle error responses
        if isinstance(ocr_result, str) and ocr_result.startswith("<e>:"):
            log_debug(f"OCR error in batch {sequence_number}: {ocr_result}")
            app.last_displayed_batch_sequence = sequence_number  # Update sequence even for errors
            return
        
        # Handle <EMPTY> response (no text detected)
        if ocr_result == "<EMPTY>":
            log_debug(f"OCR batch {sequence_number}: No text detected")
            app.handle_empty_ocr_result()
            app.last_displayed_batch_sequence = sequence_number
            return
        
        # Handle successive identical subtitle detection
        if hasattr(app, 'last_processed_subtitle') and ocr_result == app.last_processed_subtitle:
            log_debug(f"OCR batch {sequence_number}: Successive identical subtitle detected - '{ocr_result}'")
            # Reset timeout since text is still present, but DON'T send to translation again
            app.reset_clear_timeout()
            # Keep the existing translation displayed - no need to re-translate or clear
            log_debug(f"Keeping existing translation displayed for successive identical: '{ocr_result}'")
            app.last_displayed_batch_sequence = sequence_number
            return
        
        # New/different text detected
        log_debug(f"OCR batch {sequence_number}: New text detected: '{ocr_result}'")
        
        # Update last processed subtitle for successive comparison
        app.last_processed_subtitle = ocr_result
        
        # Reset clear timeout (text detected)
        app.reset_clear_timeout()
        
        # Send extracted text to async translation pipeline (replaces queue-based approach)
        start_async_translation(app, ocr_result, sequence_number)
        
        # Update the last displayed sequence number
        app.last_displayed_batch_sequence = sequence_number
        
    except Exception as e:
        log_debug(f"Error processing OCR response for batch {sequence_number}: {type(e).__name__} - {e}")
        # On error, try to clear any timeout state
        try:
            app.reset_clear_timeout()
        except:
            pass


# ==================== ASYNC TRANSLATION PROCESSING (Phase 2) ====================

def start_async_translation(app, text_to_translate, ocr_sequence_number):
    """Start async translation processing to eliminate queue bottlenecks."""
    try:
        # Ensure async translation infrastructure is initialized
        app.initialize_async_translation_infrastructure()
        
        # Increment translation sequence counter
        app.translation_sequence_counter += 1
        translation_sequence = app.translation_sequence_counter
        
        # Check concurrent calls limit
        if len(app.active_translation_calls) >= app.max_concurrent_translation_calls:
            log_debug(f"Max concurrent translation calls ({app.max_concurrent_translation_calls}) reached, skipping translation {translation_sequence}")
            return
        
        # Start translation processing immediately (no queue for async translations)
        app.active_translation_calls.add(translation_sequence)
        
        import threading
        translation_thread = threading.Thread(
            target=process_translation_async,
            args=(app, text_to_translate, translation_sequence, ocr_sequence_number),
            name=f"Translation-{translation_sequence}",
            daemon=True
        )
        translation_thread.start()
        
        log_debug(f"Started async translation {translation_sequence} for OCR batch {ocr_sequence_number} (active calls: {len(app.active_translation_calls)}): '{text_to_translate}'")
        
    except Exception as e:
        log_debug(f"Error starting async translation: {type(e).__name__} - {e}")


def process_translation_async(app, text_to_translate, translation_sequence, ocr_sequence_number):
    """Process translation API call asynchronously with timeout and staleness handling."""
    start_time = time.monotonic()
    
    try:
        log_debug(f"Processing async translation {translation_sequence}")
        
        # Make the translation API call with timeout consideration
        translation_result = app.translation_handler.translate_text_with_timeout(text_to_translate, timeout_seconds=10.0)
        
        # Check if translation took too long (consider potentially stale)
        elapsed_time = time.monotonic() - start_time
        if elapsed_time > 5.0:
            log_debug(f"Translation {translation_sequence} took {elapsed_time:.1f}s, may be stale but will attempt display")
        
        log_debug(f"Translation {translation_sequence} completed in {elapsed_time:.3f}s: '{translation_result}'")
        
        # Schedule processing of the translation response on the main thread
        app.root.after(0, process_translation_response, app, translation_result, translation_sequence, text_to_translate, ocr_sequence_number)
        
    except Exception as e:
        elapsed_time = time.monotonic() - start_time
        log_debug(f"Error in async translation {translation_sequence} after {elapsed_time:.2f}s: {type(e).__name__} - {e}")
        
        # Schedule error handling on main thread
        error_msg = f"Translation error: {str(e)}"
        app.root.after(0, process_translation_response, app, error_msg, translation_sequence, text_to_translate, ocr_sequence_number)
    
    finally:
        # Always remove from active calls
        try:
            app.active_translation_calls.discard(translation_sequence)
            log_debug(f"Translation {translation_sequence} finished (active calls: {len(app.active_translation_calls)})")
        except Exception as cleanup_error:
            log_debug(f"Error cleaning up translation {translation_sequence}: {cleanup_error}")


def process_translation_response(app, translation_result, translation_sequence, original_text, ocr_sequence_number):
    """Process translation response with chronological order enforcement - same logic as OCR."""
    try:
        log_debug(f"Processing translation response for sequence {translation_sequence}: '{translation_result}'")
        
        # Initialize last displayed sequence if not exists
        if not hasattr(app, 'last_displayed_translation_sequence'):
            app.last_displayed_translation_sequence = 0
        
        # CHRONOLOGICAL ORDER ENFORCEMENT - Only display if this is newer than what's currently shown
        if translation_sequence <= app.last_displayed_translation_sequence:
            log_debug(f"Translation {translation_sequence}: Sequence too old (last displayed: {app.last_displayed_translation_sequence}), discarding but caching result")
            # Still update caches even if we don't display - translation result is valid
            return
        
        # This is a newer translation - proceed with display
        log_debug(f"Translation {translation_sequence}: Processing newer sequence (last displayed: {app.last_displayed_translation_sequence})")
        
        # Handle error responses
        error_prefixes = ("Err:", "MarianMT error:", "Google API error:", "DeepL API error:", 
                          "No translation for model:", "MarianMT not initialized.", 
                          "MarianMT language pair not determined:", "Google API key missing:",
                          "DeepL API key missing:", "Google Client init error:", 
                          "DeepL Client init error:", "Translation error:", 
                          "Google Translate API client not initialized", 
                          "DeepL API client not initialized", 
                          "MarianMT translator not initialized",
                          "Translation timeout:", "Translation error:")
        
        if isinstance(translation_result, str) and any(translation_result.startswith(p) for p in error_prefixes):
            log_debug(f"Translation error in sequence {translation_sequence}: {translation_result}")
            app.update_translation_text(f"Translation Error:\n{translation_result}")
            app.last_displayed_translation_sequence = translation_sequence
            app.last_successful_translation_time = time.monotonic()
            return
        
        # Successful translation - process and display
        if isinstance(translation_result, str) and translation_result.strip():
            final_processed_translation = post_process_translation_text(translation_result)
            app.update_translation_text(final_processed_translation)
            log_debug(f"Translation {translation_sequence} displayed: '{final_processed_translation}' (from OCR batch {ocr_sequence_number})")
            app.last_displayed_translation_sequence = translation_sequence
            app.last_successful_translation_time = time.monotonic()
        else:
            log_debug(f"Translation {translation_sequence}: Empty or invalid result, not displaying")
            
    except Exception as e:
        log_debug(f"Error processing translation response for sequence {translation_sequence}: {type(e).__name__} - {e}")
        # On error, try to display error message
        try:
            app.update_translation_text(f"Translation Processing Error:\n{type(e).__name__}")
        except:
            pass
