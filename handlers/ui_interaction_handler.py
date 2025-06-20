# handlers/ui_interaction_handler.py
import os
import time
import re
import tkinter as tk
from tkinter import messagebox, colorchooser
import cv2 
from PIL import Image 
from config_manager import save_app_config 
from logger import log_debug
import traceback


class UIInteractionHandler:
    def __init__(self, app):
        self.app = app
        
    def choose_color_for_settings(self, color_type):
        initial_color = ""
        if color_type == 'source': initial_color = self.app.source_colour_var.get()
        elif color_type == 'target': initial_color = self.app.target_colour_var.get()
        elif color_type == 'target_text': initial_color = self.app.target_text_colour_var.get()

        # Map color_type to appropriate translation key
        title_key_map = {
            'source': 'choose_source_color_title',
            'target': 'choose_target_color_title', 
            'target_text': 'choose_target_text_color_title'
        }
        
        # Fallback titles for backward compatibility
        fallback_titles = {
            'source': 'Choose Source Color',
            'target': 'Choose Target Color',
            'target_text': 'Choose Target Text Color'
        }
        
        title_key = title_key_map.get(color_type, 'choose_source_color_title')
        fallback_title = fallback_titles.get(color_type, 'Choose Color')
        dialog_title = self.app.ui_lang.get_label(title_key, fallback_title)

        chosen_color_tuple = colorchooser.askcolor(color=initial_color, 
                                                 title=dialog_title, 
                                                 parent=self.app.root)
        if chosen_color_tuple and chosen_color_tuple[1]:
            hex_color = chosen_color_tuple[1] 
            
            if color_type == 'source':
                self.app.source_colour_var.set(hex_color) 
                if hasattr(self.app, 'color_displays') and 'source' in self.app.color_displays:
                    self.app.color_displays['source'].configure(bg=hex_color)
                if self.app.source_overlay and self.app.source_overlay.winfo_exists():
                    self.app.source_overlay.update_color(hex_color)
            elif color_type == 'target':
                self.app.target_colour_var.set(hex_color) 
                if hasattr(self.app, 'color_displays') and 'target' in self.app.color_displays:
                    self.app.color_displays['target'].configure(bg=hex_color)
                if self.app.target_overlay and self.app.target_overlay.winfo_exists():
                    self.app.target_overlay.update_color(hex_color)
                    if self.app.translation_text and self.app.translation_text.winfo_exists():
                        self.app.translation_text.configure(bg=hex_color)
            elif color_type == 'target_text':
                self.app.target_text_colour_var.set(hex_color) 
                if hasattr(self.app, 'color_displays') and 'target_text' in self.app.color_displays:
                    self.app.color_displays['target_text'].configure(bg=hex_color)
                if self.app.translation_text and self.app.translation_text.winfo_exists():
                    self.app.translation_text.configure(fg=hex_color)
            log_debug(f"Color {color_type} changed to: {hex_color}")
            
    def toggle_api_key_visibility(self, api_type_toggle):
        target_entry, target_button, visibility_flag_attr = None, None, None
        if api_type_toggle == "google":
            target_entry, target_button, visibility_flag_attr = self.app.google_api_key_entry, self.app.google_api_key_button, "google_api_key_visible"
        elif api_type_toggle == "deepl":
            target_entry, target_button, visibility_flag_attr = self.app.deepl_api_key_entry, self.app.deepl_api_key_button, "deepl_api_key_visible"
        
        if target_entry and target_button:
            current_visibility = getattr(self.app, visibility_flag_attr, False)
            new_visibility = not current_visibility
            setattr(self.app, visibility_flag_attr, new_visibility)
            target_entry.config(show="" if new_visibility else "*")
            
            # Use the language system for button text
            if new_visibility:
                button_text = self.app.ui_lang.get_label("hide_btn", "Hide")
            else:
                button_text = self.app.ui_lang.get_label("show_btn", "Show")
            
            target_button.config(text=button_text)
            log_debug(f"API key visibility for {api_type_toggle} changed to {new_visibility}, button text: {button_text}")

    def update_translation_model_ui(self):
        selected_model_ui_code = self.app.translation_model_var.get() 
        log_debug(f"Updating UI visibility for model code: {selected_model_ui_code}")

        def manage_grid(widget, show=True):
            if widget and hasattr(widget, 'grid_remove') and hasattr(widget, 'grid'):
                is_gridded = False
                try:
                    if widget.grid_info():
                        is_gridded = True
                except tk.TclError: 
                    is_gridded = False
                
                if show and not is_gridded: 
                    widget.grid() 
                elif not show and is_gridded: 
                    widget.grid_remove()
        
        is_google = (selected_model_ui_code == 'google_api')
        is_deepl = (selected_model_ui_code == 'deepl_api')
        is_marian = (selected_model_ui_code == 'marianmt')
        is_api_model = is_google or is_deepl

        manage_grid(self.app.source_lang_label, show=is_api_model)
        manage_grid(self.app.source_lang_combobox, show=is_api_model)
        manage_grid(self.app.target_lang_label, show=is_api_model)
        manage_grid(self.app.target_lang_combobox, show=is_api_model)
        
        manage_grid(self.app.google_api_key_label, show=is_google)
        manage_grid(self.app.google_api_key_entry, show=is_google)
        manage_grid(self.app.google_api_key_button, show=is_google)
        
        manage_grid(self.app.deepl_api_key_label, show=is_deepl)
        manage_grid(self.app.deepl_api_key_entry, show=is_deepl)
        manage_grid(self.app.deepl_api_key_button, show=is_deepl)
        
        # DeepL Model Type visibility
        if hasattr(self.app, 'deepl_model_type_label'):
            manage_grid(self.app.deepl_model_type_label, show=is_deepl)
        if hasattr(self.app, 'deepl_model_type_combobox'):
            manage_grid(self.app.deepl_model_type_combobox, show=is_deepl)
        
        manage_grid(self.app.marian_model_label, show=is_marian)
        manage_grid(self.app.marian_model_combobox, show=is_marian)
        manage_grid(self.app.models_file_label, show=is_marian)
        manage_grid(self.app.models_file_frame, show=is_marian) 
        manage_grid(self.app.beam_size_label, show=is_marian)
        manage_grid(self.app.beam_spinbox, show=is_marian)

        if hasattr(self.app, 'marian_explanation_labels'):
            for lbl in self.app.marian_explanation_labels:
                manage_grid(lbl, show=is_marian)
    
    def update_marian_models_dropdown_for_language(self, ui_language=None):
        """Update MarianMT models dropdown with localized display names."""
        if not hasattr(self.app, 'marian_model_combobox') or not self.app.marian_model_combobox.winfo_exists():
            return
            
        # Use current UI language if not provided
        if ui_language is None:
            ui_language = self.get_current_ui_language_for_lookup()
        
        # Get current model path from the config variable (this is the source of truth)
        current_model_path = self.app.marian_model_var.get()
        
        # We need to maintain original English model names 
        # Load them fresh from the configuration to ensure they're in English
        original_models_dict, original_models_list = self.app.configuration_handler.load_marian_models(localize_names=False)
        
        # Convert to localized names
        localized_models_list = []
        localized_models_dict = {}
        
        for english_display_name, model_path in original_models_dict.items():
            localized_display_name = self.app.language_manager.get_localized_marian_display_name(
                english_display_name, ui_language
            )
            localized_models_list.append(localized_display_name)
            localized_models_dict[localized_display_name] = model_path
        
        # IMPORTANT FIX: Sort the localized names properly for Polish
        # This addresses Issue 2: MarianMT sorting in Polish
        if ui_language == 'polish':
            # Use Polish-aware sorting for correct alphabetical order
            localized_models_list = self.app.language_manager.sort_polish_names(localized_models_list)
        else:
            # Use standard sorting for English and other languages
            localized_models_list.sort()
        
        # Update the combobox values
        self.app.marian_model_combobox['values'] = localized_models_list
        
        # Update the models list and dict to use localized names
        self.app.marian_models_list = localized_models_list
        self.app.marian_models_dict = localized_models_dict
        
        # Restore selection based on the current model path
        selection_restored = False
        if current_model_path:
            for localized_name, path in localized_models_dict.items():
                if path == current_model_path:
                    self.app.marian_model_display_var.set(localized_name)
                    selection_restored = True
                    log_debug(f"Restored MarianMT selection: {localized_name} (path: {path})")
                    break
        
        if not selection_restored:
            if localized_models_list:
                self.app.marian_model_display_var.set(localized_models_list[0])
                # Update the path to match the first item
                first_path = localized_models_dict.get(localized_models_list[0], "")
                if first_path:
                    self.app.marian_model_var.set(first_path)
                log_debug(f"No valid selection found, defaulting to first MarianMT model: {localized_models_list[0]}")
            else:
                self.app.marian_model_display_var.set("")
                self.app.marian_model_var.set("")
        
        log_debug(f"Updated MarianMT models dropdown for UI language: {ui_language} (total models: {len(localized_models_list)}) - sorted alphabetically")

    def update_all_dropdowns_for_language_change(self):
        """Update all language dropdowns when UI language changes."""
        try:
            ui_language_for_lookup = self.get_current_ui_language_for_lookup()
            
            log_debug(f"Updating dropdowns for language change - UI language: {ui_language_for_lookup}")
            
            # Preserve current selections before updating dropdowns
            current_google_source = self.app.google_source_lang
            current_google_target = self.app.google_target_lang  
            current_deepl_source = self.app.deepl_source_lang
            current_deepl_target = self.app.deepl_target_lang
            current_marian_model = self.app.marian_model_var.get()
            
            log_debug(f"Preserving selections: Google({current_google_source}->{current_google_target}), DeepL({current_deepl_source}->{current_deepl_target}), MarianMT({current_marian_model})")
            
            # Update API language dropdowns
            active_model = self.app.translation_model_var.get()
            if active_model in ['google_api', 'deepl_api']:
                self._update_language_dropdowns_for_model(active_model)
            
            # Update MarianMT models dropdown
            self.update_marian_models_dropdown_for_language(ui_language_for_lookup)
            
            # Verify selections were preserved
            log_debug(f"After update: Google({self.app.google_source_lang}->{self.app.google_target_lang}), DeepL({self.app.deepl_source_lang}->{self.app.deepl_target_lang}), MarianMT({self.app.marian_model_var.get()})")
            
            # If any selections were lost, restore them
            if self.app.google_source_lang != current_google_source:
                log_debug(f"Restoring Google source: {current_google_source}")
                self.app.google_source_lang = current_google_source
                
            if self.app.google_target_lang != current_google_target:
                log_debug(f"Restoring Google target: {current_google_target}")
                self.app.google_target_lang = current_google_target
                
            if self.app.deepl_source_lang != current_deepl_source:
                log_debug(f"Restoring DeepL source: {current_deepl_source}")
                self.app.deepl_source_lang = current_deepl_source
                
            if self.app.deepl_target_lang != current_deepl_target:
                log_debug(f"Restoring DeepL target: {current_deepl_target}")
                self.app.deepl_target_lang = current_deepl_target
                
            if self.app.marian_model_var.get() != current_marian_model:
                log_debug(f"Restoring MarianMT model: {current_marian_model}")
                self.app.marian_model_var.set(current_marian_model)
            
            log_debug(f"Updated all dropdowns for UI language change to: {self.app.ui_lang.current_lang}")
        except Exception as e:
            log_debug(f"Error updating dropdowns for language change: {e}")
            import traceback
            log_debug(f"Traceback: {traceback.format_exc()}")

    def get_current_ui_language_for_lookup(self):
        """Get the current UI language in the format expected by localization methods."""
        current_ui_language = self.app.ui_lang.current_lang
        ui_language_for_lookup = 'polish' if current_ui_language == 'pol' else 'english'
        
        # Add debugging to track UI language state
        log_debug(f"UI Language Detection: app.ui_lang.current_lang='{current_ui_language}' -> lookup='{ui_language_for_lookup}'")
        
        return ui_language_for_lookup

    def _update_language_dropdowns_for_model(self, active_model_code):
        lm = self.app.language_manager
        
        # Get current UI language
        ui_language_for_lookup = self.get_current_ui_language_for_lookup()
        
        source_names_list, current_source_api_code_from_app = [], 'auto'
        if active_model_code == 'google_api':
            # Get raw API codes
            source_codes = [code for _, code in lm.google_source_languages]
            # Convert to localized names and create code mapping
            source_name_to_code = {}
            source_names_list = []
            for code in source_codes:
                # Use 'google' as provider for language_display_names.csv lookup
                localized_name = lm.get_localized_language_name(code, 'google', ui_language_for_lookup)
                source_names_list.append(localized_name)
                source_name_to_code[localized_name] = code
            
            # Sort alphabetically, but keep "Auto" at the top if present
            if "Auto" in source_names_list:
                source_names_list.remove("Auto")
                if ui_language_for_lookup == 'polish':
                    source_names_list = self.app.language_manager.sort_polish_names(source_names_list)
                else:
                    source_names_list.sort()
                source_names_list.insert(0, "Auto")
            else:
                if ui_language_for_lookup == 'polish':
                    source_names_list = self.app.language_manager.sort_polish_names(source_names_list)
                else:
                    source_names_list.sort()
            
            current_source_api_code_from_app = self.app.google_source_lang
        elif active_model_code == 'deepl_api':
            # Get raw API codes
            source_codes = [code for _, code in lm.deepl_source_languages]
            # Convert to localized names and create code mapping
            source_name_to_code = {}
            source_names_list = []
            for code in source_codes:
                # Use 'deepl' as provider for language_display_names.csv lookup
                localized_name = lm.get_localized_language_name(code, 'deepl', ui_language_for_lookup)
                source_names_list.append(localized_name)
                source_name_to_code[localized_name] = code
            
            # Sort alphabetically, but keep "Auto" at the top if present
            if "Auto" in source_names_list:
                source_names_list.remove("Auto")
                if ui_language_for_lookup == 'polish':
                    source_names_list = self.app.language_manager.sort_polish_names(source_names_list)
                else:
                    source_names_list.sort()
                source_names_list.insert(0, "Auto")
            else:
                if ui_language_for_lookup == 'polish':
                    source_names_list = self.app.language_manager.sort_polish_names(source_names_list)
                else:
                    source_names_list.sort()
            
            current_source_api_code_from_app = self.app.deepl_source_lang
        
        if hasattr(self.app, 'source_lang_combobox') and self.app.source_lang_combobox.winfo_exists():
            self.app.source_lang_combobox['values'] = source_names_list
            # Get localized display name for current API code
            provider_for_display = 'google' if active_model_code == 'google_api' else 'deepl'
            display_name_src_to_set = lm.get_localized_language_name(
                current_source_api_code_from_app, provider_for_display, ui_language_for_lookup)
            
            if display_name_src_to_set and display_name_src_to_set in source_names_list:
                self.app.source_display_var.set(display_name_src_to_set)
            else:
                # Better fallback: try to find by code in original lists
                fallback_found = False
                if active_model_code == 'google_api':
                    for name, code in lm.google_source_languages:
                        if code == current_source_api_code_from_app:
                            localized_fallback = lm.get_localized_language_name(code, 'google', ui_language_for_lookup)
                            if localized_fallback in source_names_list:
                                self.app.source_display_var.set(localized_fallback)
                                fallback_found = True
                                break
                elif active_model_code == 'deepl_api':
                    for name, code in lm.deepl_source_languages:
                        if code == current_source_api_code_from_app:
                            localized_fallback = lm.get_localized_language_name(code, 'deepl', ui_language_for_lookup)
                            if localized_fallback in source_names_list:
                                self.app.source_display_var.set(localized_fallback)
                                fallback_found = True
                                break
                
                if not fallback_found:
                    if "Auto" in source_names_list: 
                        self.app.source_display_var.set("Auto")
                    elif source_names_list: 
                        self.app.source_display_var.set(source_names_list[0])
                    else: 
                        self.app.source_display_var.set("")
            
            log_debug(f"Updated source lang dropdown for {active_model_code} to display: {self.app.source_display_var.get()} (API code: {current_source_api_code_from_app}) [UI: {ui_language_for_lookup}]")

        target_names_list, current_target_api_code_from_app = [], 'en'
        if active_model_code == 'google_api':
            # Get raw API codes
            target_codes = [code for _, code in lm.google_target_languages]
            # Convert to localized names and create code mapping
            target_name_to_code = {}
            target_names_list = []
            for code in target_codes:
                # Use 'google' as provider for language_display_names.csv lookup
                localized_name = lm.get_localized_language_name(code, 'google', ui_language_for_lookup)
                target_names_list.append(localized_name)
                target_name_to_code[localized_name] = code
            
            # Sort alphabetically
            if ui_language_for_lookup == 'polish':
                target_names_list = self.app.language_manager.sort_polish_names(target_names_list)
            else:
                target_names_list.sort()
            
            current_target_api_code_from_app = self.app.google_target_lang
        elif active_model_code == 'deepl_api':
            # Get raw API codes
            target_codes = [code for _, code in lm.deepl_target_languages]
            # Convert to localized names and create code mapping
            target_name_to_code = {}
            target_names_list = []
            for code in target_codes:
                # Use 'deepl' as provider for language_display_names.csv lookup
                localized_name = lm.get_localized_language_name(code, 'deepl', ui_language_for_lookup)
                target_names_list.append(localized_name)
                target_name_to_code[localized_name] = code
            
            # Sort alphabetically
            if ui_language_for_lookup == 'polish':
                target_names_list = self.app.language_manager.sort_polish_names(target_names_list)
            else:
                target_names_list.sort()
            
            current_target_api_code_from_app = self.app.deepl_target_lang

        if hasattr(self.app, 'target_lang_combobox') and self.app.target_lang_combobox.winfo_exists():
            self.app.target_lang_combobox['values'] = target_names_list
            # Get localized display name for current API code
            provider_for_display = 'google' if active_model_code == 'google_api' else 'deepl'
            display_name_tgt_to_set = lm.get_localized_language_name(
                current_target_api_code_from_app, provider_for_display, ui_language_for_lookup)

            if display_name_tgt_to_set and display_name_tgt_to_set in target_names_list:
                self.app.target_display_var.set(display_name_tgt_to_set)
            else:
                # Better fallback: try to find by code in original lists
                fallback_found = False
                if active_model_code == 'google_api':
                    for name, code in lm.google_target_languages:
                        if code == current_target_api_code_from_app:
                            localized_fallback = lm.get_localized_language_name(code, 'google', ui_language_for_lookup)
                            if localized_fallback in target_names_list:
                                self.app.target_display_var.set(localized_fallback)
                                fallback_found = True
                                break
                elif active_model_code == 'deepl_api':
                    for name, code in lm.deepl_target_languages:
                        if code == current_target_api_code_from_app:
                            localized_fallback = lm.get_localized_language_name(code, 'deepl', ui_language_for_lookup)
                            if localized_fallback in target_names_list:
                                self.app.target_display_var.set(localized_fallback)
                                fallback_found = True
                                break
                
                if not fallback_found:
                    if target_names_list: 
                        self.app.target_display_var.set(target_names_list[0])
                    else: 
                        self.app.target_display_var.set("")
            
            log_debug(f"Updated target lang dropdown for {active_model_code} to display: {self.app.target_display_var.get()} (API code: {current_target_api_code_from_app}) [UI: {ui_language_for_lookup}]")


    def parse_marian_model_for_langs(self, model_path_or_display_name):
        match_model_langs = re.match(r'Helsinki-NLP/opus-mt-([a-z]{2,3}(?:_[a-z]+)?(?:-[a-z]{2,3}(?:_[a-z]+)?)?)-([a-z]{2,3}(?:_[a-z]+)?(?:-[a-z]{2,3}(?:_[a-z]+)?)?)', model_path_or_display_name)
        if match_model_langs:
            source_code = match_model_langs.group(1).replace('_', '-') 
            target_code = match_model_langs.group(2).replace('_', '-')
            log_debug(f"Parsed MarianMT langs from path '{model_path_or_display_name}': {source_code} -> {target_code}")
            return source_code, target_code

        match_display_langs = re.match(r'([A-Za-z\s\(\)-]+?)\s+to\s+([A-Za-z\s\(\)-]+)', model_path_or_display_name, re.IGNORECASE)
        if match_display_langs:
            source_lang_name_raw = match_display_langs.group(1).strip().lower()
            target_lang_name_raw = match_display_langs.group(2).strip().lower()
            
            source_lang_name_clean = re.sub(r'\s*\(.*\)', '', source_lang_name_raw).strip()
            target_lang_name_clean = re.sub(r'\s*\(.*\)', '', target_lang_name_raw).strip()

            source_iso = self.app.language_manager.get_iso_code_from_generic_name(source_lang_name_clean)
            target_iso = self.app.language_manager.get_iso_code_from_generic_name(target_lang_name_clean)
            
            if source_iso and target_iso:
                log_debug(f"Parsed MarianMT langs from display name '{model_path_or_display_name}': {source_iso} -> {target_iso}")
                return source_iso, target_iso
        
        log_debug(f"Could not parse languages from MarianMT model string: {model_path_or_display_name}")
        return None

    def on_marian_model_selection_changed(self, event=None, preload=False, initial_setup=False):
        selected_display_name = self.app.marian_model_display_var.get() 
        actual_model_name_path = self.app.marian_models_dict.get(selected_display_name)

        if not actual_model_name_path: 
            log_debug(f"MarianMT display name '{selected_display_name}' not found in dictionary. Attempting to use display name as path or find fallback.")
            if selected_display_name in self.app.marian_models_dict.values(): 
                actual_model_name_path = selected_display_name
            elif self.app.marian_models_list: 
                new_display_name = self.app.marian_models_list[0]
                self.app.marian_model_display_var.set(new_display_name) # Update UI
                actual_model_name_path = self.app.marian_models_dict.get(new_display_name)
                log_debug(f"Fell back to first MarianMT model: {new_display_name}")
                # Also update marian_model_var (path) to reflect this fallback
                if self.app.marian_model_var.get() != actual_model_name_path:
                    self.app.marian_model_var.set(actual_model_name_path) # Triggers save via trace
            else: 
                self.app.marian_model_var.set("")
                self.app.marian_source_lang, self.app.marian_target_lang = None, None
                if self.app.translation_model_var.get() == 'marianmt':
                    self.app.source_lang_var.set("")
                    self.app.target_lang_var.set("")
                log_debug("No MarianMT models available to select.")
                return

        # Update the main marian_model_var (stores the path) if it changed from what was in config
        if self.app.marian_model_var.get() != actual_model_name_path:
            self.app.marian_model_var.set(actual_model_name_path) # This will trigger save via trace
        
        log_debug(f"MarianMT model selection: Display='{selected_display_name}', Path='{actual_model_name_path}'")
        
        parsed_langs = self.parse_marian_model_for_langs(actual_model_name_path) or \
                       self.parse_marian_model_for_langs(selected_display_name)
        
        if parsed_langs:
            self.app.marian_source_lang, self.app.marian_target_lang = parsed_langs[0], parsed_langs[1]
            log_debug(f"MarianMT languages set: {self.app.marian_source_lang} -> {self.app.marian_target_lang}")
            if self.app.translation_model_var.get() == 'marianmt':
                self.app.source_lang_var.set(self.app.marian_source_lang)
                self.app.target_lang_var.set(self.app.marian_target_lang)
        else:
            self.app.marian_source_lang, self.app.marian_target_lang = None, None
            if self.app.translation_model_var.get() == 'marianmt':
                self.app.source_lang_var.set("") 
                self.app.target_lang_var.set("")
            log_debug(f"Could not parse languages for MarianMT model: {actual_model_name_path}")

        if self.app.marian_translator is None and (preload or not initial_setup):
            self.app.translation_handler.initialize_marian_translator()

        if self.app.marian_translator and self.app.marian_source_lang and self.app.marian_target_lang:
            self.app.translation_handler.update_marian_active_model(
                actual_model_name_path, self.app.marian_source_lang, self.app.marian_target_lang
            )
        elif self.app.marian_translator and hasattr(self.app.translation_handler, '_cached_marian_translate'):
            self.app.translation_handler._cached_marian_translate.cache_clear()
            if self.app.marian_translator and hasattr(self.app.marian_translator, '_unload_current_model'):
                self.app.marian_translator._unload_current_model() 

    def on_translation_model_selection_changed(self, event=None, initial_setup=False):
        preload = initial_setup 

        if event is not None: 
            selected_display_name_from_ui = self.app.translation_model_display_var.get()
            newly_selected_model_code = self.app.translation_model_values.get(selected_display_name_from_ui, 'google_api')
            
            if newly_selected_model_code != self.app.translation_model_var.get():
                self.app.translation_model_var.set(newly_selected_model_code) # This triggers save via trace
                log_debug(f"Translation model var updated by UI to: {newly_selected_model_code}")
        
        model_to_configure_for = self.app.translation_model_var.get()
        
        expected_display_name = self.app.translation_model_names.get(model_to_configure_for)
        if expected_display_name and self.app.translation_model_display_var.get() != expected_display_name:
            self.app.translation_model_display_var.set(expected_display_name)

        log_debug(f"Configuring UI for model: {model_to_configure_for} (Initial: {initial_setup}, Event: {event is not None})")
        
        self.update_translation_model_ui() 

        if model_to_configure_for == 'google_api' or model_to_configure_for == 'deepl_api':
            self._update_language_dropdowns_for_model(model_to_configure_for)
            if model_to_configure_for == 'google_api':
                self.app.source_lang_var.set(self.app.google_source_lang)
                self.app.target_lang_var.set(self.app.google_target_lang)
            elif model_to_configure_for == 'deepl_api':
                self.app.source_lang_var.set(self.app.deepl_source_lang)
                self.app.target_lang_var.set(self.app.deepl_target_lang)
        elif model_to_configure_for == 'marianmt':
            if self.app.MARIANMT_AVAILABLE and self.app.marian_translator is None and (preload or not initial_setup):
                self.app.translation_handler.initialize_marian_translator()
            
            current_marian_path_from_app_var = self.app.marian_model_var.get() 
            marian_display_name_to_set_in_ui = self.app.marian_model_display_var.get() # Current UI value

            # If the UI display var isn't correctly reflecting the config path, fix it.
            # This happens if app_logic.py correctly initialized marian_model_display_var,
            # and this function is called for initial_setup.
            path_for_current_ui_display = self.app.marian_models_dict.get(marian_display_name_to_set_in_ui)
            
            if current_marian_path_from_app_var and path_for_current_ui_display != current_marian_path_from_app_var:
                # Config path is different from what UI currently implies. Set UI to match config path.
                temp_display_name_for_config_path = None
                for disp_n, path_c in self.app.marian_models_dict.items():
                    if path_c == current_marian_path_from_app_var:
                        temp_display_name_for_config_path = disp_n
                        break
                if temp_display_name_for_config_path:
                    marian_display_name_to_set_in_ui = temp_display_name_for_config_path
                    self.app.marian_model_display_var.set(marian_display_name_to_set_in_ui)
                # If config path still not found, marian_model_display_var (and thus selected_display_name in
                # on_marian_model_selection_changed) will use the fallback from app_logic init.
            
            # If marian_model_display_var is empty but list isn't, set to first
            if not self.app.marian_model_display_var.get() and self.app.marian_models_list:
                 self.app.marian_model_display_var.set(self.app.marian_models_list[0])
                 # Update underlying marian_model_var path too
                 new_path = self.app.marian_models_dict.get(self.app.marian_models_list[0], "")
                 if self.app.marian_model_var.get() != new_path:
                    self.app.marian_model_var.set(new_path)


            self.on_marian_model_selection_changed(preload=preload, initial_setup=initial_setup)


    def update_stability_from_spinbox(self):
        try:
            new_threshold = self.app.stability_var.get()
            if new_threshold != self.app.stable_threshold: 
                self.app.stable_threshold = new_threshold
        except tk.TclError: pass 
    
    def update_target_font_size(self):
        if self.app.translation_text and self.app.translation_text.winfo_exists():
            try:
                font_size = self.app.target_font_size_var.get()
                self.app.translation_text.configure(font=("Arial", font_size))
            except tk.TclError: pass
    
    def refresh_debug_log(self):
        if not hasattr(self.app, 'log_text') or not self.app.log_text or not self.app.log_text.winfo_exists(): return
        try:
            self.app.log_text.config(state=tk.NORMAL)
            self.app.log_text.delete(1.0, tk.END)
            log_file = 'translator_debug.log'
            if os.path.exists(log_file):
                try:
                    with open(log_file, 'r', encoding='utf-8') as f: log_lines = f.readlines()
                    start_index = max(0, len(log_lines) - 200)
                    for line in log_lines[start_index:]: self.app.log_text.insert(tk.END, line)
                    self.app.log_text.see(tk.END)
                except Exception as read_err: self.app.log_text.insert(tk.END, f"Error reading log: {read_err}")
            else: self.app.log_text.insert(tk.END, f"Log file not found: {log_file}")
            self.app.log_text.config(state=tk.DISABLED)
        except Exception as e: log_debug(f"Error refreshing log text: {e}")

    def save_debug_images(self):
        try:
            if not self.app.ocr_debugging_var.get():
                messagebox.showinfo("Debug", "OCR Debugging disabled.", parent=self.app.root); return
            if self.app.last_screenshot is None:
                messagebox.showinfo("Debug", "No screenshot captured.", parent=self.app.root); return
            debug_dir = "debug_images"; os.makedirs(debug_dir, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            original_fn = os.path.join(debug_dir, f"original_{ts}.png")
            self.app.last_screenshot.save(original_fn)
            log_debug(f"Saved original debug image: {original_fn}")
            if isinstance(self.app.last_processed_image, cv2.typing.MatLike) or isinstance(self.app.last_processed_image, type(cv2.imread('dummy.png'))): # Check type
                processed_fn = os.path.join(debug_dir, f"processed_{self.app.preprocessing_mode_var.get()}_{ts}.png")
                if cv2.imwrite(processed_fn, self.app.last_processed_image):
                    log_debug(f"Saved processed debug image: {processed_fn}")
                    messagebox.showinfo(
                        self.app.ui_lang.get_label("dialog_debug_images_saved_title", "Debug Images Saved"), 
                        self.app.ui_lang.get_label("dialog_debug_images_saved_message", "Images saved to '{0}'.").format(debug_dir), 
                        parent=self.app.root
                    )
                else: messagebox.showerror("Error", f"Failed to save processed image to {processed_fn}", parent=self.app.root)
            else: 
                messagebox.showinfo(
                    self.app.ui_lang.get_label("dialog_debug_image_saved_title", "Debug Image Saved"), 
                    self.app.ui_lang.get_label("dialog_debug_image_saved_message", "Original image saved to '{0}'. No processed image.").format(debug_dir), 
                    parent=self.app.root
                )
        except Exception as e:
            log_debug(f"Error saving debug images: {e}")
            messagebox.showerror("Error", f"Failed to save debug images: {e}", parent=self.app.root)
    
    def save_settings(self):
        try:
            cfg = self.app.config['Settings']
            
            active_model_code = self.app.translation_model_var.get()
            cfg['translation_model'] = active_model_code

            # Validate and save language codes (never save display names!)
            google_source = self.app.google_source_lang
            google_target = self.app.google_target_lang
            deepl_source = self.app.deepl_source_lang
            deepl_target = self.app.deepl_target_lang
            
            # Basic validation: codes should be short and not contain spaces
            def is_valid_code(code):
                if not code:
                    return False
                # Valid codes can be up to 8 characters, don't contain spaces, and typically:
                # - Are uppercase/lowercase short codes (EN, de, ZH-HANS, auto)
                # - Don't contain display name indicators like parentheses or common words
                if len(code) > 8 or ' ' in code:
                    return False
                # Reject common display name patterns
                if ('(' in code or ')' in code or 
                    'na' in code.lower() or 
                    any(word in code.lower() for word in ['english', 'chinese', 'german', 'french', 'spanish', 'polish'])):
                    return False
                return True
            
            if is_valid_code(google_source):
                cfg['google_source_lang'] = google_source
                log_debug(f"Saving Google source lang: {google_source}")
            else:
                log_debug(f"ERROR: Invalid Google source lang code '{google_source}' - not saving")
                
            if is_valid_code(google_target):
                cfg['google_target_lang'] = google_target
                log_debug(f"Saving Google target lang: {google_target}")
            else:
                log_debug(f"ERROR: Invalid Google target lang code '{google_target}' - not saving")
                
            if is_valid_code(deepl_source):
                cfg['deepl_source_lang'] = deepl_source
                log_debug(f"Saving DeepL source lang: {deepl_source}")
            else:
                log_debug(f"ERROR: Invalid DeepL source lang code '{deepl_source}' - not saving")
                
            if is_valid_code(deepl_target):
                cfg['deepl_target_lang'] = deepl_target
                log_debug(f"Saving DeepL target lang: {deepl_target}")
            else:
                log_debug(f"ERROR: Invalid DeepL target lang code '{deepl_target}' - not saving")
            
            cfg['marian_model'] = self.app.marian_model_var.get() 

            cfg['tesseract_path'] = self.app.tesseract_path_var.get()
            cfg['scan_interval'] = str(self.app.scan_interval_var.get())
            cfg['stability_threshold'] = str(self.app.stability_var.get())
            cfg['clear_translation_timeout'] = str(self.app.clear_translation_timeout_var.get())
            cfg['image_preprocessing_mode'] = self.app.preprocessing_mode_var.get()
            cfg['adaptive_block_size'] = str(self.app.adaptive_block_size_var.get())
            cfg['adaptive_c'] = str(self.app.adaptive_c_var.get())
            cfg['ocr_debugging'] = str(self.app.ocr_debugging_var.get())
            cfg['confidence_threshold'] = str(self.app.confidence_var.get())
            cfg['remove_trailing_garbage'] = str(self.app.remove_trailing_garbage_var.get())
            cfg['debug_logging_enabled'] = str(self.app.debug_logging_enabled_var.get())
            cfg['source_area_colour'] = self.app.source_colour_var.get()
            cfg['target_area_colour'] = self.app.target_colour_var.get()
            cfg['target_text_colour'] = self.app.target_text_colour_var.get()
            cfg['target_font_size'] = str(self.app.target_font_size_var.get())
            cfg['gui_language'] = self.app.gui_language_var.get()
            
            cfg['google_translate_api_key'] = self.app.google_api_key_var.get()
            cfg['deepl_api_key'] = self.app.deepl_api_key_var.get()
            cfg['deepl_model_type'] = self.app.deepl_model_type_var.get()
            cfg['google_file_cache'] = str(self.app.google_file_cache_var.get())
            cfg['deepl_file_cache'] = str(self.app.deepl_file_cache_var.get())
            cfg['marian_models_file'] = self.app.models_file_var.get()
            try: 
                beam_val = int(self.app.num_beams_var.get())
                cfg['num_beams'] = str(max(1, min(50, beam_val)))
                if int(cfg['num_beams']) != beam_val: self.app.num_beams_var.set(int(cfg['num_beams']))
            except (ValueError, tk.TclError): cfg['num_beams'] = '2'


            if self.app.source_overlay and self.app.source_overlay.winfo_exists():
                area = self.app.source_overlay.get_geometry()
                if area: cfg['source_area_x1'], cfg['source_area_y1'], \
                         cfg['source_area_x2'], cfg['source_area_y2'] = map(str, area)
                cfg['source_area_visible'] = str(self.app.source_overlay.winfo_viewable())
            if self.app.target_overlay and self.app.target_overlay.winfo_exists():
                area = self.app.target_overlay.get_geometry()
                if area: cfg['target_area_x1'], cfg['target_area_y1'], \
                         cfg['target_area_x2'], cfg['target_area_y2'] = map(str, area)

            self.app.configuration_handler.save_current_window_geometry() 

            if not save_app_config(self.app.config): 
                messagebox.showerror("Error", "Failed to write settings to config file.", parent=self.app.root)
                return False
            
            new_tess_path = self.app.tesseract_path_var.get()
            import pytesseract 
            if pytesseract.pytesseract.tesseract_cmd != new_tess_path:
                 pytesseract.pytesseract.tesseract_cmd = new_tess_path
            
            self.app.stable_threshold = int(cfg['stability_threshold'])
            self.app.confidence_threshold = int(cfg['confidence_threshold'])
            self.app.clear_translation_timeout = int(cfg['clear_translation_timeout'])
            log_debug("Settings saved successfully by UIInteractionHandler.save_settings.")
            
            if hasattr(self.app, 'status_label') and self.app.status_label.winfo_exists():
                original_status_text = self.app.status_label.cget("text")
                self.app.status_label.config(text=self.app.ui_lang.get_label("settings_saved", "Status: Settings Saved"))
                if self.app.root.winfo_exists(): 
                    self.app.root.after(2000, lambda: self.app.status_label.config(text=original_status_text) if self.app.status_label.winfo_exists() else None)
            return True
        except Exception as e:
             log_debug(f"Error saving settings: {e}\n{traceback.format_exc()}")
             if self.app.root.winfo_exists(): 
                messagebox.showerror("Error", f"Failed to save settings:\n{e}", parent=self.app.root)
             return False
             
    def clear_debug_log(self):
        try:
            log_filename = 'translator_debug.log' 
            with open(log_filename, 'w', encoding='utf-8') as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}: Debug log cleared by user.\n")
            self.refresh_debug_log()
            if hasattr(self.app, 'status_label') and self.app.status_label.winfo_exists():
                original_status_text = self.app.status_label.cget("text")
                self.app.status_label.config(text="Status: Debug log cleared")
                if self.app.root.winfo_exists():
                    self.app.root.after(2000, lambda: self.app.status_label.config(text=original_status_text) if self.app.status_label.winfo_exists() else None)
        except Exception as e:
            log_debug(f"Error clearing debug log: {e}")
            if self.app.root.winfo_exists():
                messagebox.showerror("Error", f"Failed to clear debug log: {e}", parent=self.app.root)