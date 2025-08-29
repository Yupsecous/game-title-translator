# update_applier.py
"""
Update Applier Module - Startup Update Detection and Application
Handles detecting staged updates on startup and applying them safely.
"""

import os
import sys
import json
import shutil
import time
import glob
from pathlib import Path

from logger import log_debug


class UpdateApplier:
    """Handles applying staged updates on application startup."""
    
    def __init__(self):
        self.staging_dir = "update_staging"
        self.backup_dir = "update_backup"
        
        # Determine base directory (works for both script and compiled)
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            self.base_dir = os.path.dirname(sys.executable)
            self.current_executable = sys.executable
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
            self.current_executable = os.path.abspath(__file__)
            
        self.staging_path = os.path.join(self.base_dir, self.staging_dir)
        self.backup_path = os.path.join(self.base_dir, self.backup_dir)
        
        # Files to preserve during update (user data)
        self.preserve_patterns = [
            "*.txt",     # Cache files, logs
            "*.ini",     # Configuration files
            "*.log",     # Debug logs
        ]
        
        # Specific files to always preserve
        self.preserve_exact = [
            "ocr_translator_config.ini",
            "deepl_cache.txt", 
            "gemini_cache.txt",
            "googletrans_cache.txt",
            "translator_debug.log",
            "Gemini_API_call_logs.txt",
            "API_OCR_short_log.txt",
            "API_TRA_short_log.txt",
        ]
        
        log_debug(f"UpdateApplier initialized - Base directory: {self.base_dir}")
    
    def has_staged_update(self):
        """Check if there's a staged update waiting to be applied."""
        try:
            info_file_path = os.path.join(self.staging_path, 'update_info.json')
            return (os.path.exists(self.staging_path) and 
                    os.path.exists(info_file_path) and
                    self._validate_staged_files())
        except Exception as e:
            log_debug(f"Error checking for staged update: {e}")
            return False
    
    def _validate_staged_files(self):
        """Validate that staged files exist and are valid."""
        try:
            info_file_path = os.path.join(self.staging_path, 'update_info.json')
            
            # Read update info
            with open(info_file_path, 'r', encoding='utf-8') as f:
                update_info = json.load(f)
            
            # Check if staged file exists
            staged_file = update_info.get('staged_file')
            if not staged_file or not os.path.exists(staged_file):
                log_debug(f"Staged file not found: {staged_file}")
                return False
                
            # Check if file is not empty
            if os.path.getsize(staged_file) == 0:
                log_debug("Staged file is empty")
                return False
                
            return True
            
        except Exception as e:
            log_debug(f"Error validating staged files: {e}")
            return False
    
    def apply_staged_update(self):
        """Apply the staged update and return success status."""
        try:
            log_debug("Starting staged update application")
            
            # Read update information
            info_file_path = os.path.join(self.staging_path, 'update_info.json')
            with open(info_file_path, 'r', encoding='utf-8') as f:
                update_info = json.load(f)
            
            log_debug(f"Applying update to version: {update_info.get('version', 'unknown')}")
            
            # Step 1: Create backup of current version
            if not self._create_backup():
                log_debug("Failed to create backup - aborting update")
                return False
            
            # Step 2: Preserve user files
            preserved_files = self._preserve_user_files()
            log_debug(f"Preserved {len(preserved_files)} user files")
            
            # Step 3: Apply the update
            if not self._replace_application_files(update_info):
                log_debug("Failed to replace application files")
                self._restore_from_backup()
                return False
            
            # Step 4: Restore preserved user files
            self._restore_preserved_files(preserved_files)
            
            # Step 5: Cleanup staging directory
            self._cleanup_staging()
            
            log_debug("Update applied successfully")
            return True
            
        except Exception as e:
            log_debug(f"Error applying staged update: {e}")
            try:
                self._restore_from_backup()
            except Exception as restore_error:
                log_debug(f"Error restoring from backup: {restore_error}")
            return False
    
    def _create_backup(self):
        """Create backup of current application before update."""
        try:
            if os.path.exists(self.backup_path):
                shutil.rmtree(self.backup_path)
            
            os.makedirs(self.backup_path)
            
            # Backup main executable
            if os.path.exists(self.current_executable):
                backup_exe = os.path.join(self.backup_path, os.path.basename(self.current_executable))
                shutil.copy2(self.current_executable, backup_exe)
                log_debug(f"Backed up executable: {self.current_executable}")
            
            # Backup _internal directory (PyInstaller dependencies)
            internal_dir = os.path.join(self.base_dir, '_internal')
            if os.path.exists(internal_dir):
                backup_internal = os.path.join(self.backup_path, '_internal')
                shutil.copytree(internal_dir, backup_internal)
                log_debug(f"Backed up _internal directory: {internal_dir}")
            
            # Backup resources directory
            resources_dir = os.path.join(self.base_dir, 'resources')
            if os.path.exists(resources_dir):
                backup_resources = os.path.join(self.backup_path, 'resources')
                shutil.copytree(resources_dir, backup_resources)
                log_debug(f"Backed up resources directory: {resources_dir}")
            
            # Backup docs directory
            docs_dir = os.path.join(self.base_dir, 'docs')
            if os.path.exists(docs_dir):
                backup_docs = os.path.join(self.backup_path, 'docs')
                shutil.copytree(docs_dir, backup_docs)
                log_debug(f"Backed up docs directory: {docs_dir}")
            
            log_debug("Backup creation completed")
            return True
            
        except Exception as e:
            log_debug(f"Error creating backup: {e}")
            return False
    
    def _preserve_user_files(self):
        """Preserve user files by moving them to temp location."""
        preserved_files = []
        temp_preserve_dir = os.path.join(self.base_dir, 'temp_preserve')
        
        try:
            # Create temporary preservation directory
            if os.path.exists(temp_preserve_dir):
                shutil.rmtree(temp_preserve_dir)
            os.makedirs(temp_preserve_dir)
            
            # Get all files to preserve
            files_to_preserve = self._get_files_to_preserve()
            
            for file_path in files_to_preserve:
                if os.path.exists(file_path):
                    try:
                        filename = os.path.basename(file_path)
                        temp_path = os.path.join(temp_preserve_dir, filename)
                        shutil.copy2(file_path, temp_path)
                        preserved_files.append((file_path, temp_path))
                        log_debug(f"Preserved file: {file_path}")
                    except Exception as e:
                        log_debug(f"Error preserving file {file_path}: {e}")
            
            return preserved_files
            
        except Exception as e:
            log_debug(f"Error preserving user files: {e}")
            return preserved_files
    
    def _get_files_to_preserve(self):
        """Get list of files that should be preserved during update."""
        files_to_preserve = []
        
        # Add exact files
        for filename in self.preserve_exact:
            file_path = os.path.join(self.base_dir, filename)
            if os.path.exists(file_path):
                files_to_preserve.append(file_path)
        
        # Add pattern-based files
        for pattern in self.preserve_patterns:
            pattern_path = os.path.join(self.base_dir, pattern)
            matching_files = glob.glob(pattern_path)
            files_to_preserve.extend(matching_files)
        
        # Remove duplicates
        files_to_preserve = list(set(files_to_preserve))
        
        log_debug(f"Found {len(files_to_preserve)} files to preserve")
        return files_to_preserve
    
    def _replace_application_files(self, update_info):
        """Replace application files with staged versions."""
        try:
            staged_file = update_info.get('staged_file')
            if not staged_file or not os.path.exists(staged_file):
                log_debug(f"Staged file not found: {staged_file}")
                return False
            
            # For now, we'll handle .exe files directly
            # In the future, this could be extended to handle .zip files
            
            if staged_file.endswith('.exe'):
                # Replace the main executable
                target_exe = os.path.join(self.base_dir, 'GameChangingTranslator.exe')
                
                # Remove old executable if it exists
                if os.path.exists(target_exe):
                    try:
                        os.remove(target_exe)
                    except PermissionError:
                        log_debug("Cannot remove running executable - this is normal")
                        # Create new name for the update
                        target_exe = os.path.join(self.base_dir, 'GameChangingTranslator_new.exe')
                
                # Copy new executable
                shutil.copy2(staged_file, target_exe)
                log_debug(f"Replaced executable: {target_exe}")
                
                # Note: For a complete update system, you might also need to:
                # - Extract and replace _internal/ directory from installer
                # - Update resources/ directory
                # This simplified version focuses on executable replacement
                
                return True
            else:
                log_debug(f"Unsupported staged file type: {staged_file}")
                return False
                
        except Exception as e:
            log_debug(f"Error replacing application files: {e}")
            return False
    
    def _restore_preserved_files(self, preserved_files):
        """Restore preserved user files after update."""
        try:
            for original_path, temp_path in preserved_files:
                try:
                    if os.path.exists(temp_path):
                        # Ensure directory exists
                        os.makedirs(os.path.dirname(original_path), exist_ok=True)
                        shutil.copy2(temp_path, original_path)
                        log_debug(f"Restored file: {original_path}")
                except Exception as e:
                    log_debug(f"Error restoring file {original_path}: {e}")
            
            # Cleanup temporary preservation directory
            temp_preserve_dir = os.path.join(self.base_dir, 'temp_preserve')
            if os.path.exists(temp_preserve_dir):
                shutil.rmtree(temp_preserve_dir)
                
        except Exception as e:
            log_debug(f"Error restoring preserved files: {e}")
    
    def _restore_from_backup(self):
        """Restore application from backup if update fails."""
        try:
            if not os.path.exists(self.backup_path):
                log_debug("No backup available for restoration")
                return False
            
            log_debug("Restoring application from backup")
            
            # Restore executable
            backup_files = os.listdir(self.backup_path)
            for filename in backup_files:
                if filename.endswith('.exe'):
                    backup_exe = os.path.join(self.backup_path, filename)
                    target_exe = os.path.join(self.base_dir, filename)
                    shutil.copy2(backup_exe, target_exe)
                    log_debug(f"Restored executable: {target_exe}")
            
            # Restore directories
            for dirname in ['_internal', 'resources', 'docs']:
                backup_dir = os.path.join(self.backup_path, dirname)
                target_dir = os.path.join(self.base_dir, dirname)
                
                if os.path.exists(backup_dir):
                    if os.path.exists(target_dir):
                        shutil.rmtree(target_dir)
                    shutil.copytree(backup_dir, target_dir)
                    log_debug(f"Restored directory: {target_dir}")
            
            log_debug("Backup restoration completed")
            return True
            
        except Exception as e:
            log_debug(f"Error restoring from backup: {e}")
            return False
    
    def _cleanup_staging(self):
        """Clean up staging directory after successful update."""
        try:
            if os.path.exists(self.staging_path):
                shutil.rmtree(self.staging_path)
                log_debug("Staging directory cleaned up")
        except Exception as e:
            log_debug(f"Error cleaning up staging directory: {e}")
    
    def cleanup_backup(self):
        """Clean up backup directory (call after successful update verification)."""
        try:
            if os.path.exists(self.backup_path):
                shutil.rmtree(self.backup_path)
                log_debug("Backup directory cleaned up")
        except Exception as e:
            log_debug(f"Error cleaning up backup directory: {e}")
    
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
