import tkinter as tk
from tkinter import messagebox # filedialog is not used here
import time
from logger import log_debug
from ui_elements import ResizableMovableFrame # Assuming ui_elements.py contains ResizableMovableFrame
from pyside_overlay import get_pyside_manager, is_pyside_available

def _select_screen_area_interactive(app, prompt_text, is_target=False):
    selection_result = None
    try:
        sel_win = tk.Toplevel(app.root)
        sel_win.attributes("-fullscreen", True)
        sel_win.attributes("-alpha", 0.6)  # Make it a bit more visible
        sel_win.configure(cursor="crosshair")
        
        # ISSUE 1 FIX: More aggressive focus handling for fullscreen app transitions
        sel_win.attributes("-topmost", True)    # Force topmost
        sel_win.update_idletasks()              # Force window to be created
        sel_win.wait_visibility()               # Wait for window to be visible
        sel_win.attributes("-topmost", True)    # Ensure still topmost after visibility
        sel_win.lift()                          # Bring to front
        sel_win.focus_force()                   # Force focus
        sel_win.grab_set()                      # Grab input
        sel_win.update()                        # Process events
        
        tk.Label(sel_win, text=prompt_text + "\n(Esc to cancel)", font=("Arial", 16, "bold"), bg="black", fg="white").place(relx=0.5, rely=0.1, anchor="center")
        canvas = tk.Canvas(sel_win, highlightthickness=0, bg=sel_win['bg']) # Match background
        canvas.pack(fill=tk.BOTH, expand=True)
        
        start_coords = {'x': None, 'y': None}
        rect_item = None # Initialize rect_item

        def on_press(e):
            nonlocal start_coords, rect_item # Ensure rect_item is accessible
            start_coords['x'], start_coords['y'] = e.x, e.y
            if rect_item: # If a rectangle already exists, delete it
                canvas.delete(rect_item)
            
            # Use the actual colors from app settings to match the overlay windows
            if is_target:
                # Target area: use target_colour_var from app settings
                rect_item = canvas.create_rectangle(
                    e.x, e.y, e.x, e.y, 
                    outline=app.target_colour_var.get(), 
                    width=3,
                    fill=app.target_colour_var.get(),
                    stipple="gray25"  # Similar to the 0.85 alpha value used for target overlay
                )
            else:
                # Source area: use source_colour_var from app settings 
                rect_item = canvas.create_rectangle(
                    e.x, e.y, e.x, e.y, 
                    outline=app.source_colour_var.get(), 
                    width=3,
                    fill=app.source_colour_var.get(),
                    stipple="gray50"  # Similar to the 0.7 alpha value used for source overlay
                )

        def on_drag(e):
            nonlocal rect_item # Ensure rect_item is accessible
            if start_coords['x'] is not None and rect_item: # Check if rect_item exists
                canvas.coords(rect_item, start_coords['x'], start_coords['y'], e.x, e.y)
                canvas.update_idletasks()  # Force the canvas to redraw immediately

        def on_release(e):
            nonlocal selection_result, start_coords, rect_item # Ensure all are accessible
            if start_coords['x'] is None: # If no press event occurred
                sel_win.destroy()
                return
            x1,y1,x2,y2 = min(start_coords['x'],e.x), min(start_coords['y'],e.y), max(start_coords['x'],e.x), max(start_coords['y'],e.y)
            if abs(x2-x1) < 10 or abs(y2-y1) < 10:
                messagebox.showwarning("Selection Small", "Area too small. Drag again or Esc to cancel.", parent=sel_win)
                if rect_item: # Delete the invalid rectangle
                    canvas.delete(rect_item)
                rect_item = None # Reset rect_item
                start_coords['x'] = None # Reset start_coords to allow new selection
                return
            selection_result = [x1,y1,x2,y2]
            sel_win.destroy()

        def on_escape(e):
            nonlocal selection_result # Ensure selection_result is accessible
            selection_result=None
            sel_win.destroy()

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        sel_win.bind("<Escape>", on_escape)
        sel_win.wait_window()
    except tk.TclError as e_sel:
        log_debug(f"OverlayManager: Screen selection error: {e_sel}")
        selection_result = None
    finally:
        if 'sel_win' in locals() and sel_win.winfo_exists():
            sel_win.grab_release()
    return selection_result

def select_source_area_om(app): # Suffix _om for OverlayManager
    # ISSUE 1 FIX: Ensure proper focus when coming from fullscreen apps like YouTube
    app.root.lift()           # Bring app to front first
    app.root.focus_force()    # Force focus on app
    app.root.update()         # Process any pending events
    time.sleep(0.1)           # Brief pause for window manager
    
    app.root.withdraw()       # Now minimize the app
    time.sleep(0.3)           # Longer delay for fullscreen transition
    selected = _select_screen_area_interactive(app, "Select OCR Source Area (Click & Drag)", is_target=False)
    app.root.deiconify()
    app.root.lift()
    app.root.focus_force()
    if selected:
        app.source_area = selected # Update app's source_area attribute
        log_debug(f"OverlayManager: Source area selected: {app.source_area}")
        messagebox.showinfo(
            app.ui_lang.get_label("dialog_area_selected_title", "Area Selected"), 
            f"{app.ui_lang.get_label('dialog_source_area_set_message', 'Source area set to:')}\n{app.source_area}", 
            parent=app.root
        )
        create_source_overlay_om(app) # Call the overlay creation function
        
        # Hide source overlay by default after creation
        if app.source_overlay and app.source_overlay.winfo_exists() and app.source_overlay.winfo_viewable():
            app.source_overlay.hide()
            # Update visibility setting in config
            app.config['Settings']['source_area_visible'] = 'False'
            log_debug("OverlayManager: Source overlay hidden after initial selection")

def select_target_area_om(app):
    # ISSUE 1 FIX: Ensure proper focus when coming from fullscreen apps like YouTube
    app.root.lift()           # Bring app to front first
    app.root.focus_force()    # Force focus on app
    app.root.update()         # Process any pending events
    time.sleep(0.1)           # Brief pause for window manager
    
    app.root.withdraw()       # Now minimize the app
    time.sleep(0.3)           # Longer delay for fullscreen transition
    selected = _select_screen_area_interactive(app, "Select Translation Display Area (Click & Drag)", is_target=True)
    app.root.deiconify()
    app.root.lift()
    app.root.focus_force()
    if selected:
        app.target_area = selected # Update app's target_area attribute
        log_debug(f"OverlayManager: Target area selected: {app.target_area}")
        messagebox.showinfo(
            app.ui_lang.get_label("dialog_area_selected_title", "Area Selected"), 
            f"{app.ui_lang.get_label('dialog_target_area_set_message', 'Target display area set to:')}\n{app.target_area}", 
            parent=app.root
        )
        create_target_overlay_om(app) # Call the overlay creation function
        
        # Hide target overlay by default after creation
        if app.target_overlay and app.target_overlay.winfo_exists() and app.target_overlay.winfo_viewable():
            app.target_overlay.hide()
            # Update visibility setting in config
            app.config['Settings']['target_area_visible'] = 'False'
            log_debug("OverlayManager: Target overlay hidden after initial selection")

def create_source_overlay_om(app):
    # If no source area provided on app instance, try to load from config
    if not app.source_area or len(app.source_area) != 4:
         try:
             # Load coordinates from config
             x1 = int(app.config['Settings'].get('source_area_x1', '0'))
             y1 = int(app.config['Settings'].get('source_area_y1', '0'))
             x2 = int(app.config['Settings'].get('source_area_x2', '200'))
             y2 = int(app.config['Settings'].get('source_area_y2', '100'))
             app.source_area = [x1, y1, x2, y2] # Update app's attribute
         except (ValueError, KeyError) as e:
             log_debug(f"OverlayManager: Could not load source area from config for overlay creation: {e}")
             return # Cannot proceed without valid area
    
    # Destroy existing overlay if it exists
    if app.source_overlay and app.source_overlay.winfo_exists():
        try:
            app.source_overlay.destroy()
        except tk.TclError:
            log_debug("OverlayManager: Error destroying existing source overlay (already gone?).")
        app.source_overlay = None

    # Create the new overlay frame
    try:
        # Use color from app's settings
        app.source_overlay = ResizableMovableFrame(app.root, app.source_area, bg_color=app.source_colour_var.get(), title="")
        app.source_overlay.attributes("-alpha", 0.7) # Higher value for less transparency (more visible)
        
        # Force the color to be applied properly after setting transparency
        app.source_overlay.update_color(app.source_colour_var.get())

        # Set initial visibility based on config - default to hidden
        should_be_visible = app.config['Settings'].getboolean('source_area_visible', fallback=False)
        if not should_be_visible and app.source_overlay.winfo_viewable():
            app.source_overlay.hide()
        elif should_be_visible and not app.source_overlay.winfo_viewable():
            app.source_overlay.show()
        else:
            # For new installations, hide by default
            app.source_overlay.hide()
            app.config['Settings']['source_area_visible'] = 'False'
        
        log_debug(f"OverlayManager: Created source overlay. Visible: {app.source_overlay.winfo_viewable()}")
    except Exception as e_cso:
        log_debug(f"OverlayManager: Error creating source overlay: {e_cso}")
        app.source_overlay = None

def _preserve_overlay_position(app):
    """Extract and save current overlay position before destruction to prevent position loss during recreation"""
    if not app.target_overlay:
        return
        
    try:
        current_geometry = None
        
        # For PySide overlays - use get_geometry method
        if hasattr(app.target_overlay, 'get_geometry'):
            current_geometry = app.target_overlay.get_geometry()
            log_debug(f"OverlayManager: Extracted PySide overlay geometry: {current_geometry}")
            
        # For tkinter overlays - use winfo methods
        elif hasattr(app.target_overlay, 'winfo_x') and hasattr(app.target_overlay, 'winfo_exists'):
            if app.target_overlay.winfo_exists():
                x = app.target_overlay.winfo_x()
                y = app.target_overlay.winfo_y()
                w = app.target_overlay.winfo_width()
                h = app.target_overlay.winfo_height()
                current_geometry = [x, y, x + w, y + h]
                log_debug(f"OverlayManager: Extracted tkinter overlay geometry: {current_geometry}")
        
        # Update app.target_area and config if we got valid geometry
        if current_geometry and len(current_geometry) == 4:
            app.target_area = current_geometry
            
            # Save to config immediately to persist across sessions
            app.config['Settings']['target_area_x1'] = str(current_geometry[0])
            app.config['Settings']['target_area_y1'] = str(current_geometry[1])
            app.config['Settings']['target_area_x2'] = str(current_geometry[2])
            app.config['Settings']['target_area_y2'] = str(current_geometry[3])
            
            log_debug(f"OverlayManager: Preserved overlay position: {current_geometry}")
        else:
            log_debug("OverlayManager: Could not extract valid overlay geometry")
            
    except Exception as e:
        log_debug(f"OverlayManager: Error preserving overlay position: {e}")

def create_target_overlay_om(app):
    if not app.target_area or len(app.target_area) != 4:
         try:
             x1 = int(app.config['Settings'].get('target_area_x1', '200'))
             y1 = int(app.config['Settings'].get('target_area_y1', '200'))
             x2 = int(app.config['Settings'].get('target_area_x2', '500'))
             y2 = int(app.config['Settings'].get('target_area_y2', '400'))
             app.target_area = [x1, y1, x2, y2]
         except (ValueError, KeyError) as e:
             log_debug(f"OverlayManager: Could not load target area from config for overlay creation: {e}")
             return

    # Clean up existing overlay - preserve position before destruction
    if app.target_overlay and hasattr(app.target_overlay, 'winfo_exists'):
        try:
            if app.target_overlay.winfo_exists():
                _preserve_overlay_position(app)  # Save current position before destroying
                app.target_overlay.destroy()
        except tk.TclError:
            log_debug("OverlayManager: Error destroying existing tkinter target overlay (already gone?).")
    elif app.target_overlay and hasattr(app.target_overlay, 'close'):
        try:
            _preserve_overlay_position(app)  # Save current position before destroying
            app.target_overlay.close()
        except:
            log_debug("OverlayManager: Error destroying existing PySide target overlay (already gone?).")

    app.target_overlay = None
    app.translation_text = None  # Reset text widget reference

    try:
        target_color = app.target_colour_var.get()

        # --- Read visual settings used by the tkinter fallback so we can mirror them for PySide ---
        # Font size (tkinter branch used this): default to 14 when var missing
        try:
            font_size = int(app.target_font_size_var.get())
        except Exception:
            font_size = int(app.config['Settings'].get('default_font_size', '14'))

        # Padding used in tkinter Text widget (padx, pady)
        pad_x = int(app.config['Settings'].get('target_text_pad_x', '5'))
        pad_y = int(app.config['Settings'].get('target_text_pad_y', '5'))

        # Top-bar height to match tkinter overlay feel (try to read from config, fallback to 10)
        top_bar_height = int(app.config['Settings'].get('target_top_bar_height', '10'))

        # Border thickness (tkinter Text used bd=0)
        border_px = int(app.config['Settings'].get('target_border_px', '0'))

        # Opacity (you previously set 0.85 for tkinter branch)
        opacity = float(app.config['Settings'].get('target_opacity', '0.85'))

        # Try to create PySide overlay for translation window if available
        if is_pyside_available():
            log_debug("OverlayManager: PySide6 available, attempting to create PySide overlay")
            pyside_manager = get_pyside_manager()

            # Pass visual consistency options into the PySide overlay
            app.target_overlay = pyside_manager.create_overlay(
                app.target_area,
                target_color,
                title="Translation",
                top_bar_height=top_bar_height,
                text_padding=(pad_x, pad_y),
                font_size=font_size,
                font_family="Arial",
                border_px=border_px,
                opacity=opacity
            )

            if app.target_overlay:
                # Store reference to PySide text widget for compatibility
                app.translation_text = app.target_overlay.text_widget
                # Ensure color & opacity applied immediately after creation
                app.target_overlay.update_color(target_color)
                try:
                    app.target_overlay.setWindowOpacity(opacity)
                except Exception:
                    pass
                log_debug("OverlayManager: PySide target overlay created successfully")
                log_debug(f"OverlayManager: Target overlay exists: {app.target_overlay.winfo_exists()}")
                # translation_text may be None if creation failed internally
                if hasattr(app, 'translation_text') and app.translation_text:
                    try:
                        log_debug(f"OverlayManager: Translation text exists: {app.translation_text.winfo_exists()}")
                    except Exception:
                        pass
            else:
                log_debug("OverlayManager: Failed to create PySide overlay, falling back to tkinter")
                app.target_overlay = None
        else:
            log_debug("OverlayManager: PySide6 not available, will use tkinter overlay")

        # Fallback to tkinter overlay if PySide is not available or failed (unchanged) ...
        if not app.target_overlay:
            log_debug("OverlayManager: Using tkinter target overlay as fallback")
            try:
                app.target_overlay = ResizableMovableFrame(app.root, app.target_area, bg_color=target_color, title="Translation")
                app.target_overlay.attributes("-alpha", opacity) # Less transparent to read text
                app.target_overlay.update_color(target_color)

                # font_size already read above
                target_lang_code = None
                try:
                    target_lang_name = app.target_lang_var.get()
                    if hasattr(app, 'language_manager') and app.language_manager:
                        current_model = app.translation_model_var.get()
                        if 'gemini' in current_model.lower():
                            target_lang_code = app.language_manager.get_code_from_name(target_lang_name, "gemini_api", "target")
                        elif current_model == "Google Translate API":
                            target_lang_code = app.language_manager.get_code_from_name(target_lang_name, "google_api", "target")
                        elif current_model == "DeepL API":
                            target_lang_code = app.language_manager.get_code_from_name(target_lang_name, "deepl_api", "target")
                        is_rtl = app.language_manager.is_rtl_language(target_lang_code) if target_lang_code else False
                        log_debug(f"OverlayManager: Target language '{target_lang_name}' (code: {target_lang_code}) RTL: {is_rtl}")
                    else:
                        is_rtl = False
                except Exception as e:
                    log_debug(f"OverlayManager: Error determining RTL status: {e}")
                    is_rtl = False

                text_justify = tk.RIGHT if is_rtl else tk.LEFT

                app.translation_text = tk.Text(
                    app.target_overlay.content_frame,
                    wrap=tk.WORD,
                    bg=target_color,
                    fg=app.target_text_colour_var.get(),
                    font=("Arial", font_size),
                    bd=border_px,
                    relief="flat",
                    padx=pad_x,
                    pady=pad_y,
                    state=tk.DISABLED
                )

                if is_rtl:
                    app.translation_text.tag_configure("rtl", justify=tk.RIGHT)
                    app.translation_text.is_rtl = True
                else:
                    app.translation_text.tag_configure("ltr", justify=tk.LEFT)
                    app.translation_text.is_rtl = False

                app.translation_text.bind("<Configure>", app.display_manager.on_translation_widget_resize)
                app.translation_text.pack(fill=tk.BOTH, expand=True)

                log_debug("OverlayManager: tkinter target overlay created successfully")
                log_debug(f"OverlayManager: Target overlay exists: {app.target_overlay.winfo_exists()}")
                log_debug(f"OverlayManager: Translation text exists: {app.translation_text.winfo_exists()}")

            except Exception as e_tkinter:
                log_debug(f"OverlayManager: Error creating tkinter target overlay: {e_tkinter}")
                app.target_overlay = None
                app.translation_text = None
                raise e_tkinter

        # Set target overlay visibility as before (unchanged)...
        should_be_visible = app.config['Settings'].getboolean('target_area_visible', fallback=False)
        if not should_be_visible and app.target_overlay.winfo_viewable():
            app.target_overlay.hide()
        elif should_be_visible and not app.target_overlay.winfo_viewable():
            app.target_overlay.show()
        else:
            app.target_overlay.hide()
            app.config['Settings']['target_area_visible'] = 'False'

        overlay_type = "PySide" if hasattr(app.translation_text, 'set_rtl_text') else "tkinter"
        log_debug(f"OverlayManager: {overlay_type} target overlay created. Visible: {app.target_overlay.winfo_viewable()}")

    except Exception as e_cto:
        log_debug(f"OverlayManager: Error creating target overlay: {e_cto}")
        app.target_overlay = None
        app.translation_text = None


def toggle_source_visibility_om(app):
    if app.source_overlay and app.source_overlay.winfo_exists():
        app.source_overlay.toggle_visibility()
        action = "hidden" if not app.source_overlay.winfo_viewable() else "shown"
        log_debug(f"OverlayManager: Source overlay {action} by user.")
    else:
        messagebox.showwarning("Warning", "Source area overlay window does not exist.\nPlease select the source area first.", parent=app.root)
        log_debug("OverlayManager: Toggle source visibility failed: Overlay does not exist.")

def toggle_target_visibility_om(app):
    if app.target_overlay and app.target_overlay.winfo_exists():
        # ISSUE 2 FIX: Ensure correct color when toggling visibility
        if hasattr(app.target_overlay, 'update_color'):
            app.target_overlay.update_color(app.target_colour_var.get())
        app.target_overlay.toggle_visibility()
        action = "hidden" if not app.target_overlay.winfo_viewable() else "shown"
        log_debug(f"OverlayManager: Target overlay {action} by user.")
    else:
        messagebox.showwarning("Warning", "Target area overlay window does not exist.\nPlease select the target area first.", parent=app.root)
        log_debug("OverlayManager: Toggle target visibility failed: Overlay does not exist.")

def load_areas_from_config_om(app):
    """Loads the source and target areas from saved config and creates overlays via OM functions."""
    try:
        # Load source area coordinates from config
        x1 = int(app.config['Settings'].get('source_area_x1', '0'))
        y1 = int(app.config['Settings'].get('source_area_y1', '0'))
        x2 = int(app.config['Settings'].get('source_area_x2', '200'))
        y2 = int(app.config['Settings'].get('source_area_y2', '100'))
        app.source_area = [x1, y1, x2, y2] # Set on app instance

        # Create source overlay if it doesn't exist or is destroyed
        if not app.source_overlay or not app.source_overlay.winfo_exists():
            create_source_overlay_om(app) # Use OM function
            log_debug(f"OverlayManager: Created source overlay from config: {app.source_area}")

        # Load target area coordinates
        target_x1 = int(app.config['Settings'].get('target_area_x1', '200'))
        target_y1 = int(app.config['Settings'].get('target_area_y1', '200'))
        target_x2 = int(app.config['Settings'].get('target_area_x2', '500'))
        target_y2 = int(app.config['Settings'].get('target_area_y2', '400'))
        app.target_area = [target_x1, target_y1, target_x2, target_y2] # Set on app instance

        if not app.target_overlay or not app.target_overlay.winfo_exists():
            create_target_overlay_om(app) # Use OM function
            log_debug(f"OverlayManager: Created target overlay from config: {app.target_area}")

    except (ValueError, KeyError) as e:
        log_debug(f"OverlayManager: Could not load areas from config: {e}")
