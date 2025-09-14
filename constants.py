# Right-to-Left (RTL) languages that require special text direction handling
RTL_LANGUAGES = {
    'ar',     # Arabic
    'fa',     # Persian/Farsi
    'he',     # Hebrew
    'ur',     # Urdu
    'ku',     # Kurdish
    'sd',     # Sindhi
    'ps',     # Pashto
    'yi'      # Yiddish
}

# Version Management - Centralized version control
APP_VERSION = "v3.6.0"
APP_RELEASE_DATE = "14 September 2025"
APP_RELEASE_DATE_POLISH = "14 września 2025"
GITHUB_API_URL = "https://api.github.com/repos/tomkam1702/OCR-Translator/releases/latest"

def parse_version(version_str):
    """Parse version string like 'v3.5.7' into comparable tuple (3, 5, 7)"""
    try:
        # Remove 'v' prefix if present and split by '.'
        clean_version = version_str.lstrip('v')
        return tuple(map(int, clean_version.split('.')))
    except (ValueError, AttributeError):
        # Fallback for invalid version strings
        return (0, 0, 0)

def is_newer_version(current, latest):
    """Compare two version strings and return True if latest > current"""
    try:
        current_tuple = parse_version(current)
        latest_tuple = parse_version(latest)
        return latest_tuple > current_tuple
    except Exception:
        # If comparison fails, assume no update needed
        return False

def get_current_version():
    """Get the current application version"""
    return APP_VERSION
