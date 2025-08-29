# update_applier_simple.py
"""
Simple Update Applier - Simplified Version
Handles applying staged updates with a much simpler approach.
"""

import os
import sys
import json
import subprocess
from pathlib import Path

from logger import log_debug


class UpdateApplier:
    """Simple, direct update applier that creates a minimal batch file."""
    
    def __init__(self):
        self.staging_dir = "update_staging"
        
        # Determine base directory
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            self.base_dir = os.path.dirname(sys.executable)
            self.current_executable = sys.executable
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
            self.current_executable = os.path.abspath(__file__)
            
        self.staging_path = os.path.join(self.base_dir, self.staging_dir)
        
        log_debug(f"UpdateApplier initialized - Base directory: {self.base_dir}")
    
    def has_staged_update(self):
        """Check if there's a staged update waiting to be applied."""
        try:
            info_file_path = os.path.join(self.staging_path, 'update_info.json')
            if not (os.path.exists(self.staging_path) and os.path.exists(info_file_path)):
                return False
                
            # Read and validate update info
            with open(info_file_path, 'r', encoding='utf-8') as f:
                update_info = json.load(f)
            
            # Check if staged file exists and is valid
            staged_file = update_info.get('staged_file')
            if not staged_file or not os.path.exists(staged_file):
                return False
                
            # Check if it's a reasonable size (at least 10MB)
            file_size = os.path.getsize(staged_file)
            if file_size < 10 * 1024 * 1024:
                return False
                
            # Check if it's an .exe file
            if not staged_file.endswith('.exe'):
                return False
                
            return True
            
        except Exception as e:
            log_debug(f"Error checking for staged update: {e}")
            return False
    
    def apply_staged_update(self):
        """Apply the staged update by creating simple batch file and exiting."""
        try:
            log_debug("Starting simple update application")
            
            # Read update information
            info_file_path = os.path.join(self.staging_path, 'update_info.json')
            with open(info_file_path, 'r', encoding='utf-8') as f:
                update_info = json.load(f)
            
            staged_file = update_info.get('staged_file')
            if not staged_file or not os.path.exists(staged_file):
                log_debug(f"Staged file not found: {staged_file}")
                return False
            
            log_debug(f"Applying update to version: {update_info.get('version', 'unknown')}")
            
            # Create simple batch file
            batch_file = self._create_simple_batch_file(staged_file)
            if not batch_file:
                log_debug("Failed to create simple batch file")
                return False
            
            # Launch batch file and schedule application exit
            if not self._launch_batch_and_exit(batch_file):
                log_debug("Failed to launch batch file")
                return False
            
            log_debug("Simple update process initiated - application will restart")
            return True
            
        except Exception as e:
            log_debug(f"Error applying staged update: {e}")
            return False
    
    def _create_simple_batch_file(self, installer_path):
        """Create a simple, direct batch file for the update."""
        try:
            current_pid = os.getpid()
            
            # Normalize all paths
            base_dir = os.path.normpath(self.base_dir)
            main_exe = os.path.normpath(os.path.join(base_dir, 'GameChangingTranslator.exe'))
            internal_dir = os.path.normpath(os.path.join(base_dir, '_internal'))
            installer = os.path.normpath(installer_path)
            staging_dir = os.path.normpath(self.staging_path)
            
            batch_content = f'''@echo off
REM Simple Game-Changing Translator Update Script

REM Wait for application to close (max 10 seconds)
set /a counter=0
:wait_loop
tasklist /FI "PID eq {current_pid}" 2>NUL | find /I "{current_pid}" >NUL
if errorlevel 1 goto start_update
timeout /t 1 /nobreak >NUL 2>&1
set /a counter+=1
if %counter% geq 10 goto start_update
goto wait_loop

:start_update
REM Preserve user files (.log, .ini, .txt in main folder)
if not exist "temp_preserve" mkdir "temp_preserve"
for %%f in ("{base_dir}\\*.log" "{base_dir}\\*.ini" "{base_dir}\\*.txt") do (
    if exist "%%f" copy "%%f" "temp_preserve\\" >NUL 2>&1
)

REM Delete old application folders and main executable
if exist "{main_exe}" del "{main_exe}" >NUL 2>&1
if exist "{internal_dir}" rmdir /s /q "{internal_dir}" >NUL 2>&1
if exist "{base_dir}\\resources" rmdir /s /q "{base_dir}\\resources" >NUL 2>&1
if exist "{base_dir}\\docs" rmdir /s /q "{base_dir}\\docs" >NUL 2>&1

REM Extract new application files from installer
"{installer}" -o"{base_dir}" -y -bd >NUL 2>&1

REM If extraction created nested directory, move files up
if exist "{base_dir}\\GameChangingTranslator\\GameChangingTranslator.exe" (
    xcopy "{base_dir}\\GameChangingTranslator\\*" "{base_dir}\\" /E /I /H /Y >NUL 2>&1
    rmdir /s /q "{base_dir}\\GameChangingTranslator" >NUL 2>&1
)

REM Restore user files
if exist "temp_preserve" (
    for %%f in ("temp_preserve\\*.*") do copy "%%f" "{base_dir}\\" >NUL 2>&1
    rmdir /s /q "temp_preserve" >NUL 2>&1
)

REM Clean up temporary files and folders
if exist "{staging_dir}" rmdir /s /q "{staging_dir}" >NUL 2>&1
if exist "{installer}" del "{installer}" >NUL 2>&1

REM Launch updated application
if exist "{main_exe}" (
    start "" "{main_exe}"
    timeout /t 2 >NUL 2>&1
    (goto) 2>nul & del "%~f0"
) else (
    echo Update failed - executable not found
    pause
    (goto) 2>nul & del "%~f0"
)
'''
            
            # Write batch file
            batch_file_path = os.path.join(self.base_dir, 'simple_update.bat')
            with open(batch_file_path, 'w', encoding='utf-8') as f:
                f.write(batch_content)
            
            log_debug(f"Created simple batch file: {batch_file_path}")
            return batch_file_path
            
        except Exception as e:
            log_debug(f"Error creating simple batch file: {e}")
            return None
    
    def _launch_batch_and_exit(self, batch_file_path):
        """Launch the batch file and prepare for application exit."""
        try:
            log_debug(f"Launching simple batch file: {batch_file_path}")
            
            # Launch batch file hidden
            subprocess.Popen([
                'cmd.exe', '/C', batch_file_path
            ], 
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            cwd=self.base_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL
            )
            
            log_debug("Simple batch file launched successfully")
            return True
            
        except Exception as e:
            log_debug(f"Error launching simple batch file: {e}")
            return False
    
    def get_staged_update_info(self):
        """Get information about staged update."""
        try:
            info_file_path = os.path.join(self.staging_path, 'update_info.json')
            if os.path.exists(info_file_path):
                with open(info_file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return None
        except Exception as e:
            log_debug(f"Error reading staged update info: {e}")
            return None
