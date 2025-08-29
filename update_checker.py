# update_checker.py
"""
Update Checker Module - GitHub API Integration for Auto-Update System
Handles checking for updates, downloading, and staging update files.
"""

import os
import sys
import json
import time
import shutil
import zipfile
import tempfile
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    requests = None

from logger import log_debug
from constants import APP_VERSION, GITHUB_API_URL, is_newer_version


class UpdateChecker:
    """Handles checking for updates and downloading them from GitHub releases."""
    
    def __init__(self):
        self.current_version = APP_VERSION
        self.github_api_url = GITHUB_API_URL
        self.staging_dir = "update_staging"
        self.timeout_seconds = 10
        
        # Determine base directory (works for both script and compiled)
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
            
        self.staging_path = os.path.join(self.base_dir, self.staging_dir)
        
        log_debug(f"UpdateChecker initialized - Current version: {self.current_version}")
        log_debug(f"Base directory: {self.base_dir}")
        log_debug(f"Staging path: {self.staging_path}")
    
    def check_for_updates(self):
        """
        Check GitHub API for latest release.
        Returns dict with update info or None if no update available.
        """
        if not requests:
            log_debug("Requests library not available for update checking")
            return None
            
        try:
            log_debug(f"Checking for updates at: {self.github_api_url}")
            
            headers = {
                'User-Agent': 'Game-Changing-Translator-UpdateChecker',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            response = requests.get(
                self.github_api_url,
                headers=headers,
                timeout=self.timeout_seconds
            )
            
            if response.status_code == 200:
                release_data = response.json()
                latest_version = release_data.get("tag_name", "")
                
                log_debug(f"Latest version on GitHub: {latest_version}")
                log_debug(f"Current version: {self.current_version}")
                
                if is_newer_version(self.current_version, latest_version):
                    # Find the main executable asset
                    download_url = None
                    asset_name = None
                    
                    for asset in release_data.get('assets', []):
                        if asset['name'].endswith('.exe') and 'GameChangingTranslator' in asset['name']:
                            download_url = asset['browser_download_url']
                            asset_name = asset['name']
                            break
                    
                    if download_url:
                        update_info = {
                            'version': latest_version,
                            'download_url': download_url,
                            'asset_name': asset_name,
                            'release_notes': release_data.get('body', ''),
                            'published_at': release_data.get('published_at', ''),
                            'release_name': release_data.get('name', ''),
                            'size': next((a['size'] for a in release_data.get('assets', []) 
                                        if a['browser_download_url'] == download_url), 0)
                        }
                        
                        log_debug(f"Update available: {latest_version}")
                        log_debug(f"Download URL: {download_url}")
                        return update_info
                    else:
                        log_debug("No suitable executable found in release assets")
                        return None
                else:
                    log_debug("No newer version available")
                    return None
            else:
                log_debug(f"GitHub API returned status {response.status_code}: {response.text}")
                return None
                
        except requests.exceptions.RequestException as e:
            log_debug(f"Network error checking for updates: {e}")
            return None
        except json.JSONDecodeError as e:
            log_debug(f"Error parsing GitHub API response: {e}")
            return None
        except Exception as e:
            log_debug(f"Unexpected error checking for updates: {e}")
            return None
    
    def download_update(self, update_info, progress_callback=None):
        """
        Download update files to staging directory.
        
        Args:
            update_info: Dict with update information from check_for_updates()
            progress_callback: Optional function(current, total, status) for progress updates
        
        Returns:
            bool: True if download successful, False otherwise
        """
        if not requests:
            log_debug("Requests library not available for downloading updates")
            return False
            
        try:
            download_url = update_info['download_url']
            asset_name = update_info['asset_name']
            
            log_debug(f"Starting download of {asset_name} from {download_url}")
            
            # Create staging directory
            if not self._create_staging_directory():
                return False
            
            # Download the file
            response = requests.get(download_url, stream=True, timeout=30)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0
            
            # Save to staging directory
            staged_file_path = os.path.join(self.staging_path, asset_name)
            
            with open(staged_file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        
                        # Call progress callback if provided
                        if progress_callback:
                            progress_callback(downloaded_size, total_size, "Downloading...")
            
            log_debug(f"Download completed: {staged_file_path} ({downloaded_size} bytes)")
            
            # Create update info file
            if self._create_update_info(update_info, staged_file_path):
                log_debug("Update staging completed successfully")
                return True
            else:
                log_debug("Failed to create update info file")
                return False
                
        except requests.exceptions.RequestException as e:
            log_debug(f"Network error downloading update: {e}")
            self._cleanup_staging()
            return False
        except Exception as e:
            log_debug(f"Error downloading update: {e}")
            self._cleanup_staging()
            return False
    
    def _create_staging_directory(self):
        """Create staging directory if it doesn't exist."""
        try:
            if os.path.exists(self.staging_path):
                # Clean existing staging directory
                shutil.rmtree(self.staging_path)
                log_debug(f"Cleaned existing staging directory: {self.staging_path}")
            
            os.makedirs(self.staging_path)
            log_debug(f"Created staging directory: {self.staging_path}")
            return True
            
        except Exception as e:
            log_debug(f"Error creating staging directory: {e}")
            return False
    
    def _create_update_info(self, update_info, staged_file_path):
        """Create update metadata file in staging directory."""
        try:
            update_metadata = {
                'version': update_info['version'],
                'download_url': update_info['download_url'],
                'asset_name': update_info['asset_name'],
                'staged_file': staged_file_path,
                'release_notes': update_info['release_notes'][:500],  # Limit size
                'published_at': update_info['published_at'],
                'download_time': time.time(),
                'current_version_before_update': self.current_version
            }
            
            info_file_path = os.path.join(self.staging_path, 'update_info.json')
            with open(info_file_path, 'w', encoding='utf-8') as f:
                json.dump(update_metadata, f, indent=2, ensure_ascii=False)
            
            log_debug(f"Created update info file: {info_file_path}")
            return True
            
        except Exception as e:
            log_debug(f"Error creating update info file: {e}")
            return False
    
    def _cleanup_staging(self):
        """Clean up staging directory on error."""
        try:
            if os.path.exists(self.staging_path):
                shutil.rmtree(self.staging_path)
                log_debug(f"Cleaned up staging directory: {self.staging_path}")
        except Exception as e:
            log_debug(f"Error cleaning up staging directory: {e}")
    
    def has_staged_update(self):
        """Check if there's a staged update waiting."""
        try:
            info_file_path = os.path.join(self.staging_path, 'update_info.json')
            return os.path.exists(info_file_path) and os.path.exists(self.staging_path)
        except Exception:
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
    
    def format_file_size(self, size_bytes):
        """Format file size for display."""
        try:
            if size_bytes < 1024:
                return f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                return f"{size_bytes / 1024:.1f} KB"
            elif size_bytes < 1024 * 1024 * 1024:
                return f"{size_bytes / (1024 * 1024):.1f} MB"
            else:
                return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
        except Exception:
            return "Unknown size"
    
    def validate_staged_update(self):
        """Validate that staged update files exist and are valid."""
        try:
            if not self.has_staged_update():
                return False
                
            update_info = self.get_staged_update_info()
            if not update_info:
                return False
                
            staged_file = update_info.get('staged_file')
            if not staged_file or not os.path.exists(staged_file):
                log_debug(f"Staged file not found: {staged_file}")
                return False
                
            # Check if file is not empty
            if os.path.getsize(staged_file) == 0:
                log_debug("Staged file is empty")
                return False
                
            log_debug("Staged update validation passed")
            return True
            
        except Exception as e:
            log_debug(f"Error validating staged update: {e}")
            return False
