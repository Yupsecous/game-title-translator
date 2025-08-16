import tkinter as tk
from tkinter import messagebox # filedialog is not used here
import time
from logger import log_debug
from ui_elements import ResizableMovableFrame # Assuming ui_elements.py contains ResizableMovableFrame

def _select_screen_area_interactive(app, prompt_text, is_target=False):
    selection_result = None
    try:
        sel_win = tk.Toplevel(app.root)
        sel_win.attributes("-fullscreen", True)
        sel_win.attributes("-alpha", 0.6)  # Make it a bit more visible
        sel_win.configure(cursor="crosshair")
        sel_win.wait_visibility()
        sel_win.grab_set()
        sel_win.focus_force()
        
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
    app.root.withdraw()
    time.sleep(0.2)
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
    app.root.withdraw()
    time.sleep(0.2)
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

    if app.target_overlay and app.target_overlay.winfo_exists():
        try:
            app.target_overlay.destroy()
        except tk.TclError:
            log_debug("OverlayManager: Error destroying existing target overlay (already gone?).")
        app.target_overlay = None
    app.translation_text = None # Reset text widget reference too

    try:
        target_color = app.target_colour_var.get()
        app.target_overlay = ResizableMovableFrame(app.root, app.target_area, bg_color=target_color, title="Translation")
        app.target_overlay.attributes("-alpha", 0.85) # Less transparent to read text
        app.target_overlay.update_color(target_color)

        font_size = app.target_font_size_var.get() # Get from app's Tkinter IntVar
        
        # Determine text direction based on target language
        target_lang_code = None
        try:
            # Get the target language code from the current translation model
            target_lang_name = app.target_lang_var.get()
            if hasattr(app, 'language_manager') and app.language_manager:
                # Get the current translation model to determine service type
                current_model = app.translation_model_var.get()
                if 'gemini' in current_model.lower():
                    target_lang_code = app.language_manager.get_code_from_name(target_lang_name, "gemini_api", "target")
                elif current_model == "Google Translate API":
                    target_lang_code = app.language_manager.get_code_from_name(target_lang_name, "google_api", "target")
                elif current_model == "DeepL API":
                    target_lang_code = app.language_manager.get_code_from_name(target_lang_name, "deepl_api", "target")
                
                # Check if the target language is RTL
                is_rtl = app.language_manager.is_rtl_language(target_lang_code) if target_lang_code else False
                log_debug(f"OverlayManager: Target language '{target_lang_name}' (code: {target_lang_code}) RTL: {is_rtl}")
            else:
                is_rtl = False
        except Exception as e:
            log_debug(f"OverlayManager: Error determining RTL status: {e}")
            is_rtl = False
        
        # Configure text widget with appropriate settings for RTL/LTR
        text_justify = tk.RIGHT if is_rtl else tk.LEFT
        
        app.translation_text = tk.Text(
            app.target_overlay.content_frame,
            wrap=tk.WORD,
            bg=target_color,
            fg=app.target_text_colour_var.get(),
            font=("Arial", font_size),
            bd=0,
            relief="flat",
            padx=5,
            pady=5,
            state=tk.DISABLED
        )
        
        # Configure text widget for RTL if needed
        if is_rtl:
            # For RTL languages, configure text alignment and reading order
            app.translation_text.tag_configure("rtl", justify=tk.RIGHT)
            # Store RTL status for use in text updates
            app.translation_text.is_rtl = True
            log_debug("OverlayManager: Text widget configured for RTL display")
        else:
            app.translation_text.tag_configure("ltr", justify=tk.LEFT)
            app.translation_text.is_rtl = False
        app.translation_text.pack(fill=tk.BOTH, expand=True)
        
        # Set target overlay to hidden by default or based on config
        should_be_visible = app.config['Settings'].getboolean('target_area_visible', fallback=False)
        if not should_be_visible and app.target_overlay.winfo_viewable():
            app.target_overlay.hide()
        elif should_be_visible and not app.target_overlay.winfo_viewable():
            app.target_overlay.show()
        else:
            # For new installations, hide by default
            app.target_overlay.hide()
            app.config['Settings']['target_area_visible'] = 'False'
            
        log_debug(f"OverlayManager: Target overlay and text widget created. Visible: {app.target_overlay.winfo_viewable()}")
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
