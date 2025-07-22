# Developer Guide

This guide provides information for developers who want to understand or modify the Game-Changing Translator application.

> **IMPORTANT NOTE**: This project is considered complete. I won't be accepting pull requests, feature enhancements, or implementing new features that someone else has coded. You are welcome to fork the repository and develop it further as your own project. The code is shared under the GPL licence for others to use, update, and modify as they wish, but I consider my work on it complete and won't be actively engaged in future development.

## Architecture Overview

Game-Changing Translator follows a modular design with the following key components:

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
    ├── gemini_trans_source.csv    # Source language codes for Gemini API
    ├── gemini_trans_target.csv    # Target language codes for Gemini API
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
├── gemini_cache.txt               # Cached translations from Gemini API
├── Gemini_API_call_logs.txt       # Detailed Gemini API call logging with cost tracking
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

### Gemini API Integration and Logging

The application features sophisticated Gemini API integration with comprehensive logging and cost tracking capabilities designed for the Gemini 2.5 Flash-Lite model.

#### Gemini API Call Logging System (`Gemini_API_call_logs.txt`)

When enabled in settings, the application generates detailed logs of all Gemini API interactions for cost monitoring, debugging, and usage analysis.

**Log Structure and Content:**
Each API call creates a comprehensive log entry containing:

1. **Call Metadata:**
   - Precise timestamp and language pair
   - Message character/word/line counts
   - API call duration for performance analysis

2. **Complete Context Window:**
   - Full message content sent to Gemini API
   - Shows context-aware translation implementation
   - Demonstrates how previous subtitles are included for narrative coherence

3. **Token and Cost Analysis:**
   - Exact input/output token counts from Gemini API
   - Per-call cost breakdown using Gemini 2.5 Flash-Lite pricing
   - Cumulative cost tracking across sessions
   - Cost-per-word analysis for budget planning

**Example Log Entry Format:**
```
=== GEMINI API CALL LOG ===
Timestamp: 2025-07-03 01:10:10
Language Pair: en -> pl
Original Text: [source text]

CALL DETAILS:
- Message Length: 117 characters
- Word Count: 17 words
- Line Count: 4 lines

COMPLETE MESSAGE CONTENT SENT TO GEMINI:
---BEGIN MESSAGE---
<Translate idiomatically from English to Polish. Return translation only.>

ENGLISH: [source text]
POLISH:
---END MESSAGE---

RESPONSE RECEIVED:
[translation result]

TOKEN & COST ANALYSIS (CURRENT CALL):
- Translated Words: 6
- Exact Input Tokens: 28
- Exact Output Tokens: 11
- Input Cost: $0.00000280
- Output Cost: $0.00000440
- Total Cost for this Call: $0.00000720

CUMULATIVE TOTALS:
- Total Translated Words (so far): 6
- Total Input Tokens (so far): 28
- Total Output Tokens (so far): 11
- Cumulative Log Cost: $0.00000720
```

**Context Window Implementation:**
The logs demonstrate the sophisticated context-aware translation system:
```
ENGLISH: [Previous subtitle 1]
ENGLISH: [Previous subtitle 2]
ENGLISH: [Current subtitle to translate]

POLISH: [Previous translation 1]
POLISH: [Previous translation 2]
POLISH: [Space for current translation]
```

This context window (configurable 0-2 previous subtitles) enables narrative coherence and improved grammar flow.

#### Gemini Translation Cache (`gemini_cache.txt`)

**Cache Format:**
```
Gemini(LANG_PAIR,timestamp):original_text:==:translated_text
```

**Format Components:**
- **Provider**: "Gemini" identifier
- **Language Pair**: Source-target codes (e.g., "CS-PL", "FR-EN")  
- **Timestamp**: Cache entry creation time
- **Delimiter**: ":==:" separates original from translated text

**Integration with Unified Cache:**
- Level 2 persistent storage in two-tier caching system
- Works alongside unified in-memory cache (Level 1)
- Reduces API costs through intelligent caching
- Cache effectiveness depends on OCR consistency

### Multi-Language UI Support

The application supports multiple UI languages through:
- `language_ui.py` - UILanguageManager class that loads translations
- CSV files in `resources/` directory containing UI text translations
- Dynamic UI rebuilding when language changes

### Working with Gemini API Files

**Monitoring API Usage:**
Developers can analyze the `Gemini_API_call_logs.txt` file to:
- Track exact API costs with token-level precision
- Monitor context window effectiveness
- Debug translation quality issues
- Analyze performance patterns (call duration, token efficiency)

**Cache Management:**
The `gemini_cache.txt` file enables:
- API cost reduction through intelligent caching
- Long-term storage of translation pairs
- Integration with unified in-memory cache system
- Manual cache analysis for optimization

**Cost Optimization Strategies:**
- Monitor cumulative costs through log analysis
- Analyze cache hit rates for different content types
- Optimize OCR settings to improve cache consistency
- Configure context window size based on cost/quality trade-offs

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
   pyinstaller GameChangingTranslator.spec
   ```

3. The executable will be in the `dist/GameChangingTranslator` directory

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

### Testing Gemini API Integration

When testing Gemini API functionality, verify:

1. **API Call Logging:**
   - Enable API logging in settings
   - Perform test translations
   - Verify `Gemini_API_call_logs.txt` contains complete log entries
   - Check token counts and cost calculations for accuracy

2. **Cache Functionality:**
   - Test cache file creation and format in `gemini_cache.txt`
   - Verify cache hits for identical OCR text
   - Test cache persistence across application restarts

3. **Context Window:**
   - Test different context window settings (0, 1, 2 previous subtitles)
   - Verify context is included in API call logs
   - Check translation quality with and without context

4. **Cost Tracking:**
   - Monitor cumulative cost tracking accuracy
   - Verify per-call cost calculations match expected Gemini pricing
   - Test cost reset functionality when logs are cleared

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

### Gemini API Integration (Latest)
- **Context-aware translation** with configurable sliding window for narrative coherence
- **Comprehensive API call logging** with detailed cost tracking and token analysis
- **OCR error intelligence** that automatically corrects recognition imperfections
- **Cost-effective translation** using Gemini 2.5 Flash-Lite pricing model
- **Advanced caching integration** with both in-memory and persistent file storage

### Unified Translation Cache System
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
