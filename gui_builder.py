# gui_builder.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
import os
from logger import log_debug
from ui_elements import create_scrollable_tab

def create_main_tab(app):
    # Create a scrollable tab content frame
    scrollable_content = create_scrollable_tab(app.tab_control, app.ui_lang.get_label("main_tab_title"))
    app.tab_main = scrollable_content
    
    # Create the main frame inside the scrollable area
    frame = ttk.LabelFrame(scrollable_content, text=app.ui_lang.get_label("main_tab_title"))
    frame.pack(fill="both", expand=True, padx=10, pady=10)

    # Add GUI language selection at the top
    language_frame = ttk.Frame(frame)
    language_frame.grid(row=0, column=0, columnspan=2, padx=5, pady=5, sticky="w")
    
    ttk.Label(language_frame, text=app.ui_lang.get_label("gui_language_label")).pack(side=tk.LEFT, padx=(0,5))
    app.gui_language_combobox = ttk.Combobox(language_frame, textvariable=app.gui_language_var,
                                           values=app.ui_lang.get_language_list(), width=15, state='readonly')
    app.gui_language_combobox.pack(side=tk.LEFT)
    
    def on_gui_language_changed(event):
        selected_display_name = app.gui_language_var.get()
        lang_code = app.ui_lang.get_language_code_from_name(selected_display_name)
        
        log_debug(f"GUI Language Change: selected_display='{selected_display_name}', lang_code='{lang_code}', current_lang='{app.ui_lang.current_lang}'")
        
        if lang_code != app.ui_lang.current_lang:
            log_debug(f"Changing GUI language from {app.ui_lang.current_lang} to {lang_code}")
            app.ui_lang.load_language(lang_code)
            
            # Log the new state after language change
            log_debug(f"GUI language changed - new current_lang: '{app.ui_lang.current_lang}'")
            
            # Update all dropdowns with new language before rebuilding UI
            app.ui_interaction_handler.update_all_dropdowns_for_language_change()
            
            # This complete UI rebuild is necessary to update all elements
            app.update_ui_language()
            app.save_settings()
        else:
            log_debug(f"GUI language unchanged: {lang_code}")
    
    app.gui_language_combobox.bind('<<ComboboxSelected>>', on_gui_language_changed)

    ttk.Button(frame, text=app.ui_lang.get_label("select_source_btn"), command=app.select_source_area, width=30).grid(row=1, column=0, padx=5, pady=5, sticky="w")
    ttk.Button(frame, text=app.ui_lang.get_label("select_target_btn"), command=app.select_target_area, width=30).grid(row=2, column=0, padx=5, pady=5, sticky="w")
    app.start_stop_btn = ttk.Button(frame, text=app.ui_lang.get_label("start_btn"), command=app.toggle_translation, width=30)
    app.start_stop_btn.grid(row=3, column=0, padx=5, pady=5, sticky="w")
    
    # Remove individual tab bindings and add a general binding in app_logic.py after tabs are created
    app.main_tab_start_button = app.start_stop_btn  # Store reference for the tab changed handler in app_logic.py
    ttk.Button(frame, text=app.ui_lang.get_label("hide_source_btn"), command=app.toggle_source_visibility, width=30).grid(row=4, column=0, padx=5, pady=5, sticky="w")
    ttk.Button(frame, text=app.ui_lang.get_label("hide_target_btn"), command=app.toggle_target_visibility, width=30).grid(row=5, column=0, padx=5, pady=5, sticky="w")
    ttk.Button(frame, text=app.ui_lang.get_label("clear_cache_btn"), command=app.clear_cache, width=30).grid(row=6, column=0, padx=5, pady=5, sticky="w")
    ttk.Button(frame, text=app.ui_lang.get_label("clear_debug_log_btn"), command=app.clear_debug_log, width=30).grid(row=7, column=0, padx=5, pady=5, sticky="w")
    
    # Debug log toggle button
    if app.debug_logging_enabled_var.get():
        initial_debug_toggle_text = app.ui_lang.get_label("toggle_debug_log_disable_btn")
    else:
        initial_debug_toggle_text = app.ui_lang.get_label("toggle_debug_log_enable_btn")
    app.debug_log_toggle_btn = ttk.Button(frame, text=initial_debug_toggle_text, command=app.toggle_debug_logging, width=30)
    app.debug_log_toggle_btn.grid(row=8, column=0, padx=5, pady=5, sticky="w")

    if app.KEYBOARD_AVAILABLE:
        shortcuts_frame = ttk.LabelFrame(frame, text=app.ui_lang.get_label("keyboard_shortcuts_title"))
        shortcuts_frame.grid(row=9, column=0, columnspan=2, padx=5, pady=10, sticky="ew")
        ttk.Label(shortcuts_frame, text="~ : " + app.ui_lang.get_label("shortcut_start_stop", "Start/Stop Translation")).grid(row=0, column=0, padx=10, pady=2, sticky="w")
        ttk.Label(shortcuts_frame, text="Alt+1 : " + app.ui_lang.get_label("shortcut_toggle_source", "Toggle Source Window Visibility")).grid(row=1, column=0, padx=10, pady=2, sticky="w")
        ttk.Label(shortcuts_frame, text="Alt+2 : " + app.ui_lang.get_label("shortcut_toggle_target", "Toggle Translation Window Visibility")).grid(row=2, column=0, padx=10, pady=2, sticky="w")
        ttk.Label(shortcuts_frame, text="Alt+S : " + app.ui_lang.get_label("shortcut_save_settings", "Save Settings")).grid(row=3, column=0, padx=10, pady=2, sticky="w")
        ttk.Label(shortcuts_frame, text="Alt+C : " + app.ui_lang.get_label("shortcut_clear_cache", "Clear Cache")).grid(row=4, column=0, padx=10, pady=2, sticky="w")
        ttk.Label(shortcuts_frame, text="Alt+L : " + app.ui_lang.get_label("shortcut_clear_log", "Clear Debug Log")).grid(row=5, column=0, padx=10, pady=(2,8), sticky="w")
        status_row = 10
        app.status_label = ttk.Label(frame, text=app.ui_lang.get_label("status_ready_hotkey"))
    else:
        status_row = 9
        app.status_label = ttk.Label(frame, text=app.ui_lang.get_label("status_ready"))
    
    app.status_label.grid(row=status_row, column=0, columnspan=2, padx=5, pady=5, sticky="w")
    frame.columnconfigure(0, weight=1)


def create_settings_tab(app):
    # Create a scrollable tab content frame
    scrollable_content = create_scrollable_tab(app.tab_control, app.ui_lang.get_label("settings_tab_title"))
    app.tab_settings = scrollable_content
    
    # Create the settings frame inside the scrollable area
    frame = ttk.LabelFrame(scrollable_content, text=app.ui_lang.get_label("settings_tab_title"))
    frame.pack(fill="both", expand=True, padx=10, pady=10)

    def validate_int_range(P, min_val, max_val):
        if P == "": return True
        try:
            value = int(P)
            return min_val <= value <= max_val
        except ValueError: return False

    def validate_odd_int_range(P, min_val, max_val):
        if P == "": return True
        try:
            value = int(P)
            return min_val <= value <= max_val and value % 2 == 1  # Must be odd
        except ValueError: return False
            
    # Validation functions for parameters
    validate_block_size = frame.register(lambda P: validate_odd_int_range(P, 3, 101))
    validate_c_value = frame.register(lambda P: validate_int_range(P, -75, 75))
    validate_beam_size = frame.register(lambda P: validate_int_range(P, 1, 50))
    validate_scan_interval = frame.register(lambda P: validate_int_range(P, 50, 2000))
    validate_timeout = frame.register(lambda P: validate_int_range(P, 0, 60))
    validate_stability = frame.register(lambda P: validate_int_range(P, 0, 5))
    validate_confidence = frame.register(lambda P: validate_int_range(P, 0, 100))
    validate_font_size = frame.register(lambda P: validate_int_range(P, 8, 72))
    
    style = ttk.Style()
    
    # Configure TCombobox style for better readability when focused
    # Simple fix: just change text color to white when focused (blue background is system default)
    style.map('TCombobox',
        foreground=[
            ('readonly', 'focus', 'white'),      # White text when focused for better contrast
            ('readonly', '!focus', 'black'),     # Black text when not focused  
            ('!readonly', 'focus', 'white'),     # White text when focused (editable)
            ('!readonly', '!focus', 'black')     # Black text when not focused (editable)
        ]
    )

    # Ensure no insertion cursor is visible
    style.configure('TCombobox',
                    insertwidth=0,
                    insertontime=0
                   )

    # Wrapper function to shift focus after combobox selection
    def create_combobox_handler_wrapper(original_handler_func):
        def wrapper(event):
            # Call the original handler
            original_handler_func(event)

            # Schedule focus shift to the parent tab frame (app.tab_settings)
            widget = event.widget
            if widget.winfo_exists() and app.tab_settings.winfo_exists():
                widget.after_idle(app.tab_settings.focus_set)
        return wrapper

    # Row 0: Translation Model Selection
    ttk.Label(frame, text=app.ui_lang.get_label("translation_model_label")).grid(row=0, column=0, padx=5, pady=5, sticky="w")
    
    translation_models_available_for_ui = []
    if app.MARIANMT_AVAILABLE: translation_models_available_for_ui.append(app.translation_model_names['marianmt'])
    if app.DEEPL_API_AVAILABLE: translation_models_available_for_ui.append(app.translation_model_names['deepl_api'])
    if app.GOOGLE_TRANSLATE_API_AVAILABLE: translation_models_available_for_ui.append(app.translation_model_names['google_api'])
    if not translation_models_available_for_ui: 
        default_model_key_from_var = app.translation_model_var.get() 
        translation_models_available_for_ui.append(app.translation_model_names.get(default_model_key_from_var, "MarianMT (offline and free)"))

    app.translation_model_combobox = ttk.Combobox(frame, textvariable=app.translation_model_display_var,
                                           values=translation_models_available_for_ui, width=25, state='readonly')
    app.translation_model_combobox.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
    
    def handle_translation_model_selection(event):
        app.on_translation_model_selection_changed(event=event, initial_setup=False)
    app.translation_model_combobox.bind('<<ComboboxSelected>>', 
        create_combobox_handler_wrapper(handle_translation_model_selection))


    app.source_lang_label = ttk.Label(frame, text=app.ui_lang.get_label("source_lang_label"))
    app.source_lang_label.grid(row=1, column=0, padx=5, pady=5, sticky="w")
    app.source_lang_combobox = ttk.Combobox(frame, textvariable=app.source_display_var, width=25, state='readonly')
    app.source_lang_combobox.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

    def on_source_lang_gui_changed(event):
        selected_display_name = app.source_display_var.get()
        active_model = app.translation_model_var.get()
        
        # Get current UI language - more robust detection
        current_ui_language = app.ui_lang.current_lang
        ui_language_for_lookup = 'polish' if current_ui_language == 'pol' else 'english'
        
        log_debug(f"Source lang GUI changed: selected='{selected_display_name}', model='{active_model}', ui_lang='{current_ui_language}', lookup='{ui_language_for_lookup}'")
        
        # Convert localized display name back to API code
        # Use the correct provider format for lookup
        provider_for_lookup = active_model  # Keep original format: 'google_api', 'deepl_api'
        api_code = app.language_manager.get_code_from_localized_name(
            selected_display_name, provider_for_lookup, ui_language_for_lookup)
        
        log_debug(f"Lookup result: '{selected_display_name}' -> '{api_code}'")
        
        if api_code:
            if active_model == 'google_api': 
                app.google_source_lang = api_code
                log_debug(f"Google source lang set to: {api_code}")
            elif active_model == 'deepl_api': 
                app.deepl_source_lang = api_code
                log_debug(f"DeepL source lang set to: {api_code}")
            
            app.source_lang_var.set(api_code) 
            log_debug(f"Source lang GUI changed for {active_model}: Display='{selected_display_name}', API Code='{api_code}' - SAVING")
            app.save_settings() 
        else:
            log_debug(f"ERROR: Could not find API code for source display '{selected_display_name}' / model '{active_model}' / ui_language '{ui_language_for_lookup}' - not saving invalid value")
            # Don't save invalid values - keep the previous valid selection
    
    app.source_lang_combobox.bind('<<ComboboxSelected>>', 
        create_combobox_handler_wrapper(on_source_lang_gui_changed))


    app.target_lang_label = ttk.Label(frame, text=app.ui_lang.get_label("target_lang_label"))
    app.target_lang_label.grid(row=2, column=0, padx=5, pady=5, sticky="w")
    app.target_lang_combobox = ttk.Combobox(frame, textvariable=app.target_display_var, width=25, state='readonly')
    app.target_lang_combobox.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

    def on_target_lang_gui_changed(event):
        selected_display_name = app.target_display_var.get()
        active_model = app.translation_model_var.get()
        
        # Get current UI language - more robust detection
        current_ui_language = app.ui_lang.current_lang
        ui_language_for_lookup = 'polish' if current_ui_language == 'pol' else 'english'
        
        log_debug(f"Target lang GUI changed: selected='{selected_display_name}', model='{active_model}', ui_lang='{current_ui_language}', lookup='{ui_language_for_lookup}'")
        
        # Convert localized display name back to API code
        # Use the correct provider format for lookup
        provider_for_lookup = active_model  # Keep original format: 'google_api', 'deepl_api'
        api_code = app.language_manager.get_code_from_localized_name(
            selected_display_name, provider_for_lookup, ui_language_for_lookup)
        
        log_debug(f"Lookup result: '{selected_display_name}' -> '{api_code}'")
        
        if api_code:
            if active_model == 'google_api': 
                app.google_target_lang = api_code
                log_debug(f"Google target lang set to: {api_code}")
            elif active_model == 'deepl_api': 
                app.deepl_target_lang = api_code
                log_debug(f"DeepL target lang set to: {api_code}")
            
            app.target_lang_var.set(api_code)
            log_debug(f"Target lang GUI changed for {active_model}: Display='{selected_display_name}', API Code='{api_code}' - SAVING")
            app.save_settings() 
        else:
            log_debug(f"ERROR: Could not find API code for target display '{selected_display_name}' / model '{active_model}' / ui_language '{ui_language_for_lookup}' - not saving invalid value")
            # Don't save invalid values - keep the previous valid selection
    app.target_lang_combobox.bind('<<ComboboxSelected>>', 
        create_combobox_handler_wrapper(on_target_lang_gui_changed))


    app.marian_model_label = ttk.Label(frame, text=app.ui_lang.get_label("marian_model_label"))
    app.marian_model_label.grid(row=3, column=0, padx=5, pady=5, sticky="w")
    app.marian_model_combobox = ttk.Combobox(frame, textvariable=app.marian_model_display_var, 
                                             values=app.marian_models_list, width=25, state='readonly')
    app.marian_model_combobox.grid(row=3, column=1, padx=5, pady=5, sticky="ew")
    
    def handle_marian_model_selection(event):
        # The marian_models_dict now contains localized display names as keys
        # so we can use the existing logic
        app.on_marian_model_selection_changed(event=event, initial_setup=False)
    app.marian_model_combobox.bind('<<ComboboxSelected>>', 
        create_combobox_handler_wrapper(handle_marian_model_selection))
    
    app.google_api_key_label = ttk.Label(frame, text=app.ui_lang.get_label("google_api_key_label")) 
    app.google_api_key_label.grid(row=4, column=0, padx=5, pady=5, sticky="w")
    app.google_api_key_entry = ttk.Entry(frame, textvariable=app.google_api_key_var, width=40, show="*")
    app.google_api_key_entry.grid(row=4, column=1, padx=5, pady=5, sticky="ew")
    # Set initial button text based on visibility
    initial_google_text = app.ui_lang.get_label("show_btn", "Show")
    if hasattr(app, 'google_api_key_visible') and app.google_api_key_visible:
        initial_google_text = app.ui_lang.get_label("hide_btn", "Hide")
    app.google_api_key_button = ttk.Button(frame, text=initial_google_text, width=5, 
                                          command=lambda: app.toggle_api_key_visibility("google"))
    app.google_api_key_button.grid(row=4, column=2, padx=5, pady=5, sticky="w")

    app.deepl_api_key_label = ttk.Label(frame, text=app.ui_lang.get_label("deepl_api_key_label")) 
    app.deepl_api_key_label.grid(row=5, column=0, padx=5, pady=5, sticky="w")
    app.deepl_api_key_entry = ttk.Entry(frame, textvariable=app.deepl_api_key_var, width=40, show="*")
    app.deepl_api_key_entry.grid(row=5, column=1, padx=5, pady=5, sticky="ew")
    # Set initial button text based on visibility
    initial_deepl_text = app.ui_lang.get_label("show_btn", "Show") 
    if hasattr(app, 'deepl_api_key_visible') and app.deepl_api_key_visible:
        initial_deepl_text = app.ui_lang.get_label("hide_btn", "Hide")
    app.deepl_api_key_button = ttk.Button(frame, text=initial_deepl_text, width=5,
                                         command=lambda: app.toggle_api_key_visibility("deepl"))
    app.deepl_api_key_button.grid(row=5, column=2, padx=5, pady=5, sticky="w")

    # DeepL Model Type Selection (only visible when DeepL is selected)
    app.deepl_model_type_label = ttk.Label(frame, text=app.ui_lang.get_label("deepl_model_type_label", "Quality"))
    app.deepl_model_type_label.grid(row=6, column=0, padx=5, pady=5, sticky="w")
    
    # Create model type options with user-friendly names
    deepl_model_options = [
        ("latency_optimized", app.ui_lang.get_label("deepl_classic_model", "Classic")),
        ("quality_optimized", app.ui_lang.get_label("deepl_nextgen_model", "Next-gen"))
    ]
    
    app.deepl_model_display_var = tk.StringVar()
    # Set initial display value based on current setting
    current_model_type = app.deepl_model_type_var.get()
    for value, display in deepl_model_options:
        if value == current_model_type:
            app.deepl_model_display_var.set(display)
            break
    else:
        # Fallback if current setting doesn't match any option
        app.deepl_model_display_var.set(deepl_model_options[0][1])  # Default to Classic
    
    app.deepl_model_type_combobox = ttk.Combobox(frame, textvariable=app.deepl_model_display_var,
                                               values=[display for _, display in deepl_model_options], 
                                               width=25, state='readonly')
    app.deepl_model_type_combobox.grid(row=6, column=1, padx=5, pady=5, sticky="ew")
    
    def on_deepl_model_type_changed(event):
        selected_display = app.deepl_model_display_var.get()
        # Find the corresponding value
        for value, display in deepl_model_options:
            if display == selected_display:
                app.deepl_model_type_var.set(value)
                log_debug(f"DeepL model type changed to: {value} (display: {display})")
                if app._fully_initialized:
                    app.save_settings()
                break
    
    app.deepl_model_type_combobox.bind('<<ComboboxSelected>>', 
        create_combobox_handler_wrapper(on_deepl_model_type_changed))

    # Store the options for later use when updating language
    app.deepl_model_options = deepl_model_options
    
    # Function to update DeepL model type options when language changes
    def update_deepl_model_type_for_language():
        if hasattr(app, 'deepl_model_type_combobox') and app.deepl_model_type_combobox.winfo_exists():
            # Get current model type setting
            current_model_type = app.deepl_model_type_var.get()
            
            # Update options with new language
            new_deepl_model_options = [
                ("latency_optimized", app.ui_lang.get_label("deepl_classic_model", "Classic")),
                ("quality_optimized", app.ui_lang.get_label("deepl_nextgen_model", "Next-gen"))
            ]
            
            # Update combobox values
            app.deepl_model_type_combobox['values'] = [display for _, display in new_deepl_model_options]
            
            # Restore selection based on current setting
            for value, display in new_deepl_model_options:
                if value == current_model_type:
                    app.deepl_model_display_var.set(display)
                    break
            else:
                # Fallback to first option if current setting not found
                app.deepl_model_display_var.set(new_deepl_model_options[0][1])
            
            # Update stored options
            app.deepl_model_options = new_deepl_model_options
            log_debug(f"Updated DeepL model type options for language change")
    
    # Store function reference for calling during language updates
    app.update_deepl_model_type_for_language = update_deepl_model_type_for_language


    app.models_file_label = ttk.Label(frame, text=app.ui_lang.get_label("models_file_label")) 
    app.models_file_label.grid(row=7, column=0, padx=5, pady=5, sticky="w")
    app.models_file_frame = ttk.Frame(frame)
    app.models_file_frame.grid(row=7, column=1, columnspan=2, padx=5, pady=5, sticky="ew")
    app.models_file_entry = ttk.Entry(app.models_file_frame, textvariable=app.models_file_var)
    app.models_file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
    app.models_file_button = ttk.Button(app.models_file_frame, text=app.ui_lang.get_label("browse_btn"), command=app.browse_marian_models_file)
    app.models_file_button.pack(side=tk.RIGHT, padx=(5,0))

    app.beam_size_label = ttk.Label(frame, text=app.ui_lang.get_label("beam_size_label")) 
    app.beam_size_label.grid(row=8, column=0, padx=5, pady=5, sticky="w")
    app.beam_spinbox = ttk.Spinbox(frame, from_=1, to=50, textvariable=app.num_beams_var, width=10,
                                  validate="key", validatecommand=(validate_beam_size, '%P'))
    app.beam_spinbox.grid(row=8, column=1, padx=5, pady=5, sticky="w")
    def on_beam_spinbox_focus_out(event):
        try:
            value = int(app.num_beams_var.get())
            clamped = max(1, min(50, value))
            if clamped != value: app.num_beams_var.set(clamped)
            app.update_marian_beam_value() 
        except (ValueError, tk.TclError): app.num_beams_var.set(2) 
        app.save_settings() 
    app.beam_spinbox.bind("<FocusOut>", on_beam_spinbox_focus_out)

    app.marian_explanation_labels = [] 
    row_offset = 9
    if app.MARIANMT_AVAILABLE:
        texts = [
            app.ui_lang.get_label("marian_beam_explanation", "Higher beam values = better but slower translations"),
            app.ui_lang.get_label("marian_quality_note", "Note: MarianMT provides higher quality translations"),
            app.ui_lang.get_label("marian_quality_vary", "for many language pairs. Quality may vary by language."),
            app.ui_lang.get_label("marian_download_note", "Models are downloaded on first use (requires internet).")
        ]
    else:
        texts = [
            app.ui_lang.get_label("marian_unavailable_line1", "MarianMT is not available. To enable, install:"),
            app.ui_lang.get_label("marian_unavailable_line2", "pip install transformers torch sentencepiece")
        ]
    for i, text_content in enumerate(texts):
        lbl = ttk.Label(frame, text=text_content)
        lbl.grid(row=row_offset + i, column=0, columnspan=3, padx=5, pady=0, sticky="w")
        app.marian_explanation_labels.append(lbl)
    current_row = row_offset + len(texts)

    ttk.Label(frame, text=app.ui_lang.get_label("tesseract_path_label")).grid(row=current_row, column=0, padx=5, pady=5, sticky="w") 
    path_frame_settings = ttk.Frame(frame) # Renamed to avoid conflict with debug tab's path_frame
    path_frame_settings.grid(row=current_row, column=1, columnspan=2, padx=5, pady=5, sticky="ew")
    app.tesseract_path_entry = ttk.Entry(path_frame_settings, textvariable=app.tesseract_path_var) 
    app.tesseract_path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
    ttk.Button(path_frame_settings, text=app.ui_lang.get_label("browse_btn"), command=app.browse_tesseract).pack(side=tk.RIGHT, padx=(5,0))
    current_row += 1

    ttk.Label(frame, text=app.ui_lang.get_label("scan_interval_label")).grid(row=current_row, column=0, padx=5, pady=5, sticky="w") 
    scan_spinbox = ttk.Spinbox(frame, from_=50, to=2000, increment=50, textvariable=app.scan_interval_var, 
                             width=10, validate="key", validatecommand=(validate_scan_interval, '%P'))
    scan_spinbox.grid(row=current_row, column=1, padx=5, pady=5, sticky="w")
    def on_scan_interval_focus_out(event):
        try:
            value = int(app.scan_interval_var.get())
            if not (50 <= value <= 2000): app.scan_interval_var.set(max(50, min(2000, value)))
        except (ValueError, tk.TclError): app.scan_interval_var.set(200)
        app.save_settings()
    scan_spinbox.bind("<FocusOut>", on_scan_interval_focus_out)
    current_row += 1

    ttk.Label(frame, text=app.ui_lang.get_label("clear_timeout_label")).grid(row=current_row, column=0, padx=5, pady=5, sticky="w") 
    timeout_spinbox = ttk.Spinbox(frame, from_=0, to=60, textvariable=app.clear_translation_timeout_var, 
                                width=10, validate="key", validatecommand=(validate_timeout, '%P'))
    timeout_spinbox.grid(row=current_row, column=1, padx=5, pady=5, sticky="w")
    def on_timeout_focus_out(event):
        try:
            value = int(app.clear_translation_timeout_var.get())
            if not (0 <= value <= 60): app.clear_translation_timeout_var.set(max(0, min(60, value)))
            app.clear_translation_timeout = app.clear_translation_timeout_var.get() 
        except (ValueError, tk.TclError): app.clear_translation_timeout_var.set(0)
        app.save_settings()
    timeout_spinbox.bind("<FocusOut>", on_timeout_focus_out)
    current_row += 1
    
    ttk.Label(frame, text=app.ui_lang.get_label("stability_threshold_label")).grid(row=current_row, column=0, padx=5, pady=5, sticky="w") 
    stability_spinbox = ttk.Spinbox(frame, from_=0, to=5, textvariable=app.stability_var, 
                                  width=10, validate="key", validatecommand=(validate_stability, '%P'))
    stability_spinbox.grid(row=current_row, column=1, padx=5, pady=5, sticky="w")
    def on_stability_focus_out(event):
        try:
            value = int(app.stability_var.get())
            if not (0 <= value <= 5) : app.stability_var.set(max(0, min(5,value)))
            app.update_stability_from_spinbox() 
        except (ValueError, tk.TclError): app.stability_var.set(0)
        app.save_settings()
    stability_spinbox.bind("<FocusOut>", on_stability_focus_out)
    current_row += 1

    ttk.Label(frame, text=app.ui_lang.get_label("confidence_threshold_label")).grid(row=current_row, column=0, padx=5, pady=5, sticky="w") 
    confidence_spinbox = ttk.Spinbox(frame, from_=0, to=100, textvariable=app.confidence_var, 
                                   width=10, validate="key", validatecommand=(validate_confidence, '%P'))
    confidence_spinbox.grid(row=current_row, column=1, padx=5, pady=5, sticky="w")
    def on_confidence_focus_out(event):
        try:
            value = int(app.confidence_var.get())
            if not (0 <= value <= 100) : app.confidence_var.set(max(0, min(100, value)))
            app.confidence_threshold = app.confidence_var.get() 
        except (ValueError, tk.TclError): app.confidence_var.set(50)
        app.save_settings()
    confidence_spinbox.bind("<FocusOut>", on_confidence_focus_out)
    current_row += 1
    
    ttk.Label(frame, text=app.ui_lang.get_label("preprocessing_mode_label")).grid(row=current_row, column=0, padx=5, pady=5, sticky="w") 
    
    # Create a display mapping for the preprocessing mode
    preprocessing_values = {
        'none': app.ui_lang.get_label("preprocessing_none", "None"),
        'binary': app.ui_lang.get_label("preprocessing_binary", "Binary"),
        'binary_inv': app.ui_lang.get_label("preprocessing_binary_inv", "Binary Inverted"),
        'adaptive': app.ui_lang.get_label("preprocessing_adaptive", "Adaptive")
    }
    
    # Convert values to list for dropdown
    preprocessing_list = ['none', 'binary', 'binary_inv', 'adaptive']
    
    # Create a custom StringVar for display
    display_var = tk.StringVar()
    
    # Set current display value
    current_value = app.preprocessing_mode_var.get()
    display_var.set(preprocessing_values.get(current_value, preprocessing_values['none']))
    
    # Create combobox with display values
    preprocessing_display_values = [preprocessing_values[val] for val in preprocessing_list]
    preprocessing_combobox = ttk.Combobox(frame, textvariable=display_var, 
                                       values=preprocessing_display_values, width=15, state='readonly')
    preprocessing_combobox.grid(row=current_row, column=1, padx=5, pady=5, sticky="w")
    
    # Create mapping from display name back to value
    display_to_value = {display: value for value, display in preprocessing_values.items()}
    
    def on_preprocessing_combo_selected(event): 
        # Get selected display value
        selected_display = display_var.get()
        # Map back to actual value
        actual_value = display_to_value.get(selected_display, 'none')
        # Update the actual value
        app.preprocessing_mode_var.set(actual_value)
        app.save_settings()
    
    preprocessing_combobox.bind('<<ComboboxSelected>>', 
        create_combobox_handler_wrapper(on_preprocessing_combo_selected))
    current_row += 1

    # Adaptive thresholding parameters (shown only when Adaptive is selected)
    app.adaptive_block_size_label = ttk.Label(frame, text=app.ui_lang.get_label("adaptive_block_size_label", "Block Size"))
    app.adaptive_block_size_label.grid(row=current_row, column=0, padx=5, pady=5, sticky="w")
    app.adaptive_block_size_spinbox = ttk.Spinbox(frame, from_=3, to=101, increment=2, textvariable=app.adaptive_block_size_var, 
                                                 width=10, validate="key", validatecommand=(validate_block_size, '%P'))
    app.adaptive_block_size_spinbox.grid(row=current_row, column=1, padx=5, pady=5, sticky="w")
    def on_block_size_focus_out(event):
        try:
            value = int(app.adaptive_block_size_var.get())
            # Ensure odd number in range
            if value % 2 == 0:
                value += 1  # Make odd
            clamped = max(3, min(101, value))
            if clamped != app.adaptive_block_size_var.get():
                app.adaptive_block_size_var.set(clamped)
        except (ValueError, tk.TclError): 
            app.adaptive_block_size_var.set(41)
        app.save_settings()
    app.adaptive_block_size_spinbox.bind("<FocusOut>", on_block_size_focus_out)
    current_row += 1

    app.adaptive_c_label = ttk.Label(frame, text=app.ui_lang.get_label("adaptive_c_label", "C Value"))
    app.adaptive_c_label.grid(row=current_row, column=0, padx=5, pady=5, sticky="w")
    app.adaptive_c_spinbox = ttk.Spinbox(frame, from_=-75, to=75, textvariable=app.adaptive_c_var, 
                                        width=10, validate="key", validatecommand=(validate_c_value, '%P'))
    app.adaptive_c_spinbox.grid(row=current_row, column=1, padx=5, pady=5, sticky="w")
    def on_c_value_focus_out(event):
        try:
            value = int(app.adaptive_c_var.get())
            clamped = max(-75, min(75, value))
            if clamped != app.adaptive_c_var.get():
                app.adaptive_c_var.set(clamped)
        except (ValueError, tk.TclError): 
            app.adaptive_c_var.set(-60)
        app.save_settings()
    app.adaptive_c_spinbox.bind("<FocusOut>", on_c_value_focus_out)
    current_row += 1

    # Function to show/hide adaptive parameters based on preprocessing mode
    def update_adaptive_fields_visibility():
        mode = app.preprocessing_mode_var.get()
        if mode == 'adaptive':
            app.adaptive_block_size_label.grid()
            app.adaptive_block_size_spinbox.grid()
            app.adaptive_c_label.grid()
            app.adaptive_c_spinbox.grid()
        else:
            app.adaptive_block_size_label.grid_remove()
            app.adaptive_block_size_spinbox.grid_remove()
            app.adaptive_c_label.grid_remove()
            app.adaptive_c_spinbox.grid_remove()
    
    # Store reference to update function for later use
    app.update_adaptive_fields_visibility = update_adaptive_fields_visibility
    
    # Update the preprocessing combo selection handler to show/hide fields
    original_preprocessing_handler = on_preprocessing_combo_selected
    def on_preprocessing_combo_selected_with_visibility(event):
        original_preprocessing_handler(event)
        update_adaptive_fields_visibility()
    
    # Rebind with new handler
    preprocessing_combobox.bind('<<ComboboxSelected>>', 
        create_combobox_handler_wrapper(on_preprocessing_combo_selected_with_visibility))
    
    # Initial visibility update
    update_adaptive_fields_visibility()
    current_row += 1

    # Create a frame for the OCR debugging label and preview button
    ocr_debug_frame = ttk.Frame(frame)
    ocr_debug_frame.grid(row=current_row, column=0, columnspan=3, padx=5, pady=5, sticky="ew")
    
    ttk.Label(ocr_debug_frame, text=app.ui_lang.get_label("ocr_debugging_label")).pack(side=tk.LEFT)
    ttk.Checkbutton(ocr_debug_frame, text=app.ui_lang.get_label("show_debug_checkbox"), variable=app.ocr_debugging_var).pack(side=tk.LEFT, padx=(5,0))
    
    # Add Preview button
    ttk.Button(ocr_debug_frame, text=app.ui_lang.get_label("preview_btn", "Preview"), 
               command=app.show_ocr_preview).pack(side=tk.LEFT, padx=(10,0))
    current_row += 1

    ttk.Label(frame, text=app.ui_lang.get_label("remove_trailing_label")).grid(row=current_row, column=0, padx=5, pady=5, sticky="w") 
    ttk.Checkbutton(frame, text=app.ui_lang.get_label("remove_trailing_checkbox"), variable=app.remove_trailing_garbage_var).grid(row=current_row, column=1, padx=5, pady=5, sticky="w")
    current_row += 1
    
    color_options = [ 
        (app.ui_lang.get_label("source_color_label"), app.source_colour_var, 'source'),
        (app.ui_lang.get_label("target_color_label"), app.target_colour_var, 'target'),
        (app.ui_lang.get_label("target_text_color_label"), app.target_text_colour_var, 'target_text')
    ]
    app.color_displays = {}
    for i, (label_text, var, color_type) in enumerate(color_options):
        ttk.Label(frame, text=label_text).grid(row=current_row + i, column=0, padx=5, pady=5, sticky="w")
        color_frame_inner = ttk.Frame(frame)
        color_frame_inner.grid(row=current_row + i, column=1, columnspan=2, padx=5, pady=5, sticky="w")
        
        app.color_displays[color_type] = tk.Label(color_frame_inner, width=3, relief="solid", bg=var.get())
        app.color_displays[color_type].pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(color_frame_inner, text=app.ui_lang.get_label("choose_color_btn"), command=lambda ct=color_type: app.choose_color_for_settings(ct)).pack(side=tk.LEFT)
    current_row += len(color_options)

    ttk.Label(frame, text=app.ui_lang.get_label("font_size_label")).grid(row=current_row, column=0, padx=5, pady=5, sticky="w") 
    font_spinbox = ttk.Spinbox(frame, from_=8, to=72, textvariable=app.target_font_size_var, 
                             width=10, validate="key", validatecommand=(validate_font_size, '%P'))
    font_spinbox.grid(row=current_row, column=1, padx=5, pady=5, sticky="w")
    def on_font_size_focus_out(event):
        try:
            value = int(app.target_font_size_var.get())
            if not (8 <= value <= 72): app.target_font_size_var.set(max(8, min(72, value)))
            app.update_target_font_size() 
        except (ValueError, tk.TclError): app.target_font_size_var.set(12)
        app.save_settings()
    font_spinbox.bind("<FocusOut>", on_font_size_focus_out)
    current_row += 1
    
    file_cache_frame_outer = ttk.LabelFrame(frame, text=app.ui_lang.get_label("file_cache_frame_title")) 
    file_cache_frame_outer.grid(row=current_row, column=0, columnspan=3, padx=5, pady=5, sticky="ew")
    ttk.Label(file_cache_frame_outer, text=app.ui_lang.get_label("file_cache_description"), wraplength=400).grid(row=0, column=0, columnspan=2, padx=5, pady=2, sticky="w")
    ttk.Checkbutton(file_cache_frame_outer, text=app.ui_lang.get_label("google_cache_checkbox"), variable=app.google_file_cache_var).grid(row=1, column=0, padx=5, pady=2, sticky="w")
    ttk.Checkbutton(file_cache_frame_outer, text=app.ui_lang.get_label("deepl_cache_checkbox"), variable=app.deepl_file_cache_var).grid(row=2, column=0, padx=5, pady=2, sticky="w")
    ttk.Label(file_cache_frame_outer, text=f"{app.ui_lang.get_label('cache_files_label')} {os.path.basename(app.google_cache_file)}, {os.path.basename(app.deepl_cache_file)}", wraplength=400).grid(row=3, column=0, columnspan=2, padx=5, pady=2, sticky="w")
    ttk.Button(file_cache_frame_outer, text=app.ui_lang.get_label("clear_caches_btn"), command=app.clear_file_caches).grid(row=4, column=0, padx=5, pady=5, sticky="w")
    current_row += 1
    
    button_frame_outer = ttk.Frame(frame)
    button_frame_outer.grid(row=current_row, column=0, columnspan=3, pady=10)
    save_settings_button = ttk.Button(button_frame_outer, text=app.ui_lang.get_label("save_settings_btn"), command=app.save_settings)
    save_settings_button.pack(side=tk.LEFT, padx=5)
    
    # Store reference for the tab changed handler in app_logic.py
    app.settings_tab_save_button = save_settings_button
    
    frame.columnconfigure(1, weight=1)

def create_debug_tab(app):
    # Create a scrollable tab content frame
    scrollable_content = create_scrollable_tab(app.tab_control, app.ui_lang.get_label("debug_tab_title"))
    app.tab_debug = scrollable_content
    
    # Create the debug frame inside the scrollable area
    frame = ttk.LabelFrame(scrollable_content, text=app.ui_lang.get_label("debug_tab_title"))
    frame.pack(fill="both", expand=True, padx=10, pady=10)

    image_frame = ttk.Frame(frame)
    image_frame.pack(fill="x", padx=5, pady=5)

    original_frame = ttk.LabelFrame(image_frame, text=app.ui_lang.get_label("original_image_label"))
    original_frame.pack(side=tk.LEFT, padx=5, fill="both", expand=True)
    app.original_image_label = ttk.Label(original_frame, text=app.ui_lang.get_label("no_image_captured", "No image captured yet"))
    app.original_image_label.pack(padx=5, pady=5)

    processed_frame = ttk.LabelFrame(image_frame, text=app.ui_lang.get_label("processed_image_label"))
    processed_frame.pack(side=tk.RIGHT, padx=5, fill="both", expand=True)
    app.processed_image_label = ttk.Label(processed_frame, text=app.ui_lang.get_label("no_image_processed", "No image processed yet"))
    app.processed_image_label.pack(padx=5, pady=5)

    ocr_frame = ttk.LabelFrame(frame, text=app.ui_lang.get_label("ocr_results_label"))
    ocr_frame.pack(fill="x", padx=5, pady=5)  # Remove expand=True
    app.ocr_results_text = tk.Text(ocr_frame, height=16, width=50, wrap=tk.WORD)
    app.ocr_results_text.pack(fill="both", expand=True, padx=5, pady=5)
    app.ocr_results_text.insert(tk.END, app.ui_lang.get_label("ocr_results_placeholder"))
    app.ocr_results_text.config(state=tk.DISABLED)

    button_frame = ttk.Frame(frame) # Renamed to avoid conflict
    button_frame.pack(fill="x", padx=5, pady=5)
    ttk.Button(button_frame, text=app.ui_lang.get_label("save_debug_images_btn"), command=app.save_debug_images).pack(side=tk.LEFT, padx=5)
    ttk.Button(button_frame, text=app.ui_lang.get_label("refresh_log_btn"), command=app.refresh_debug_log).pack(side=tk.LEFT, padx=5)

    log_frame = ttk.LabelFrame(frame, text=app.ui_lang.get_label("app_log_label"))
    log_frame.pack(fill="both", expand=True, padx=5, pady=5)
    
    # Create text widget without fixed height to allow expansion
    app.log_text = tk.Text(log_frame, wrap=tk.WORD)
    
    # Add scrollbar
    scrollbar = ttk.Scrollbar(log_frame, command=app.log_text.yview)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    app.log_text.config(yscrollcommand=scrollbar.set, state=tk.DISABLED)
    
    # Pack the text widget to fill the frame
    app.log_text.pack(fill="both", expand=True, padx=5, pady=5)
    
    app.refresh_debug_log()
