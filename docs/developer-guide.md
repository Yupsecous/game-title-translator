# Developer Guide

This guide provides information for developers who want to understand or modify the OCR Translator application.

> **IMPORTANT NOTE**: This project is considered complete. I won't be accepting pull requests, feature enhancements, or implementing new features that someone else has coded. You are welcome to fork the repository and develop it further as your own project. The code is shared under the GPL licence for others to use, update, and modify as they wish, but I consider my work on it complete and won't be actively engaged in future development.

## Architecture Overview

OCR Translator follows a modular design with the following key components:

### Core Components

1. **Main Application (`app_logic.py`)**
   - Central coordinator that initializes and manages all other components
   - Holds main application state and references to UI elements
   - Delegates specialized tasks to handler classes

2. **Handler Classes (in `handlers/` directory)**
   - `CacheManager` - Manages translation file caching and persistence (Level 2)
   - `ConfigurationHandler` - Manages loading and saving of application settings
   - `DisplayManager` - Handles UI updates for overlays and debug information
   - `HotkeyHandler` - Manages keyboard shortcuts
   - `TranslationHandler` - Coordinates translation with different providers and unified cache
   - `UIInteractionHandler` - Manages UI interactions and settings

3. **Worker Threads (`worker_threads.py`)**
   - `run_capture_thread` - Captures screenshots from selected screen areas
   - `run_ocr_thread` - Performs OCR on captured images
   - `run_translation_thread` - Translates OCR text and updates display

4. **UI Components**
   - `gui_builder.py` - Creates the application's tabbed interface
   - `ui_elements.py` - Custom UI components including the overlay windows
   - `overlay_manager.py` - Manages the creation and positioning of overlay windows
   - `language_ui.py` - Manages UI localization for multiple languages

5. **Specialized Modules**
   - `marian_mt_translator.py` - Neural machine translation implementation
   - `unified_translation_cache.py` - Unified LRU cache system for all translation providers
   - `ocr_utils.py` - OCR utility functions with adaptive preprocessing
   - `translation_utils.py` - Translation utility functions
   - `language_manager.py` - Language code management and mappings for different translation services
   - `config_manager.py` - Configuration file handling with OCR Preview geometry support
   - `resource_handler.py` - Resource path resolution for packaged applications
   - `resource_copier.py` - Resource management for compiled executables
   - `logger.py` - Logging functionality
   - `constants.py` - Application constants and language definitions

### Data Flow

The application uses a pipeline architecture for processing:

1. **Capture** → **OCR** → **Translation** → **Display**

Data flows between stages through thread-safe queues:
- `ocr_queue` - Screenshots from capture thread to OCR thread
- `translation_queue` - OCR text from OCR thread to translation thread

This design allows each stage to operate at its own pace without blocking other stages.

## Code Structure

```
ocr-translator/
├── __init__.py                    # Package initialization
├── main.py                        # Application entry point
├── app_logic.py                   # Main application logic
├── bundled_app.py                 # All-in-one bundler for PyInstaller
├── resource_copier.py             # Resource management for compiled executables
├── config_manager.py              # Configuration handling
├── constants.py                   # Constant definitions
├── gui_builder.py                 # GUI building functions
├── handlers/                      # Specialized handler classes
│   ├── __init__.py                # Package initialization
│   ├── cache_manager.py           # Translation cache management
│   ├── configuration_handler.py   # Settings and configuration
│   ├── display_manager.py         # Display and UI updates
│   ├── hotkey_handler.py          # Keyboard shortcuts
│   ├── translation_handler.py     # Translation coordination
│   └── ui_interaction_handler.py  # UI event handling
├── language_manager.py            # Language code management and mapping
├── language_ui.py                 # UI localization support
├── logger.py                      # Logging functionality
├── marian_mt_translator.py        # Neural translation implementation
├── ocr_utils.py                   # OCR utility functions
├── overlay_manager.py             # Overlay window management
├── resource_handler.py            # Resource path resolution
├── translation_utils.py           # Translation utilities
├── ui_elements.py                 # Custom UI components
├── unified_translation_cache.py   # Unified LRU cache for all translation providers
└── worker_threads.py              # Worker thread implementations
```

### Configuration and Resource Files

```
ocr-translator/
├── ocr_translator_config.ini      # Application configuration file
└── resources/                     # Resource files directory
    ├── lang_codes.csv             # Generic language name to ISO code mappings
    ├── google_trans_source.csv    # Source language codes for Google Translate API
    ├── google_trans_target.csv    # Target language codes for Google Translate API
    ├── deepl_trans_source.csv     # Source language codes for DeepL API
    ├── deepl_trans_target.csv     # Target language codes for DeepL API
    ├── MarianMT_select_models.csv # Available MarianMT translation models
    ├── MarianMT_models_short_list.csv # Preferred/recommended MarianMT models
    ├── language_display_names.csv # Localized language display names
    ├── gui_eng.csv                # English UI translations
    └── gui_pol.csv                # Polish UI translations
```

### Cache and Data Files

```
ocr-translator/
├── deepl_cache.txt                # Cached translations from DeepL API
├── googletrans_cache.txt          # Cached translations from Google Translate API
├── marian_models_cache/           # Directory for cached MarianMT models
└── translator_debug.log           # Application debug log file
```

### Debug Resources

```
ocr-translator/
└── debug_images/                  # Directory for saving debug images
```

## Key Features and Implementation Details

### Unified Translation Cache Architecture

The application features a sophisticated two-tier caching system that was redesigned to eliminate memory waste and fix cache clearing bugs:

#### Level 1: Unified In-Memory Cache (`unified_translation_cache.py`)
- **Single LRU cache** for all translation providers (Google, DeepL, MarianMT)
- **Thread-safe design** with proper RLock() mechanisms for concurrent access
- **Smart cache key generation** using MD5 hashes and provider-specific parameters
- **Configurable cache size** (default: 1000 entries) with automatic LRU eviction
- **Provider-specific clearing** allows selective cache management

**Key Benefits:**
- ✅ **40-60% memory reduction** from eliminating duplicate cache storage
- ✅ **Fixed cache clearing bugs** - unified system actually clears all cache levels
- ✅ **Consistent behavior** across all translation providers
- ✅ **Better performance** with reduced cache management overhead

#### Level 2: Persistent File Cache (Existing)
- **`deepl_cache.txt`** - DeepL API translations persisted to disk
- **`googletrans_cache.txt`** - Google Translate API translations persisted to disk  
- **MarianMT has no file cache** (offline model, no API costs to optimize)
- **Preserved compatibility** - existing user cache files remain intact

#### Cache Flow:
```
Translation Request
    ↓
🚀 Level 1: Check Unified In-Memory Cache (fast)
    ↓ (cache miss)
💾 Level 2: Check File Cache (for Google/DeepL only)
    ↓ (cache miss)
🌐 Level 3: Call Translation API/Model
    ↓
📝 Store in BOTH Level 1 (unified) AND Level 2 (file cache)
```

#### Previous Problems Solved:
- **Double caching bug**: MarianMT previously had two overlapping LRU caches storing identical data
- **Incomplete cache clearing**: Cache clearing didn't clear all cache levels, leaving stale data
- **Memory waste**: Multiple caches storing the same translations
- **Thread safety issues**: Inconsistent locking mechanisms across different cache implementations

### Multi-Language UI Support

The application supports multiple UI languages through:
- `language_ui.py` - UILanguageManager class that loads translations
- CSV files in `resources/` directory containing UI text translations
- Dynamic UI rebuilding when language changes

### Modular Handler Architecture

The handler classes in the `handlers/` directory provide separation of concerns:
- Each handler manages a specific aspect of the application
- Handlers are initialized with a reference to the main app instance
- This design makes it easier to maintain and extend functionality

### Resource Management

The application handles resources differently for development and compiled versions:
- `resource_handler.py` - Provides cross-platform resource path resolution
- `resource_copier.py` - Ensures resources are available next to compiled executables
- Resources are organized in the `resources/` directory for better structure

## Adding New Features

### Adding a New Translation Provider

1. Update `translation_handler.py` to add your new translation method:
   - Add a new method in `TranslationHandler` for your provider
   - Update the `translate_text` method to include your provider
   - Consider adding caching for your provider

2. Update UI elements in `gui_builder.py`:
   - Add UI elements for your provider's settings
   - Handle visibility toggling in `update_translation_model_ui`

3. Add the provider to the available options:
   - Update `translation_model_names` in `app_logic.py`
   - Add any necessary API flag detection in `__init__`

### Adding New OCR Preprocessing Modes

1. Update `ocr_utils.py`:
   - Add your preprocessing mode to the `preprocess_for_ocr` function
   - Consider adding specialized OCR parameters for your mode

2. Add the mode to the UI in `gui_builder.py`:
   - Add your mode to the preprocessing mode dropdown values

### Supporting New Languages

1. Ensure Tesseract supports the language:
   - Update language mapping in the `tesseract_to_iso` dictionary in `language_manager.py`
   - Add language codes to `constants.py` if necessary

2. For API-based translation services:
   - Update the appropriate language CSV files in `resources/` directory
   - Add the language name and code to mappings in `language_manager.py` if needed

3. For MarianMT, add models to the MarianMT models CSV file:
   - Add appropriate Helsinki-NLP model paths and display names
   - Ensure language code mapping is present in `translation_handler.py`

### Adding New UI Languages

1. Create a new CSV file in the `resources/` directory:
   - Name it `gui_XXX.csv` where XXX is the language code
   - Copy an existing file (e.g., `gui_eng.csv`) as a template
   - Translate all the UI text entries

2. Update `language_ui.py`:
   - Add the new language to the available languages list
   - Ensure the language code mapping is correct

## Packaging

The application can be packaged as a standalone executable:

### Using PyInstaller

1. Install PyInstaller:
   ```
   pip install pyinstaller
   ```

2. Use the provided spec file:
   ```
   pyinstaller OCRTranslator.spec
   ```

3. The executable will be in the `dist/OCRTranslator` directory

### Using cx_Freeze

1. Install cx_Freeze:
   ```
   pip install cx_freeze
   ```

2. Use the provided setup.py file:
   ```
   python setup.py build
   ```

## Testing

The application includes several test files for manual testing and verification:

### Available Test Files
- `test_*.py` - Various component-specific test files
- `test_unified_cache.py` - Test script for unified translation cache functionality
- `comprehensive_test.py` - Comprehensive testing script
- `simple_verification.py` - Simple verification script
- `verification_test.py` - Verification testing script

### Testing the Unified Cache

Run the unified cache test to verify the new caching system:

```bash
python test_unified_cache.py
```

This test verifies:
- Basic cache operations (store/retrieve)
- LRU eviction functionality when cache is full
- Provider-specific cache clearing
- Full cache clearing
- Cache statistics and utilization

### Manual Testing Areas

When adding new functionality, be sure to:

1. Test manually with different scenarios:
   - Different language pairs
   - Various text complexities
   - Different screen configurations
   - Edge cases (empty text, very long text, special characters)

2. Check the debug log for errors or warnings

3. Test performance impact of new features

## Thread Safety Considerations

The application uses multiple threads for capture, OCR, and translation with improved thread safety:

1. **Queue-based communication**: Thread-safe queues are used for passing data between threads
2. **UI updates**: All UI updates must be scheduled on the main thread using `root.after()`
3. **Shared state**: Access to shared state variables should be minimized and protected
4. **Unified cache thread safety**: The unified translation cache uses `threading.RLock()` for safe concurrent access across all translation providers
5. **Cache clearing**: No longer requires pausing translation threads - the unified cache can be safely cleared while translation is running

## Performance Optimization Tips

1. **Adaptive timing**: The threads use adaptive intervals based on queue fullness
2. **Image hashing**: Duplicate frames are detected and skipped using MD5 hashing
3. **Unified translation cache**: Single efficient cache reduces memory usage by 40-60% and eliminates cache management overhead
4. **Text similarity**: Similar text is cached to avoid redundant translations
5. **Preprocessing modes**: Different modes optimize for different text types
6. **OCR Preview**: Updates run on separate timer to avoid impacting main translation performance

## Recent Enhancements

The application has been enhanced with several recent features:

### Unified Translation Cache System (Latest)
- **Single LRU cache** replacing multiple overlapping cache layers
- **Thread-safe design** with proper locking mechanisms  
- **Fixed cache clearing bugs** that previously left stale data
- **40-60% memory reduction** from eliminating duplicate storage
- **Preserved file cache compatibility** for existing user data
- **Improved cache clearing** no longer requires pausing translation threads

### OCR Preview Window
- Real-time preview of OCR processing
- 1:1 scale image display with horizontal scrolling
- Configurable adaptive thresholding parameters
- Continuous updates independent of translation state
- Persistent window geometry

### Enhanced OCR Processing
- Adaptive thresholding with configurable parameters
- Trailing garbage removal option
- Multiple preprocessing modes for different text types
- Improved processing pipeline with better error handling

### Improved Localization
- Comprehensive language display names in CSV files
- Support for provider-specific language mappings
- Proper Polish alphabetical sorting
- Bilingual UI with complete translations

### Resource Organization
- All configuration files organized in `resources/` directory
- Automatic resource copying for compiled executables
- Better separation of user-modifiable files
- Improved path resolution for different deployment scenarios

## Contributing

This project is considered complete and is not accepting contributions. If you want to extend or modify the application:

1. Create a fork of the repository
2. Develop your own version as a separate project
3. Respect the GPL licence terms for any derived works

Please do not submit pull requests or feature requests as they will not be reviewed or accepted. The project is shared as-is for educational purposes and for others to build upon as they see fit.

## Code Style

The project follows these general conventions:

- Function and variable names use `snake_case`
- Classes use `CamelCase`
- Constants use `UPPER_CASE`
- Comments should explain "why" not just "what"
- Use descriptive variable names
- Break complex operations into smaller, well-named functions
- Add log statements for important operations or potential failure points

## Dependencies and Imports

The application has several categories of dependencies:

### Required Dependencies
- `tkinter` - GUI framework (included with Python)
- `numpy` - Numerical computing
- `opencv-python` - Computer vision operations
- `pytesseract` - Tesseract OCR wrapper
- `Pillow` - Image processing
- `pyautogui` - Screen capture

### Optional Dependencies
- `keyboard` - Global hotkey support (enables keyboard shortcuts)
- `google-cloud-translate` - Google Translate API
- `deepl` - DeepL API
- `torch` + `transformers` - MarianMT neural translation

The application gracefully handles missing optional dependencies and provides appropriate fallback behavior.
