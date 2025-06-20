import os
import sys

def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # When running in a PyInstaller executable, prioritize the executable directory
        # over the _MEIPASS directory to allow for user-modified files
        
        # First check in the executable's directory - this allows users to update files
        # without rebuilding the application
        exe_dir = os.path.dirname(sys.executable)
        exe_path = os.path.join(exe_dir, relative_path)
        if os.path.exists(exe_path):
            return exe_path
            
        # If not found next to the executable, use the bundled version in _MEIPASS
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
        direct_path = os.path.join(base_path, relative_path)
        if os.path.exists(direct_path):
            return direct_path
            
        # If still not found, default to _MEIPASS path anyway (consistent with original behavior)
        return direct_path
    except Exception:
        # In development mode, look relative to the script directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(script_dir, relative_path)
