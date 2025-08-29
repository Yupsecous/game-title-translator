import tkinter as tk
import traceback
from tkinter import messagebox
import os
import pytesseract # Import to set cmd path early

from app_logic import GameChangingTranslator # Main application class
from logger import log_debug # For logging fatal errors
from resource_copier import ensure_all_folders_in_main_directory # Auto-copy resources and docs
from update_applier import UpdateApplier # For startup update detection and application

def main_entry_point():
    # Ensure resources and docs folders are available next to executable
    ensure_all_folders_in_main_directory()
    
    # =========================================================================
    # STARTUP UPDATE CHECK - Apply staged updates before starting GUI
    # =========================================================================
    try:
        log_debug("Checking for staged updates at startup")
        update_applier = UpdateApplier()
        
        if update_applier.has_staged_update():
            log_debug("Staged update detected - applying update")
            
            # Get update info for logging
            update_info = update_applier.get_staged_update_info()
            if update_info:
                log_debug(f"Applying staged update to version: {update_info.get('version', 'unknown')}")
            
            # Apply the update
            success = update_applier.apply_staged_update()
            
            if success:
                log_debug("Staged update applied successfully")
                # Optional: Clean up backup after successful update
                # update_applier.cleanup_backup()  # Commented out to keep backup for safety
            else:
                log_debug("Staged update application failed")
        else:
            log_debug("No staged update found")
            
    except Exception as e:
        log_debug(f"Error during startup update check: {e}")
        # Continue with normal startup even if update fails
    
    # =========================================================================
    # NORMAL APPLICATION STARTUP
    # =========================================================================
    root = tk.Tk()
    app_instance = None
    try:
        # Set Tesseract path early if possible (config will override later)
        default_tess_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        if os.path.exists(default_tess_path):
             pytesseract.pytesseract.tesseract_cmd = default_tess_path
        
        app_instance = GameChangingTranslator(root)
        root.mainloop()
    except Exception as e:
         log_msg = f"FATAL ERROR in main_entry_point: {type(e).__name__} - {e}"
         print(log_msg) 
         log_debug(log_msg) # Ensure logger is working or this might fail
         tb_str = traceback.format_exc()
         log_debug("Traceback:\n" + tb_str)
         try:
             messagebox.showerror(
                 "Fatal Application Error",
                 f"An unexpected error occurred:\n{type(e).__name__}: {e}\n\n"
                 f"Check 'translator_debug.log' for details.\nTraceback:\n{tb_str[:1000]}..."
             )
         except Exception as mb_err: print(f"Could not display fatal error messagebox: {mb_err}")
         finally:
             if root and root.winfo_exists(): root.destroy()

if __name__ == "__main__":
    main_entry_point()
