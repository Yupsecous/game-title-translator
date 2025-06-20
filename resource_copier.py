import os
import shutil
import sys
from logger import log_debug

def ensure_folder_in_main_directory(folder_name):
    """
    Ensures a specific folder exists next to the executable.
    If not found, copies it from _internal folder.
    
    Args:
        folder_name (str): Name of the folder to ensure exists
    """
    if not (getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')):
        # Not running as compiled executable, skip
        return
    
    exe_dir = os.path.dirname(sys.executable)
    main_folder = os.path.join(exe_dir, folder_name)
    
    # If folder already exists next to executable, we're good
    if os.path.exists(main_folder) and os.path.isdir(main_folder):
        log_debug(f"{folder_name} folder found next to executable")
        return
    
    # Try to copy from _internal
    internal_folder = os.path.join(sys._MEIPASS, folder_name)
    
    if os.path.exists(internal_folder):
        try:
            log_debug(f"Copying {folder_name} from {internal_folder} to {main_folder}")
            shutil.copytree(internal_folder, main_folder)
            log_debug(f"{folder_name} folder successfully copied to main directory")
        except Exception as e:
            log_debug(f"Failed to copy {folder_name} folder: {e}")
    else:
        log_debug(f"Warning: Internal {folder_name} folder not found at {internal_folder}")

def ensure_resources_in_main_directory():
    """
    Ensures resources folder exists next to the executable.
    If not found, copies it from _internal folder.
    """
    ensure_folder_in_main_directory("resources")

def ensure_docs_in_main_directory():
    """
    Ensures docs folder exists next to the executable.
    If not found, copies it from _internal folder.
    """
    ensure_folder_in_main_directory("docs")

def ensure_all_folders_in_main_directory():
    """
    Ensures all required folders exist next to the executable.
    This function should be called on application startup for compiled versions.
    """
    ensure_resources_in_main_directory()
    ensure_docs_in_main_directory()
